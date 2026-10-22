"""Aba Roteamento — módulo TabModule (F2-route).

Migrado de ``pages/builder.py`` (``_build_route_page``): a construção
virou ``RouteTab.build(ctx) -> QWidget`` e o estado vive em
:class:`RouteState`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QWidget

import huawei_manager.constants as C
from huawei_manager.constants import ROUTE_FILTER_LABELS
from huawei_manager.tabs import _ui
from huawei_manager.tabs.route.handlers import RouteHandlers
from huawei_manager.tabs.route.state import RouteState
from huawei_manager.widgets.neon_button import action_button
from huawei_manager.widgets.neon_entry import output_text

if TYPE_CHECKING:
    from PySide6.QtWidgets import QTextEdit

    from huawei_manager.tabs._contract import TabContext


class RouteTab:
    """Módulo da aba Roteamento (TabModule)."""

    def __init__(self) -> None:
        self.state = RouteState()
        self._ctx: TabContext | None = None
        self._handlers: RouteHandlers | None = None

    # ── TabModule ────────────────────────────────────────────────────
    def attach(self, ctx: TabContext) -> None:
        """Injeta o contexto (idempotente) — chamado por build e fachadas.

        Permite executar ações da aba sem que a UI tenha sido
        construída: os writes caem nos guards de widget ``None``.
        """
        if self._ctx is None:
            self._ctx = ctx
            self._handlers = RouteHandlers(ctx, self.state)

    def build(self, ctx: TabContext) -> QWidget:
        """Constrói a página das tabelas do roteador."""
        self.attach(ctx)
        state = self.state

        p = _ui.page_frame("route")
        _ui.page_title(p, "Tabelas e Status do Roteador", C.NEON_CYAN,
                       "Visualizacao de tabelas, vizinhos e metricas do dispositivo")
        row = QWidget(p)
        row.setStyleSheet(f"background: {C.BG_CARD};")
        row.setMaximumHeight(40)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        page_layout = _ui.page_layout(p)
        page_layout.addWidget(row)
        page_layout.addSpacing(8)

        lbl = QLabel("Filtro:", row)
        lbl.setStyleSheet(_ui.css_label(C.FG_DIM, C.BG_CARD, 11))
        row_layout.addWidget(lbl)
        row_layout.addSpacing(8)

        state.filter_var = "Tabela de Rotas do Roteador"
        state.filter_cb = QComboBox(row)
        state.filter_cb.setEditable(False)
        state.filter_cb.addItems(list(ROUTE_FILTER_LABELS.values()))
        state.filter_cb.setCurrentText(state.filter_var)
        state.filter_cb.setMinimumWidth(300)
        state.filter_cb.setStyleSheet(f"""
            QComboBox {{ background: {C.BG_INPUT}; color: {C.NEON_CYAN};
                         border: 1px solid {C.BORDER_NRM}; border-radius: 4px;
                         padding: 4px 8px; font: 11px {C.FONT_UI_FAMILY}; }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{ background: {C.BG_INPUT};
                                           color: {C.NEON_CYAN};
                                           selection-background-color: {C.NEON_PURP}; }}
        """)
        row_layout.addWidget(state.filter_cb)

        state.out = output_text(p)
        page_layout.addWidget(state.out, stretch=1)
        page_layout.addSpacing(10)
        btn = action_button(p, "↻  Carregar",
                            lambda: self.fetch_route(), C.NEON_CYAN)
        page_layout.addWidget(btn)

        return p

    def dispose(self) -> None:
        """Solta refs de widget no rebuild (estado lógico é preservado)."""
        state = self.state
        state.out = None
        state.filter_cb = None

    # ── Fachadas (usadas pelo shell: atalhos, paleta) ────────────────
    def fetch_route(self) -> None:
        """Extrai o fkey na UI thread e despacha o fetch na IO thread."""
        if self._ctx is None:
            return
        state = self.state
        if state.filter_cb is not None:
            fkey = {v: k for k, v in ROUTE_FILTER_LABELS.items()}.get(
                state.filter_cb.currentText(), "routing")
        else:
            fkey = "routing"
        self._ctx.run(lambda: self._h().fetch_route(fkey))

    def filter_label(self) -> str:
        """Texto do filtro selecionado."""
        state = self.state
        if state.filter_cb is None:
            return state.filter_var
        return state.filter_cb.currentText()

    def out_widget(self) -> QTextEdit | None:
        """Widget de saída (Ctrl+L limpa a saída)."""
        return self.state.out

    # ── Internos ─────────────────────────────────────────────────────
    def _h(self) -> RouteHandlers:
        if self._handlers is None:
            raise RuntimeError("RouteTab não foi construído (build ausente)")
        return self._handlers
