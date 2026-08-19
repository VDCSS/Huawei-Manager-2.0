#!/usr/bin/env python3
"""Page builders (PySide6) — all _build_*_page methods."""

from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import huawei_manager.constants as C
from huawei_manager._protocols import AppCoreProtocol
from huawei_manager.constants import ROUTE_FILTER_LABELS
from huawei_manager.pages.cmd import PageBuilderCmdMixin
from huawei_manager.pages.manutencao import PageBuilderManutencaoMixin
from huawei_manager.pages.services import PageBuilderServicesMixin
from huawei_manager.sdn_controller.authz import role_meets
from huawei_manager.topology import TopologyCanvas
from huawei_manager.widgets.elide_label import ElideLabel
from huawei_manager.widgets.neon_button import action_button
from huawei_manager.widgets.neon_entry import neon_entry, output_text


class PageBuilder(PageBuilderServicesMixin, PageBuilderManutencaoMixin, PageBuilderCmdMixin):
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
        assert isinstance(layout, QVBoxLayout)
        return layout

    def _page_title(self, parent: QWidget, title: str, color: str, subtitle: str = "") -> None:
        lbl = QLabel(title, parent)
        lbl.setStyleSheet(f"color: {color}; font: bold {C.FONT_TITLE}px 'Inter'; padding: 0px; margin: 0px;")
        parent.layout().addWidget(lbl)
        if subtitle:
            sub = QLabel(subtitle, parent)
            sub.setStyleSheet(f"color: {C.FG_DIM}; font: {C.FONT_SUBHEAD}px 'Inter'; padding: 0px;")
            parent.layout().addWidget(sub)
        parent.layout().addSpacing(8)

    def _css_label(self, color: str, bg: str = "", font_size: int = 12, bold: bool = False) -> str:
        weight = "bold" if bold else "normal"
        bg_css = f"background: {bg};" if bg else ""
        return f"color: {color}; {bg_css} font: {weight} {font_size}px 'Inter';"

    # ── Config ────────────────────────────────────────────────────────
    def _build_config_page(self: AppCoreProtocol) -> None:
        p = self._make_page("config")
        self._page_title(p, "Configuracao Atual", C.NEON_CYAN, "")
        self.out_config = output_text(p)
        self._page_layout(p).addWidget(self.out_config, stretch=1)
        self._page_layout(p).addSpacing(10)
        btn = action_button(p, "\u21bb  Carregar Configuracao Atual",
                            lambda: self._run(self._fetch_config), C.NEON_CYAN)
        self._page_layout(p).addWidget(btn)

    # ── Route ─────────────────────────────────────────────────────────
    def _build_route_page(self: AppCoreProtocol) -> None:
        p = self._make_page("route")
        self._page_title(p, "Tabelas e Status do Roteador", C.NEON_CYAN,
                         "Visualizacao de tabelas, vizinhos e metricas do dispositivo")
        row = QWidget(p)
        row.setStyleSheet(f"background: {C.BG_CARD};")
        row.setMaximumHeight(40)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        self._page_layout(p).addWidget(row)
        self._page_layout(p).addSpacing(8)

        lbl = QLabel("Filtro:", row)
        lbl.setStyleSheet(self._css_label(C.FG_DIM, C.BG_CARD, 11))
        row_layout.addWidget(lbl)
        row_layout.addSpacing(8)

        self.route_filter_var = "Tabela de Rotas do Roteador"
        self._route_filter_cb = QComboBox(row)
        self._route_filter_cb.setEditable(False)
        self._route_filter_cb.addItems(list(ROUTE_FILTER_LABELS.values()))
        self._route_filter_cb.setCurrentText(self.route_filter_var)
        self._route_filter_cb.setMinimumWidth(300)
        self._route_filter_cb.setStyleSheet(f"""
            QComboBox {{ background: {C.BG_INPUT}; color: {C.NEON_CYAN};
                         border: 1px solid {C.BORDER_NRM}; border-radius: 4px;
                         padding: 4px 8px; font: 11px 'Inter'; }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{ background: {C.BG_INPUT};
                                           color: {C.NEON_CYAN};
                                           selection-background-color: {C.NEON_PURP}; }}
        """)
        row_layout.addWidget(self._route_filter_cb)

        self.out_route = output_text(p)
        self._page_layout(p).addWidget(self.out_route, stretch=1)
        self._page_layout(p).addSpacing(10)
        btn = action_button(p, "\u21bb  Carregar",
                            lambda: self._run(
                                lambda fkey=(
                                    {v: k for k, v in ROUTE_FILTER_LABELS.items()}
                                    .get(self._route_filter_cb.currentText(), "routing")
                                ): self._fetch_route(fkey)), C.NEON_CYAN)
        self._page_layout(p).addWidget(btn)

    # ── ARP ───────────────────────────────────────────────────────────
    def _build_arp_page(self: AppCoreProtocol) -> None:
        p = self._make_page("arp")
        self._page_title(p, "Tabela ARP", C.NEON_CYAN, "CLI: display arp")
        self.out_arp = output_text(p)
        self._page_layout(p).addWidget(self.out_arp, stretch=1)
        self._page_layout(p).addSpacing(10)
        btn = action_button(p, "\u21bb  get arp",
                            lambda: self._run(self._fetch_arp), C.NEON_CYAN)
        self._page_layout(p).addWidget(btn)

    # ── Info ──────────────────────────────────────────────────────────
    def _build_info_page(self: AppCoreProtocol) -> None:
        p = self._make_page("info")
        self._page_title(p, "Informacoes do Sistema", C.NEON_MAG,
                         "CLI: display version / cpu-usage / memory-usage")
        self.out_info = output_text(p)
        self._page_layout(p).addWidget(self.out_info, stretch=1)
        self._page_layout(p).addSpacing(10)
        btn = action_button(p, "\u21bb  get system info",
                            lambda: self._run(self._fetch_info), C.NEON_MAG)
        self._page_layout(p).addWidget(btn)

    # ── Backup ────────────────────────────────────────────────────────
    def _build_backup_page(self: AppCoreProtocol) -> None:
        p = self._make_page("backup")
        self._page_title(p, "Backup de Configuracao", C.NEON_PURP,
                         "display current-configuration \u2192 arquivo")

        ctrl = QWidget(p)
        ctrl.setStyleSheet(f"background: {C.BG_CARD};")
        ctrl.setMaximumHeight(40)
        ctrl_layout = QHBoxLayout(ctrl)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        self._page_layout(p).addWidget(ctrl)
        self._page_layout(p).addSpacing(12)

        dest_lbl = QLabel("Destino:", ctrl)
        dest_lbl.setStyleSheet(self._css_label(C.FG_DIM, C.BG_CARD, 11))
        ctrl_layout.addWidget(dest_lbl)
        ctrl_layout.addSpacing(8)

        self._backup_entry = neon_entry(ctrl, width=24)
        self._backup_entry.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.backup_path = os.path.expanduser("~")
        self._backup_entry.setText(self.backup_path)
        self._backup_entry.textChanged.connect(lambda t: setattr(self, 'backup_path', t))
        ctrl_layout.addWidget(self._backup_entry)

        btn_dir = action_button(ctrl, "\U0001f4c1 Escolha",
                                self._choose_backup_dir, C.NEON_PURP)
        ctrl_layout.addWidget(btn_dir)
        ctrl_layout.addSpacing(8)

        fmt_frame = QWidget(p)
        fmt_frame.setStyleSheet(f"background: {C.BG_CARD};")
        fmt_frame.setMaximumHeight(40)
        fmt_layout = QHBoxLayout(fmt_frame)
        fmt_layout.setContentsMargins(0, 0, 0, 0)
        self._page_layout(p).addWidget(fmt_frame)
        self._page_layout(p).addSpacing(8)

        fmt_lbl = QLabel("Formato:", fmt_frame)
        fmt_lbl.setStyleSheet(self._css_label(C.FG_DIM, C.BG_CARD, 11))
        fmt_layout.addWidget(fmt_lbl)
        fmt_layout.addSpacing(8)

        self._backup_fmt_cb = QComboBox(fmt_frame)
        self._backup_fmt_cb.setEditable(False)
        self._backup_fmt_cb.addItems(["Texto (CLI)"])
        self._backup_fmt_cb.setStyleSheet(f"""
            QComboBox {{ background: {C.BG_INPUT}; color: {C.NEON_CYAN};
                         border: 1px solid {C.BORDER_NRM}; border-radius: 4px;
                         padding: 4px 8px; font: 11px 'Inter'; }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{ background: {C.BG_INPUT};
                                           color: {C.NEON_CYAN};
                                           selection-background-color: {C.NEON_PURP}; }}
        """)
        fmt_layout.addWidget(self._backup_fmt_cb)
        fmt_layout.addStretch()

        self.out_backup = output_text(p)
        self._page_layout(p).addWidget(self.out_backup, stretch=1)
        self._page_layout(p).addSpacing(10)
        btn = action_button(p, "\U0001f4be  Fazer Backup",
                            lambda: self._run(
                                lambda fmt=self._backup_fmt_cb.currentText(): self._do_backup(fmt)), C.NEON_PURP)
        self._page_layout(p).addWidget(btn)

    # ── Topology ──────────────────────────────────────────────────────
    def _build_topology_page(self: AppCoreProtocol) -> None:
        p = self._make_page("topology")
        self._page_title(p, "Topologia / Devices", C.NEON_AMBER,
                         "Cadastro manual + alvo SSH clicavel")

        ctrl = QWidget(p)
        ctrl.setStyleSheet(f"background: {C.BG_CARD};")
        ctrl_layout = QHBoxLayout(ctrl)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        self._page_layout(p).addWidget(ctrl)

        admin_label = "\U0001f512  Acesso"
        if role_meets(self._access_level, "tecnico"):
            admin_label = "\U0001f513  Admin" if self._access_level == "admin" else "\U0001f6e0  Tecnico"
        self._admin_btn = action_button(ctrl, admin_label,
                                        self._show_auth_dialog, C.NEON_PURP)
        ctrl_layout.addWidget(self._admin_btn)
        ctrl_layout.addSpacing(8)

        if role_meets(self._access_level, "tecnico"):
            cad_btn = action_button(ctrl, "\u2795  Cadastrar Dispositivo",
                                    lambda: self._show_device_dialog(), C.NEON_CYAN)
            ctrl_layout.addWidget(cad_btn)
            ctrl_layout.addSpacing(8)

        btn_refresh = action_button(ctrl, "\u21bb  Atualizar",
                                    lambda: self._spawn_io(self._refresh_devices),
                                    C.NEON_AMBER)
        ctrl_layout.addWidget(btn_refresh)
        ctrl_layout.addSpacing(8)
        btn_back = action_button(ctrl, "\u2716  Voltar",
                                 self._clear_device_target, C.NEON_PURP)
        ctrl_layout.addWidget(btn_back)

        ctrl_layout.addStretch()

        self._device_info_lbl = ElideLabel("  Nenhum device selecionado", ctrl)
        self._device_info_lbl.setStyleSheet(self._css_label(C.FG_DIM, C.BG_CARD, 11))
        self._device_info_lbl.setMinimumWidth(220)
        ctrl_layout.addWidget(self._device_info_lbl)
        ctrl_layout.addSpacing(8)

        self._topo_canvas = TopologyCanvas(
            p,
            on_select=self._on_device_selected,
            on_edit=self._show_device_dialog,
            on_delete=self._delete_device,
        )
        self._page_layout(p).addWidget(self._topo_canvas, stretch=1)

        self._device_status_lbl = QLabel("Invent\u00e1rio: 0 devices", p)
        self._device_status_lbl.setStyleSheet(self._css_label(C.NEON_AMBER, C.BG_CARD, 10))
        self._page_layout(p).addWidget(self._device_status_lbl)
        self._page_layout(p).addSpacing(4)

        self._spawn_io(self._refresh_devices)

    # ── Dashboard ─────────────────────────────────────────────────────
    def _build_home_page(self: AppCoreProtocol) -> None:
        p = self._make_page("home")
        self._page_title(p, "Dashboard", C.NEON_CYAN,
                         "Painel de controle — conectividade, Devices, operacoes recentes")

        self._dash_labels: dict[str, QLabel] = {}

        row1 = QWidget(p)
        row1_layout = QHBoxLayout(row1)
        row1_layout.setContentsMargins(0, 0, 0, 0)
        self._page_layout(p).addWidget(row1, stretch=3)
        self._page_layout(p).addSpacing(10)

        def _make_card(parent: QWidget) -> QFrame:
            card = QFrame(parent)
            card.setStyleSheet(f"background: {C.BG_INPUT}; border: 1px solid {C.BORDER_NRM}; border-radius: 4px;")
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            card._clayout = QVBoxLayout(card)
            card._clayout.setContentsMargins(12, 10, 12, 10)
            card._clayout.setSpacing(2)
            return card

        def _card_title(card: QFrame, text: str, color: str) -> QLabel:
            lbl = QLabel(text, card)
            lbl.setStyleSheet(self._css_label(color, C.BG_INPUT, 12, True))
            card._clayout.addWidget(lbl)
            card._clayout.addSpacing(4)
            return lbl

        # Card: Conexao
        card1 = _make_card(row1)
        _card_title(card1, "\U0001f50c CONEXAO", C.NEON_CYAN)
        row1_layout.addWidget(card1)

        self._dash_conn_status = QLabel("Desconectado", card1)
        self._dash_conn_status.setStyleSheet(f"color: {C.NEON_RED}; font: bold 14px 'Inter'; background: {C.BG_INPUT};")
        card1._clayout.addWidget(self._dash_conn_status)

        self._dash_conn_host = QLabel("Host: ---", card1)
        self._dash_conn_host.setStyleSheet(self._css_label(C.FG_DIM, C.BG_INPUT, 11))
        card1._clayout.addWidget(self._dash_conn_host)
        card1._clayout.addStretch()

        # Card: Devices
        card2 = _make_card(row1)
        _card_title(card2, "\U0001f4e1 DISPOSITIVOS", C.NEON_MAG)
        row1_layout.addWidget(card2)

        self._dash_device_online = QLabel("Online: 0", card2)
        self._dash_device_online.setStyleSheet(self._css_label(C.NEON_CYAN, C.BG_INPUT, 11))
        card2._clayout.addWidget(self._dash_device_online)

        self._dash_device_offline = QLabel("Offline: 0", card2)
        self._dash_device_offline.setStyleSheet(self._css_label(C.NEON_RED, C.BG_INPUT, 11))
        card2._clayout.addWidget(self._dash_device_offline)

        self._dash_device_unknown = QLabel("Desconhecido: 0", card2)
        self._dash_device_unknown.setStyleSheet(self._css_label(C.NEON_AMBER, C.BG_INPUT, 11))
        card2._clayout.addWidget(self._dash_device_unknown)
        card2._clayout.addStretch()

        # Card: Ultimas Operacoes
        card3 = _make_card(row1)
        _card_title(card3, "\U0001f4cb ULTIMAS OPERACOES", C.NEON_AMBER)
        row1_layout.addWidget(card3)

        self._dash_audit_text = QTextEdit(card3)
        self._dash_audit_text.setReadOnly(True)
        self._dash_audit_text.setStyleSheet(f"""
            QTextEdit {{
                background: {C.BG_BASE}; color: {C.FG_CODE};
                border: 1px solid {C.BORDER_NRM}; border-radius: 4px;
                padding: 4px; font: {C.FONT_CAPTION}px 'Inter';
            }}
        """)
        self._dash_audit_text.setMinimumHeight(60)
        card3._clayout.addWidget(self._dash_audit_text, stretch=1)

        # Card: Atalhos Rapidos (full width)
        card4 = QFrame(p)
        card4.setStyleSheet(f"background: {C.BG_INPUT}; border: 1px solid {C.BORDER_NRM}; border-radius: 4px;")
        card4_layout = QVBoxLayout(card4)
        card4_layout.setContentsMargins(12, 10, 12, 10)
        card4._clayout = card4_layout
        self._page_layout(p).addWidget(card4, stretch=2)

        _card_title(card4, "\u2328 ATALHOS RAPIDOS", C.NEON_PURP)

        bar = QWidget(card4)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        card4_layout.addWidget(bar)

        self._dash_shortcut_btns = {
            "config": "  \U0001f4cb Config  ",
            "route":  "  \U0001f310 Rotas   ",
            "backup": "  \U0001f4be Backup  ",
            "cmd":    "  \u2328  Editor  ",
        }
        for key, label in self._dash_shortcut_btns.items():
            btn = action_button(bar, label,
                                lambda _chk, k=key: self._show_page(k),
                                C.FG_MAIN)
            bar_layout.addWidget(btn)
            bar_layout.addSpacing(6)
        bar_layout.addStretch()

    # ── Backup helper ─────────────────────────────────────────────────
    def _choose_backup_dir(self: AppCoreProtocol) -> None:
        d = QFileDialog.getExistingDirectory(
            None, "Escolha o diretorio", self.backup_path)
        if d:
            self.backup_path = d
            self._backup_entry.setText(d)
