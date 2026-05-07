# 标签导入 V2.0

同人音乐 FLAC 标签批量写入工具。

## 功能

- CD 读取：通过 MusicBrainz 识别物理光盘，自动获取专辑信息
- VGMdb 解析：浏览器保存 MHTML 后拖入解析，支持多语言曲目切换
- AI 提取：接入LLM，通过文本或图片自动提取元数据
- 手动编辑：可以手动修改Tag
- 数据库缓存：标签资料存储，支持搜索、去重、合并
- 标签写入：写入tag，封面嵌入 + 曲目重命名


## 依赖

PySide6 / mutagen / musicbrainzngs / discid / requests / Pillow / beautifulsoup4 / pyinstaller
