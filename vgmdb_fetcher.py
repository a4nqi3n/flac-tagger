import re
import email
from email import policy
import requests
from bs4 import BeautifulSoup, Tag


def fetch_url(url: str, cookies: str = '') -> str | None:
    cookie_dict = {}
    if cookies:
        for item in cookies.split(';'):
            item = item.strip()
            if '=' in item:
                k, v = item.split('=', 1)
                cookie_dict[k.strip()] = v.strip()

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/131.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9,ja;q=0.8,zh-CN;q=0.7,zh;q=0.6',
        'Referer': 'https://vgmdb.net/',
    }

    try:
        resp = requests.get(url, cookies=cookie_dict, headers=headers, timeout=30)
    except requests.RequestException as e:
        print(f'[VGMdb] 请求失败: {e}')
        return None

    if resp.status_code == 403 or 'Just a moment' in resp.text[:500]:
        print(f'[VGMdb] 被 Cloudflare 拦截 (status={resp.status_code})')
        return None

    if resp.status_code != 200:
        print(f'[VGMdb] HTTP {resp.status_code}')
        return None

    return resp.text


def parse_album_html(html: str) -> dict | None:
    soup = BeautifulSoup(html, 'html.parser')
    innermain = soup.select_one('#innermain')
    if not innermain:
        return None

    title_h1 = innermain.find('h1')
    title = _pick_ja_text(title_h1) if title_h1 else ''
    title_by_lang = _extract_lang_texts(title_h1) if title_h1 else {}

    if not title:
        return None

    meta = {}
    rightfloat = soup.select_one('#rightfloat')
    if rightfloat:
        info_table = rightfloat.find('table')
        if info_table:
            _parse_info_table(info_table, meta)

    artist = (meta.get('Performed by')
              or meta.get('Composed by')
              or meta.get('Arranged by')
              or meta.get('Lyrics by')
              or '')
    artist_by_lang = {}
    if not artist:
        artist, artist_by_lang = _parse_credits(soup)
    year = (meta.get('Release Date', '') or '')[:4]
    disc_id = meta.get('Catalog Number', '') or ''

    if artist and ' / ' in title:
        parts = title.rsplit(' / ', 1)
        if len(parts) == 2 and parts[1].strip() == artist.strip():
            title = parts[0].strip()
    for lang, t in title_by_lang.items():
        if ' / ' not in t:
            continue
        art_name = artist_by_lang.get(lang, artist)
        parts = t.rsplit(' / ', 1)
        if len(parts) == 2 and parts[1].strip() == art_name.strip():
            title_by_lang[lang] = parts[0].strip()

    tracks, track_languages = _parse_tracklist(soup)
    notes = _parse_notes(soup)

    return {
        'disc_id': disc_id,
        'artist': artist,
        'title': title,
        'year': year,
        'tracks': tracks,
        'track_languages': track_languages,
        'title_by_lang': title_by_lang,
        'artist_by_lang': artist_by_lang,
        'raw_meta': meta,
        'notes': notes,
    }


def parse_search_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, 'html.parser')
    innermain = soup.select_one('#innermain')
    if not innermain:
        return []

    results = []
    album_section = soup.select_one('#albumresults')
    if not album_section:
        return []

    rows = album_section.find_all('tr')[1:] if album_section else []
    for row in rows:
        cells = row.find_all('td', recursive=False)
        if len(cells) < 2:
            continue
        link = cells[0].find('a')
        if not link:
            continue
        album_url = link.get('href', '')
        album_title = link.get_text(strip=True)
        catalog = ''
        cat_span = cells[0].find('span')
        if cat_span:
            catalog = cat_span.get_text(strip=True)

        date_str = ''
        if len(cells) > 3:
            date_str = cells[3].get_text(strip=True)

        results.append({
            'disc_id': catalog or album_url,
            'artist': '',
            'title': album_title,
            'year': date_str[:4] if date_str else '',
            'tracks': [],
            'album_url': album_url,
        })

    return results


_LANG_CODES: dict[str, str] = {
    'en': 'English',
    'ja': 'Japanese',
    'ja-Latn': 'Romaji',
}


