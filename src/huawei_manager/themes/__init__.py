"""QSS global do Huawei Manager — tradução do design system do MVP.

Os valores abaixo são os mesmos tokens de ``huawei-manager-mvp-main/style.css``
(temas Black/White), convertidos para Qt Style Sheets. O objetivo é manter a
linguagem visual do MVP — superfícies planas, bordas finas, tipografia IBM
Plex/Space Grotesk/JetBrains Mono, acentos neon, cantos de 4–14 px — sem
alterar nenhuma mecânica das abas.
"""
from __future__ import annotations

from string import Template

import huawei_manager.constants as C

# ─── Tokens auxiliares ───────────────────────────────────────────────
# O QSS não aceita variáveis; cada tema recebe um dicionário já resolvido.
# Os nomes espelham as CSS custom properties do MVP para facilitar a
# manutenção e a comparação lado a lado com o style.css original.
_DARK_TOKENS: dict[str, str] = {
    "bg": C.BG_BASE,
    "bg_deep": C.BG_DEEP,
    "bg_soft": C.BG_SOFT,
    "surface": C.BG_CARD,
    "surface_2": C.BG_SURFACE_2,
    "surface_3": C.BG_SURFACE_3,
    "surface_hover": C.BG_HOVER,
    "sidebar": C.BG_SIDEBAR,
    "titlebar": C.BG_TITLEBAR,
    "statusbar": C.BG_STATUS,
    "input": C.BG_INPUT,
    "code_bg": C.BG_CODE,
    "code_text": C.FG_CODE,
    "border": C.BORDER_NRM,
    "border_soft": C.BORDER_SOFT,
    "border_strong": C.BORDER_STRONG,
    "text": C.FG_MAIN,
    "text_2": C.FG_CODE,
    "dim": C.FG_DIM,
    "faint": C.FG_FAINT,
    "cyan": C.NEON_CYAN,
    "cyan_strong": C.NEON_CYAN_STRONG,
    "cyan_soft": C.rgba(C.NEON_CYAN, 0.09),
    "cyan_border": C.rgba(C.NEON_CYAN, 0.34),
    "cyan_ink": "#041116",
    "magenta": C.NEON_MAG,
    "magenta_soft": C.rgba(C.NEON_MAG, 0.10),
    "magenta_border": C.rgba(C.NEON_MAG, 0.30),
    "purple": C.NEON_PURP,
    "purple_soft": C.rgba(C.NEON_PURP, 0.11),
    "purple_border": C.rgba(C.NEON_PURP, 0.30),
    "amber": C.NEON_AMBER,
    "amber_soft": C.rgba(C.NEON_AMBER, 0.10),
    "amber_border": C.rgba(C.NEON_AMBER, 0.30),
    "red": C.NEON_RED,
    "red_soft": C.rgba(C.NEON_RED, 0.10),
    "red_border": C.rgba(C.NEON_RED, 0.30),
    "green": C.NEON_GREEN,
    "green_soft": C.rgba(C.NEON_GREEN, 0.10),
    "green_border": C.rgba(C.NEON_GREEN, 0.30),
}

