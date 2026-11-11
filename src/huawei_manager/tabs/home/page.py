"""Aba Dashboard — módulo TabModule (F2-home).

Migrado de ``pages/builder.py`` (``_build_home_page``): a construção
virou ``HomeTab.build(ctx) -> QWidget`` e o refresh vive em
:class:`HomeHandlers`. O refresh roda direto na thread GUI (o timer do
shell chama a fachada sem ``ctx.run`` — não é operação de IO).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt
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
from huawei_manager.widgets.icons import icon, icon_pixmap
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
                       "Painel de controle — conectividade, Devices, operações recentes")

        row1 = QWidget(p)
        row1.setStyleSheet("background: transparent;")
        row1_layout = QHBoxLayout(row1)
        row1_layout.setContentsMargins(0, 0, 0, 0)
        row1_layout.setSpacing(10)
        _ui.page_layout(p).addWidget(row1, stretch=3)
        _ui.page_layout(p).addSpacing(10)

        def _card_title(
            card: QFrame, card_layout: QVBoxLayout, text: str,
            color: str, icon_id: str = "",
        ) -> QLabel:
            """Topo do ``.stat-card``: label 11 px uppercase + ícone 38 px."""
            row = QWidget(card)
            row.setStyleSheet("background: transparent;")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)

            lbl = QLabel(text.upper(), row)
            lbl.setStyleSheet(
                f"color: {C.FG_DIM}; background: transparent;"
                f" font: 600 11px '{C.FONT_UI_FAMILY}'; letter-spacing: 0.06em;")
            row_layout.addWidget(lbl)
            row_layout.addStretch()

            if icon_id:
                box = QLabel(row)
                box.setFixedSize(38, 38)
                box.setAlignment(Qt.AlignmentFlag.AlignCenter)
                box.setPixmap(icon_pixmap(icon_id, color, 18))
                box.setStyleSheet(
                    f"background: {C.BG_SURFACE_3}; border: 1px solid {C.BORDER_NRM};"
                    f" border-radius: 6px;")
                row_layout.addWidget(box)

            card_layout.addWidget(row)
            card_layout.addSpacing(4)
            return lbl

        # Card: Conexao
        card1, card1_layout = _ui.card_frame(row1, accent=C.NEON_CYAN)
        card1.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        row1_layout.addWidget(card1)
        _card_title(card1, card1_layout, "Conexão", C.NEON_CYAN, "i-link")

        state.conn_status = _ui.stat_label(card1, "Desconectado", C.NEON_RED)
        card1_layout.addWidget(state.conn_status)

        state.conn_host = QLabel("Host: ---", card1)
        state.conn_host.setStyleSheet(_ui.css_label(C.FG_FAINT, "", 12))
        card1_layout.addWidget(state.conn_host)
        card1_layout.addStretch()

        # Card: Devices
        card2, card2_layout = _ui.card_frame(row1, accent=C.NEON_MAG)
        card2.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        row1_layout.addWidget(card2)
        _card_title(card2, card2_layout, "Dispositivos", C.NEON_MAG, "i-server")

        state.device_online = QLabel("Online: 0", card2)
        state.device_online.setStyleSheet(_ui.css_label(C.NEON_GREEN, "", 12.5, True))
        card2_layout.addWidget(state.device_online)

        state.device_offline = QLabel("Offline: 0", card2)
        state.device_offline.setStyleSheet(_ui.css_label(C.NEON_RED, "", 12.5, True))
        card2_layout.addWidget(state.device_offline)

        state.device_unknown = QLabel("Desconhecido: 0", card2)
        state.device_unknown.setStyleSheet(_ui.css_label(C.NEON_AMBER, "", 12.5, True))
        card2_layout.addWidget(state.device_unknown)
        card2_layout.addStretch()

        # Card: Ultimas Operacoes
        card3, card3_layout = _ui.card_frame(row1, accent=C.NEON_AMBER)
        card3.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        row1_layout.addWidget(card3)
        _card_title(card3, card3_layout, "Últimas operações", C.NEON_AMBER, "i-audit")

        state.audit_text = QTextEdit(card3)
        state.audit_text.setReadOnly(True)
        state.audit_text.setStyleSheet(f"""
            QTextEdit {{
                background: {C.BG_CODE}; color: {C.FG_CODE};
                border: 1px solid {C.BORDER_NRM}; border-radius: 8px;
                padding: 10px; font: 11px '{C.FONT_MONO_FAMILY}';
            }}
        """)
        state.audit_text.setMinimumHeight(72)
        card3_layout.addWidget(state.audit_text, stretch=1)

        # Card: Atalhos Rapidos (full width)
        card4, card4_layout = _ui.card_frame(p, accent=C.NEON_PURP)
        card4_layout.setContentsMargins(20, 18, 20, 18)
        _ui.page_layout(p).addWidget(card4, stretch=2)

        _card_title(card4, card4_layout, "Atalhos rápidos", C.NEON_PURP, "i-grid")

        bar = QWidget(card4)
        bar.setStyleSheet("background: transparent;")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        bar_layout.setSpacing(8)
        card4_layout.addWidget(bar)

        state.shortcut_btns = {
            "config": ("Configurações", "i-settings"),
            "route":  ("Rotas", "i-globe"),
            "backup": ("Backup", "i-archive"),
            "cmd":    ("Editor", "i-terminal"),
        }
        shortcut_colors = {
            "config": C.NEON_CYAN,
            "route": C.NEON_AMBER,
            "backup": C.NEON_PURP,
            "cmd": C.NEON_MAG,
        }
        for key, (label, icon_id) in state.shortcut_btns.items():
            color = shortcut_colors.get(key, C.FG_MAIN)
            btn = action_button(bar, label,
                                lambda _chk, k=key: ctx.show_page(k),
                                color)
            btn.setIcon(icon(icon_id, color, 16))
            btn.setIconSize(QSize(16, 16))
            bar_layout.addWidget(btn)
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
