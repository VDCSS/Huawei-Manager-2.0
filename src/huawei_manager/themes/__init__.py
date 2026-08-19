QSS_DARK = """
QWidget {
    background-color: #0d0d1a;
    color: #e0e0ff;
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 10pt;
}
QPushButton {
    background-color: #13132b;
    color: #e0e0ff;
    border: 1px solid #00e5ff;
    border-radius: 6px;
    padding: 6px 16px;
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 10pt;
}
QPushButton:hover {
    background-color: #1a1a3e;
    border-color: #40eeff;
}
QPushButton:pressed {
    background-color: #0e0e20;
}
QPushButton:disabled {
    background-color: #1a1a30;
    color: #6a6a9a;
    border-color: #2a2a4a;
}
QLineEdit {
    background-color: #1a1a30;
    color: #e0e0ff;
    border: none;
    border-bottom: 2px solid #00e5ff;
    border-radius: 4px;
    padding: 4px 8px;
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 10pt;
}
QLineEdit:focus {
    border-bottom: 2px solid #e040fb;
}
QLineEdit:disabled {
    background-color: #13132b;
    color: #6a6a9a;
    border-bottom-color: #2a2a4a;
}
QTextEdit {
    background-color: #1a1a30;
    color: #c8c8ff;
    border: 1px solid #2a2a4a;
    border-radius: 4px;
    padding: 4px;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 10pt;
}
QLabel {
    background: transparent;
    color: #e0e0ff;
}
QLabel[dim="true"] {
    color: #6a6a9a;
}
QLabel[code="true"] {
    color: #c8c8ff;
    font-family: "Consolas", "Courier New", monospace;
}
QComboBox {
    background-color: #13132b;
    color: #e0e0ff;
    border: 1px solid #2a2a4a;
    border-radius: 4px;
    padding: 4px 8px;
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 10pt;
}
QComboBox:hover {
    border-color: #00e5ff;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 20px;
    border-left: 1px solid #2a2a4a;
}
QComboBox QAbstractItemView {
    background-color: #0d0d1a;
    color: #e0e0ff;
    border: 1px solid #2a2a4a;
    selection-background-color: #00e5ff;
    selection-color: #0d0d1a;
}
QListWidget {
    background-color: #13132b;
    color: #e0e0ff;
    border: 1px solid #2a2a4a;
    border-radius: 4px;
    outline: none;
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 10pt;
}
QListWidget:focus {
    border-color: #00e5ff;
}
QListWidget::item:selected {
    background-color: #00e5ff;
    color: #0d0d1a;
}
QListWidget::item:hover {
    background-color: #1a1a3e;
}
QScrollBar:vertical {
    background: #1a1a30;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #00e5ff;
    min-height: 30px;
    border-radius: 4px;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background: #1a1a30;
    height: 8px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #00e5ff;
    min-width: 30px;
    border-radius: 4px;
}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0;
}
QCheckBox {
    spacing: 8px;
    color: #e0e0ff;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #2a2a4a;
    border-radius: 3px;
    background: #13132b;
}
QCheckBox::indicator:checked {
    background: #00e5ff;
    border-color: #00e5ff;
}
QRadioButton {
    spacing: 8px;
    color: #e0e0ff;
}
QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #2a2a4a;
    border-radius: 8px;
    background: #13132b;
}
QRadioButton::indicator:checked {
    background: #00e5ff;
    border-color: #00e5ff;
}
QStatusBar {
    background-color: #0a0a18;
    color: #6a6a9a;
    font-size: 9pt;
}
QStatusBar::item {
    border: none;
}
QMenuBar {
    background-color: #0a0a18;
    color: #e0e0ff;
    border-bottom: 1px solid #2a2a4a;
}
QMenuBar::item:selected {
    background-color: #1a1a3e;
}
QMenu {
    background-color: #0d0d1a;
    color: #e0e0ff;
    border: 1px solid #2a2a4a;
}
QMenu::item:selected {
    background-color: #00e5ff;
    color: #0d0d1a;
}
QTabWidget::pane {
    background-color: #0d0d1a;
    border: 1px solid #2a2a4a;
    border-radius: 4px;
}
QTabBar::tab {
    background-color: #13132b;
    color: #e0e0ff;
    border: 1px solid #2a2a4a;
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    padding: 6px 16px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #0d0d1a;
    border-bottom: 2px solid #00e5ff;
}
QTabBar::tab:hover:!selected {
    background-color: #1a1a3e;
}
QGroupBox {
    background-color: #13132b;
    border: 1px solid #2a2a4a;
    border-radius: 6px;
    margin-top: 12px;
    padding: 16px 12px 12px;
    font-size: 10pt;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    color: #00e5ff;
}
QProgressBar {
    background-color: #1a1a30;
    border: 1px solid #2a2a4a;
    border-radius: 4px;
    text-align: center;
    color: #e0e0ff;
    height: 12px;
}
QProgressBar::chunk {
    background-color: #00e5ff;
    border-radius: 3px;
}
QToolTip {
    background-color: #13132b;
    color: #e0e0ff;
    border: 1px solid #00e5ff;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 9pt;
}
"""