_LIGHT_TOKENS: dict[str, str] = {
    "bg": C.BG_BASE_L,
    "bg_deep": C.BG_DEEP_L,
    "bg_soft": C.BG_SOFT_L,
    "surface": C.BG_CARD_L,
    "surface_2": C.BG_SURFACE_2_L,
    "surface_3": C.BG_SURFACE_3_L,
    "surface_hover": C.BG_HOVER_L,
    "sidebar": C.BG_SIDEBAR_L,
    "titlebar": C.BG_TITLEBAR_L,
    "statusbar": C.BG_STATUS_L,
    "input": C.BG_INPUT_L,
    "code_bg": C.BG_CODE_L,
    "code_text": C.FG_CODE_L,
    "border": C.BORDER_NRM_L,
    "border_soft": C.BORDER_SOFT_L,
    "border_strong": C.BORDER_STRONG_L,
    "text": C.FG_MAIN_L,
    "text_2": C.FG_MAIN_L,
    "dim": C.FG_DIM_L,
    "faint": C.FG_FAINT_L,
    "cyan": C.NEON_CYAN_L,
    "cyan_strong": C.NEON_CYAN_STRONG_L,
    "cyan_soft": C.rgba(C.NEON_CYAN_L, 0.09),
    "cyan_border": C.rgba(C.NEON_CYAN_L, 0.32),
    "cyan_ink": "#ffffff",
    "magenta": C.NEON_MAG_L,
    "magenta_soft": C.rgba(C.NEON_MAG_L, 0.08),
    "magenta_border": C.rgba(C.NEON_MAG_L, 0.26),
    "purple": C.NEON_PURP_L,
    "purple_soft": C.rgba(C.NEON_PURP_L, 0.08),
    "purple_border": C.rgba(C.NEON_PURP_L, 0.26),
    "amber": C.NEON_AMBER_L,
    "amber_soft": C.rgba(C.NEON_AMBER_L, 0.08),
    "amber_border": C.rgba(C.NEON_AMBER_L, 0.26),
    "red": C.NEON_RED_L,
    "red_soft": C.rgba(C.NEON_RED_L, 0.08),
    "red_border": C.rgba(C.NEON_RED_L, 0.26),
    "green": C.NEON_GREEN_L,
    "green_soft": C.rgba(C.NEON_GREEN_L, 0.08),
    "green_border": C.rgba(C.NEON_GREEN_L, 0.26),
}

_HUAWEI_TOKENS: dict[str, str] = {
    "bg": C.BG_BASE_H,
    "bg_deep": C.BG_DEEP_H,
    "bg_soft": C.BG_SOFT_H,
    "surface": C.BG_CARD_H,
    "surface_2": C.BG_SURFACE_2_H,
    "surface_3": C.BG_SURFACE_3_H,
    "surface_hover": C.BG_HOVER_H,
    "sidebar": C.BG_SIDEBAR_H,
    "titlebar": C.BG_TITLEBAR_H,
    "statusbar": C.BG_STATUS_H,
    "input": C.BG_INPUT_H,
    "code_bg": C.BG_CODE_H,
    "code_text": C.FG_CODE_H,
    "border": C.BORDER_NRM_H,
    "border_soft": C.BORDER_SOFT_H,
    "border_strong": C.BORDER_STRONG_H,
    "text": C.FG_MAIN_H,
    "text_2": C.FG_MAIN_H,
    "dim": C.FG_DIM_H,
    "faint": C.FG_FAINT_H,
    "cyan": C.NEON_CYAN_H,
    "cyan_strong": C.NEON_CYAN_STRONG_H,
    "cyan_soft": C.rgba(C.NEON_CYAN_H, 0.09),
    "cyan_border": C.rgba(C.NEON_CYAN_H, 0.32),
    "cyan_ink": "#ffffff",
    "magenta": C.NEON_MAG_H,
    "magenta_soft": C.rgba(C.NEON_MAG_H, 0.08),
    "magenta_border": C.rgba(C.NEON_MAG_H, 0.26),
    "purple": C.NEON_PURP_H,
    "purple_soft": C.rgba(C.NEON_PURP_H, 0.08),
    "purple_border": C.rgba(C.NEON_PURP_H, 0.26),
    "amber": C.NEON_AMBER_H,
    "amber_soft": C.rgba(C.NEON_AMBER_H, 0.08),
    "amber_border": C.rgba(C.NEON_AMBER_H, 0.26),
    "red": C.NEON_RED_H,
    "red_soft": C.rgba(C.NEON_RED_H, 0.08),
    "red_border": C.rgba(C.NEON_RED_H, 0.26),
    "green": C.NEON_GREEN_H,
    "green_soft": C.rgba(C.NEON_GREEN_H, 0.08),
    "green_border": C.rgba(C.NEON_GREEN_H, 0.26),
}

