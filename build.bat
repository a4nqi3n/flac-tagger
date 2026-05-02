@echo off
chcp 65001 >nul
echo === 标签导入V2.0 build ===

.venv\Scripts\pip.exe install -r requirements.txt

.venv\Scripts\pyinstaller ^
  --onefile ^
  --windowed ^
  --name "标签导入V2.0" ^
  --icon "logo.ico" ^
  --add-data "discid.dll;." ^
  --add-data "logo.ico;." ^
  --hidden-import discid ^
  --hidden-import mutagen.flac ^
  --hidden-import mutagen.mp3 ^
  --hidden-import mutagen.mp4 ^
  --hidden-import mutagen.wave ^
  --hidden-import mutagen.oggvorbis ^
  --hidden-import mutagen.aiff ^
  --hidden-import mutagen.id3 ^
  flac_tagger.py

echo === Done ===
echo Output: dist\标签导入V2.0.exe
pause
