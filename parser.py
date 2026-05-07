from models import AlbumInfo, TrackInfo


def parse(text: str) -> AlbumInfo:
    album = AlbumInfo()
    track_map: dict[int, dict] = {}

    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue

        if line.startswith('#'):
            parts = line.lstrip('# CD:').strip().split()
            for part in parts:
                if '=' in part:
                    k, v = part.split('=', 1)
                    if k == 'disc_id':
                        album.disc_id = v
            continue

        if '=' not in line:
            continue

        key, _, value = line.partition('=')
        key = key.strip()
        value = value.strip()
        if not value:
            continue

        if key == 'artist':
            album.artist = value
        elif key == 'title':
            album.title = value
        elif key == 'year':
            album.year = value
        elif key == 'numtracks':
            try:
                album.num_tracks = int(value)
            except ValueError:
                pass
        elif key == 'disc_id':
            album.disc_id = value
        elif key == 'catalog_id':
            album.catalog_id = value
        elif key == 'discnumber':
            album.disc_number = value
        elif key == 'totaldiscs':
            album.total_discs = value
        elif key.endswith('artist') and len(key) > 6:
            num_str = key[:-6]
            if num_str.lstrip('-').isdigit():
                track_map.setdefault(int(num_str), {})['artist'] = value
        elif key.isdigit() or (key.startswith('-') and key[1:].isdigit()):
            track_map.setdefault(int(key), {})['title'] = value

    if not track_map:
        return album

    max_n = max(max(track_map.keys()), album.num_tracks - 1, -1)
    for num in range(max_n + 1):
        t = track_map.get(num, {})
        album.tracks.append(TrackInfo(
            num=num,
            title=t.get('title', ''),
            track_artist=t.get('artist', ''),
        ))

    if not album.num_tracks:
        album.num_tracks = len(album.tracks)

    return album


def format_album(album: AlbumInfo) -> str:
    lines = []
    if album.disc_id:
        lines.append(f'disc_id={album.disc_id}')
    if album.catalog_id:
        lines.append(f'catalog_id={album.catalog_id}')
    if album.disc_number:
        lines.append(f'discnumber={album.disc_number}')
    if album.total_discs:
        lines.append(f'totaldiscs={album.total_discs}')
    if album.artist:
        lines.append(f'artist={album.artist}')
    if album.title:
        lines.append(f'title={album.title}')
    if album.year:
        lines.append(f'year={album.year}')
    if album.num_tracks > 0:
        lines.append(f'numtracks={album.num_tracks}')
    for t in album.tracks:
        if t.title:
            lines.append(f'{t.num}={t.title}')
        if t.track_artist and t.track_artist != album.artist:
            lines.append(f'{t.num}artist={t.track_artist}')
    return '\n'.join(lines)