QSS_LIGHT = """
QWidget {
    background-color: #f0f0f8;
    color: #1a1a2e;
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 10pt;
}
QPushButton {
    background-color: #ffffff;
    color: #1a1a2e;
    border: 1px solid #0098a0;
    border-radius: 6px;
    padding: 6px 16px;
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 10pt;
}
QPushButton:hover {
    background-color: #e0e8f0;
    border-color: #00b0b8;
}
QPushButton:pressed {
    background-color: #d0d8e0;
}
QPushButton:disabled {
    background-color: #e8e8f0;
    color: #8a8aaa;
    border-color: #c0c0d0;
}
QLineEdit {
    background-color: #fafafe;
    color: #1a1a2e;
    border: none;
    border-bottom: 2px solid #0098a0;
    border-radius: 4px;
    padding: 4px 8px;
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 10pt;
}
QLineEdit:focus {
    border-bottom: 2px solid #a030c0;
}
QLineEdit:disabled {
    background-color: #f0f0f8;
    color: #8a8aaa;
    border-bottom-color: #c0c0d0;
}
QTextEdit {
    background-color: #fafafe;
    color: #2a2a40;
    border: 1px solid #c0c0d0;
    border-radius: 4px;
    padding: 4px;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 10pt;
}
QLabel {
    background: transparent;
    color: #1a1a2e;
}
QLabel[dim="true"] {
    color: #6a6a8a;
}
QLabel[code="true"] {
    color: #2a2a40;
    font-family: "Consolas", "Courier New", monospace;
}
QComboBox {
    background-color: #ffffff;
    color: #1a1a2e;
    border: 1px solid #c0c0d0;
    border-radius: 4px;
    padding: 4px 8px;
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 10pt;
}
QComboBox:hover {
    border-color: #0098a0;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 20px;
    border-left: 1px solid #c0c0d0;
}
QComboBox QAbstractItemView {
    background-color: #ffffff;
    color: #1a1a2e;
    border: 1px solid #c0c0d0;
    selection-background-color: #0098a0;
    selection-color: #ffffff;
}
QListWidget {
    background-color: #ffffff;
    color: #1a1a2e;
    border: 1px solid #c0c0d0;
    border-radius: 4px;
    outline: none;
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 10pt;
}
QListWidget:focus {
    border-color: #0098a0;
}
QListWidget::item:selected {
    background-color: #0098a0;
    color: #ffffff;
}
QListWidget::item:hover {
    background-color: #e0e8f0;
}
QScrollBar:vertical {
    background: #e8e8f0;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #0098a0;
    min-height: 30px;
    border-radius: 4px;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background: #e8e8f0;
    height: 8px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #0098a0;
    min-width: 30px;
    border-radius: 4px;
}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0;
}
QCheckBox {
    spacing: 8px;
    color: #1a1a2e;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #c0c0d0;
    border-radius: 3px;
    background: #ffffff;
}
QCheckBox::indicator:checked {
    background: #0098a0;
    border-color: #0098a0;
}
QRadioButton {
    spacing: 8px;
    color: #1a1a2e;
}
QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #c0c0d0;
    border-radius: 8px;
    background: #ffffff;
}
QRadioButton::indicator:checked {
    background: #0098a0;
    border-color: #0098a0;
}
QStatusBar {
    background-color: #e8e8f0;
    color: #6a6a8a;
    font-size: 9pt;
}
QStatusBar::item {
    border: none;
}
QMenuBar {
    background-color: #e8e8f0;
    color: #1a1a2e;
    border-bottom: 1px solid #c0c0d0;
}
QMenuBar::item:selected {
    background-color: #d0d8e0;
}
QMenu {
    background-color: #ffffff;
    color: #1a1a2e;
    border: 1px solid #c0c0d0;
}
QMenu::item:selected {
    background-color: #0098a0;
    color: #ffffff;
}
QTabWidget::pane {
    background-color: #f0f0f8;
    border: 1px solid #c0c0d0;
    border-radius: 4px;
}
QTabBar::tab {
    background-color: #ffffff;
    color: #1a1a2e;
    border: 1px solid #c0c0d0;
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    padding: 6px 16px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #f0f0f8;
    border-bottom: 2px solid #0098a0;
}
QTabBar::tab:hover:!selected {
    background-color: #e0e8f0;
}
QGroupBox {
    background-color: #ffffff;
    border: 1px solid #c0c0d0;
    border-radius: 6px;
    margin-top: 12px;
    padding: 16px 12px 12px;
    font-size: 10pt;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    color: #0098a0;
}
QProgressBar {
    background-color: #e8e8f0;
    border: 1px solid #c0c0d0;
    border-radius: 4px;
    text-align: center;
    color: #1a1a2e;
    height: 12px;
}
QProgressBar::chunk {
    background-color: #0098a0;
    border-radius: 3px;
}
QToolTip {
    background-color: #ffffff;
    color: #1a1a2e;
    border: 1px solid #0098a0;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 9pt;
}
"""
