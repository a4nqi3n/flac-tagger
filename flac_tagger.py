import os
import sys
import webbrowser
from datetime import datetime

from PySide6.QtWidgets import (
    QMainWindow, QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTabWidget, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QLineEdit, QPlainTextEdit, QTextEdit,
    QListWidget, QListWidgetItem, QGroupBox,
    QFileDialog, QMessageBox, QHeaderView,
    QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QStatusBar, QAbstractItemView, QMenu, QStyledItemDelegate,
    QInputDialog, QSizePolicy, QToolButton, QCheckBox,
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QTextOption, QIcon

from models import (
    AlbumInfo, TrackInfo, data_path,
    get_audio_files, find_cover, sanitize_filename,
)
from parser import parse, format_album
from data_store import (
    load_data, save_data, get_config, set_config as ds_set_config,
    get_albums, insert_album, update_album, delete_album,
    find_existing_album, merge_albums, search_albums,
)
from theme import get_theme
from tagger import write as write_tags
from ai_client import call as ai_call
from cd_fetcher import read as cd_read
from vgmdb_fetcher import (parse_album_html as vgmdb_parse,
                            parse_mhtml)


# QPlainTextEdit 日志

class LogHandler:
    # print → QPlainTextEdit
    def __init__(self, widget: QPlainTextEdit):
        self.widget = widget
        self._stdout = sys.stdout
        self._stderr = sys.stderr

    def write(self, text: str):
        if text.rstrip():
            self.widget.appendPlainText(text.rstrip())
            sb = self.widget.verticalScrollBar()
            sb.setValue(sb.maximum())
        self._stdout.write(text)

    def flush(self):
        self._stdout.flush()

    def install(self):
        sys.stdout = self
        sys.stderr = self

    def uninstall(self):
        sys.stdout = self._stdout
        sys.stderr = self._stderr


# AI 调用

class AIWorker(QThread):
    finished = Signal(str)   # 成功返回文本
    error = Signal(str)      # 错误消息

    def __init__(self, endpoint, token, model, text, images):
        super().__init__()
        self.endpoint = endpoint
        self.token = token
        self.model = model
        self.text = text
        self.images = images

    def run(self):
        try:
            result = ai_call(self.endpoint, self.token, self.model,
                             self.text, self.images)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


# CD 读取

class CDWorker(QThread):
    finished = Signal(object)  # list[dict] or None
    error = Signal(str)

    def run(self):
        try:
            result = cd_read()
            self.finished.emit(result)
        except Exception as e:
            print(f'[CD 错误] {e}')
            try:
                self.error.emit(str(e))
            except Exception:
                pass


# VGMdb 解析

class VgmdbWorker(QThread):
    finished = Signal(object)  # dict or None
    error = Signal(str)

    def run(self):
        try:
            html = getattr(self, 'html', None)
            if not html:
                self.finished.emit(None)
                return
            result = vgmdb_parse(html)
            self.finished.emit(result)
        except Exception as e:
            print(f'[VGMdb 错误] {e}')
            try:
                self.error.emit(str(e))
            except Exception:
                pass


# 提供商编辑对话框

class ProviderDialog(QDialog):
    # AI 提供商管理，自动暂存

    def __init__(self, providers, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI 提供商")
        self.providers = providers
        self._current_name = None
        self._block_signals = False
        self.setMinimumSize(520, 440)
        self._build()
        if self._list.count():
            self._list.setCurrentRow(0)

    def _build(self):
        layout = QVBoxLayout(self)

        # 提供商列表 + 新建/删除
        layout.addWidget(QLabel("提供商"))
        list_row = QHBoxLayout()
        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._on_select)
        list_row.addWidget(self._list, 1)
        list_btns = QVBoxLayout()
        btn_new = QPushButton("新增")
        btn_new.clicked.connect(self._new_provider)
        btn_del = QPushButton("删除")
        btn_del.clicked.connect(self._delete)
        list_btns.addWidget(btn_new)
        list_btns.addWidget(btn_del)
        list_btns.addStretch()
        list_row.addLayout(list_btns)
        layout.addLayout(list_row)
        self._refresh_list()

        # 编辑表单
        form = QFormLayout()
        self._name_edit = QLineEdit()
        self._name_edit.textChanged.connect(self._on_name_changed)
        self._endpoint_edit = QLineEdit()
        self._endpoint_edit.textChanged.connect(self._auto_save)
        self._token_edit = QLineEdit()
        self._token_edit.setEchoMode(QLineEdit.Password)
        self._token_edit.textChanged.connect(self._auto_save)
        form.addRow("名称", self._name_edit)
        form.addRow("Endpoint", self._endpoint_edit)
        form.addRow("Token", self._token_edit)
        layout.addLayout(form)

        # 模型列表
        layout.addWidget(QLabel("模型列表"))
        model_row = QHBoxLayout()
        self._model_list = QListWidget()
        model_row.addWidget(self._model_list, 1)
        model_btns = QVBoxLayout()
        self._model_edit = QLineEdit()
        self._model_edit.setPlaceholderText("输入模型名...")
        self._model_edit.returnPressed.connect(self._add_model)
        model_btns.addWidget(self._model_edit)
        btn_add_model = QPushButton("添加")
        btn_add_model.clicked.connect(self._add_model)
        btn_del_model = QPushButton("移除")
        btn_del_model.clicked.connect(self._remove_model)
        model_btns.addWidget(btn_add_model)
        model_btns.addWidget(btn_del_model)
        model_btns.addStretch()
        model_row.addLayout(model_btns)
        layout.addLayout(model_row)

    def _refresh_list(self):
        self._block_signals = True
        old_name = self._current_name
        self._list.clear()
        for p in self.providers:
            item = QListWidgetItem(p.get('name', ''))
            item.setData(Qt.UserRole, p.get('name', ''))
            self._list.addItem(item)
        # 恢复选中
        if old_name:
            for i in range(self._list.count()):
                if self._list.item(i).data(Qt.UserRole) == old_name:
                    self._list.setCurrentRow(i)
                    break
        self._block_signals = False

    def _get_current_provider(self):
        name = self._current_name
        for p in self.providers:
            if p.get('name') == name:
                return p
        return None

    def _on_select(self):
        if self._block_signals:
            return
        item = self._list.currentItem()
        if not item:
            return
        self._block_signals = True
        name = item.data(Qt.UserRole)
        self._current_name = name
        for p in self.providers:
            if p.get('name') == name:
                self._name_edit.setText(p.get('name', ''))
                self._endpoint_edit.setText(p.get('endpoint', ''))
                self._token_edit.setText(p.get('token', ''))
                # 刷新模型列表
                self._model_list.clear()
                for m in p.get('models', []):
                    self._model_list.addItem(m)
                break
        self._block_signals = False

    def _auto_save(self):
        # 字段变动 → 自动暂存
        if self._block_signals:
            return
        p = self._get_current_provider()
        if p is None:
            return
        p['endpoint'] = self._endpoint_edit.text().strip()
        p['token'] = self._token_edit.text().strip()

    def _on_name_changed(self, new_name: str):
        # 改名 → 更新 provider
        if self._block_signals:
            return
        p = self._get_current_provider()
        if p is None:
            return
        new = new_name.strip()
        if new and new != p['name']:
            p['name'] = new
            self._current_name = new
            self._refresh_list()
        self._auto_save()

    def _new_provider(self):
        name = '新提供商'
        i = 1
        while any(p.get('name') == name for p in self.providers):
            i += 1
            name = f'新提供商 {i}'
        self.providers.append({
            'name': name,
            'endpoint': '',
            'token': '',
            'models': [],
        })
        self._refresh_list()
        # 选中新建的
        self._list.setCurrentRow(self._list.count() - 1)

    def _delete(self):
        name = self._current_name
        if not name:
            return
        for i, p in enumerate(self.providers):
            if p.get('name') == name:
                self.providers.pop(i)
                break
        self._current_name = None
        self._block_signals = True
        self._name_edit.clear()
        self._endpoint_edit.clear()
        self._token_edit.clear()
        self._model_list.clear()
        self._model_edit.clear()
        self._block_signals = False
        self._refresh_list()

    def _add_model(self):
        p = self._get_current_provider()
        if p is None:
            return
        model = self._model_edit.text().strip()
        if not model:
            return
        p.setdefault('models', []).append(model)
        self._model_list.addItem(model)
        self._model_edit.clear()

    def _remove_model(self):
        p = self._get_current_provider()
        if p is None:
            return
        item = self._model_list.currentItem()
        if not item:
            return
        model = item.text()
        if model in p.get('models', []):
            p['models'].remove(model)
        self._model_list.takeItem(self._model_list.row(item))


# 合并确认对话框

class MergeDialog(QDialog):
    COVER = 0
    MERGE = 1
    CANCEL = 2

    def __init__(self, existing: dict, new: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("专辑已存在")
        self.result_choice = self.CANCEL
        self._build(existing, new)

    def _build(self, existing, new):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            f"专辑已存在于缓存中:\n\n"
            f"   {existing.get('artist', '?')} — {existing.get('title', '?')} ({existing.get('year', '?')})\n"
            f"   disc_id: {existing.get('disc_id', '无')}\n"
            f"   catalog_id: {existing.get('catalog_id', '无')}\n\n"
            f"请选择操作:"))
        btn_cover = QPushButton("覆盖 — 用新数据完全替换旧数据")
        btn_cover.clicked.connect(lambda: self._done(MergeDialog.COVER))
        btn_merge = QPushButton("合并 — 新数据非空字段补充到旧记录")
        btn_merge.clicked.connect(lambda: self._done(MergeDialog.MERGE))
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(lambda: self._done(MergeDialog.CANCEL))
        layout.addWidget(btn_cover)
        layout.addWidget(btn_merge)
        layout.addWidget(btn_cancel)

    def _done(self, choice):
        self.result_choice = choice
        self.accept()


