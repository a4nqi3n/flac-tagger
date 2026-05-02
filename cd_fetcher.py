import os
import sys

if getattr(sys, 'frozen', False):
    _dll_dir = sys._MEIPASS
else:
    _dll_dir = os.path.dirname(os.path.abspath(__file__))
if os.path.exists(os.path.join(_dll_dir, 'discid.dll')):
    if hasattr(os, 'add_dll_directory'):
        os.add_dll_directory(_dll_dir)

import discid
import musicbrainzngs

musicbrainzngs.set_useragent('FLAC-Tagger', '1.0', '')


def read() -> list[dict] | None:
    try:
        disc = discid.read()
    except Exception as e:
        print(f'[CD 读取] 光驱读取失败: {e}')
        return None

    disc_id = disc.id

    print(f'[CD] 正在查询 MusicBrainz (disc_id={disc_id})...')
    try:
        releases = musicbrainzngs.get_releases_by_discid(
            disc_id, includes=['artists', 'recordings']
        )
        results = _parse_musicbrainz(disc_id, releases)
        if results:
            print(f'[CD] MusicBrainz 找到 {len(results)} 个匹配')
            for r in results:
                label = f"{r['artist']} - {r['title']}"
                if r.get('year'):
                    label += f" ({r['year']})"
                print(f'     {label}')
        else:
            print(f'[CD] MusicBrainz 未找到匹配')
    except Exception as e:
        print(f'[CD] MusicBrainz 查询失败: {e}')
        results = []

    if not results:
        print(f'[CD] 未能识别此光盘')
        results = [{'disc_id': disc_id, 'artist': '', 'title': '', 'year': '', 'tracks': []}]

    return results


def _format_artist_credit(artist_credit: list) -> str:
    if not artist_credit:
        return ''
    parts = []
    for item in artist_credit:
        if isinstance(item, dict):
            name = item.get('name')
            if not name and 'artist' in item:
                name = item['artist'].get('name', '')
            parts.append(name or '')
            parts.append(item.get('joinphrase', ''))
        elif isinstance(item, str):
            parts.append(item)
    return ''.join(parts)


def _parse_musicbrainz(disc_id: str, releases: dict) -> list[dict]:
    release_list = releases.get('disc', {}).get('release-list', [])
    if not release_list:
        return []

    results = []
    for release in release_list:
        album_artist = _format_artist_credit(release.get('artist-credit', []))
        title = release.get('title', '')
        year = release.get('date', '')[:4] if release.get('date') else ''

        tracks = []
        media_list = release.get('medium-list', [])
        if media_list:
            for track in media_list[0].get('track-list', []):
                track_ac = (track.get('artist-credit')
                            or track.get('recording', {}).get('artist-credit', []))
                track_artist = _format_artist_credit(track_ac)
                if track_artist == album_artist:
                    track_artist = ''
                tracks.append({
                    'num': int(track.get('position', 0)) - 1,
                    'title': track.get('recording', {}).get('title', ''),
                    'artist': track_artist,
                })

        results.append({
            'disc_id': disc_id,
            'artist': album_artist,
            'title': title,
            'year': year,
            'tracks': tracks,
        })

    return results
