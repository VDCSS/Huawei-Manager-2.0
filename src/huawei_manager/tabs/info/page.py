"""Aba Info do Sistema — módulo TabModule (F2-info).

Migrado de ``pages/builder.py`` (``_build_info_page``): a construção
virou ``InfoTab.build(ctx) -> QWidget`` e a coleta vive em
:class:`InfoHandlers`. O botão envolve ``ctx.run`` (a aba cuida do
threading — o shell chama só a fachada, sem ``_run`` externo).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QWidget

import huawei_manager.constants as C
from huawei_manager.tabs import _ui
from huawei_manager.tabs.info.handlers import InfoHandlers
from huawei_manager.tabs.info.state import InfoState
from huawei_manager.widgets.neon_button import action_button
from huawei_manager.widgets.neon_entry import output_text

if TYPE_CHECKING:
    from PySide6.QtWidgets import QTextEdit

    from huawei_manager.tabs._contract import TabContext


class InfoTab:
    """Módulo da aba Info do Sistema (TabModule)."""

    def __init__(self) -> None:
        self.state = InfoState()
        self._ctx: TabContext | None = None
        self._handlers: InfoHandlers | None = None

    # ── TabModule ────────────────────────────────────────────────────
    def attach(self, ctx: TabContext) -> None:
        """Injeta o contexto (idempotente) — chamado por build e fachadas.

        Permite coletar informações sem a UI ter sido construída: os
        writes caem nos guards de widget ``None`` (paridade legada).
        """
        if self._ctx is None:
            self._ctx = ctx
            self._handlers = InfoHandlers(ctx, self.state)

    def build(self, ctx: TabContext) -> QWidget:
        """Constrói a página de Informações do Sistema."""
        self.attach(ctx)
        state = self.state

        p = _ui.page_frame("info")
        _ui.page_title(p, "Informacoes do Sistema", C.NEON_MAG,
                       "CLI: display version / cpu-usage / memory-usage")

        state.out = output_text(p)
        _ui.page_layout(p).addWidget(state.out, stretch=1)
        _ui.page_layout(p).addSpacing(10)

        btn = action_button(p, "↻  get system info",
                            lambda: self.fetch_info(), C.NEON_MAG)
        _ui.page_layout(p).addWidget(btn)

        return p

    def dispose(self) -> None:
        """Solta refs de widget no rebuild (estado lógico é preservado)."""
        self.state.out = None

    # ── Fachadas (usadas pelo shell: atalhos Enter/F5, Ctrl+L) ───────
    def fetch_info(self) -> None:
        """Despacha a coleta na IO thread (ctx.run cuida do guard)."""
        if self._ctx is None:
            return
        self._ctx.run(lambda: self._h().fetch_info())

    def out_widget(self) -> QTextEdit | None:
        """Widget de saída (Ctrl+L limpa a saída do info)."""
        return self.state.out

    # ── Internos ─────────────────────────────────────────────────────
    def _h(self) -> InfoHandlers:
        if self._handlers is None:
            raise RuntimeError("InfoTab não foi construído (build ausente)")
        return self._handlers
