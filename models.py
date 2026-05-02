from dataclasses import dataclass, field
import os
import sys


# 路径工具

def app_dir() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def data_path() -> str:
    return os.path.join(app_dir(), 'data.json')


# 文件名安全化

_FILENAME_MAP = {
    chr(92): chr(0x29f5),
    '/': chr(0x29f8),
    ':': chr(0xff1a),
    '*': chr(0x2217),
    '?': chr(0xff1f),
    chr(0x22): chr(0x2033),
    '<': chr(0xff1c),
    '>': chr(0xff1e),
    '|': chr(0xff5c),
}

def sanitize_filename(name: str) -> str:
    for old, new in _FILENAME_MAP.items():
        name = name.replace(old, new)
    return name


# 数据模型

@dataclass
class TrackInfo:
    num: int = 0
    title: str = ''
    track_artist: str = ''
    file_path: str = ''


@dataclass
class AlbumInfo:
    artist: str = ''
    title: str = ''
    year: str = ''
    num_tracks: int = 0
    cover_path: str = ''
    tracks: list = field(default_factory=list)
    disc_id: str = ''
    catalog_id: str = ''
    disc_number: str = ''
    total_discs: str = ''
    source: str = 'manual'


# 音频格式

SUPPORTED_EXTS: dict[str, str] = {
    '.flac': 'flac',
    '.mp3':  'mp3',
    '.m4a':  'm4a',
    '.wav':  'wav',
    '.ogg':  'ogg',
    '.aiff': 'aiff',
}

def get_audio_files(directory: str) -> list[str]:
    try:
        files = [
            os.path.join(directory, f)
            for f in os.listdir(directory)
            if os.path.splitext(f)[1].lower() in SUPPORTED_EXTS
        ]
        files.sort()
        return files
    except OSError:
        return []


def find_cover(directory: str) -> str:
    for name in ('cover.jpg', 'cover.png', 'Cover.jpg', 'Cover.png',
                 'folder.jpg', 'folder.png'):
        path = os.path.join(directory, name)
        if os.path.isfile(path):
            return path
    try:
        for f in sorted(os.listdir(directory)):
            if os.path.splitext(f)[1].lower() in ('.jpg', '.jpeg', '.png'):
                return os.path.join(directory, f)
    except OSError:
        pass
    return ''
