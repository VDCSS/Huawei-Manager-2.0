from PySide6.QtWidgets import QLineEdit, QTextEdit, QWidget

import huawei_manager.constants as _C
from huawei_manager.widgets.helpers import _css_font


def neon_entry(
    parent: QWidget | None = None,
    textvariable: list | dict | None = None,
    width: int = 30,
    state: str = "normal",
) -> QLineEdit:
    entry = QLineEdit(parent)
    entry.setMinimumWidth(width * 8)
    entry.setMaximumWidth(width * 14)
    entry.setPlaceholderText("")
    entry.setStyleSheet(f"""
        QLineEdit {{
            background-color: {_C.BG_INPUT};
            color: {_C.NEON_CYAN};
            border: none;
            border-bottom: 2px solid {_C.NEON_CYAN};
            padding: 4px 6px;
            font: {_css_font(_C.FONT_UI_MEDIUM)};
        }}
        QLineEdit:focus {{
            border-bottom: 2px solid {_C.NEON_CYAN};
        }}
        QLineEdit:disabled {{
            background-color: {_C.BG_INPUT};
            color: {_C.FG_DIM};
            border-bottom: 2px solid {_C.BORDER_NRM};
        }}
    """)
    if isinstance(textvariable, list):
        def _on_change(text: str) -> None:
            if textvariable:
                textvariable[0] = text
        entry.textChanged.connect(_on_change)
    elif isinstance(textvariable, dict):
        def _on_change(text: str) -> None:
            if textvariable is not None:
                textvariable["value"] = text
        entry.textChanged.connect(_on_change)

    if state == "disabled":
        entry.setEnabled(False)
    return entry


def styled_text(parent: QWidget | None = None, **kw) -> QTextEdit:
    ed = QTextEdit(parent)
    family, size = _C.FONT_LARGE[0], _C.FONT_LARGE[1]
    ed.setFont(font := ed.font())
    font.setFamily(family)
    font.setPointSize(size)
    ed.setFont(font)
    ed.setStyleSheet(f"""
        QTextEdit {{
            background-color: {_C.BG_INPUT};
            color: {_C.FG_CODE};
            border: 1px solid {_C.BORDER_NRM};
            border-radius: 4px;
            padding: 4px;
            font: {size}pt '{family}';
        }}
    """)
    ed.setTabStopDistance(20)
    ed.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
    for k, v in kw.items():
        if hasattr(ed, k):
            try:
                setattr(ed, k, v)
            except Exception:
                pass
    return ed


def output_text(parent: QWidget | None = None, **kw) -> QTextEdit:
    ed = styled_text(parent, **kw)
    ed.setReadOnly(True)
    family, size = _C.FONT_LARGE[0], _C.FONT_LARGE[1]
    base_style = f"""
        QTextEdit {{
            background-color: {_C.BG_INPUT};
            color: {_C.FG_CODE};
            border: 1px solid {_C.BORDER_NRM};
            border-radius: 4px;
            padding: 4px;
            font: {size}pt '{family}';
        }}
        QTextEdit:read-only {{
            color: #b0b0d0;
        }}
    """
    ed.setStyleSheet(base_style)
    return ed
