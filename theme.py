DARK = """
QMainWindow, QDialog { background-color: #1e1e2e; color: #cdd6f4; }
QMenuBar { background-color: #181825; color: #cdd6f4; border-bottom: 1px solid #313244; }
QMenuBar::item:selected { background-color: #313244; }
QMenu { background-color: #1e1e2e; color: #cdd6f4; border: 1px solid #313244; }
QMenu::item:selected { background-color: #45475a; }
QLabel { color: #cdd6f4; }
QPushButton {
    background-color: #45475a; color: #cdd6f4;
    border: 1px solid #585b70; padding: 6px 14px; border-radius: 4px;
}
QPushButton:hover { background-color: #585b70; }
QPushButton:pressed { background-color: #313244; }
QPushButton:disabled { background-color: #313244; color: #6c7086; }
QToolButton {
    background-color: #45475a; color: #cdd6f4;
    border: 1px solid #585b70; border-radius: 4px;
}
QToolButton:hover { background-color: #585b70; }
QToolButton:checked {
    background-color: #89b4fa; color: #1e1e2e;
    border-color: #89b4fa;
}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox {
    background-color: #313244; color: #cdd6f4;
    border: 1px solid #45475a; border-radius: 4px; padding: 4px;
    selection-background-color: #89b4fa; selection-color: #1e1e2e;
}
QTableWidget {
    background-color: #313244; color: #cdd6f4;
    gridline-color: #45475a; border: 1px solid #45475a; border-radius: 4px;
}
QTableWidget::item:selected { background-color: #89b4fa; color: #1e1e2e; }
QHeaderView::section {
    background-color: #45475a; color: #cdd6f4;
    border: 1px solid #585b70; padding: 4px;
}
QTableCornerButton::section {
    background-color: #45475a;
    border: 1px solid #585b70;
}
QTabWidget::pane { border: 1px solid #45475a; background-color: #2a2a3c; }
QTabBar::tab {
    background-color: #313244; color: #cdd6f4;
    padding: 6px 14px; border: 1px solid #45475a; border-bottom: none;
}
QTabBar::tab:selected { background-color: #2a2a3c; border-bottom: 2px solid #89b4fa; }
QListWidget {
    background-color: #313244; color: #cdd6f4;
    border: 1px solid #45475a; border-radius: 4px;
}
QListWidget::item:selected { background-color: #89b4fa; color: #1e1e2e; }
QGroupBox {
    color: #cdd6f4; border: 1px solid #45475a; border-radius: 6px;
    margin-top: 14px; padding-top: 16px; font-weight: bold;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
QScrollBar:vertical {
    background-color: #1e1e2e; width: 10px; border-radius: 5px;
}
QScrollBar::handle:vertical {
    background-color: #585b70; border-radius: 5px; min-height: 30px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QSplitter::handle { background-color: #45475a; }
QStatusBar { background-color: #181825; color: #a6adc8; }
QComboBox {
    background-color: #313244; color: #cdd6f4;
    border: 1px solid #45475a; border-radius: 4px; padding: 4px 8px;
}
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView {
    background-color: #313244; color: #cdd6f4;
    border: 1px solid #45475a; selection-background-color: #89b4fa;
    selection-color: #1e1e2e;
}
"""

LIGHT = """
QMainWindow, QDialog { background-color: #eff1f5; color: #4c4f69; }
QMenuBar { background-color: #e6e9ef; color: #4c4f69; border-bottom: 1px solid #ccd0da; }
QMenuBar::item:selected { background-color: #ccd0da; }
QMenu { background-color: #eff1f5; color: #4c4f69; border: 1px solid #ccd0da; }
QMenu::item:selected { background-color: #1e66f5; color: #eff1f5; }
QLabel { color: #4c4f69; }
QPushButton {
    background-color: #ccd0da; color: #4c4f69;
    border: 1px solid #bcc0cc; padding: 6px 14px; border-radius: 4px;
}
QPushButton:hover { background-color: #bcc0cc; }
QPushButton:pressed { background-color: #1e66f5; color: #eff1f5; }
QPushButton:disabled { background-color: #e6e9ef; color: #acb0be; }
QToolButton {
    background-color: #ccd0da; color: #4c4f69;
    border: 1px solid #bcc0cc; border-radius: 4px;
}
QToolButton:hover { background-color: #bcc0cc; }
QToolButton:checked {
    background-color: #1e66f5; color: #ffffff;
    border-color: #1e66f5;
}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox {
    background-color: #ffffff; color: #4c4f69;
    border: 1px solid #ccd0da; border-radius: 4px; padding: 4px;
    selection-background-color: #1e66f5; selection-color: #ffffff;
}
QTableWidget {
    background-color: #ffffff; color: #4c4f69;
    gridline-color: #ccd0da; border: 1px solid #ccd0da; border-radius: 4px;
}
QTableWidget::item:selected { background-color: #1e66f5; color: #ffffff; }
QHeaderView::section {
    background-color: #e6e9ef; color: #4c4f69;
    border: 1px solid #ccd0da; padding: 4px;
}
QTableCornerButton::section {
    background-color: #e6e9ef;
    border: 1px solid #ccd0da;
}
QTabWidget::pane { border: 1px solid #ccd0da; background-color: #eff1f5; }
QTabBar::tab {
    background-color: #e6e9ef; color: #4c4f69;
    padding: 6px 14px; border: 1px solid #ccd0da; border-bottom: none;
}
QTabBar::tab:selected { background-color: #eff1f5; border-bottom: 2px solid #1e66f5; }
QListWidget {
    background-color: #ffffff; color: #4c4f69;
    border: 1px solid #ccd0da; border-radius: 4px;
}
QListWidget::item:selected { background-color: #1e66f5; color: #ffffff; }
QGroupBox {
    color: #4c4f69; border: 1px solid #ccd0da; border-radius: 6px;
    margin-top: 14px; padding-top: 16px; font-weight: bold;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
QScrollBar:vertical {
    background-color: #e6e9ef; width: 10px; border-radius: 5px;
}
QScrollBar::handle:vertical {
    background-color: #bcc0cc; border-radius: 5px; min-height: 30px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QSplitter::handle { background-color: #ccd0da; }
QStatusBar { background-color: #e6e9ef; color: #6c6f85; }
QComboBox {
    background-color: #ffffff; color: #4c4f69;
    border: 1px solid #ccd0da; border-radius: 4px; padding: 4px 8px;
}
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView {
    background-color: #ffffff; color: #4c4f69;
    border: 1px solid #ccd0da; selection-background-color: #1e66f5;
    selection-color: #ffffff;
}
"""


def get_theme(name: str) -> str:
    return LIGHT if name == 'light' else DARK