# ─── Template QSS ────────────────────────────────────────────────────
# ``Template`` ($token) deixa as chaves do CSS/QSS intactas — muito mais
# legível do que escapar ``{{``/``}}`` em uma f-string gigante.
_QSS_TEMPLATE = Template(r"""
/* ═══════════════ BASE ═══════════════ */
QWidget {
    background-color: $bg;
    color: $text;
    font-family: "IBM Plex Sans", "Segoe UI", "Noto Sans", sans-serif;
    font-size: 14px;
}
QMainWindow, QDialog {
    background-color: $bg;
}
QLabel {
    background: transparent;
    color: $text;
}
QLabel[dim="true"] {
    color: $dim;
}
QLabel[code="true"] {
    color: $code_text;
    font-family: "JetBrains Mono", "Cascadia Mono", "Consolas", monospace;
}
QLabel[role="eyebrow"] {
    color: $cyan;
    font-family: "JetBrains Mono", "Consolas", monospace;
    font-size: 11px;
    font-weight: 500;
}
QLabel[role="title"] {
    color: $text;
    font-family: "Space Grotesk", "IBM Plex Sans", "Segoe UI", sans-serif;
    font-size: 34px;
    font-weight: 650;
}
QLabel[role="subtitle"] {
    color: $dim;
    font-size: 14px;
}
QLabel[role="caption"] {
    color: $faint;
    font-size: 11px;
}
QLabel[role="section"] {
    color: $text;
    font-size: 18px;
    font-weight: 600;
}
QLabel[role="stat"] {
    color: $text;
    font-family: "JetBrains Mono", "Consolas", monospace;
    font-size: 34px;
    font-weight: 600;
}
QLabel[role="badge"] {
    color: $dim;
    font-family: "JetBrains Mono", "Consolas", monospace;
    font-size: 10px;
    background: $surface_3;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 3px 8px;
}

/* ═══════════════ SHELL (topbar / sidebar / statusbar) ═══════════════ */
#sidebar {
    background: $sidebar;
    border-right: 1px solid $border;
}
#topbar {
    background: $bg;
    border-bottom: 1px solid $border;
}
#statusbar {
    background: $statusbar;
    border-top: 1px solid $border;
}
#pageContainer {
    background: $bg;
}
#navGroupLabel {
    color: $faint;
    font-size: 10.5px;
    font-weight: 600;
    padding: 12px 16px 7px 16px;
}
#navSeparator {
    background: $border;
    max-height: 1px;
    border: none;
}
#sidebarFoot {
    background: $sidebar;
    border-top: 1px solid $border_soft;
}
#targetCard {
    background: $surface;
    border: 1px solid $border;
    border-radius: 6px;
}
#targetCard:hover {
    background: $surface_hover;
    border-color: $cyan_border;
}
#userCard {
    background: transparent;
    border-top: 1px solid $border_soft;
}
#wordmarkAccent {
    color: $cyan;
}
#wordmark {
    color: $text;
    font-family: "Space Grotesk", "IBM Plex Sans", "Segoe UI", sans-serif;
    font-size: 17px;
    font-weight: 700;
}
#breadcrumb {
    color: $dim;
    font-size: 12.5px;
}
#breadcrumbCurrent {
    color: $text_2;
    font-size: 12.5px;
    font-weight: 500;
}
#avatar {
    color: $cyan;
    font-family: "JetBrains Mono", "Consolas", monospace;
    font-size: 12px;
    font-weight: 700;
    background: $cyan_soft;
    border: 1px solid $cyan_border;
    border-radius: 16px;
}
#searchBox {
    background: $input;
    border: 1px solid $border;
    border-radius: 6px;
}
#searchBox:hover {
    border-color: $cyan_border;
}
#searchChip {
    background: $input;
    border: 1px solid $border;
    border-radius: 6px;
    color: $faint;
    padding: 5px 10px;
}
#searchChip:hover {
    border-color: $cyan_border;
    color: $dim;
}

/* ═══════════════ BOTÕES ═══════════════ */
QPushButton {
    background-color: $surface_2;
    color: $text_2;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 0 16px;
    font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
    font-size: 13.5px;
    min-height: 38px;
}
QPushButton:hover {
    background-color: $surface_hover;
    border-color: $border_strong;
}
QPushButton:pressed {
    background-color: $bg_soft;
}
QPushButton:focus {
    border-color: $cyan_border;
}
QPushButton:disabled {
    background-color: $surface_2;
    color: $faint;
    border-color: $border_soft;
}
QPushButton:default {
    background-color: $cyan;
    color: $cyan_ink;
    border-color: $cyan;
}
QToolButton {
    background: transparent;
    color: $dim;
    border: none;
    border-radius: 6px;
    padding: 4px;
}
QToolButton:hover {
    background: $surface_hover;
    color: $text;
}
QToolButton:checked {
    background: $cyan_soft;
    color: $cyan;
}

/* ═══════════════ INPUTS ═══════════════ */
QLineEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit {
    background-color: $input;
    color: $text;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 0 12px;
    min-height: 42px;
    selection-background-color: $cyan;
    selection-color: $cyan_ink;
    font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
    font-size: 13.5px;
}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover {
    border-color: $border_strong;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid $cyan;
    background-color: $surface_2;
}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {
    background-color: $surface_2;
    color: $faint;
    border-color: $border_soft;
}
QLineEdit[error="true"] {
    border-color: $red;
    color: $red;
}
QComboBox {
    background-color: $input;
    color: $text;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 0 12px;
    min-height: 42px;
    font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
    font-size: 13.5px;
}
QComboBox:hover {
    border-color: $border_strong;
}
QComboBox:focus {
    border-color: $cyan;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 22px;
    border-left: 1px solid $border_soft;
}
QComboBox QAbstractItemView {
    background-color: $surface;
    color: $text;
    border: 1px solid $border_strong;
    border-radius: 6px;
    padding: 4px;
    outline: none;
    selection-background-color: $cyan;
    selection-color: $cyan_ink;
}

/* ═══════════════ TEXTO / CÓDIGO ═══════════════ */
QTextEdit, QPlainTextEdit {
    background-color: $code_bg;
    color: $code_text;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 8px;
    selection-background-color: $cyan;
    selection-color: $cyan_ink;
    font-family: "JetBrains Mono", "Cascadia Mono", "Consolas", monospace;
    font-size: 12px;
}
QTextEdit:focus, QPlainTextEdit:focus {
    border-color: $cyan_border;
}
QTextEdit:read-only, QPlainTextEdit:read-only {
    color: $code_text;
}
QTextBrowser {
    background-color: $code_bg;
    color: $code_text;
    border: 1px solid $border;
    border-radius: 8px;
}

/* ═══════════════ LISTAS / TABELAS / ÁRVORES ═══════════════ */
QListWidget, QTreeWidget, QTableWidget, QListView, QTreeView, QTableView {
    background-color: $surface;
    color: $text;
    border: 1px solid $border;
    border-radius: 8px;
    outline: none;
    alternate-background-color: $surface_2;
    selection-background-color: $cyan_soft;
    selection-color: $cyan;
    font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
    font-size: 12.5px;
}
QListWidget:focus, QTreeWidget:focus, QTableWidget:focus {
    border-color: $cyan;
}
QListWidget::item, QTreeWidget::item {
    padding: 7px 9px;
    border-radius: 4px;
}
QListWidget::item:hover, QTreeWidget::item:hover {
    background-color: $surface_hover;
}
QListWidget::item:selected, QTreeWidget::item:selected {
    background-color: $cyan_soft;
    color: $cyan;
}
QTableWidget {
    gridline-color: $border_soft;
}
QTableWidget::item {
    padding: 13px 14px;
}
QTableWidget::item:selected {
    background-color: $cyan_soft;
    color: $cyan;
}
QHeaderView::section {
    background-color: $surface_3;
    color: $faint;
    border: none;
    border-bottom: 1px solid $border;
    padding: 11px 14px;
    font-size: 10.5px;
    font-weight: 600;
}
QTableCornerButton::section {
    background-color: $surface_2;
    border: none;
}

/* ═══════════════ SCROLLBARS ═══════════════ */
QScrollBar:vertical {
    background: transparent;
    width: 9px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: $border_strong;
    min-height: 28px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: $dim;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: transparent;
}
QScrollBar:horizontal {
    background: transparent;
    height: 9px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: $border_strong;
    min-width: 28px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal:hover {
    background: $dim;
}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0;
}
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {
    background: transparent;
}

/* ═══════════════ CHECK / RADIO / SLIDER ═══════════════ */
QCheckBox, QRadioButton {
    spacing: 8px;
    color: $text;
    background: transparent;
}
QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border: 1px solid $border_strong;
    border-radius: 4px;
    background: $input;
}
QCheckBox::indicator:hover {
    border-color: $cyan_border;
}
QCheckBox::indicator:checked {
    background: $cyan;
    border-color: $cyan;
}
QRadioButton::indicator {
    width: 15px;
    height: 15px;
    border: 1px solid $border_strong;
    border-radius: 8px;
    background: $input;
}
QRadioButton::indicator:checked {
    background: $cyan;
    border-color: $cyan;
}
QSlider::groove:horizontal {
    height: 4px;
    background: $surface_3;
    border-radius: 2px;
}
QSlider::sub-page:horizontal {
    background: $cyan;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    width: 14px;
    margin: -5px 0;
    background: $cyan;
    border: 2px solid $bg;
    border-radius: 7px;
}

/* ═══════════════ MENUS / TABS / GRUPOS ═══════════════ */
QMenuBar {
    background-color: $titlebar;
    color: $text_2;
    border-bottom: 1px solid $border;
}
QMenuBar::item {
    background: transparent;
    padding: 5px 9px;
    border-radius: 2px;
}
QMenuBar::item:selected {
    background: $surface_hover;
    color: $text;
}
QMenu {
    background-color: $surface;
    color: $text;
    border: 1px solid $border_strong;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 12px;
    border-radius: 3px;
}
QMenu::item:selected {
    background: $cyan;
    color: $cyan_ink;
}
QMenu::separator {
    height: 1px;
    background: $border;
    margin: 4px 6px;
}
QTabWidget::pane {
    background-color: $surface;
    border: 1px solid $border;
    border-radius: 10px;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    color: $dim;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 8px 14px;
    margin-right: 2px;
    font-size: 12px;
}
QTabBar::tab:hover {
    color: $text;
    background: $surface_hover;
}
QTabBar::tab:selected {
    color: $cyan;
    border-bottom: 2px solid $cyan;
    font-weight: 600;
}
QGroupBox {
    background-color: $surface;
    border: 1px solid $border;
    border-radius: 10px;
    margin-top: 14px;
    padding: 18px 14px 14px;
    font-size: 12px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: $cyan;
    background: transparent;
}

/* ═══════════════ DIVERSOS ═══════════════ */
QProgressBar {
    background-color: $surface_3;
    border: 1px solid $border;
    border-radius: 5px;
    text-align: center;
    color: $text;
    min-height: 12px;
    max-height: 12px;
}
QProgressBar::chunk {
    background-color: $cyan;
    border-radius: 4px;
}
QSplitter::handle {
    background: $border;
}
QSplitter::handle:horizontal {
    width: 1px;
}
QSplitter::handle:vertical {
    height: 1px;
}
QStatusBar {
    background-color: $statusbar;
    color: $faint;
    border-top: 1px solid $border;
    font-size: 11px;
}
QStatusBar::item {
    border: none;
}
QToolTip {
    background-color: $surface_3;
    color: $text;
    border: 1px solid $border_strong;
    border-radius: 6px;
    padding: 5px 8px;
    font-size: 11px;
}
QScrollArea {
    background: transparent;
    border: none;
}
QFrame[frameShape="4"], QFrame[frameShape="5"] {
    background: $border;
}

/* ═══════════════ CONTROLES DE JANELA (TITLEBAR) ═══════════════ */
#winMinimizeBtn, #winMaximizeBtn {
    background: transparent;
    color: $dim;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 0;
    min-height: 34px;
}
#winMinimizeBtn:hover, #winMaximizeBtn:hover {
    background: $surface_hover;
    color: $text;
    border-color: $border_soft;
}
#winCloseBtn {
    background: transparent;
    color: $dim;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 0;
    min-height: 34px;
}
#winCloseBtn:hover {
    background: #c42b1c;
    color: #ffffff;
    border-color: #c42b1c;
}

/* ═══════════════ DRAWER LATERAL ═══════════════ */
#drawerPanel {
    background-color: $bg;
    border-left: 1px solid $border_strong;
}
""")


def _qss(tokens: dict[str, str]) -> str:
    return _QSS_TEMPLATE.substitute(**tokens)


QSS_DARK = _qss(_DARK_TOKENS)
QSS_LIGHT = _qss(_LIGHT_TOKENS)
QSS_HUAWEI = _qss(_HUAWEI_TOKENS)

__all__ = ["QSS_DARK", "QSS_LIGHT", "QSS_HUAWEI"]