def _extract_lang_texts(element: Tag) -> dict[str, str]:
    texts: dict[str, str] = {}
    for span in element.find_all('span'):
        lang = span.get('lang', '')
        if not lang:
            continue
        text = span.get_text(strip=True)
        text = text.lstrip('/ \u3000')
        if text:
            texts[lang] = text
    return texts


def _pick_ja_text(element: Tag) -> str:
    texts = _extract_lang_texts(element)
    if 'ja' in texts:
        return texts['ja']
    for span in element.find_all('span'):
        style = span.get('style', '')
        if 'display:none' not in style.replace(' ', ''):
            text = span.get_text(strip=True)
            if text:
                return text
    return element.get_text(strip=True)


def _parse_info_table(table: Tag, meta: dict):
    rows = table.find_all('tr')
    for row in rows:
        cells = row.find_all('td', recursive=False)
        if len(cells) < 2:
            continue
        label_cell = cells[0]
        value_cell = cells[1]

        label_tag = label_cell.find('b')
        if not label_tag:
            continue
        label = label_tag.get_text(strip=True).rstrip(':')
        if not label:
            continue

        if label in ('Composed by', 'Arranged by',
                      'Performed by', 'Lyrics by'):
            _parse_artist_meta(label, value_cell, meta)
        else:
            _parse_simple_meta(label, value_cell, meta)


def _parse_simple_meta(label: str, cell: Tag, meta: dict):
    links = cell.find_all('a')
    if links:
        if label == 'Release Date':
            href = links[0].get('href', '')
            if '#' in href:
                meta[label] = href.rsplit('#', 1)[-1]
                return
        texts = [a.get_text(strip=True) for a in links if a.get_text(strip=True)]
        if texts:
            meta[label] = ', '.join(texts)
            return
    raw = cell.get_text(' ', strip=True)
    if raw:
        meta[label] = raw


def _parse_artist_meta(label: str, cell: Tag, meta: dict):
    names = []
    for child in cell.children:
        if isinstance(child, Tag) and child.name == 'a':
            name = _pick_ja_text(child)
            if name:
                names.append(name)
        elif isinstance(child, str):
            pass
    if names:
        meta[label] = ', '.join(names)


def _parse_credits(soup: BeautifulSoup) -> tuple[str, dict[str, str]]:
    innermain = soup.select_one('#innermain')
    if not innermain:
        return '', {}

    credits_h3 = None
    for h3 in innermain.find_all('h3'):
        if 'credits' in h3.get_text(strip=True).lower():
            credits_h3 = h3
            break
    if not credits_h3:
        return '', {}

    container = credits_h3.parent
    if container and container.parent:
        container = container.parent
    if not container:
        return '', {}

    rows = container.find_all('tr', class_='maincred')
    if not rows:
        return '', {}

    credits: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        cells = row.find_all('td', recursive=False)
        if len(cells) < 2:
            continue
        label_b = cells[0].find('b')
        if not label_b:
            continue
        role = ''
        for span in label_b.find_all('span'):
            style = span.get('style', '')
            if 'display:none' in style.replace(' ', ''):
                continue
            role = span.get_text(strip=True)
            if role:
                break
        if not role:
            role = label_b.get_text(strip=True)
        if role not in credits:
            credits[role] = []
        for child in cells[1].children:
            if isinstance(child, Tag) and child.name == 'a':
                artist_langs = _extract_lang_texts(child)
                if not artist_langs:
                    name = child.get_text(strip=True)
                    if name:
                        artist_langs = {'_raw': name}
                if artist_langs:
                    credits[role].append(artist_langs)
            elif isinstance(child, str):
                for piece in child.split(','):
                    piece = piece.strip()
                    if piece and not piece.startswith('('):
                        credits[role].append({'_raw': piece})

    def _flatten(artists: list[dict]) -> tuple[str, dict[str, str]]:
        primary = []
        for a in artists:
            name = a.get('ja') or a.get('_raw') or a.get('en', '')
            if name:
                primary.append(name)
        ja_str = ', '.join(primary)

        langs: dict[str, str] = {}
        for lang in ('en', 'ja', 'ja-Latn'):
            names = []
            for a in artists:
                name = a.get(lang) or a.get('_raw', '')
                if name:
                    names.append(name)
            if names:
                langs[lang] = ', '.join(names)
        return ja_str, langs

    for priority in ('Vocals', 'Vocal', 'Performer', 'Music', 'Composer',
                     'Arranger', 'Lyricist', 'Lyrics', 'Featuring'):
        for role_key, role_data in credits.items():
            if priority.lower() in role_key.lower():
                return _flatten(role_data)

    return _flatten(next(iter(credits.values())))


