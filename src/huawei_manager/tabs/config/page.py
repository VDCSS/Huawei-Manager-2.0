"""Aba Configuração Atual — módulo TabModule (F2-config).

Migrado de ``pages/builder.py`` (``_build_config_page``): a construção
virou ``ConfigTab.build(ctx) -> QWidget`` e o fetch vive em
:class:`ConfigHandlers`. O botão envolve ``ctx.run`` (a aba cuida do
threading — o shell chama só a fachada, sem ``_run`` externo).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QWidget

import huawei_manager.constants as C
from huawei_manager.tabs import _ui
from huawei_manager.tabs.config.handlers import ConfigHandlers
from huawei_manager.tabs.config.state import ConfigState
from huawei_manager.widgets.neon_button import action_button
from huawei_manager.widgets.neon_entry import output_text

if TYPE_CHECKING:
    from PySide6.QtWidgets import QTextEdit

    from huawei_manager.tabs._contract import TabContext


class ConfigTab:
    """Módulo da aba Configuração Atual (TabModule)."""

    def __init__(self) -> None:
        self.state = ConfigState()
        self._ctx: TabContext | None = None
        self._handlers: ConfigHandlers | None = None

    # ── TabModule ────────────────────────────────────────────────────
    def attach(self, ctx: TabContext) -> None:
        """Injeta o contexto (idempotente) — chamado por build e fachadas.

        Permite buscar config sem a UI ter sido construída: os writes
        caem nos guards de widget ``None`` (paridade com o mixin legado).
        """
        if self._ctx is None:
            self._ctx = ctx
            self._handlers = ConfigHandlers(ctx, self.state)

    def build(self, ctx: TabContext) -> QWidget:
        """Constrói a página da Configuração Atual."""
        self.attach(ctx)
        state = self.state

        p = _ui.page_frame("config")
        _ui.page_title(p, "Configuracao Atual", C.NEON_CYAN, "")

        state.out = output_text(p)
        _ui.page_layout(p).addWidget(state.out, stretch=1)
        _ui.page_layout(p).addSpacing(10)

        btn = action_button(p, "↻  Carregar Configuracao Atual",
                            lambda: self.fetch_config(), C.NEON_CYAN)
        _ui.page_layout(p).addWidget(btn)

        return p

    def dispose(self) -> None:
        """Solta refs de widget no rebuild (estado lógico é preservado)."""
        self.state.out = None

    # ── Fachadas (usadas pelo shell: atalhos Enter/F5, Ctrl+L) ───────
    def fetch_config(self) -> None:
        """Despacha o fetch na IO thread (ctx.run cuida do guard)."""
        if self._ctx is None:
            return
        self._ctx.run(lambda: self._h().fetch_config())

    def out_widget(self) -> QTextEdit | None:
        """Widget de saída (Ctrl+L limpa a saída do config)."""
        return self.state.out

    # ── Internos ─────────────────────────────────────────────────────
    def _h(self) -> ConfigHandlers:
        if self._handlers is None:
            raise RuntimeError("ConfigTab não foi construído (build ausente)")
        return self._handlers
