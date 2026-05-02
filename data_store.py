import json
import os
import uuid
from datetime import datetime
from typing import Any
from models import data_path, AlbumInfo, TrackInfo


_DEFAULT = {
    'config': {
        'theme': 'dark',
        'window_geometry': '',
        'providers': [
            {'name': 'DeepSeek', 'endpoint': 'https://api.deepseek.com/', 'token': '',
             'models': ['deepseek-v4-pro', 'deepseek-v4-flash', 'deepseek-reasoner', 'deepseek-chat']},
            {'name': '通义千问', 'endpoint': 'https://dashscope.aliyuncs.com/compatible-mode/v1', 'token': '',
             'models': ['qwen3.5-flash', 'qwen3.5-plus', 'qwen3.6-plus']},
            {'name': 'OpenAI', 'endpoint': 'https://api.openai.com/', 'token': '',
             'models': []},
        ],
        'musicbrainz': {
            'useragent': '',
            'contact': '',
        },
        'vgmdb': {
            'cookie': '',
        },
        'last_directory': '',
    },
    'albums': [],
}


def load_data() -> dict:
    try:
        with open(data_path(), 'r', encoding='utf-8') as f:
            data = json.load(f)
        data.setdefault('config', {})
        for k, v in _DEFAULT['config'].items():
            data['config'].setdefault(k, v)
        data.setdefault('albums', _DEFAULT['albums'])
        return data
    except (FileNotFoundError, json.JSONDecodeError) as e:
        if isinstance(e, json.JSONDecodeError):
            print(f'[data_store] JSON 解析失败，使用默认配置: {e}')
        return _DEFAULT.copy()


def save_data(data: dict) -> bool:
    path = data_path()
    tmp = path + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except OSError as e:
        print(f'[data_store 错误] 保存失败: {e}')
        return False


def get_config(data: dict, key: str, default: Any = None) -> Any:
    return data.get('config', {}).get(key, default)


def set_config(data: dict, key: str, value: Any):
    data.setdefault('config', {})[key] = value


def get_albums(data: dict) -> list[dict]:
    return data.get('albums', [])


def _album_to_dict(album: AlbumInfo, album_id: str | None = None) -> dict:
    return {
        'id': album_id or str(uuid.uuid4()),
        'disc_id': album.disc_id,
        'catalog_id': album.catalog_id,
        'disc_number': album.disc_number,
        'total_discs': album.total_discs,
        'artist': album.artist,
        'title': album.title,
        'year': album.year,
        'num_tracks': album.num_tracks,
        'cover_path': album.cover_path,
        'tracks': [{'num': t.num, 'title': t.title, 'track_artist': t.track_artist}
                    for t in album.tracks],
        'source': album.source,
        'created_at': datetime.now().isoformat(),
        'updated_at': datetime.now().isoformat(),
    }


def _dict_to_album(d: dict) -> AlbumInfo:
    album = AlbumInfo(
        artist=d.get('artist', ''),
        title=d.get('title', ''),
        year=d.get('year', ''),
        num_tracks=d.get('num_tracks', 0),
        cover_path=d.get('cover_path', ''),
        disc_id=d.get('disc_id', ''),
        catalog_id=d.get('catalog_id', ''),
        disc_number=d.get('disc_number', ''),
        total_discs=d.get('total_discs', ''),
        source=d.get('source', 'manual'),
    )
    for t in d.get('tracks', []):
        album.tracks.append(TrackInfo(
            num=t.get('num', 0),
            title=t.get('title', ''),
            track_artist=t.get('track_artist', ''),
        ))
    return album


def find_existing_album(data: dict, album: AlbumInfo) -> dict | None:
    albums = data.get('albums', [])
    if album.disc_id:
        for a in albums:
            if a.get('disc_id') == album.disc_id:
                return a
    if album.catalog_id:
        for a in albums:
            if a.get('catalog_id') == album.catalog_id:
                return a
    for a in albums:
        if (a.get('artist') == album.artist
                and a.get('title') == album.title
                and a.get('year') == album.year
                and a.get('artist') and a.get('title')):
            return a
    return None


def merge_albums(old: dict, new: AlbumInfo) -> dict:
    merged = dict(old)
    nd = _album_to_dict(new)
    for key in ('disc_id', 'catalog_id', 'disc_number', 'total_discs', 'artist', 'title', 'year', 'num_tracks', 'cover_path'):
        if nd.get(key):
            merged[key] = nd[key]
    if nd.get('tracks'):
        old_tracks = {t['num']: t for t in merged.get('tracks', [])}
        for nt in nd['tracks']:
            if nt['num'] in old_tracks:
                ot = old_tracks[nt['num']]
                if nt.get('title') and not ot.get('title'):
                    ot['title'] = nt['title']
                if nt.get('track_artist') and not ot.get('track_artist'):
                    ot['track_artist'] = nt['track_artist']
            else:
                old_tracks[nt['num']] = nt
        merged['tracks'] = sorted(old_tracks.values(), key=lambda t: t['num'])
    merged['source'] = 'merged'
    merged['updated_at'] = datetime.now().isoformat()
    return merged


def insert_album(data: dict, album: AlbumInfo) -> str:
    d = _album_to_dict(album)
    data.setdefault('albums', []).append(d)
    return d['id']


def update_album(data: dict, album_id: str, album: AlbumInfo):
    albums = data.get('albums', [])
    for i, a in enumerate(albums):
        if a.get('id') == album_id:
            d = _album_to_dict(album, album_id)
            d['created_at'] = a.get('created_at', d['created_at'])
            d['updated_at'] = datetime.now().isoformat()
            albums[i] = d
            return


def delete_album(data: dict, album_id: str) -> bool:
    albums = data.get('albums', [])
    for i, a in enumerate(albums):
        if a.get('id') == album_id:
            albums.pop(i)
            return True
    return False


def search_albums(data: dict, query: str) -> list[dict]:
    q = query.lower()
    return [a for a in data.get('albums', [])
            if q in a.get('artist', '').lower() or q in a.get('title', '').lower()]
