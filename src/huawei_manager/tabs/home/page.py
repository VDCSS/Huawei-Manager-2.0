"""Aba Dashboard — módulo TabModule (F2-home).

Migrado de ``pages/builder.py`` (``_build_home_page``): a construção
virou ``HomeTab.build(ctx) -> QWidget`` e o refresh vive em
:class:`HomeHandlers`. O refresh roda direto na thread GUI (o timer do
shell chama a fachada sem ``ctx.run`` — não é operação de IO).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import huawei_manager.constants as C
from huawei_manager.tabs import _ui
from huawei_manager.tabs.home.handlers import HomeHandlers
from huawei_manager.tabs.home.state import HomeState
from huawei_manager.widgets.neon_button import action_button

if TYPE_CHECKING:
    from huawei_manager.tabs._contract import TabContext


class HomeTab:
    """Módulo da aba Dashboard (TabModule)."""

    def __init__(self) -> None:
        self.state = HomeState()
        self._ctx: TabContext | None = None
        self._handlers: HomeHandlers | None = None

    # ── TabModule ────────────────────────────────────────────────────
    def attach(self, ctx: TabContext) -> None:
        """Injeta o contexto (idempotente) — chamado por build e fachadas."""
        if self._ctx is None:
            self._ctx = ctx
            self._handlers = HomeHandlers(ctx, self.state)

    def build(self, ctx: TabContext) -> QWidget:
        """Constrói a página do Dashboard."""
        self.attach(ctx)
        state = self.state

        p = _ui.page_frame("home")
        _ui.page_title(p, "Dashboard", C.NEON_CYAN,
                       "Painel de controle — conectividade, Devices, operacoes recentes")

        row1 = QWidget(p)
        row1_layout = QHBoxLayout(row1)
        row1_layout.setContentsMargins(0, 0, 0, 0)
        _ui.page_layout(p).addWidget(row1, stretch=3)
        _ui.page_layout(p).addSpacing(10)

        def _make_card(parent: QWidget) -> tuple[QFrame, QVBoxLayout]:
            card = QFrame(parent)
            card.setStyleSheet(
                f"background: {C.BG_INPUT}; border: 1px solid {C.BORDER_NRM}; border-radius: 4px;")
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 10)
            card_layout.setSpacing(2)
            return card, card_layout

        def _card_title(card: QFrame, card_layout: QVBoxLayout, text: str, color: str) -> QLabel:
            lbl = QLabel(text, card)
            lbl.setStyleSheet(_ui.css_label(color, C.BG_INPUT, 12, True))
            card_layout.addWidget(lbl)
            card_layout.addSpacing(4)
            return lbl

        # Card: Conexao
        card1, card1_layout = _make_card(row1)
        _card_title(card1, card1_layout, "🔌 CONEXAO", C.NEON_CYAN)
        row1_layout.addWidget(card1)

        state.conn_status = QLabel("Desconectado", card1)
        state.conn_status.setStyleSheet(
            f"color: {C.NEON_RED}; font: bold 14px {C.FONT_UI_FAMILY};"
            f" background: {C.BG_INPUT};")
        card1_layout.addWidget(state.conn_status)

        state.conn_host = QLabel("Host: ---", card1)
        state.conn_host.setStyleSheet(_ui.css_label(C.FG_DIM, C.BG_INPUT, 11))
        card1_layout.addWidget(state.conn_host)
        card1_layout.addStretch()

        # Card: Devices
        card2, card2_layout = _make_card(row1)
        _card_title(card2, card2_layout, "📡 DISPOSITIVOS", C.NEON_MAG)
        row1_layout.addWidget(card2)

        state.device_online = QLabel("Online: 0", card2)
        state.device_online.setStyleSheet(_ui.css_label(C.NEON_CYAN, C.BG_INPUT, 11))
        card2_layout.addWidget(state.device_online)

        state.device_offline = QLabel("Offline: 0", card2)
        state.device_offline.setStyleSheet(_ui.css_label(C.NEON_RED, C.BG_INPUT, 11))
        card2_layout.addWidget(state.device_offline)

        state.device_unknown = QLabel("Desconhecido: 0", card2)
        state.device_unknown.setStyleSheet(_ui.css_label(C.NEON_AMBER, C.BG_INPUT, 11))
        card2_layout.addWidget(state.device_unknown)
        card2_layout.addStretch()

        # Card: Ultimas Operacoes
        card3, card3_layout = _make_card(row1)
        _card_title(card3, card3_layout, "📋 ULTIMAS OPERACOES", C.NEON_AMBER)
        row1_layout.addWidget(card3)

        state.audit_text = QTextEdit(card3)
        state.audit_text.setReadOnly(True)
        state.audit_text.setStyleSheet(f"""
            QTextEdit {{
                background: {C.BG_BASE}; color: {C.FG_CODE};
                border: 1px solid {C.BORDER_NRM}; border-radius: 4px;
                padding: 4px; font: {C.FONT_CAPTION}px {C.FONT_UI_FAMILY};
            }}
        """)
        state.audit_text.setMinimumHeight(60)
        card3_layout.addWidget(state.audit_text, stretch=1)

        # Card: Atalhos Rapidos (full width)
        card4 = QFrame(p)
        card4.setStyleSheet(
            f"background: {C.BG_INPUT}; border: 1px solid {C.BORDER_NRM}; border-radius: 4px;")
        card4_layout = QVBoxLayout(card4)
        card4_layout.setContentsMargins(12, 10, 12, 10)
        _ui.page_layout(p).addWidget(card4, stretch=2)

        _card_title(card4, card4_layout, "⌨ ATALHOS RAPIDOS", C.NEON_PURP)

        bar = QWidget(card4)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        card4_layout.addWidget(bar)

        state.shortcut_btns = {
            "config": "  📋 Config  ",
            "route":  "  🌐 Rotas   ",
            "backup": "  💾 Backup  ",
            "cmd":    "  ⌨  Editor  ",
        }
        for key, label in state.shortcut_btns.items():
            btn = action_button(bar, label,
                                lambda _chk, k=key: ctx.show_page(k),
                                C.FG_MAIN)
            bar_layout.addWidget(btn)
            bar_layout.addSpacing(6)
        bar_layout.addStretch()

        return p

    def dispose(self) -> None:
        """Solta refs de widget no rebuild (estado lógico é preservado)."""
        state = self.state
        state.conn_status = None
        state.conn_host = None
        state.device_online = None
        state.device_offline = None
        state.device_unknown = None
        state.audit_text = None
        state.shortcut_btns = {}

    # ── Fachadas (usadas pelo shell: timer de refresh do dashboard) ──
    def refresh(self) -> None:
        """Atualiza os cards na thread GUI (chamada direta — não é IO)."""
        if self._ctx is None:
            return
        self._h().refresh_dashboard()

    # ── Internos ─────────────────────────────────────────────────────
    def _h(self) -> HomeHandlers:
        if self._handlers is None:
            raise RuntimeError("HomeTab não foi construído (build ausente)")
        return self._handlers
