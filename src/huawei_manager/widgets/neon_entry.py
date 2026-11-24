"""Inputs e painéis de código alinhados ao design system do MVP.

``neon_entry`` é o campo de formulário (superfície de input, borda fina,
foco em ciano). ``styled_text``/``output_text`` são os painéis de saída
em JetBrains Mono sobre a superfície de código (``--code-bg``).
"""
from typing import Any

from PySide6.QtWidgets import QLineEdit, QTextEdit, QWidget

import huawei_manager.constants as _C
from huawei_manager.widgets.helpers import _css_font


def neon_entry(
    parent: QWidget | None = None,
    textvariable: list[str] | dict[str, str] | None = None,
    width: int = 30,
    state: str = "normal",
) -> QLineEdit:
    entry = QLineEdit(parent)
    entry.setMinimumWidth(width * 8)
    entry.setMaximumWidth(width * 14)
    entry.setPlaceholderText("")
    entry.setMinimumHeight(_C.FIELD_MIN_HEIGHT)
    entry.setStyleSheet(f"""
        QLineEdit {{
            background-color: {_C.BG_INPUT};
            color: {_C.FG_MAIN};
            border: 1px solid {_C.BORDER_NRM};
            border-radius: 6px;
            padding: 0px 11px;
            selection-background-color: {_C.NEON_CYAN};
            selection-color: {_C.BG_BASE};
            font: {_css_font(_C.FONT_UI_MEDIUM)};
        }}
        QLineEdit:hover {{
            border-color: {_C.BORDER_STRONG};
        }}
        QLineEdit:focus {{
            border: 1px solid {_C.NEON_CYAN};
            background-color: {_C.BG_SURFACE_2};
        }}
        QLineEdit:disabled {{
            background-color: {_C.BG_SURFACE_2};
            color: {_C.FG_FAINT};
            border: 1px solid {_C.BORDER_SOFT};
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


def _code_style(line_wrap: bool = True) -> str:
    family, size = _C.FONT_LARGE[0], _C.FONT_LARGE[1]
    return f"""
        QTextEdit {{
            background-color: {_C.BG_CODE};
            color: {_C.FG_CODE};
            border: 1px solid {_C.BORDER_NRM};
            border-radius: 8px;
            padding: 12px 14px;
            selection-background-color: {_C.NEON_CYAN};
            selection-color: {_C.BG_BASE};
            font: {size}px '{family}';
        }}
        QTextEdit:focus {{
            border-color: {_C.rgba(_C.NEON_CYAN, 0.34)};
        }}
        QTextEdit:read-only {{
            color: {_C.FG_CODE};
        }}
    """


def styled_text(parent: QWidget | None = None, **kw: Any) -> QTextEdit:
    ed = QTextEdit(parent)
    family, size = _C.FONT_LARGE[0], _C.FONT_LARGE[1]
    ed.setFont(font := ed.font())
    font.setFamily(family)
    font.setPointSize(size)
    ed.setFont(font)
    ed.setStyleSheet(_code_style())
    ed.setTabStopDistance(20)
    ed.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
    for k, v in kw.items():
        if hasattr(ed, k):
            try:
                setattr(ed, k, v)
            except Exception:
                pass
    return ed


def output_text(parent: QWidget | None = None, **kw: Any) -> QTextEdit:
    ed = styled_text(parent, **kw)
    ed.setReadOnly(True)
    ed.setStyleSheet(_code_style())
    return ed