def _parse_tracklist(soup: BeautifulSoup) -> tuple[list[dict], dict[str, list[dict]]]:
    tracklist_header = None
    for h3 in soup.find_all('h3'):
        if 'tracklist' in h3.get_text(strip=True).lower():
            tracklist_header = h3
            break

    if not tracklist_header:
        return [], {}

    tabnav = tracklist_header.find_next_sibling('ul')
    if tabnav and tabnav.get('id') == 'tlnav':
        tabs = []
        for a in tabnav.find_all('a'):
            lang = a.get_text(strip=True)
            rel = a.get('rel', '')
            if lang and rel:
                tabs.append((lang, rel))

        all_langs: dict[str, list[dict]] = {}
        for lang, rel in tabs:
            content_span = soup.find('span', id=rel)
            if content_span:
                tbl = content_span.find('table', class_='role')
                if tbl:
                    tracks = _parse_track_table(tbl)
                    if tracks:
                        all_langs[lang] = tracks

        default_lang = None
        for lang, _ in tabs:
            if lang.lower() in ('japanese', '日本語'):
                default_lang = lang
                break
        if not default_lang:
            for lang, _ in tabs:
                if lang.lower() == 'english':
                    default_lang = lang
                    break
        if not default_lang and all_langs:
            default_lang = next(iter(all_langs))

        default_tracks = all_langs.get(default_lang, [])
        return default_tracks, all_langs

    container = tracklist_header.parent
    for _ in range(3):
        if container and container.parent:
            container = container.parent
    if container:
        tables = container.find_all('table')
        best = []
        for tbl in tables:
            tracks = _parse_track_table(tbl)
            if len(tracks) > len(best):
                best = tracks
        return best, {}

    return [], {}


def _parse_track_table(table: Tag) -> list[dict]:
    tracks = []
    rows = table.find_all('tr')
    for row in rows:
        cells = row.find_all('td', recursive=False)
        if len(cells) < 2:
            continue
        num_text = cells[0].get_text(strip=True)
        title_text = cells[1].get_text(strip=True)
        if not num_text or not title_text:
            continue
        try:
            num = int(re.sub(r'[^\d]', '', num_text))
        except ValueError:
            continue
        if not num:
            continue
        tracks.append({
            'num': num - 1,
            'title': title_text,
            'artist': '',
        })
    return tracks


def _parse_notes(soup: BeautifulSoup) -> str:
    notes_div = soup.find('div', id='notes')
    if not notes_div:
        return ''
    text = notes_div.get_text('\n', strip=True)
    return text


def parse_mhtml(filepath: str) -> str | None:
    try:
        with open(filepath, 'rb') as f:
            msg = email.message_from_binary_file(f, policy=policy.default)
    except (OSError, email.errors.MessageError) as e:
        print(f'[VGMdb] MHTML 读取失败: {e}')
        return None

    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == 'text/html':
                charset = part.get_content_charset() or 'utf-8'
                try:
                    return part.get_payload(decode=True).decode(charset, errors='replace')
                except Exception as e:
                    print(f'[VGMdb] MHTML 解码失败: {e}')
                    return None
    else:
        charset = msg.get_content_charset() or 'utf-8'
        try:
            return msg.get_payload(decode=True).decode(charset, errors='replace')
        except Exception as e:
            print(f'[VGMdb] MHTML 解码失败: {e}')
            return None

    return None


def search_album_url(html: str) -> str | None:
    results = parse_search_html(html)
    if not results:
        return None
    album_url = results[0].get('album_url', '')
    if album_url:
        if album_url.startswith('/'):
            return f'https://vgmdb.net{album_url}'
        if album_url.startswith('http'):
            return album_url
    return None
