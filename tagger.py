import os
from mutagen.flac import FLAC, Picture
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover
from mutagen.wave import WAVE
from mutagen.oggvorbis import OggVorbis
from mutagen.aiff import AIFF
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TPE2, TALB, TDRC, TRCK, TPOS
from models import AlbumInfo, TrackInfo, sanitize_filename


def write(file_path: str, track: TrackInfo, album: AlbumInfo,
          cover_path: str = '') -> bool:
    ext = os.path.splitext(file_path)[1].lower()

    try:
        if ext == '.flac':
            _tag_flac(file_path, track, album, cover_path)
        elif ext == '.mp3':
            _tag_id3(file_path, track, album, cover_path)
        elif ext == '.m4a':
            _tag_m4a(file_path, track, album, cover_path)
        elif ext == '.wav':
            _tag_id3(file_path, track, album, cover_path)
        elif ext == '.ogg':
            _tag_ogg(file_path, track, album, cover_path)
        elif ext == '.aiff':
            _tag_id3(file_path, track, album, cover_path)
        else:
            print(f'[tagger] 不支持的格式: {ext}')
            return False
    except Exception as e:
        print(f'[tagger 错误] 写入 {file_path} 失败: {e}')
        return False

    if track.title:
        _rename(file_path, track.num, track.title, ext)
    print(f'[写入] {os.path.basename(file_path)}')
    return True


def _tag_flac(path: str, track: TrackInfo, album: AlbumInfo, cover_path: str):
    audio = FLAC(path)
    audio['album'] = album.title
    audio['albumartist'] = album.artist
    audio['artist'] = track.track_artist or album.artist
    audio['title'] = track.title
    audio['date'] = album.year
    audio['tracknumber'] = str(track.num + 1)
    audio['tracktotal'] = str(album.num_tracks)
    if cover_path and os.path.isfile(cover_path):
        audio.clear_pictures()
        pic = Picture()
        pic.type = 3
        pic.mime = _mime_type(cover_path)
        with open(cover_path, 'rb') as f:
            pic.data = f.read()
        audio.add_picture(pic)
    audio.save()


def _tag_id3(path: str, track: TrackInfo, album: AlbumInfo, cover_path: str):
    try:
        audio = ID3(path)
    except Exception:
        audio = ID3()
    audio.clear()
    audio['TIT2'] = TIT2(encoding=3, text=track.title)
    audio['TPE1'] = TPE1(encoding=3, text=track.track_artist or album.artist)
    audio['TPE2'] = TPE2(encoding=3, text=album.artist)
    audio['TALB'] = TALB(encoding=3, text=album.title)
    audio['TDRC'] = TDRC(encoding=3, text=album.year)
    audio['TRCK'] = TRCK(encoding=3,
                         text=f'{track.num + 1}/{album.num_tracks}')
    if cover_path and os.path.isfile(cover_path):
        with open(cover_path, 'rb') as f:
            audio['APIC'] = APIC(encoding=3, mime=_mime_type(cover_path),
                                 type=3, desc='Cover', data=f.read())
    audio.save(path)


def _tag_m4a(path: str, track: TrackInfo, album: AlbumInfo, cover_path: str):
    audio = MP4(path)
    audio['\xa9alb'] = album.title
    audio['aART'] = album.artist
    artist = track.track_artist or album.artist
    audio['\xa9ART'] = artist
    audio['\xa9nam'] = track.title
    audio['\xa9day'] = album.year
    audio['trkn'] = [(track.num + 1, album.num_tracks)]
    if cover_path and os.path.isfile(cover_path):
        fmt = MP4Cover.FORMAT_JPEG
        if cover_path.lower().endswith('.png'):
            fmt = MP4Cover.FORMAT_PNG
        with open(cover_path, 'rb') as f:
            audio['covr'] = [MP4Cover(f.read(), imageformat=fmt)]
    audio.save()


def _tag_ogg(path: str, track: TrackInfo, album: AlbumInfo, cover_path: str):
    audio = OggVorbis(path)
    audio['album'] = album.title
    audio['albumartist'] = album.artist
    audio['artist'] = track.track_artist or album.artist
    audio['title'] = track.title
    audio['date'] = album.year
    audio['tracknumber'] = str(track.num + 1)
    audio['tracktotal'] = str(album.num_tracks)
    audio.save()


def _rename(path: str, track_num: int, title: str, ext: str):
    safe_title = sanitize_filename(title)
    new_name = f'{track_num + 1:02d}. {safe_title}{ext}'
    new_path = os.path.join(os.path.dirname(path), new_name)
    if path.lower() == new_path.lower():
        return
    try:
        os.rename(path, new_path)
        print(f'[tagger] 重命名: {os.path.basename(path)} -> {new_name}')
    except OSError as e:
        print(f'[tagger 错误] 重命名失败: {e}')


def _mime_type(path: str) -> str:
    if path.lower().endswith('.png'):
        return 'image/png'
    return 'image/jpeg'
