"""Aba Tabela ARP — módulo TabModule (F2-arp).

Migrado de ``pages/builder.py`` (``_build_arp_page``): a construção
virou ``ArpTab.build(ctx) -> QWidget`` e o fetch vive em
:class:`ArpHandlers`. O botão envolve ``ctx.run`` (a aba cuida do
threading — o shell chama só a fachada, sem ``_run`` externo).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QWidget

import huawei_manager.constants as C
from huawei_manager.tabs import _ui
from huawei_manager.tabs.arp.handlers import ArpHandlers
from huawei_manager.tabs.arp.state import ArpState
from huawei_manager.widgets.neon_button import action_button
from huawei_manager.widgets.neon_entry import output_text

if TYPE_CHECKING:
    from PySide6.QtWidgets import QTextEdit

    from huawei_manager.tabs._contract import TabContext


class ArpTab:
    """Módulo da aba Tabela ARP (TabModule)."""

    def __init__(self) -> None:
        self.state = ArpState()
        self._ctx: TabContext | None = None
        self._handlers: ArpHandlers | None = None

    # ── TabModule ────────────────────────────────────────────────────
    def attach(self, ctx: TabContext) -> None:
        """Injeta o contexto (idempotente) — chamado por build e fachadas.

        Permite buscar a tabela ARP sem a UI ter sido construída: os
        writes caem nos guards de widget ``None`` (paridade legada).
        """
        if self._ctx is None:
            self._ctx = ctx
            self._handlers = ArpHandlers(ctx, self.state)

    def build(self, ctx: TabContext) -> QWidget:
        """Constrói a página da Tabela ARP."""
        self.attach(ctx)
        state = self.state

        p = _ui.page_frame("arp")
        _ui.page_title(p, "Tabela ARP", C.NEON_CYAN, "CLI: display arp")

        state.out = output_text(p)
        _ui.page_layout(p).addWidget(state.out, stretch=1)
        _ui.page_layout(p).addSpacing(10)

        btn = action_button(p, "↻  get arp",
                            lambda: self.fetch_arp(), C.NEON_CYAN)
        _ui.page_layout(p).addWidget(btn)

        return p

    def dispose(self) -> None:
        """Solta refs de widget no rebuild (estado lógico é preservado)."""
        self.state.out = None

    # ── Fachadas (usadas pelo shell: atalhos Enter/F5, Ctrl+L) ───────
    def fetch_arp(self) -> None:
        """Despacha o fetch na IO thread (ctx.run cuida do guard)."""
        if self._ctx is None:
            return
        self._ctx.run(lambda: self._h().fetch_arp())

    def out_widget(self) -> QTextEdit | None:
        """Widget de saída (Ctrl+L limpa a saída do arp)."""
        return self.state.out

    # ── Internos ─────────────────────────────────────────────────────
    def _h(self) -> ArpHandlers:
        if self._handlers is None:
            raise RuntimeError("ArpTab não foi construído (build ausente)")
        return self._handlers