# 实时跟踪编辑

class TrackDelegate(QStyledItemDelegate):
    editingTextChanged = Signal(int, int, str)

    def createEditor(self, parent, option, index):
        editor = super().createEditor(parent, option, index)
        if isinstance(editor, QLineEdit):
            editor.textChanged.connect(
                lambda text, row=index.row(), col=index.column():
                self.editingTextChanged.emit(row, col, text)
            )
        return editor



class MusicBrainzDialog(QDialog):
    # MusicBrainz 设置

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MusicBrainz 设置")
        self.config = config
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(12, 12, 12, 12)
        form = QFormLayout()
        form.setSpacing(4)
        self._ua = QLineEdit()
        self._ua.setPlaceholderText("例如: MyApp/1.0 (user@example.com)")
        self._ua.setText(config.get('useragent', ''))
        self._contact = QLineEdit()
        self._contact.setPlaceholderText("例如: user@example.com")
        self._contact.setText(config.get('contact', ''))
        form.addRow("User-Agent", self._ua)
        form.addRow("Contact", self._contact)
        layout.addLayout(form)
        note = QLabel("MusicBrainz仅需合法 User-Agent。Contact 填邮箱便于必要时联系。")
        note.setWordWrap(True)
        note.setStyleSheet("color: #6c7086; font-size: 11px;")
        layout.addWidget(note)
        btn_save = QPushButton("保存到数据库")
        btn_save.clicked.connect(self._save)
        layout.addWidget(btn_save)

    def _save(self):
        self.config['useragent'] = self._ua.text().strip()
        self.config['contact'] = self._contact.text().strip()
        self.accept()


def _vgmdb_lang_code(display_name: str | None) -> str | None:
    # VGMdb 语言名 → lang 代码
    if not display_name:
        return None
    name = display_name.lower()
    if 'japanese' in name or '日本語' in name or name == 'ja':
        return 'ja'
    if 'english' in name or name == 'en':
        return 'en'
    if 'romaji' in name or 'latn' in name:
        return 'ja-Latn'
    return None


def _search_albums_deep(albums: list[dict], query: str) -> list[dict]:
    # 深搜索：全字段匹配
    q = query.lower()
    result = []
    for a in albums:
        # 顶层字段
        if q in a.get('artist', '').lower():
            result.append(a)
            continue
        if q in a.get('title', '').lower():
            result.append(a)
            continue
        if q in a.get('year', '').lower():
            result.append(a)
            continue
        if q in a.get('disc_id', '').lower():
            result.append(a)
            continue
        if q in a.get('catalog_id', '').lower():
            result.append(a)
            continue
        # 曲目字段
        found = False
        for t in a.get('tracks', []):
            if q in t.get('title', '').lower() or q in t.get('track_artist', '').lower():
                result.append(a)
                found = True
                break
        if found:
            continue
    return result


class WelcomeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("欢迎")
        self.setMinimumWidth(480)
        self._dont_show = False
        self._set_icon()

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 20, 24, 20)

        title = QLabel("标签导入 V2.0")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        desc = QLabel(
            "本程序由暗昑制作，用于帮同人音乐爱好者购买 CD 后快速填入标签。\n"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #a6adc8; font-size: 13px;")
        layout.addWidget(desc)

        changes = QLabel(
            "<b>V2.0 更新内容</b>"
        )
        changes.setStyleSheet("font-size: 13px; font-weight: bold; margin-top: 4px;")
        layout.addWidget(changes)

        items = QLabel(
            "1. 新增数据库功能，可将标签资料保存到数据库\n"
            "2. 新增 MusicBrainz 支持，可直接读取光驱并在线查询标签\n"
            "3. 完善标签种类，支持更多音频格式\n"
            "4. 新增 VGMdb 手动导入接口（VGMdb 暂未开放官方 API，暂时通过 MHTML 解析实现标签获取）"
        )
        items.setWordWrap(True)
        items.setStyleSheet("font-size: 12px; margin-left: 8px;")
        layout.addWidget(items)

        self._checkbox = QCheckBox("下次不再显示")
        layout.addWidget(self._checkbox)

        btn = QPushButton("我知道了")
        btn.setMinimumHeight(36)
        btn.clicked.connect(self._accept)
        layout.addWidget(btn)

    @staticmethod
    def _get_icon_path():
        if getattr(sys, 'frozen', False):
            return os.path.join(sys._MEIPASS, 'logo.ico')
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logo.ico')

    def _set_icon(self):
        path = self._get_icon_path()
        if os.path.isfile(path):
            self.setWindowIcon(QIcon(path))

    def _accept(self):
        self._dont_show = self._checkbox.isChecked()
        self.accept()


class FlacTaggerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("标签导入V2.0")
        self.setMinimumSize(1024, 640)
        self.resize(1280, 780)

        if getattr(sys, 'frozen', False):
            icon_path = os.path.join(sys._MEIPASS, 'logo.ico')
        else:
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logo.ico')
        if os.path.isfile(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # 数据
        self._data = load_data()
        self._current_dir = get_config(self._data, "last_directory", "")
        self._current_album = AlbumInfo()
        self._cd_result: dict | None = None
        self._search_deep = False
        self._cd_busy = False
        self._ai_busy = False
        self._vgmdb_busy = False
        self._vgmdb_result: dict | None = None
        self._vgmdb_file_path: str | None = None

        # 布局
        self._build_ui()
        self._apply_theme()
        self._restore_geometry()

        # 应用已保存的 MusicBrainz 设置
        self._apply_musicbrainz_config()

        # CD 手动读取，不自动检测
    def showEvent(self, event):
        super().showEvent(event)
        self._fit_track_columns()

    def _track_avail(self):
    # 视口宽度减固定第0列
        return self._track_table.viewport().width() - 34

    def _apply_track_ratios(self):
    # 按比例填满屏幕
        if not hasattr(self, '_track_table'):
            return
        avail = self._track_avail()
        if avail < 100:
            return

        w1 = int(avail * self._track_ratios[0])
        w2 = int(avail * self._track_ratios[1])
        w3 = avail - w1 - w2  # 剩余像素全部塞给文件列，保证 100% 对齐

        self._track_resizing = True
        self._track_table.setColumnWidth(1, w1)
        self._track_table.setColumnWidth(2, w2)
        self._track_table.setColumnWidth(3, w3)
        self._track_resizing = False

    def _fit_track_columns(self):
    # 兼容 showEvent
        self._apply_track_ratios()

    def _on_track_col_resized(self, idx, old_size, new_size):
    # 联动缩放：左加右减，总和守恒
        if self._track_resizing:
            return

        # 禁止用户拖拽表格最右侧边缘，避免撑破布局
        if idx == 3 or idx == 0:
            if idx == 3:
                self._track_resizing = True
                self._track_table.setColumnWidth(3, old_size)
                self._track_resizing = False
            return

        t = self._track_table
        avail = self._track_avail()
        delta = new_size - old_size
        if delta == 0:
            return

        adj_idx = idx + 1  # 永远联动当前列的右侧相邻列
        adj_old_size = t.columnWidth(adj_idx)
        adj_new_size = adj_old_size - delta

        min_width = 40  # 极限防挤压底线

        # 核心修复 1：如果右边列被压扁了，必须把吃进去的宽度"吐"还给左边列
        if adj_new_size < min_width:
            rebound = min_width - adj_new_size
            adj_new_size = min_width
            new_size -= rebound

        # 核心修复 2：如果左边列被压扁了（猛向左拉），同理反弹给右边列
        if new_size < min_width:
            rebound = min_width - new_size
            new_size = min_width
            adj_new_size -= rebound

        self._track_resizing = True

        # 强制写回两列的值
        t.setColumnWidth(idx, new_size)
        t.setColumnWidth(adj_idx, adj_new_size)

        # 核心修复 3：吸收浮点计算和高速拖拽带来的像素级残差
        current_sum = t.columnWidth(1) + t.columnWidth(2) + t.columnWidth(3)
        if current_sum != avail:
            diff = avail - current_sum
            t.setColumnWidth(3, t.columnWidth(3) + diff)

        # 核心修复 4：记录你拖拽后的新比例，以便下次缩放窗口时依然保持你的喜好
        new_sum = t.columnWidth(1) + t.columnWidth(2) + t.columnWidth(3)
        if new_sum > 0:
            self._track_ratios[0] = t.columnWidth(1) / new_sum
            self._track_ratios[1] = t.columnWidth(2) / new_sum
            self._track_ratios[2] = t.columnWidth(3) / new_sum

        self._track_resizing = False

    def _apply_musicbrainz_config(self):
        mb = get_config(self._data, 'musicbrainz', {})
        try:
            import musicbrainzngs
            musicbrainzngs.set_useragent(
                mb.get('useragent', ''),
                '',
                mb.get('contact', ''),
            )
        except Exception:
            pass


    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        self.menuBar().hide()
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(4)

        # 顶层水平分割器：数据库侧栏 | 折叠按钮 | 主区域
        # 侧栏在左，折叠时可完全收起，主区域不受挤压
        top_splitter = QSplitter(Qt.Horizontal)

        # 数据库侧栏（在折叠按钮左侧）
        top_splitter.addWidget(self._build_history_sidebar())

        # 窄折叠按钮条 — 始终可见
        self._db_toggle_bar = QWidget()
        self._db_toggle_bar.setFixedWidth(30)
        tb_layout = QVBoxLayout(self._db_toggle_bar)
        tb_layout.setContentsMargins(2, 4, 0, 0)
        self._btn_toggle_db = QToolButton()
        self._btn_toggle_db.setArrowType(Qt.RightArrow)
        self._btn_toggle_db.setFixedSize(24, 24)
        self._btn_toggle_db.setToolTip("展开数据库")
        self._btn_toggle_db.clicked.connect(self._toggle_database)
        tb_layout.addWidget(self._btn_toggle_db)
        tb_layout.addStretch()
        top_splitter.addWidget(self._db_toggle_bar)

        # 主区域：左编辑区 | 右工具面板
        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.addWidget(self._build_left_panel())
        main_splitter.addWidget(self._build_right_panel())
        main_splitter.setStretchFactor(0, 3)
        main_splitter.setStretchFactor(1, 1)
        main_splitter.setSizes([700, 280])
        top_splitter.addWidget(main_splitter)

        top_splitter.setStretchFactor(0, 0)
        top_splitter.setStretchFactor(1, 0)
        top_splitter.setStretchFactor(2, 1)
        top_splitter.setSizes([220, 30, 1000])
        root.addWidget(top_splitter, 1)

        # 默认收起数据库
        self._hist_sidebar.hide()
        self._btn_toggle_db.setArrowType(Qt.RightArrow)
        self._btn_toggle_db.setToolTip("展开数据库")

        # 日志区
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(500)
        self._log.setFixedHeight(100)
        root.addWidget(self._log)

        self._log_handler = LogHandler(self._log)
        self._log_handler.install()

        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("就绪")

    def _build_history_sidebar(self):
    # 数据库侧栏
        w = QWidget()
        self._hist_sidebar = w  # 保存引用以便折叠
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(4)

        title_row = QHBoxLayout()
        title = QLabel("数据库")
        title.setStyleSheet("font-weight: bold; font-size: 12px;")
        title_row.addWidget(title)
        title_row.addStretch()
        layout.addLayout(title_row)

        self._hist_search = QLineEdit()
        self._hist_search.setPlaceholderText("搜索...")
        self._hist_search.textChanged.connect(self._on_hist_search)
        layout.addWidget(self._hist_search)

        # 搜索模式切换
        search_mode_row = QHBoxLayout()
        search_mode_row.setSpacing(2)
        self._btn_search_mode = QToolButton()
        self._btn_search_mode.setText("Aa")
        self._btn_search_mode.setFixedSize(32, 20)
        self._btn_search_mode.setToolTip("搜索模式：仅艺术家/专辑名 — 点击切换")
        self._btn_search_mode.clicked.connect(self._on_hist_search_mode)
        search_mode_row.addWidget(self._btn_search_mode)
        search_mode_row.addStretch()
        layout.addLayout(search_mode_row)

        self._hist_list = QListWidget()
        self._hist_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._hist_list.customContextMenuRequested.connect(self._on_hist_context_menu)
        self._hist_list.itemDoubleClicked.connect(self._on_hist_double_click)
        layout.addWidget(self._hist_list, 1)

        self._refresh_history()
        return w

    def _toggle_database(self):
    # 展开/收起数据库
        visible = self._hist_sidebar.isVisible()
        self._hist_sidebar.setVisible(not visible)
        self._btn_toggle_db.setArrowType(Qt.LeftArrow if not visible else Qt.RightArrow)
        self._btn_toggle_db.setToolTip("收起数据库" if not visible else "展开数据库")

    def _build_left_panel(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(4)

        # 目录选择
        dir_row = QHBoxLayout()
        self._dir_edit = QLineEdit()
        self._dir_edit.setPlaceholderText("选择音频文件所在目录...")
        self._dir_edit.setText(self._current_dir)
        self._dir_edit.editingFinished.connect(self._on_dir_edited)
        btn_browse = QPushButton("浏览...")
        btn_browse.clicked.connect(self._browse_dir)
        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(self._refresh_files)
        dir_row.addWidget(self._dir_edit, 1)
        dir_row.addWidget(btn_browse)
        dir_row.addWidget(btn_refresh)
        layout.addLayout(dir_row)

        # 元数据文本 + 元数据字段
        text_and_id_row = QHBoxLayout()

        # 左侧：元数据文本
        txt_grp = QGroupBox("元数据文本")
        txt_layout = QVBoxLayout(txt_grp)
        txt_layout.setContentsMargins(4, 8, 4, 4)
        self._text_editor = QPlainTextEdit()
        self._text_editor.setPlaceholderText(
            "在此粘贴/编辑 key=value 格式的元数据...\nartist=X\ntitle=Y\n0=Track 1\n1=Track 2"
        )
        self._text_editor.textChanged.connect(self._schedule_auto_parse)
        self._parse_timer_id = None
        self._syncing = False
        txt_layout.addWidget(self._text_editor)
        text_and_id_row.addWidget(txt_grp, 2)

        # 右侧：元数据字段
        id_grp = QGroupBox("元数据字段")
        id_layout = QVBoxLayout(id_grp)
        id_layout.setContentsMargins(4, 8, 4, 4)

        # 行1: 品番  Disc ID
        id_row1 = QHBoxLayout()
        id_row1.addWidget(QLabel("碟编号:"))
        self._catalog_id_edit = QLineEdit()
        self._catalog_id_edit.setPlaceholderText("例: LACM-12345")
        self._catalog_id_edit.editingFinished.connect(self._on_id_field_edited)
        id_row1.addWidget(self._catalog_id_edit, 2)
        id_row1.addWidget(QLabel("Disc ID:"))
        self._disc_id_edit = QLineEdit()
        self._disc_id_edit.setPlaceholderText("MusicBrainz disc ID")
        self._disc_id_edit.editingFinished.connect(self._on_id_field_edited)
        id_row1.addWidget(self._disc_id_edit, 3)
        id_layout.addLayout(id_row1)

        # 行2: 专辑名
        id_row2 = QHBoxLayout()
        id_row2.addWidget(QLabel("专辑名:"))
        self._album_edit = QLineEdit()
        self._album_edit.editingFinished.connect(self._on_id_field_edited)
        id_row2.addWidget(self._album_edit)
        id_layout.addLayout(id_row2)

        # 行3: 专辑艺术家
        id_row3 = QHBoxLayout()
        id_row3.addWidget(QLabel("艺术家:"))
        self._artist_edit = QLineEdit()
        self._artist_edit.editingFinished.connect(self._on_id_field_edited)
        id_row3.addWidget(self._artist_edit)
        id_layout.addLayout(id_row3)

        text_and_id_row.addWidget(id_grp, 3)

        layout.addLayout(text_and_id_row, 2)

        # 底部字段行
        bottom_row = QHBoxLayout()
        bottom_row.addStretch(1)

        self._btn_disc_toggle = QPushButton("碟号/总碟数")
        self._btn_disc_toggle.setCheckable(True)
        self._btn_disc_toggle.clicked.connect(self._toggle_disc_edit)
        bottom_row.addWidget(self._btn_disc_toggle)

        self._disc_number_edit = QLineEdit()
        self._disc_number_edit.setPlaceholderText("碟号")
        self._disc_number_edit.setMaximumWidth(40)
        self._disc_number_edit.setEnabled(False)
        self._disc_number_edit.editingFinished.connect(self._on_id_field_edited)
        bottom_row.addWidget(self._disc_number_edit)

        bottom_row.addWidget(QLabel("/"))

        self._total_discs_edit = QLineEdit()
        self._total_discs_edit.setPlaceholderText("总碟")
        self._total_discs_edit.setMaximumWidth(40)
        self._total_discs_edit.setEnabled(False)
        self._total_discs_edit.editingFinished.connect(self._on_id_field_edited)
        bottom_row.addWidget(self._total_discs_edit)

        bottom_row.addWidget(QLabel("年份:"))
        self._year_edit = QLineEdit()
        self._year_edit.setMaximumWidth(70)
        self._year_edit.setMinimumWidth(40)
        self._year_edit.editingFinished.connect(self._on_id_field_edited)
        bottom_row.addWidget(self._year_edit)

        bottom_row.addWidget(QLabel("曲数:"))
        self._ntracks_edit = QLineEdit()
        self._ntracks_edit.setMaximumWidth(56)
        self._ntracks_edit.setMinimumWidth(36)
        self._ntracks_edit.editingFinished.connect(self._on_ntracks_edited)
        bottom_row.addWidget(self._ntracks_edit)

        bottom_row.addWidget(QLabel("封面:"))
        self._cover_edit = QLineEdit()
        self._cover_edit.setReadOnly(True)
        bottom_row.addWidget(self._cover_edit, 2)
        btn_cover = QPushButton("选择封面")
        btn_cover.clicked.connect(self._browse_cover)
        bottom_row.addWidget(btn_cover)
        bottom_row.addStretch(1)
        layout.addLayout(bottom_row)

        # 曲目列表
        tbl_grp = QGroupBox("曲目列表")
        tbl_layout = QVBoxLayout(tbl_grp)
        tbl_layout.setContentsMargins(4, 8, 4, 4)
        self._track_table = QTableWidget()
        self._track_table.setColumnCount(4)
        self._track_table.setHorizontalHeaderLabels(["#", "曲目标题", "轨艺术家", "文件"])

        # 砍掉水平滚动条，迫使 Qt 在视口内完成计算
        self._track_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        hdr = self._track_table.horizontalHeader()
        hdr.setMinimumSectionSize(40)
        hdr.setStretchLastSection(False)  # 禁止 Qt 默认拉伸最后一列

        hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        self._track_table.setColumnWidth(0, 34)
        hdr.setSectionResizeMode(1, QHeaderView.Interactive)
        hdr.setSectionResizeMode(2, QHeaderView.Interactive)
        hdr.setSectionResizeMode(3, QHeaderView.Interactive)

        hdr.sectionResized.connect(self._on_track_col_resized)
        self._track_resizing = False
        self._track_ratios = [0.55, 0.30, 0.15]  # 三列当前比例

        # 注册事件过滤器，接管窗口缩放
        self._track_table.viewport().installEventFilter(self)

        self._track_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._track_table.setEditTriggers(QAbstractItemView.CurrentChanged)
        self._track_delegate = TrackDelegate()
        self._track_table.setItemDelegate(self._track_delegate)
        self._track_delegate.editingTextChanged.connect(self._on_table_editing)
        tbl_layout.addWidget(self._track_table)
        layout.addWidget(tbl_grp, 3)

        # 操作按钮行
        btn_row = QHBoxLayout()
        btn_write = QPushButton("写入标签")
        btn_write.clicked.connect(self._write_tags)
        btn_export_json = QPushButton("保存数据")
        btn_export_json.clicked.connect(self._export_json)
        btn_export_txt = QPushButton("导出 txt")
        btn_export_txt.clicked.connect(self._export_txt)
        btn_row.addWidget(btn_write)
        btn_row.addWidget(btn_export_json)
        btn_row.addWidget(btn_export_txt)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        return w

    def _build_right_panel(self):
        # 右侧面板容器：tab + 主题按钮（角标）
        w = QWidget()
        w.setMinimumWidth(280)
        w.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._tool_tabs = QTabWidget()
        self._theme_btn = QPushButton()
        self._theme_btn.setFixedSize(36, 28)
        self._theme_btn.setToolTip("切换暗/亮主题")
        self._theme_btn.clicked.connect(self._toggle_theme)
        self._tool_tabs.setCornerWidget(self._theme_btn, Qt.TopRightCorner)

        # CD tab
        self._cd_tab = QWidget()
        cd_layout = QVBoxLayout(self._cd_tab)
        cd_layout.setContentsMargins(4, 8, 4, 4)
        self._cd_status = QLabel("未检测到 CD")
        cd_layout.addWidget(self._cd_status)
        self._cd_result_text = QTextEdit()
        self._cd_result_text.setReadOnly(True)
        self._cd_result_text.setLineWrapMode(QTextEdit.WidgetWidth)
        self._cd_result_text.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self._cd_result_text.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        cd_layout.addWidget(self._cd_result_text, 1)
        cd_btn_row = QHBoxLayout()
        btn_cd_read = QPushButton("读取 CD")
        btn_cd_read.clicked.connect(self._cd_read)
        btn_cd_fill = QPushButton("导入编辑器")
        btn_cd_fill.clicked.connect(self._cd_fill)
        self._btn_cd_match = QPushButton("匹配缓存")
        self._btn_cd_match.clicked.connect(self._cd_match_cache)
        self._btn_cd_match.hide()
        btn_mb_settings = QPushButton("MB 设置")
        btn_mb_settings.clicked.connect(self._musicbrainz_settings)
        cd_btn_row.addWidget(btn_cd_read)
        cd_btn_row.addWidget(btn_cd_fill)
        cd_btn_row.addWidget(self._btn_cd_match)
        cd_btn_row.addWidget(btn_mb_settings)
        cd_layout.addLayout(cd_btn_row)
        self._tool_tabs.addTab(self._cd_tab, "CD 读取")

        # AI tab
        self._ai_tab = QWidget()
        ai_layout = QVBoxLayout(self._ai_tab)
        ai_layout.setContentsMargins(4, 8, 4, 4)
        ai_layout.addWidget(QLabel("输入文本或拖入图片:"))
        self._ai_text = QPlainTextEdit()
        self._ai_text.setPlaceholderText("描述专辑信息，AI 会提取元数据...")
        self._ai_text.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        ai_layout.addWidget(self._ai_text, 2)
        # 图片拖放区
        self._image_area = QLabel("将图片拖放到此处 (可选)")
        self._image_area.setAlignment(Qt.AlignCenter)
        self._image_area.setMinimumHeight(50)
        self._image_area.setMaximumHeight(60)
        self._image_area.setStyleSheet("border: 2px dashed #585b70; border-radius: 6px;")
        self._image_area.setAcceptDrops(True)
        self._image_area.dragEnterEvent = self._on_image_drag_enter
        self._image_area.dropEvent = self._on_image_drop
        ai_layout.addWidget(self._image_area)
        self._dropped_images: list[bytes] = []
        # 提供商和模型
        ai_settings_row = QHBoxLayout()
        ai_settings_row.addStretch()
        btn_ai_settings = QPushButton("AI 设置")
        btn_ai_settings.clicked.connect(self._manage_providers)
        ai_settings_row.addWidget(btn_ai_settings)
        ai_layout.addLayout(ai_settings_row)

        ai_form = QFormLayout()
        self._provider_combo = QComboBox()
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        ai_form.addRow("提供商:", self._provider_combo)
        self._model_combo = QComboBox()
        ai_form.addRow("模型:", self._model_combo)
        ai_layout.addLayout(ai_form)
        self._refresh_providers()
        btn_extract = QPushButton("AI 提取")
        btn_extract.clicked.connect(self._ai_extract)
        ai_layout.addWidget(btn_extract)
        self._tool_tabs.addTab(self._ai_tab, "AI 提取")

        self._build_vgmdb_tab()

        layout.addWidget(self._tool_tabs, 1)
        return w

    def _build_vgmdb_tab(self):
    # VGMdb tab：浏览器 MHTML + 本地解析
        self._vgmdb_tab = QWidget()
        layout = QVBoxLayout(self._vgmdb_tab)
        layout.setContentsMargins(4, 8, 4, 4)
        layout.setSpacing(4)

        # 状态标签
        self._vgmdb_status = QLabel(
            "找到专辑页 → 保存mhtml → 解析")
        layout.addWidget(self._vgmdb_status)

        # 输入 + 浏览器打开 行
        url_row = QHBoxLayout()
        self._vgmdb_input = QLineEdit()
        self._vgmdb_input.setPlaceholderText(
            "品番或关键词（用于在浏览器中搜索 VGMdb）")
        self._vgmdb_input.returnPressed.connect(self._vgmdb_open_browser)
        url_row.addWidget(self._vgmdb_input, 1)
        btn_browser = QPushButton("浏览器打开")
        btn_browser.setToolTip("在默认浏览器中搜索 VGMdb")
        btn_browser.clicked.connect(self._vgmdb_open_browser)
        url_row.addWidget(btn_browser)
        layout.addLayout(url_row)

        # 结果显示区
        self._vgmdb_result_text = QTextEdit()
        self._vgmdb_result_text.setReadOnly(True)
        self._vgmdb_result_text.setLineWrapMode(QTextEdit.WidgetWidth)
        self._vgmdb_result_text.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self._vgmdb_result_text.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        layout.addWidget(self._vgmdb_result_text, 1)

        # 语言选择行（多语言时显示，初始隐藏）
        self._vgmdb_lang_row = QHBoxLayout()
        self._vgmdb_lang_label = QLabel("语言:")
        self._vgmdb_lang_combo = QComboBox()
        self._vgmdb_lang_combo.currentIndexChanged.connect(self._on_vgmdb_lang_changed)
        self._vgmdb_lang_row.addWidget(self._vgmdb_lang_label)
        self._vgmdb_lang_row.addWidget(self._vgmdb_lang_combo)
        self._vgmdb_lang_row.addStretch()
        layout.addLayout(self._vgmdb_lang_row)
        self._vgmdb_lang_label.hide()
        self._vgmdb_lang_combo.hide()

        # 按钮行
        btn_row = QHBoxLayout()
        btn_load = QPushButton("加载文件")
        btn_load.setToolTip("加载浏览器保存的 MHTML/HTML 文件，解析后自动删除")
        btn_load.clicked.connect(self._vgmdb_load_file)
        btn_fill = QPushButton("填充")
        btn_fill.clicked.connect(self._vgmdb_fill)
        btn_ai = QPushButton("AI 提取")
        btn_ai.setToolTip("将 VGMdb 元数据发送到 AI 提取标签页")
        btn_ai.clicked.connect(self._vgmdb_send_to_ai)
        btn_row.addWidget(btn_load)
        btn_row.addWidget(btn_fill)
        btn_row.addWidget(btn_ai)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._tool_tabs.addTab(self._vgmdb_tab, "VGMdb")


    def _apply_theme(self):
        theme_name = get_config(self._data, 'theme', 'dark')
        app = QApplication.instance()
        app.setStyleSheet(get_theme(theme_name))
        if hasattr(self, '_theme_btn'):
            self._theme_btn.setText('\u263e' if theme_name == 'light' else '\u2600')
        self._update_disc_disabled_style()

    def _update_disc_disabled_style(self):
        if not hasattr(self, '_disc_number_edit'):
            return
        theme = get_config(self._data, 'theme', 'dark')
        bg = '#3d3d3d' if theme == 'dark' else '#f0f0f0'
        style = f'QLineEdit:disabled {{ background: {bg}; }}'
        self._disc_number_edit.setStyleSheet(style)
        self._total_discs_edit.setStyleSheet(style)

    def _toggle_theme(self):
        cur = get_config(self._data, 'theme', 'dark')
        new = 'light' if cur == 'dark' else 'dark'
        ds_set_config(self._data, 'theme', new)
        save_data(self._data)
        self._apply_theme()


    def _browse_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择音频目录", self._current_dir)
        if dir_path:
            self._current_dir = dir_path
            self._dir_edit.setText(dir_path)
            ds_set_config(self._data, "last_directory", dir_path)
            save_data(self._data)
            self._auto_detect()

    def _on_dir_edited(self):
        path = self._dir_edit.text().strip()
        if path and os.path.isdir(path):
            self._current_dir = path
            ds_set_config(self._data, "last_directory", path)
            save_data(self._data)
            self._auto_detect()

    def _refresh_files(self):
        if self._current_dir:
            self._auto_detect()

    def _auto_detect(self):
    # 检测目录下的音频文件和封面
        # 封面
        cover = find_cover(self._current_dir)
        if cover:
            self._cover_edit.setText(os.path.basename(cover))
            self._current_album.cover_path = cover

        # 音频文件
        audio_files = get_audio_files(self._current_dir)
        self._status.showMessage(f"检测到 {len(audio_files)} 个音频文件")

        # 填充曲目列表的文件列
        table = self._track_table
        for row in range(table.rowCount()):
            if row < len(audio_files):
                item = table.item(row, 3)
                if not item:
                    item = QTableWidgetItem()
                    table.setItem(row, 3, item)
                item.setText(os.path.basename(audio_files[row]))


    def _schedule_auto_parse(self):
    # 300ms 后自动解析
        if self._parse_timer_id is not None:
            self.killTimer(self._parse_timer_id)
        self._parse_timer_id = self.startTimer(150)

    def timerEvent(self, event):
    # 定时器触发：自动解析
        if self._parse_timer_id and event.timerId() == self._parse_timer_id:
            self.killTimer(self._parse_timer_id)
            self._parse_timer_id = None
            self._parse_text()

    def _parse_text(self):
        text = self._text_editor.toPlainText().strip()
        if not text:
            return
        self._current_album = parse(text)
        self._fill_fields()

    def _fill_fields(self):
        if self._syncing:
            return
        self._syncing = True
        try:
            self._fill_fields_impl()
        finally:
            self._syncing = False

    def _fill_fields_impl(self):
        a = self._current_album
        self._album_edit.setText(a.title)
        self._artist_edit.setText(a.artist)
        self._year_edit.setText(a.year)
        self._ntracks_edit.setText(str(a.num_tracks) if a.num_tracks else '')
        if a.cover_path:
            self._cover_edit.setText(os.path.basename(a.cover_path))
        self._catalog_id_edit.setText(a.catalog_id)
        self._disc_id_edit.setText(a.disc_id)
        self._disc_number_edit.setText(a.disc_number)
        self._total_discs_edit.setText(a.total_discs)

        # 填充曲目列表
        table = self._track_table
        table.setRowCount(max(len(a.tracks), a.num_tracks))
        for i, t in enumerate(a.tracks):
            # 轨号
            num_item = QTableWidgetItem(str(t.num + 1))
            num_item.setFlags(num_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(i, 0, num_item)
            # 标题
            table.setItem(i, 1, QTableWidgetItem(t.title))
            # 轨艺术家
            table.setItem(i, 2, QTableWidgetItem(t.track_artist))
            # 文件（保留已有）
            existing = table.item(i, 3)
            if not existing or not existing.text():
                table.setItem(i, 3, QTableWidgetItem(t.file_path if t.file_path else ''))

        # 自动匹配音频文件
        self._auto_detect()


    def _toggle_disc_edit(self):
        enabled = self._btn_disc_toggle.isChecked()
        self._disc_number_edit.setEnabled(enabled)
        self._total_discs_edit.setEnabled(enabled)
        self._update_disc_disabled_style()


    def _on_id_field_edited(self):
    # ID 面板编辑 → 同步到元数据文本
        if self._syncing:
            return
        self._syncing = True
        try:
            album = self._gather_album()
            self._current_album = album
            self._text_editor.setPlainText(format_album(album))
        finally:
            self._syncing = False


    def _on_ntracks_edited(self):
    # 曲目数变更 → 刷新表格行
        try:
            n = int(self._ntracks_edit.text().strip())
        except ValueError:
            return
        table = self._track_table
        table.setRowCount(n)
        for row in range(n):
            num_item = table.item(row, 0)
            if not num_item:
                num_item = QTableWidgetItem(str(row + 1))
                num_item.setFlags(num_item.flags() & ~Qt.ItemIsEditable)
                table.setItem(row, 0, num_item)
        self._on_id_field_edited()

    def _on_table_editing(self, row, col, text):
    # 曲目编辑实时同步
        if self._syncing or col not in (1, 2):
            return
        self._syncing = True
        try:
            item = self._track_table.item(row, col)
            if item:
                item.setText(text)
            album = self._gather_album()
            self._current_album = album
            self._text_editor.setPlainText(format_album(album))
        finally:
            self._syncing = False


    def _browse_cover(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择封面图片", self._current_dir,
            "图片 (*.jpg *.jpeg *.png)"
        )
        if path:
            self._current_album.cover_path = path
            self._cover_edit.setText(os.path.basename(path))


    def _gather_album(self) -> AlbumInfo:
        a = AlbumInfo()
        a.artist = self._artist_edit.text().strip()
        a.title = self._album_edit.text().strip()
        a.year = self._year_edit.text().strip()
        try:
            a.num_tracks = int(self._ntracks_edit.text().strip())
        except ValueError:
            a.num_tracks = 0
        a.cover_path = self._current_album.cover_path
        a.disc_id = self._disc_id_edit.text().strip()
        a.catalog_id = self._catalog_id_edit.text().strip()
        a.disc_number = self._disc_number_edit.text().strip()
        a.total_discs = self._total_discs_edit.text().strip()
        a.source = self._current_album.source

        table = self._track_table
        for row in range(table.rowCount()):
            title = table.item(row, 1)
            t_artist = table.item(row, 2)
            file_item = table.item(row, 3)
            if title:
                a.tracks.append(TrackInfo(
                    num=row,
                    title=title.text().strip(),
                    track_artist=t_artist.text().strip() if t_artist else '',
                    file_path=file_item.text().strip() if file_item else '',
                ))
        return a


    def _write_tags(self):
        if not self._current_dir:
            QMessageBox.warning(self, "错误", "请先选择目录")
            return
        album = self._gather_album()
        if not album.tracks:
            QMessageBox.warning(self, "错误", "没有曲目数据")
            return

        audio_files = get_audio_files(self._current_dir)
        file_map = {os.path.basename(f): f for f in audio_files}

        count_ok = count_fail = 0
        for t in album.tracks:
            file_path = ''
            if t.file_path:
                file_path = os.path.join(self._current_dir, t.file_path)
            if not os.path.isfile(file_path):
                # 尝试按索引匹配
                if t.num < len(audio_files):
                    file_path = audio_files[t.num]
            if not file_path or not os.path.isfile(file_path):
                print(f'[写入] 未找到第 {t.num + 1} 轨的文件')
                count_fail += 1
                continue
            if write_tags(file_path, t, album, album.cover_path):
                count_ok += 1
            else:
                count_fail += 1

        print(f'[标签] 写入完成: {count_ok} 成功, {count_fail} 失败')
        self._status.showMessage(f"写入完成: {count_ok} 成功, {count_fail} 失败")
        self._refresh_files()


    def _export_json(self):
        album = self._gather_album()
        existing = find_existing_album(self._data, album)
        if existing:
            dlg = MergeDialog(existing, album.__dict__ if hasattr(album, '__dict__') else {}, self)
            dlg.exec()
            if dlg.result_choice == MergeDialog.COVER:
                update_album(self._data, existing['id'], album)
                print(f'[缓存] 已覆盖: {album.artist} - {album.title}')
            elif dlg.result_choice == MergeDialog.MERGE:
                merged = merge_albums(existing, album)
                update_album(self._data, existing['id'],
                             self._dict_to_albuminfo(merged))
                print(f'[缓存] 已合并: {album.artist} - {album.title}')
            else:
                return
        else:
            insert_album(self._data, album)
            print(f'[缓存] 新增: {album.artist} - {album.title}')
        save_data(self._data)
        self._refresh_history()

    def _dict_to_albuminfo(self, d: dict) -> AlbumInfo:
        a = AlbumInfo()
        a.artist = d.get('artist', '')
        a.title = d.get('title', '')
        a.year = d.get('year', '')
        a.num_tracks = d.get('num_tracks', 0)
        a.cover_path = d.get('cover_path', '')
        a.disc_id = d.get('disc_id', '')
        a.catalog_id = d.get('catalog_id', '')
        a.source = d.get('source', 'manual')
        for t in d.get('tracks', []):
            a.tracks.append(TrackInfo(num=t.get('num', 0), title=t.get('title', ''),
                                       track_artist=t.get('track_artist', '')))
        return a


    def _export_txt(self):
        album = self._gather_album()
        text = format_album(album)
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cdplayer.txt')
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(text)
            print(f'[导出] cdplayer.txt 已保存到 {os.path.dirname(path)}')
        except OSError as e:
            print(f'[导出错误] {e}')


    def _musicbrainz_settings(self):
        mb_config = self._data.get('config', {}).get('musicbrainz', {})
        dlg = MusicBrainzDialog(mb_config, self)
        if dlg.exec() == QDialog.Accepted:
            ds_set_config(self._data, 'musicbrainz', mb_config)
            save_data(self._data)
            try:
                import musicbrainzngs
                musicbrainzngs.set_useragent(
                    mb_config.get('useragent', ''),
                    '',
                    mb_config.get('contact', ''),
                )
            except Exception:
                pass
            print(f'[MusicBrainz] 设置已保存')


    def _cd_read(self):
        if self._cd_busy:
            return
        self._cd_busy = True
        self._cd_status.setText("正在读取 CD...")
        self._cd_result_text.clear()
        self._cd_worker = CDWorker()
        self._cd_worker.finished.connect(self._on_cd_result)
        self._cd_worker.error.connect(self._on_cd_error)
        self._cd_worker.start()

    def _on_cd_error(self, err: str):
        self._cd_busy = False
        print(f'[CD 错误] {err}')

    def _on_cd_result(self, results):
        # results: list[dict] | None
        self._cd_busy = False
        self._cd_result = None
        self._btn_cd_match.hide()
        if results is None:
            self._cd_status.setText("未检测到 CD")
            return

        # 筛选有元数据的结果
        valid = [r for r in results if r.get('artist') and r.get('title')]

        if not valid:
            # 无在线元数据 — 尝试本地缓存
            result = results[0] if results else {'disc_id': '', 'artist': '', 'title': '', 'year': '', 'tracks': []}
            disc_id = result.get('disc_id', '')
            self._cd_result = result
            print(f'[CD] 光盘已识别 (disc_id={disc_id})，在线无匹配，查本地缓存...')
            self._cd_status.setText(f"光盘已识别 (disc_id={disc_id})，在线无匹配")
            self._cd_result_text.setPlainText(
                f"MusicBrainz Disc ID: {disc_id}\n\n在线数据库未找到此光盘的元数据。"
            )
            cached = find_existing_album(self._data, AlbumInfo(disc_id=disc_id))
            if cached:
                from data_store import _dict_to_album
                album = _dict_to_album(cached)
                text = format_album(album)
                self._text_editor.setPlainText(text)
                self._current_album.disc_id = disc_id
                self._current_album.source = 'cd'
                self._parse_text()
                print(f'[CD] 本地缓存命中: {cached["artist"]} - {cached["title"]}')
                self._cd_status.setText(f"本地缓存命中: {cached['artist']} - {cached['title']}")
                self._cd_result_text.setPlainText(
                    f"MusicBrainz Disc ID: {disc_id}\n\n在线无匹配，已从本地缓存填充:\n{cached['artist']} - {cached['title']}"
                )
            else:
                self._btn_cd_match.show()
            return

        # 有元数据：多个则让用户选择
        if len(valid) == 1:
            result = valid[0]
        else:
            result = self._cd_select_release(valid)
            if result is None:
                return

        self._cd_result = result
        disc_id = result.get('disc_id', '')
        print(f'[CD] 检测结果: {result["artist"]} - {result["title"]} ({len(result["tracks"])} 轨)')
        self._cd_status.setText(f"已检测到 CD: {result['title']} — {result['artist']} ({result.get('year', '未知')})")
        text = (f"MusicBrainz Disc ID: {disc_id}\n"
                 f"艺术家: {result['artist']}\n"
                 f"专辑: {result['title']}\n"
                 f"年份: {result.get('year', '未知')}\n"
                 f"曲目数: {len(result['tracks'])}\n")
        for t in result['tracks']:
            art = f" ({t['artist']})" if t.get('artist') else ""
            text += f"  {t['num'] + 1}. {t['title']}{art}\n"
        self._cd_result_text.setPlainText(text)

    def _cd_select_release(self, releases):
    # 选择对话框，选中时即时预览
        dialog = QDialog(self)
        dialog.setWindowTitle("选择发行版")
        dialog.setMinimumWidth(550)
        layout = QVBoxLayout(dialog)

        label = QLabel(f"MusicBrainz 返回了 {len(releases)} 个匹配结果，请选择最合适的:")
        layout.addWidget(label)

        top_row = QHBoxLayout()
        lst = QListWidget()
        for r in releases:
            year = f" ({r['year']})" if r.get('year') else ''
            n_tracks = len(r['tracks'])
            item = QListWidgetItem(f"{r['artist']} - {r['title']}{year}  [{n_tracks} 轨]")
            lst.addItem(item)
        top_row.addWidget(lst, 1)

        # 即时预览面板
        preview = QTextEdit()
        preview.setReadOnly(True)
        preview.setLineWrapMode(QTextEdit.WidgetWidth)
        preview.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        preview.setMinimumWidth(220)
        top_row.addWidget(preview, 2)

        def _update_preview(current, previous):
            if current is None:
                preview.clear()
                return
            idx = lst.row(current)
            r = releases[idx]
            lines = [f"{r['artist']} - {r['title']}"]
            if r.get('year'):
                lines[0] += f" ({r['year']})"
            lines.append("")
            for t in r['tracks']:
                art = f" [{t['artist']}]" if t.get('artist') else ''
                lines.append(f"{t['num'] + 1}. {t['title']}{art}")
            preview.setPlainText('\n'.join(lines))

        lst.currentItemChanged.connect(_update_preview)
        if lst.count():
            lst.setCurrentRow(0)
        layout.addLayout(top_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.Accepted:
            return None
        idx = lst.currentRow()
        if idx < 0:
            return None
        return releases[idx]

    def _cd_fill(self):
        if not self._cd_result:
            QMessageBox.information(self, "提示", "没有 CD 数据")
            return
        r = self._cd_result
        lines = [f"disc_id={r['disc_id']}"]
        if r.get('artist') and r.get('title'):
            lines.append(f"artist={r['artist']}")
            lines.append(f"title={r['title']}")
            lines.append(f"year={r.get('year', '')}")
            lines.append(f"numtracks={len(r['tracks'])}")
            for t in r['tracks']:
                lines.append(f"{t['num']}={t['title']}")
                if t.get('artist') and t['artist'] != r['artist']:
                    lines.append(f"{t['num']}artist={t['artist']}")
        self._text_editor.setPlainText('\n'.join(lines))
        self._current_album.disc_id = r['disc_id']
        self._current_album.source = 'cd'
        self._parse_text()

    def _cd_match_cache(self):
    # 从本地缓存匹配 CD
        albums = get_albums(self._data)
        if not albums:
            QMessageBox.information(self, "提示", "缓存中没有专辑")
            return
        albums = sorted(albums, key=lambda a: a.get('updated_at', ''), reverse=True)
        names = []
        for a in albums:
            year = a.get('year', '')
            name = f"{a['artist']} - {a['title']}"
            if year:
                name += f" ({year})"
            names.append(name)
        name, ok = QInputDialog.getItem(self, "匹配缓存", "选择与此 CD 对应的专辑:", names, 0, False)
        if not ok or not name:
            return
        idx = names.index(name)
        matched = albums[idx]
        from data_store import _dict_to_album
        album = _dict_to_album(matched)
        text = format_album(album)
        self._text_editor.setPlainText(text)
        self._current_album.disc_id = self._cd_result['disc_id']
        self._current_album.source = 'cd'
        # 将 ID 写回缓存
        matched['disc_id'] = self._cd_result['disc_id']
        save_data(self._data)
        self._refresh_history()
        self._parse_text()
        self._btn_cd_match.hide()
        print(f'[CD] 已与缓存关联: {matched["artist"]} - {matched["title"]} (disc_id={self._cd_result["disc_id"]})')


    def _vgmdb_open_browser(self):
    # 浏览器打开 VGMdb
        query = self._vgmdb_input.text().strip()
        if query:
            if query.startswith('http'):
                webbrowser.open(query)
            else:
                webbrowser.open(f'https://vgmdb.net/search?q={query}')
        else:
            webbrowser.open('https://vgmdb.net/')

    def _vgmdb_load_file(self):
    # 加载 MHTML/HTML 文件，解析后删除
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 VGMdb 文件", "",
            "MHTML/HTML 文件 (*.mhtml *.mht *.html *.htm);;所有文件 (*)"
        )
        if not path:
            return
        if self._vgmdb_busy:
            return
        self._vgmdb_busy = True
        self._vgmdb_file_path = path  # 记录以便解析后删除
        self._vgmdb_status.setText("正在解析文件...")
        self._vgmdb_result_text.clear()

        ext = os.path.splitext(path)[1].lower()
        try:
            if ext in ('.mhtml', '.mht'):
                html = parse_mhtml(path)
            else:
                with open(path, 'r', encoding='utf-8') as f:
                    html = f.read()
        except Exception as e:
            self._vgmdb_busy = False
            self._vgmdb_file_path = None
            self._vgmdb_status.setText(f"读取文件失败: {e}")
            return

        if not html:
            self._vgmdb_busy = False
            self._vgmdb_file_path = None
            self._vgmdb_status.setText("无法从文件中提取 HTML 内容")
            return

        self._vgmdb_worker = VgmdbWorker()
        self._vgmdb_worker.html = html
        self._vgmdb_worker.finished.connect(self._on_vgmdb_result)
        self._vgmdb_worker.error.connect(self._on_vgmdb_error)
        self._vgmdb_worker.start()

    def _on_vgmdb_result(self, result):
        self._vgmdb_busy = False
        self._vgmdb_result = result

        # 自动删除已加载的本地文件
        file_path = getattr(self, '_vgmdb_file_path', None)
        if file_path:
            self._vgmdb_file_path = None
            try:
                os.remove(file_path)
                print(f'[VGMdb] 已删除临时文件: {os.path.basename(file_path)}')
            except OSError:
                pass

        # 隐藏语言选择器
        self._vgmdb_lang_label.hide()
        self._vgmdb_lang_combo.hide()

        if result is None:
            self._vgmdb_status.setText("解析失败：未能从文件中提取专辑信息")
            self._vgmdb_result_text.setPlainText(
                "HTML 解析失败，请确认文件是 VGMdb 专辑页面。\n"
                "在浏览器中打开专辑页后，按 Ctrl+S 保存（选择「单个文件」格式）。"
            )
            return

        print(f'[VGMdb] 解析完成: {result["artist"]} - {result["title"]} ({len(result["tracks"])} 轨)')

        # 多语言曲目
        all_langs = result.get('track_languages', {})
        if len(all_langs) > 1:
            self._vgmdb_lang_combo.blockSignals(True)
            self._vgmdb_lang_combo.clear()
            for lang in all_langs:
                self._vgmdb_lang_combo.addItem(lang)
            # 选中与默认曲目匹配的语言（日语优先）
            default_tracks = result.get('tracks', [])
            self._vgmdb_selected_lang = None
            for lang, tracks in all_langs.items():
                if tracks == default_tracks:
                    self._vgmdb_selected_lang = lang
                    break
            if not self._vgmdb_selected_lang and all_langs:
                self._vgmdb_selected_lang = next(iter(all_langs))
            idx = self._vgmdb_lang_combo.findText(self._vgmdb_selected_lang)
            if idx >= 0:
                self._vgmdb_lang_combo.setCurrentIndex(idx)
            self._vgmdb_lang_combo.blockSignals(False)
            self._vgmdb_lang_label.show()
            self._vgmdb_lang_combo.show()
        else:
            self._vgmdb_selected_lang = next(iter(all_langs)) if all_langs else None

        self._vgmdb_show_tracks()
        self._vgmdb_status.setText(
            f"已解析: {result['title']} — {result['artist']}"
            f" ({result.get('year', '未知')})"
        )

    def _vgmdb_show_tracks(self):
    # 按选中语言更新曲目显示
        r = self._vgmdb_result
        if not r:
            return
        # 获取当前语言的曲目
        lang_name = getattr(self, '_vgmdb_selected_lang', None)
        if lang_name:
            all_langs = r.get('track_languages', {})
            tracks = all_langs.get(lang_name, r.get('tracks', []))
        else:
            tracks = r.get('tracks', [])

        # 获取当前语言的标题/艺术家
        lang_code = _vgmdb_lang_code(lang_name)
        artist = r['artist']
        title = r['title']
        if lang_code:
            artist = r.get('artist_by_lang', {}).get(lang_code, artist)
            title = r.get('title_by_lang', {}).get(lang_code, title)

        text = (f"艺术家: {artist}\n"
                f"专辑: {title}\n"
                f"年份: {r.get('year', '未知')}\n"
                f"品番: {r.get('disc_id', '')}\n"
                f"曲目数: {len(tracks)}\n")
        for t in tracks:
            art = f" [{t['artist']}]" if t.get('artist') else ''
            text += f"  {t['num'] + 1}. {t['title']}{art}\n"
        self._vgmdb_result_text.setPlainText(text)

    def _on_vgmdb_lang_changed(self, idx):
    # 语言切换 → 更新显示
        if idx < 0:
            return
        self._vgmdb_selected_lang = self._vgmdb_lang_combo.itemText(idx)
        self._vgmdb_show_tracks()

    def _on_vgmdb_error(self, err: str):
        self._vgmdb_busy = False
        self._vgmdb_file_path = None
        self._vgmdb_status.setText(f"错误: {err}")

    def _vgmdb_fill(self):
    # VGMdb 结果填充到编辑器
        if not self._vgmdb_result:
            QMessageBox.information(self, "提示", "没有 VGMdb 数据")
            return
        r = self._vgmdb_result

        # 使用当前选中语言的曲目、标题、艺术家
        lang_name = getattr(self, '_vgmdb_selected_lang', None)
        if lang_name:
            all_langs = r.get('track_languages', {})
            tracks = all_langs.get(lang_name, r.get('tracks', []))
        else:
            tracks = r.get('tracks', [])

        lang_code = _vgmdb_lang_code(lang_name)
        artist = r['artist']
        title = r['title']
        if lang_code:
            artist = r.get('artist_by_lang', {}).get(lang_code, artist)
            title = r.get('title_by_lang', {}).get(lang_code, title)

        lines = []
        if r.get('disc_id'):
            lines.append(f"catalog_id={r['disc_id']}")
        if artist:
            lines.append(f"artist={artist}")
        if title:
            lines.append(f"title={title}")
        if r.get('year'):
            lines.append(f"year={r['year']}")
        lines.append(f"numtracks={len(tracks)}")
        for t in tracks:
            if t.get('title'):
                lines.append(f"{t['num']}={t['title']}")
            if t.get('artist') and t['artist'] != artist:
                lines.append(f"{t['num']}artist={t['artist']}")
        self._text_editor.setPlainText('\n'.join(lines))
        self._current_album.catalog_id = r.get('disc_id', '')
        self._current_album.source = 'vgmdb'
        self._parse_text()

    def _vgmdb_send_to_ai(self):
    # VGMdb 数据发送到 AI
        if not self._vgmdb_result:
            QMessageBox.information(self, "提示", "请先加载并解析 VGMdb 文件")
            return
        r = self._vgmdb_result

        # 获取当前语言的曲目
        lang_name = getattr(self, '_vgmdb_selected_lang', None)
        if lang_name:
            all_langs = r.get('track_languages', {})
            tracks = all_langs.get(lang_name, r.get('tracks', []))
        else:
            tracks = r.get('tracks', [])

        lines = []
        lines.append("【专辑基本信息】")
        lines.append(f"艺术家: {r['artist']}")
        lines.append(f"专辑: {r['title']}")
        if r.get('year'):
            lines.append(f"年份: {r['year']}")

        # Release / Media / Supplementary Information
        meta = r.get('raw_meta', {})
        release_keys = ['Catalog Number', 'Release Date', 'Release Price',
                        'Publish Format', 'Barcode', 'Label', 'Manufacturer',
                        'Distributor', 'Phonographic Copyright', 'Publisher']
        media_keys = ['Media Format']
        other_keys = [k for k in meta if k not in release_keys
                      and k not in media_keys and k != 'Classification']

        if any(k in meta for k in release_keys):
            lines.append("\n【Release Information】")
            for k in release_keys:
                if k in meta:
                    lines.append(f"{k}: {meta[k]}")

        if any(k in meta for k in media_keys):
            lines.append("\n【Media Information】")
            for k in media_keys:
                if k in meta:
                    lines.append(f"{k}: {meta[k]}")

        if 'Classification' in meta:
            lines.append(f"\n【Classification】\n{meta['Classification']}")

        if other_keys:
            lines.append("\n【Supplementary Information】")
            for k in other_keys:
                lines.append(f"{k}: {meta[k]}")

        lines.append(f"\n【曲目列表】({len(tracks)} 轨)")
        for t in tracks:
            art = f" [{t['artist']}]" if t.get('artist') else ''
            lines.append(f"{t['num'] + 1}. {t['title']}{art}")

        # Notes（含单曲艺术家/作词/作曲等）
        notes = r.get('notes', '')
        if notes:
            lines.append(f"\n【Notes】\n{notes}")

        # 填充到 AI 输入框并切换标签页
        self._ai_text.setPlainText('\n'.join(lines))
        self._tool_tabs.setCurrentWidget(self._ai_tab)


    def _on_image_drag_enter(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def _on_image_drop(self, event: QDropEvent):
        self._dropped_images = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isfile(path) and path.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                try:
                    with open(path, 'rb') as f:
                        self._dropped_images.append(f.read())
                except OSError as e:
                    print(f'[AI] 读取图片失败: {e}')
        self._image_area.setText(f"已加载 {len(self._dropped_images)} 张图片")

    def _refresh_providers(self):
        self._provider_combo.blockSignals(True)
        self._provider_combo.clear()
        providers = get_config(self._data, 'providers', [])
        for p in providers:
            self._provider_combo.addItem(p['name'])
        self._provider_combo.blockSignals(False)
        if self._provider_combo.count():
            self._provider_combo.setCurrentIndex(0)
            self._on_provider_changed(0)

    def _on_provider_changed(self, idx):
        providers = get_config(self._data, 'providers', [])
        if 0 <= idx < len(providers):
            self._model_combo.clear()
            p = providers[idx]
            models = p.get('models', [])
            if not models:
                fallback = {
                    'DeepSeek': ['deepseek-v4-pro', 'deepseek-v4-flash', 'deepseek-reasoner', 'deepseek-chat'],
                    '通义千问': ['qwen3.5-flash', 'qwen3.5-plus', 'qwen3.6-plus'],
                    'OpenAI': [],
                }
                models = fallback.get(p['name'], [])
            for m in models:
                self._model_combo.addItem(m)
            if self._model_combo.count():
                self._model_combo.setCurrentIndex(0)

    def _ai_extract(self):
        if self._ai_busy:
            return
        providers = get_config(self._data, 'providers', [])
        idx = self._provider_combo.currentIndex()
        if idx < 0 or idx >= len(providers):
            QMessageBox.warning(self, "错误", "请选择提供商")
            return
        p = providers[idx]
        token = p.get('token', '')
        if not token:
            QMessageBox.warning(self, "错误", f"请为 {p['name']} 设置 API Token")
            return

        text = self._ai_text.toPlainText().strip()
        if not text and not self._dropped_images:
            QMessageBox.warning(self, "错误", "请输入文本或拖入图片")
            return

        self._ai_busy = True
        self._status.showMessage("AI 提取中...")
        self._ai_worker = AIWorker(
            p['endpoint'], token, self._model_combo.currentText().strip(),
            text, self._dropped_images
        )
        self._ai_worker.finished.connect(self._on_ai_result)
        self._ai_worker.error.connect(self._on_ai_error)
        self._ai_worker.start()

    def _on_ai_result(self, result: str):
        self._ai_busy = False
        print(f'[AI] 提取完成，返回 {len(result)} 字符')
        self._text_editor.setPlainText(result)
        self._current_album.source = 'ai'
        self._status.showMessage("AI 提取完成")
        self._parse_text()

    def _on_ai_error(self, err: str):
        self._ai_busy = False
        print(f'[AI 错误] {err}')
        self._status.showMessage(f"AI 提取失败: {err}")


    def _refresh_history(self):
        self._hist_list.clear()
        albums = get_albums(self._data)
        query = self._hist_search.text().strip() if hasattr(self, '_hist_search') else ''
        deep = getattr(self, '_search_deep', False)
        if query:
            if deep:
                albums = _search_albums_deep(albums, query)
            else:
                albums = search_albums(self._data, query)
        # 按时间倒序
        albums = sorted(albums, key=lambda a: a.get('updated_at', ''), reverse=True)
        for a in albums:
            year = a.get('year', '')
            display = f"{a['title']}"
            if year:
                display += f" ({year})"
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, a.get('id'))
            ttip = f"{a.get('artist', '')} - {a['title']}"
            if year:
                ttip += f" ({year})"
            if a.get('disc_id'):
                ttip += f"\ndisc_id: {a['disc_id']}"
            if a.get('catalog_id'):
                ttip += f"\ncatalog_id: {a['catalog_id']}"
            if a.get('disc_number'):
                ttip += f"\n碟号: {a['disc_number']}"
            if a.get('total_discs'):
                ttip += f"\n总碟数: {a['total_discs']}"
            if a.get('source'):
                ttip += f"\n来源: {a['source']}"
            item.setToolTip(ttip)
            self._hist_list.addItem(item)

    def _on_hist_search_mode(self):
    # 搜索模式切换
        self._search_deep = not getattr(self, '_search_deep', False)
        if self._search_deep:
            self._btn_search_mode.setText("ID")
            self._btn_search_mode.setToolTip("搜索模式：全部字段（含 ID、曲目等）— 点击切换")
        else:
            self._btn_search_mode.setText("Aa")
            self._btn_search_mode.setToolTip("搜索模式：仅艺术家/专辑名 — 点击切换")
        self._refresh_history()

    def _on_hist_search(self, text: str):
        self._refresh_history()

    def _on_hist_double_click(self, item: QListWidgetItem):
        album_id = item.data(Qt.UserRole)
        albums = get_albums(self._data)
        for a in albums:
            if a.get('id') == album_id:
                # 填充文本编辑器
                from data_store import _dict_to_album
                album = _dict_to_album(a)
                text = format_album(album)
                self._text_editor.setPlainText(text)
                self._current_album.disc_id = a.get('disc_id', '')
                self._current_album.catalog_id = a.get('catalog_id', '')
                self._current_album.source = a.get('source', 'manual')
                self._parse_text()
                return

    def _on_hist_context_menu(self, pos):
        item = self._hist_list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        act_delete = menu.addAction("删除")
        action = menu.exec(self._hist_list.mapToGlobal(pos))
        if action == act_delete:
            album_id = item.data(Qt.UserRole)
            delete_album(self._data, album_id)
            save_data(self._data)
            self._refresh_history()


    def _restore_geometry(self):
        geo = get_config(self._data, 'window_geometry', '')
        if geo:
            try:
                self.restoreGeometry(bytes.fromhex(geo))
            except Exception:
                self.resize(1280, 780)

    def _save_geometry(self):
        ds_set_config(self._data, 'window_geometry', self.saveGeometry().toHex().data().decode())
        save_data(self._data)

    def eventFilter(self, obj, event):
    # 窗口缩放 → 重绘表格列宽
        if hasattr(self, '_track_table') and obj == self._track_table.viewport():
            if event.type() == event.Type.Resize:
                self._apply_track_ratios()
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        self._log_handler.uninstall()
        self._save_geometry()
        super().closeEvent(event)

    def _open_data_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "打开 data.json", "", "JSON (*.json)"
        )
        if path:
            try:
                import json
                with open(path, 'r', encoding='utf-8') as f:
                    self._data.update(json.load(f))
                save_data(self._data)
                self._refresh_history()
                self._refresh_providers()
                print(f'[配置] 已导入: {path}')
            except Exception as e:
                print(f'[配置错误] 导入失败: {e}')

    def _manage_providers(self):
        providers = get_config(self._data, 'providers', [])
        dlg = ProviderDialog(providers, self)
        dlg.exec()
        ds_set_config(self._data, 'providers', providers)
        save_data(self._data)
        self._refresh_providers()



def main():
    import sys
    app = QApplication(sys.argv)
    app.setApplicationName("标签导入V2.0")

    window = FlacTaggerApp()
    window.show()

    skip_welcome = get_config(window._data, 'skip_welcome', False)
    if not skip_welcome:
        def _show_welcome():
            dlg = WelcomeDialog(window)
            dlg.exec()
            if dlg._dont_show:
                data = load_data()
                ds_set_config(data, 'skip_welcome', True)
                save_data(data)
        QTimer.singleShot(800, _show_welcome)

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
