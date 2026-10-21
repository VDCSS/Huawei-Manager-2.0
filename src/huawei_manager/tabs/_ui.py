"""Helpers de UI puros para abas — sem dependência de App ou mixins.

Copiados de ``pages/builder.py`` (``_page_layout``/``_page_title``/
``_css_label``) e de ``app_threading.py`` (``_write``/``_loading``) com o
corpo idêntico, mas operando sobre widgets locais e recebendo ``dispatch``
explícito (o agendamento na thread GUI vem do :class:`TabContext`).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

import huawei_manager.constants as C

if TYPE_CHECKING:
    from PySide6.QtWidgets import QTextEdit

__all__ = [
    "css_label", "loading", "page_frame", "page_layout", "page_title",
    "write",
]


def page_frame(key: str) -> QWidget:
    """Cria a QWidget padrão de página (o App registra no QStackedWidget)."""
    p = QWidget()
    p.setObjectName(f"page_{key}")
    layout = QVBoxLayout(p)
    layout.setContentsMargins(16, 12, 16, 12)
    layout.setSpacing(0)
    return p


def page_layout(p: QWidget) -> QVBoxLayout:
    layout = p.layout()
    if not isinstance(layout, QVBoxLayout):
        raise TypeError("page layout must be a QVBoxLayout")
    return layout


def page_title(parent: QWidget, title: str, color: str, subtitle: str = "") -> None:
    layout = page_layout(parent)
    lbl = QLabel(title, parent)
    lbl.setStyleSheet(f"color: {color}; font: bold {C.FONT_TITLE}px {C.FONT_UI_FAMILY}; padding: 0px; margin: 0px;")
    layout.addWidget(lbl)
    if subtitle:
        sub = QLabel(subtitle, parent)
        sub.setStyleSheet(f"color: {C.FG_DIM}; font: {C.FONT_SUBHEAD}px {C.FONT_UI_FAMILY}; padding: 0px;")
        layout.addWidget(sub)
    layout.addSpacing(8)


def css_label(color: str, bg: str = "", font_size: int = 12, bold: bool = False) -> str:
    weight = "bold" if bold else "normal"
    bg_css = f"background: {bg};" if bg else ""
    return f"color: {color}; {bg_css} font: {weight} {font_size}px {C.FONT_UI_FAMILY};"


def write(out: QTextEdit | None, text: str, dispatch: Callable[..., None]) -> None:
    """Substitui o texto inteiro do painel (na thread GUI via ``dispatch``).

    Widget C++ já deletado (rebuild em curso) → descarta em silêncio, igual
    a ``App._safe_write``.
    """
    if out is None:
        return

    def _do_write() -> None:
        try:
            out.clear()
            out.setPlainText(text)
        except (RuntimeError, AttributeError):
            return

    dispatch(_do_write)


def loading(out: QTextEdit | None, msg: str, dispatch: Callable[..., None]) -> None:
    """Mensagem de carregamento no painel (na thread GUI via ``dispatch``)."""
    if out is None:
        return

    def _do_loading() -> None:
        try:
            out.clear()
            out.setPlainText(f"⏳  {msg}\n")
        except (RuntimeError, AttributeError):
            return

    dispatch(_do_loading)
