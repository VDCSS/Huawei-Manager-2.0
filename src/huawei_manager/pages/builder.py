#!/usr/bin/env python3
"""Page builders (PySide6) — all _build_*_page methods."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QLabel,
    QVBoxLayout,
    QWidget,
)

import huawei_manager.constants as C
from huawei_manager._protocols import AppCoreProtocol


class PageBuilder:
    """Mixin com métodos de construção das páginas da interface PySide6."""

    # ── Helpers ────────────────────────────────────────────────────────

    def _make_page(self: AppCoreProtocol, key: str) -> QWidget:
        """Cria uma QWidget page e a adiciona ao _page_container (se existir)."""
        p = QWidget()
        p.setObjectName(f"page_{key}")
        layout = QVBoxLayout(p)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(0)
        if self._page_container is not None:
            from PySide6.QtWidgets import QStackedWidget

            if isinstance(self._page_container, QStackedWidget):
                self._page_container.addWidget(p)
            elif self._page_container.layout() is not None:
                self._page_container.layout().addWidget(p)
        return p

    def _page_layout(self, p: QWidget) -> QVBoxLayout:
        layout = p.layout()
        if not isinstance(layout, QVBoxLayout):
            raise TypeError("page layout must be a QVBoxLayout")
        return layout

    def _page_title(self, parent: QWidget, title: str, color: str, subtitle: str = "") -> None:
        layout = self._page_layout(parent)
        lbl = QLabel(title, parent)
        lbl.setStyleSheet(f"color: {color}; font: bold {C.FONT_TITLE}px {C.FONT_UI_FAMILY}; padding: 0px; margin: 0px;")
        layout.addWidget(lbl)
        if subtitle:
            sub = QLabel(subtitle, parent)
            sub.setStyleSheet(f"color: {C.FG_DIM}; font: {C.FONT_SUBHEAD}px {C.FONT_UI_FAMILY}; padding: 0px;")
            layout.addWidget(sub)
        layout.addSpacing(8)

    def _css_label(self, color: str, bg: str = "", font_size: int = 12, bold: bool = False) -> str:
        weight = "bold" if bold else "normal"
        bg_css = f"background: {bg};" if bg else ""
        return f"color: {color}; {bg_css} font: {weight} {font_size}px {C.FONT_UI_FAMILY};"

