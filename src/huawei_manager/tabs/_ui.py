"""Helpers visuais das abas — design system compartilhado.

As funções continuam puras (sem dependência de ``App``/mixins) e mantêm as
assinaturas usadas pelas abas. A aparência segue os tokens do MVP:
títulos em Space Grotesk, eyebrow monoespaçado no acento da aba, cartões
de 10 px de raio e superfícies planas.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

import huawei_manager.constants as C

if TYPE_CHECKING:
    from PySide6.QtWidgets import QTextEdit

__all__ = [
    "badge", "card_frame", "chip", "css_label", "loading", "page_frame",
    "page_layout", "page_title", "section_heading", "stat_label", "write",
]


def page_frame(key: str) -> QWidget:
    """Cria a QWidget padrão de página (o App registra no QStackedWidget).

    Padding do conteúdo do MVP: ``28px 32px 40px`` (top/right/bottom/left),
    ou seja, margens Qt ``(32, 28, 32, 40)``.
    """
    p = QWidget()
    p.setObjectName(f"page_{key}")
    layout = QVBoxLayout(p)
    layout.setContentsMargins(32, 28, 32, 40)
    layout.setSpacing(0)
    return p


def page_layout(p: QWidget) -> QVBoxLayout:
    layout = p.layout()
    if not isinstance(layout, QVBoxLayout):
        raise TypeError("page layout must be a QVBoxLayout")
    return layout


def page_title(parent: QWidget, title: str, color: str, subtitle: str = "") -> None:
    """Cabeçalho de página: eyebrow mono + h1 display + subtítulo.

    Espelha ``.eyebrow`` (11 px mono + marca de 6 px, gap 7, margin 8),
    ``.page-heading h1`` (34 px display 650) e ``.page-subtitle``
    (14 px, largura máxima 790 px, margin-top 8). O bloco inteiro tem
    ``margin-bottom: 24px`` (``.page-heading``).
    """
    layout = page_layout(parent)

    eyebrow_row = QWidget(parent)
    eyebrow_row.setStyleSheet("background: transparent;")
    eyebrow_layout = QHBoxLayout(eyebrow_row)
    eyebrow_layout.setContentsMargins(0, 0, 0, 0)
    eyebrow_layout.setSpacing(7)

    mark = QLabel(eyebrow_row)
    mark.setFixedSize(6, 6)
    mark.setStyleSheet(f"background: {color}; border-radius: 1px;")
    eyebrow_layout.addWidget(mark)

    eyebrow = QLabel(title.upper(), eyebrow_row)
    eyebrow.setStyleSheet(
        f"color: {color}; background: transparent; padding: 0px; margin: 0px;"
        f" font: 500 11px '{C.FONT_MONO_FAMILY}';"
    )
    eyebrow_layout.addWidget(eyebrow)
    eyebrow_layout.addStretch()
    layout.addWidget(eyebrow_row)
    layout.addSpacing(8)

    lbl = QLabel(title, parent)
    lbl.setStyleSheet(
        f"color: {C.FG_MAIN}; background: transparent; padding: 0px; margin: 0px;"
        f" font: 650 {C.FONT_TITLE}px '{C.FONT_UI_TITLE_FAMILY}';"
    )
    layout.addWidget(lbl)
    if subtitle:
        sub = QLabel(subtitle, parent)
        sub.setStyleSheet(
            f"color: {C.FG_DIM}; background: transparent; padding: 0px;"
            f" font: {C.FONT_SUBHEAD}px '{C.FONT_UI_FAMILY}';"
        )
        sub.setWordWrap(True)
        sub.setMaximumWidth(790)
        layout.addWidget(sub)
    layout.addSpacing(24)


def css_label(color: str, bg: str = "", font_size: int = 12, bold: bool = False) -> str:
    weight = "bold" if bold else "normal"
    bg_css = f" background: {bg};" if bg else ""
    return f"color: {color};{bg_css} font: {weight} {font_size}px {C.FONT_UI_FAMILY};"


def card_frame(
    parent: QWidget,
    accent: str = "",
    margins: tuple[int, int, int, int] = (20, 18, 20, 16),
    spacing: int = 6,
) -> tuple[QFrame, QVBoxLayout]:
    """Cartão de superfície (MVP ``.panel``/``.stat-card``).

    ``accent`` desenha a linha superior de 1 px (gradiente aproximado por
    ``rgba(accent, 0.55)``) que identifica o cartão na dashboard. O layout
    interno usa o padding do MVP (20/18) e raio de 10 px.
    """
    card = QFrame(parent)
    card.setObjectName("cardFrame")
    border_top = (
        f"border-top: 1px solid {C.rgba(accent, 0.55)};" if accent else ""
    )
    card.setStyleSheet(
        f"QFrame#cardFrame {{ background: {C.BG_CARD}; border: 1px solid {C.BORDER_NRM};"
        f" {border_top} border-radius: 10px; }}"
    )
    card_layout = QVBoxLayout(card)
    card_layout.setContentsMargins(*margins)
    card_layout.setSpacing(spacing)
    return card, card_layout


def section_heading(parent: QWidget, title: str, hint: str = "") -> QWidget:
    """Título de seção + dica à direita, como ``.section-heading``."""
    row = QWidget(parent)
    row.setStyleSheet("background: transparent;")
    row_layout = QHBoxLayout(row)
    row_layout.setContentsMargins(0, 0, 0, 0)
    row_layout.setSpacing(22)

    lbl = QLabel(title, row)
    lbl.setStyleSheet(
        f"color: {C.FG_MAIN}; background: transparent; font: 600 18px '{C.FONT_UI_FAMILY}';"
    )
    row_layout.addWidget(lbl)
    row_layout.addStretch()

    if hint:
        hint_lbl = QLabel(hint, row)
        hint_lbl.setStyleSheet(
            f"color: {C.FG_FAINT}; background: transparent;"
            f" font: 11.5px '{C.FONT_UI_FAMILY}';"
        )
        row_layout.addWidget(hint_lbl)
    return row


def stat_label(parent: QWidget, text: str = "", color: str = C.FG_MAIN) -> QLabel:
    """Valor grande de KPI (MVP ``.stat-card__value``)."""
    lbl = QLabel(text, parent)
    lbl.setStyleSheet(
        f"color: {color}; background: transparent;"
        f" font: 600 {C.FONT_TITLE}px '{C.FONT_MONO_FAMILY}';"
    )
    return lbl


def chip(parent: QWidget, text: str, color: str = C.FG_DIM, bg: str = "") -> QLabel:
    """Pílula/badge compacta (MVP ``.badge``/``.chip``)."""
    background = bg or C.rgba(color, 0.10)
    lbl = QLabel(text, parent)
    lbl.setStyleSheet(
        f"color: {color}; background: {background};"
        f" border: 1px solid {C.rgba(color, 0.30)}; border-radius: 8px;"
        f" padding: 3px 8px; font: 500 10px '{C.FONT_MONO_FAMILY}';"
    )
    return lbl


def badge(parent: QWidget, text: str, color: str = C.FG_DIM) -> QLabel:
    """Alias semântico para :func:`chip` (mantém leitura do MVP)."""
    return chip(parent, text, color)


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
