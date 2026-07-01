#!/usr/bin/env python3
# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false
"""Page builders (PySide6) — all _build_*_page methods ported from pages.py."""

from __future__ import annotations

import os

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import huawei_manager.constants as C
from huawei_manager.constants import (
    CMD_TEMPLATES,
    ROUTE_FILTER_LABELS,
    SERVICE_CAT_LABELS,
)
from huawei_manager.services import (
    VNF_TYPES,
    ServiceDef,
    get_all_show_commands,
    get_categories_for,
    get_services_for,
    parse_params,
)
from huawei_manager.topology import TopologyCanvas
from huawei_manager.widgets import (
    action_button,
    neon_entry,
    output_text,
    styled_text,
)


class _CmdReturnFilter(QObject):
    """Event filter for cmd_editor: Enter runs command, Shift+Enter inserts newline."""

    def __init__(self, app_ref: object) -> None:
        super().__init__()
        self.app = app_ref

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.KeyPress:
            from PySide6.QtCore import Qt as _Qt

            if event.key() == _Qt.Key.Key_Return or event.key() == _Qt.Key.Key_Enter:
                if event.modifiers() & _Qt.KeyboardModifier.ShiftModifier:
                    cursor = obj.textCursor() if hasattr(obj, "textCursor") else None
                    if cursor:
                        cursor.insertText("\n")
                    return True
                else:
                    self.app._run(self.app._exec_cmd)
                    return True
        return super().eventFilter(obj, event)


class PageBuilder:
    """Mixin com métodos de construção das páginas da interface PySide6."""

    # ── Helpers ────────────────────────────────────────────────────────

    def _make_page(self, key: str) -> QWidget:
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
        """Retorna o QVBoxLayout de uma página criada por _make_page (narrow type p/ pyright)."""
        layout = p.layout()
        assert isinstance(layout, QVBoxLayout)
        return layout

    def _page_title(self, parent: QWidget, title: str, color: str, subtitle: str = "") -> None:
        """Cria título e subtítulo da página."""
        lbl = QLabel(title, parent)
        lbl.setStyleSheet(f"color: {color}; font: bold 16px 'Inter'; padding: 0px; margin: 0px;")
        parent.layout().addWidget(lbl)
        if subtitle:
            sub = QLabel(subtitle, parent)
            sub.setStyleSheet(f"color: {C.FG_DIM}; font: 11px 'Inter'; padding: 0px 0px 8px 0px;")
            parent.layout().addWidget(sub)

    def _css_label(self, color: str, bg: str = "", font_size: int = 12, bold: bool = False) -> str:
        weight = "bold" if bold else "normal"
        bg_css = f"background: {bg};" if bg else ""
        return f"color: {color}; {bg_css} font: {weight} {font_size}px 'Inter';"

    # ── Config ────────────────────────────────────────────────────────
    def _build_config_page(self) -> None:
        p = self._make_page("config")
        self._page_title(p, "Configuracao Atual", C.NEON_CYAN, "")
        self.out_config = output_text(p)
        self._page_layout(p).addWidget(self.out_config, stretch=1)
        self._page_layout(p).addSpacing(10)
        btn = action_button(p, "\u21bb  Carregar Configuracao Atual",
                            lambda: self._run(self._fetch_config), C.NEON_CYAN)
        self._page_layout(p).addWidget(btn)

    # ── Route ─────────────────────────────────────────────────────────
    def _build_route_page(self) -> None:
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
                            lambda: self._run(self._fetch_route), C.NEON_CYAN)
        self._page_layout(p).addWidget(btn)

    # ── ARP ───────────────────────────────────────────────────────────
    def _build_arp_page(self) -> None:
        p = self._make_page("arp")
        self._page_title(p, "Tabela ARP", C.NEON_CYAN, "CLI: display arp")
        self.out_arp = output_text(p)
        self._page_layout(p).addWidget(self.out_arp, stretch=1)
        self._page_layout(p).addSpacing(10)
        btn = action_button(p, "\u21bb  get arp",
                            lambda: self._run(self._fetch_arp), C.NEON_CYAN)
        self._page_layout(p).addWidget(btn)

    # ── Info ──────────────────────────────────────────────────────────
    def _build_info_page(self) -> None:
        p = self._make_page("info")
        self._page_title(p, "Informacoes do Sistema", C.NEON_MAG,
                         "CLI: display version / cpu-usage / memory-usage")
        self.out_info = output_text(p)
        self._page_layout(p).addWidget(self.out_info, stretch=1)
        self._page_layout(p).addSpacing(10)
        btn = action_button(p, "\u21bb  get system info",
                            lambda: self._run(self._fetch_info), C.NEON_MAG)
        self._page_layout(p).addWidget(btn)

    # ── Cmd / Editor ──────────────────────────────────────────────────
    def _build_cmd_page(self) -> None:
        p = self._make_page("cmd")
        self._page_title(p, "Editor de Comandos", C.NEON_MAG, "")

        card = QFrame(p)
        card.setStyleSheet(f"background: {C.BG_INPUT}; border: 1px solid {C.BORDER_NRM}; border-radius: 4px;")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 8, 12, 8)
        self._page_layout(p).addWidget(card, stretch=1)
        self._page_layout(p).addSpacing(8)

        split_w = QWidget(card)
        split_layout = QHBoxLayout(split_w)
        split_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.addWidget(split_w, stretch=1)

        # ── Left: template list ──
        left = QWidget(split_w)
        left.setFixedWidth(260)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left.setStyleSheet(f"background: {C.BG_INPUT};")
        split_layout.addWidget(left)
        split_layout.addSpacing(10)

        tpl_header = QLabel("COMANDOS DISPONIVEIS", left)
        tpl_header.setStyleSheet(self._css_label(C.FG_DIM, C.BG_INPUT, 10, True))
        left_layout.addWidget(tpl_header)

        scroll = QScrollArea(left)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"background: {C.BG_INPUT}; border: none;")
        left_layout.addWidget(scroll, stretch=1)

        tpl_inner = QWidget()
        tpl_inner.setStyleSheet(f"background: {C.BG_INPUT};")
        tpl_inner_layout = QVBoxLayout(tpl_inner)
        tpl_inner_layout.setContentsMargins(0, 0, 0, 0)
        tpl_inner_layout.setSpacing(0)
        scroll.setWidget(tpl_inner)

        self._tpl_selected: QLabel | None = None

        def _on_tpl_click(name: str, cmd: str) -> None:
            if self._tpl_selected is not None:
                self._tpl_selected.setStyleSheet(
                    self._css_label(C.NEON_CYAN, C.BG_INPUT, 12))
            for child in tpl_inner.findChildren(QLabel):
                if child.text() == name:
                    self._tpl_selected = child
                    child.setStyleSheet(
                        f"color: white; background: {C.NEON_PURP}; "
                        f"padding: 2px 8px; font: bold 12px 'Inter';")
                    break
            self._cmd_editor.setPlainText(cmd)

        _EXCLUDED_CMDS: set[str] = {
            "display current-configuration",
            "display version", "display device", "display license",
            "display cpu-usage", "display memory-usage",
            "display interface brief", "display lldp neighbor brief",
            "display arp",
            "display interface", "display counters interface",
            "display ip routing-table", "display bgp peer",
            "display ip vpn-instance", "display ospf peer",
            "display qos policy", "display mpls ldp peer",
        }

        self._tpl_cmd_map: dict[str, str] = {}
        for name in CMD_TEMPLATES:
            cmd = CMD_TEMPLATES[name]
            if cmd and cmd not in _EXCLUDED_CMDS:
                self._tpl_cmd_map[name] = cmd

        existing_cmds = set(self._tpl_cmd_map.values())
        show_cmds = get_all_show_commands()
        for svc_name, cmd in show_cmds:
            if cmd not in existing_cmds and cmd not in _EXCLUDED_CMDS:
                existing_cmds.add(cmd)
                self._tpl_cmd_map[svc_name] = cmd

        for name in sorted(self._tpl_cmd_map.keys()):
            lbl = QLabel(name, tpl_inner)
            lbl.setStyleSheet(self._css_label(C.NEON_CYAN, C.BG_INPUT, 12))
            lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            tpl_inner_layout.addWidget(lbl)
            cmd = self._tpl_cmd_map[name]
            lbl.mousePressEvent = lambda _e, _n=name, _c=cmd: _on_tpl_click(_n, _c)

        tpl_inner_layout.addStretch()

        # ── Right: editor + output ──
        right = QWidget(split_w)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right.setStyleSheet(f"background: {C.BG_INPUT};")
        split_layout.addWidget(right, stretch=1)

        self._cmd_editor = styled_text(right)
        self._cmd_editor.setMinimumHeight(150)
        self._cmd_editor.setPlainText("display ip interface brief")
        right_layout.addWidget(self._cmd_editor)
        right_layout.addSpacing(6)

        cmd_filter = _CmdReturnFilter(self)
        self._cmd_editor.installEventFilter(cmd_filter)

        abar = QWidget(right)
        abar_layout = QHBoxLayout(abar)
        abar_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(abar)
        right_layout.addSpacing(6)

        btn_exec = action_button(abar, "\u25b6 Executar",
                                 lambda: self._run(self._exec_cmd), C.NEON_CYAN)
        abar_layout.addWidget(btn_exec)
        abar_layout.addSpacing(6)
        btn_cfg = action_button(abar, "\u2699 Enviar Config",
                                lambda: self._run(self._exec_config), C.NEON_AMBER)
        abar_layout.addWidget(btn_cfg)

        self._sysview_var = False
        sysview_cb = QCheckBox("system-view", abar)
        sysview_cb.setStyleSheet(f"""
            QCheckBox {{ color: {C.FG_DIM}; background: {C.BG_INPUT}; font: 11px 'Inter'; }}
            QCheckBox::indicator {{ width: 14px; height: 14px; }}
        """)
        sysview_cb.stateChanged.connect(lambda s: setattr(self, '_sysview_var', bool(s)))
        abar_layout.addSpacing(12)
        abar_layout.addWidget(sysview_cb)
        abar_layout.addStretch()

        warn_lbl = QLabel("\u26a0  Todas as operacoes sao registradas em huawei_audit_structured.jsonl", right)
        warn_lbl.setStyleSheet(self._css_label(C.NEON_AMBER, C.BG_INPUT, 10))
        right_layout.addWidget(warn_lbl)
        right_layout.addSpacing(4)

        self.out_cmd = output_text(right)
        right_layout.addWidget(self.out_cmd, stretch=1)

    # ── Backup ────────────────────────────────────────────────────────
    def _build_backup_page(self) -> None:
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

        self._backup_entry = neon_entry(ctrl, width=44)
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
                            lambda: self._run(self._do_backup), C.NEON_PURP)
        self._page_layout(p).addWidget(btn)

    # ── Topology ──────────────────────────────────────────────────────
    def _build_topology_page(self) -> None:
        p = self._make_page("topology")
        self._page_title(p, "Topologia / VNFs", C.NEON_AMBER,
                         "Cadastro manual + alvo SSH clicavel")

        ctrl = QWidget(p)
        ctrl.setStyleSheet(f"background: {C.BG_CARD};")
        ctrl.setMaximumHeight(40)
        ctrl_layout = QHBoxLayout(ctrl)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        self._page_layout(p).addWidget(ctrl)
        self._page_layout(p).addSpacing(10)

        admin_label = "\U0001f512  Acesso"
        if self._access_level in ("admin", "tecnico"):
            admin_label = "\U0001f513  Admin" if self._access_level == "admin" else "\U0001f6e0  Tecnico"
        self._admin_btn = action_button(ctrl, admin_label,
                                        self._show_auth_dialog, C.NEON_PURP)
        ctrl_layout.addWidget(self._admin_btn)
        ctrl_layout.addSpacing(8)

        if self._access_level in ("admin", "tecnico"):
            cad_btn = action_button(ctrl, "\u2795  Cadastrar Dispositivo",
                                    lambda: self._show_device_dialog(), C.NEON_CYAN)
            ctrl_layout.addWidget(cad_btn)
            ctrl_layout.addSpacing(8)

        btn_refresh = action_button(ctrl, "\u21bb  Atualizar",
                                    lambda: self._spawn_io(self._refresh_vnfs),
                                    C.NEON_AMBER)
        ctrl_layout.addWidget(btn_refresh)
        ctrl_layout.addSpacing(8)
        btn_back = action_button(ctrl, "\u2716  Voltar",
                                 self._clear_vnf_target, C.NEON_PURP)
        ctrl_layout.addWidget(btn_back)

        ctrl_layout.addStretch()

        self._vnf_info_lbl = QLabel("  Nenhum VNF selecionado", ctrl)
        self._vnf_info_lbl.setStyleSheet(self._css_label(C.FG_DIM, C.BG_CARD, 11))
        ctrl_layout.addWidget(self._vnf_info_lbl)
        ctrl_layout.addSpacing(8)

        self._topo_canvas = TopologyCanvas(
            p,
            on_select=self._on_vnf_selected,
            on_edit=self._show_device_dialog,
            on_delete=self._delete_device,
        )
        self._page_layout(p).addWidget(self._topo_canvas, stretch=1)

        self._vnf_status_lbl = QLabel("Inventario: vnf_inventory.json", p)
        self._vnf_status_lbl.setStyleSheet(self._css_label(C.NEON_AMBER, C.BG_CARD, 10))
        self._page_layout(p).addWidget(self._vnf_status_lbl)
        self._page_layout(p).addSpacing(4)

        self._spawn_io(self._refresh_vnfs)

    # ── Services: sub-builders ────────────────────────────────────────
    def _build_services_info_row(self, parent: QWidget) -> None:
        info_row = QWidget(parent)
        info_row.setStyleSheet(f"background: {C.BG_CARD};")
        info_row.setMaximumHeight(40)
        info_layout = QHBoxLayout(info_row)
        info_layout.setContentsMargins(0, 0, 0, 0)
        parent.layout().addWidget(info_row)
        parent.layout().addSpacing(10)

        self._svc_vnf_lbl = QLabel("VNF: (selecione um VNF na aba Topologia)", info_row)
        self._svc_vnf_lbl.setStyleSheet(self._css_label(C.NEON_AMBER, C.BG_CARD, 12, True))
        info_layout.addWidget(self._svc_vnf_lbl)
        info_layout.addSpacing(16)

        self._svc_type_lbl = QLabel("Tipo: \u2014", info_row)
        self._svc_type_lbl.setStyleSheet(self._css_label(C.FG_DIM, C.BG_CARD, 11))
        info_layout.addWidget(self._svc_type_lbl)
        info_layout.addSpacing(16)

        self._svc_status_lbl = QLabel("", info_row)
        self._svc_status_lbl.setStyleSheet(self._css_label(C.FG_DIM, C.BG_CARD, 11))
        info_layout.addWidget(self._svc_status_lbl)
        info_layout.addStretch()

    def _build_services_filter_row(self, parent: QWidget) -> None:
        filt_row = QWidget(parent)
        filt_row.setStyleSheet(f"background: {C.BG_CARD};")
        filt_row.setMaximumHeight(40)
        filt_layout = QHBoxLayout(filt_row)
        filt_layout.setContentsMargins(0, 0, 0, 0)
        parent.layout().addWidget(filt_row)
        parent.layout().addSpacing(8)

        cat_lbl = QLabel("Categoria:", filt_row)
        cat_lbl.setStyleSheet(self._css_label(C.FG_DIM, C.BG_CARD, 11))
        filt_layout.addWidget(cat_lbl)
        filt_layout.addSpacing(8)

        self._svc_cat_var = "Todas as Categorias"
        self._svc_cat_cb = QComboBox(filt_row)
        self._svc_cat_cb.setEditable(False)
        self._svc_cat_cb.addItems(["Todas as Categorias"])
        self._svc_cat_cb.setMinimumWidth(180)
        self._svc_cat_cb.setStyleSheet(f"""
            QComboBox {{ background: {C.BG_INPUT}; color: {C.NEON_CYAN};
                         border: 1px solid {C.BORDER_NRM}; border-radius: 4px;
                         padding: 4px 8px; font: 11px 'Inter'; }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{ background: {C.BG_INPUT};
                                           color: {C.NEON_CYAN};
                                           selection-background-color: {C.NEON_PURP}; }}
        """)
        self._svc_cat_cb.currentTextChanged.connect(self._on_svc_cat_changed)
        filt_layout.addWidget(self._svc_cat_cb)
        filt_layout.addSpacing(12)

        self._svc_refresh_btn = action_button(filt_row,
                                              "\u21bb  Atualizar servicos",
                                              self._refresh_service_list, C.NEON_AMBER)
        filt_layout.addWidget(self._svc_refresh_btn)
        filt_layout.addSpacing(8)

        self._svc_mode_var = "mock"
        self._svc_mode_cb = QComboBox(filt_row)
        self._svc_mode_cb.setEditable(False)
        self._svc_mode_cb.addItems(["mock", "cli"])
        self._svc_mode_cb.setStyleSheet(f"""
            QComboBox {{ background: {C.BG_INPUT}; color: {C.NEON_CYAN};
                         border: 1px solid {C.BORDER_NRM}; border-radius: 4px;
                         padding: 4px 8px; font: 11px 'Inter'; }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{ background: {C.BG_INPUT};
                                           color: {C.NEON_CYAN};
                                           selection-background-color: {C.NEON_PURP}; }}
        """)
        self._svc_mode_cb.currentTextChanged.connect(
            lambda t: setattr(self, '_svc_mode_var', t))
        filt_layout.addWidget(self._svc_mode_cb)
        filt_layout.addSpacing(4)

        mode_lbl = QLabel("Modo:", filt_row)
        mode_lbl.setStyleSheet(self._css_label(C.FG_DIM, C.BG_CARD, 11))
        filt_layout.addWidget(mode_lbl)
        filt_layout.addStretch()

    def _build_services_split(self, parent: QWidget) -> None:
        card = QFrame(parent)
        card.setStyleSheet(f"background: {C.BG_INPUT}; border: 1px solid {C.BORDER_NRM}; border-radius: 4px;")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 8, 12, 8)
        parent_layout = parent.layout()
        assert isinstance(parent_layout, QVBoxLayout)
        parent_layout.addWidget(card, stretch=1)
        parent.layout().addSpacing(8)

        split = QWidget(card)
        split_layout = QHBoxLayout(split)
        split_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.addWidget(split, stretch=1)

        left = QWidget(split)
        left.setFixedWidth(280)
        left.setStyleSheet(f"background: {C.BG_INPUT};")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        split_layout.addWidget(left)
        split_layout.addSpacing(10)

        svc_header = QLabel("SERVI\u00c7OS", left)
        svc_header.setStyleSheet(self._css_label(C.FG_DIM, C.BG_INPUT, 10, True))
        left_layout.addWidget(svc_header)

        self._svc_listbox = QListWidget(left)
        self._svc_listbox.setStyleSheet(f"""
            QListWidget {{
                background: {C.BG_INPUT}; color: {C.NEON_CYAN};
                border: none; font: 12px 'Inter';
                outline: none;
            }}
            QListWidget::item:selected {{
                background: {C.NEON_PURP}; color: white;
            }}
            QListWidget::item:hover {{
                background: #2a2a4a;
            }}
        """)
        left_layout.addWidget(self._svc_listbox, stretch=1)
        self._svc_listbox.currentRowChanged.connect(self._on_service_select)

        right = QWidget(split)
        right.setStyleSheet(f"background: {C.BG_INPUT};")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        split_layout.addWidget(right, stretch=1)

        self._svc_detail_frame = QWidget(right)
        self._svc_detail_frame.setStyleSheet(f"background: {C.BG_INPUT};")
        self._svc_detail_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        detail_layout = QVBoxLayout(self._svc_detail_frame)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self._svc_detail_frame, stretch=1)

        self._svc_param_entries: dict[str, QLineEdit] = {}
        self._svc_services: list[ServiceDef] = []
        self._svc_current_svc: ServiceDef | None = None

    # ── Services: main page ───────────────────────────────────────────
    def _build_services_page(self) -> None:
        p = self._make_page("services")
        self._page_title(p, "Catalogo de Servicos", C.NEON_AMBER,
                         "Comandos SHOW e CONFIG por tipo de VNF "
                         "(ROUTER | SWITCH | FIREWALL | \u2026)")

        self._build_services_info_row(p)
        self._build_services_filter_row(p)
        self._build_services_split(p)

        self._svc_output = output_text(p)
        self._page_layout(p).addWidget(self._svc_output)
        self._page_layout(p).addSpacing(4)

        QTimer.singleShot(500, self._refresh_service_list)

    # ── Services: listbox population ──────────────────────────────────
    def _refresh_service_list(self) -> None:
        self._svc_listbox.clear()
        self._svc_services.clear()

        vnf = self._target_vnf
        if not vnf:
            self._svc_vnf_lbl.setText("VNF: (nenhum selecionado)")
            self._svc_type_lbl.setText("Tipo: \u2014")
            self._svc_cat_cb.blockSignals(True)
            self._svc_cat_cb.clear()
            self._svc_cat_cb.addItems(["Todas as Categorias"])
            self._svc_cat_cb.blockSignals(False)
            self._clear_detail_panel()
            return

        vnf_type = vnf.type.upper()
        host_info = f"{vnf.host}:{vnf.port}" if self._access_level in ("admin", "tecnico") else vnf.host
        self._svc_vnf_lbl.setText(f"VNF: {vnf.name} ({host_info})")
        self._svc_type_lbl.setText(f"Tipo: {VNF_TYPES.get(vnf_type, vnf_type)}")

        status_color = {"online": C.NEON_CYAN, "offline": "#ff4d4d",
                        "unknown": C.NEON_AMBER}.get(vnf.status, C.NEON_AMBER)
        self._svc_status_lbl.setText(f"Status: {vnf.status}")
        self._svc_status_lbl.setStyleSheet(
            f"color: {status_color}; background: {C.BG_CARD}; font: 11px 'Inter';")

        all_cats = get_categories_for(vnf_type)
        config_cats = [c for c in all_cats if c.startswith("config-")]
        cat_labels = [SERVICE_CAT_LABELS.get(c, c) for c in config_cats]
        all_labels = ["Todas as Categorias"] + cat_labels

        self._svc_cat_cb.blockSignals(True)
        self._svc_cat_cb.clear()
        self._svc_cat_cb.addItems(all_labels)
        if self._svc_cat_var in all_labels:
            self._svc_cat_cb.setCurrentText(self._svc_cat_var)
        else:
            self._svc_cat_cb.setCurrentText("Todas as Categorias")
            self._svc_cat_var = "Todas as Categorias"
        self._svc_cat_cb.blockSignals(False)

        selected_cat = self._svc_cat_var
        label_to_cat = {v: k for k, v in SERVICE_CAT_LABELS.items()}
        cat_filter = None if selected_cat == "Todas as Categorias" else label_to_cat.get(selected_cat)
        services = get_services_for(vnf_type, category=cat_filter)
        services = [s for s in services if s.config_mode]
        self._svc_services = services

        if not services:
            self._svc_listbox.addItem("  Nenhum servico de configuracao para este tipo de VNF")
            self._clear_detail_panel()
            return

        for svc in services:
            self._svc_listbox.addItem(f"  \u2699 {svc.name}")

        self._svc_listbox.setCurrentRow(0)

    def _on_svc_cat_changed(self, text: str) -> None:
        self._svc_cat_var = text
        self._refresh_service_list()

    def _on_service_select(self, row: int) -> None:
        if row < 0 or row >= len(self._svc_services):
            self._clear_detail_panel()
            return
        svc = self._svc_services[row]
        self._svc_current_svc = svc
        self._show_service_detail(svc)

    def _clear_detail_panel(self) -> None:
        layout = self._svc_detail_frame.layout()
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                if item and item.widget():
                    item.widget().deleteLater()
        self._svc_param_entries.clear()
        self._svc_current_svc = None

    def _show_service_detail(self, svc: ServiceDef) -> None:
        self._clear_detail_panel()
        p = self._svc_detail_frame
        p_layout = self._page_layout(p)

        mode_label = "Configurando" if svc.config_mode else "Executando"
        title_color = C.NEON_AMBER if svc.config_mode else C.NEON_CYAN

        title_lbl = QLabel(f"{mode_label}: {svc.name}", p)
        title_lbl.setStyleSheet(self._css_label(title_color, C.BG_INPUT, 13, True))
        p_layout.addWidget(title_lbl, alignment=Qt.AlignLeft)
        p_layout.addSpacing(4)

        cat_lbl = QLabel(f"Categoria: {svc.category}", p)
        cat_lbl.setStyleSheet(self._css_label(C.NEON_PURP, C.BG_INPUT, 10))
        p_layout.addWidget(cat_lbl, alignment=Qt.AlignLeft)
        p_layout.addSpacing(2)

        cmd_frame = QFrame(p)
        cmd_frame.setStyleSheet(f"background: {C.BG_INPUT}; border: 1px solid {C.BORDER_NRM}; border-radius: 4px;")
        cmd_frame_layout = QVBoxLayout(cmd_frame)
        cmd_frame_layout.setContentsMargins(8, 6, 8, 6)
        p_layout.addWidget(cmd_frame)
        p_layout.addSpacing(8)

        desc_lbl = QLabel(svc.description, cmd_frame)
        desc_lbl.setStyleSheet(self._css_label(C.FG_CODE, C.BG_INPUT, 11))
        desc_lbl.setWordWrap(True)
        cmd_frame_layout.addWidget(desc_lbl)

        if svc.config_mode:
            self._build_param_fields(p, svc)

        abar = QWidget(p)
        abar_layout = QHBoxLayout(abar)
        abar_layout.setContentsMargins(0, 0, 0, 0)
        p_layout.addWidget(abar)
        p_layout.addSpacing(4)

        btn_svc_exec = action_button(abar, f"\u25b6 {mode_label}",
                                     lambda s=svc: self._run_service(s),
                                     C.NEON_CYAN)
        abar_layout.addWidget(btn_svc_exec)
        abar_layout.addSpacing(6)
        btn_svc_clr = action_button(abar, "\u2716  Limpar output",
                                    lambda: self._write(self._svc_output, ""),
                                    C.NEON_PURP)
        abar_layout.addWidget(btn_svc_clr)

    def _build_param_fields(self, parent: QWidget, svc: ServiceDef) -> None:
        params = parse_params(svc)
        if not params:
            return

        pf = QFrame(parent)
        pf.setStyleSheet(f"background: {C.BG_INPUT}; border: 1px solid {C.BORDER_NRM}; border-radius: 4px;")
        pf_layout = QVBoxLayout(pf)
        pf_layout.setContentsMargins(8, 4, 8, 4)
        parent.layout().addWidget(pf)
        parent.layout().addSpacing(8)

        param_header = QLabel("PAR\u00c2METROS", pf)
        param_header.setStyleSheet(self._css_label(C.FG_DIM, C.BG_INPUT, 10, True))
        pf_layout.addWidget(param_header)

        self._svc_param_entries.clear()
        for label, default in params:
            row = QWidget(pf)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 2, 0, 2)
            pf_layout.addWidget(row)

            lbl = QLabel(f"{label}:", row)
            lbl.setFixedWidth(100)
            lbl.setStyleSheet(self._css_label(C.FG_DIM, C.BG_INPUT, 11))
            row_layout.addWidget(lbl)

            entry = QLineEdit(row)
            entry.setText(default)
            entry.setStyleSheet(f"""
                QLineEdit {{
                    background: {C.BG_BASE}; color: {C.NEON_CYAN};
                    border: 1px solid {C.BORDER_NRM}; border-radius: 3px;
                    padding: 3px 6px; font: 12px 'Inter';
                }}
                QLineEdit:focus {{
                    border: 1px solid {C.NEON_CYAN};
                }}
            """)
            row_layout.addWidget(entry, stretch=1)
            self._svc_param_entries[label] = entry

    # ── Dashboard ─────────────────────────────────────────────────────
    def _build_home_page(self) -> None:
        p = self._make_page("home")
        self._page_title(p, "Dashboard", C.NEON_CYAN,
                         "Painel de controle — conectividade, VNFs, operacoes recentes")

        self._dash_labels: dict[str, QLabel] = {}

        row1 = QWidget(p)
        row1_layout = QHBoxLayout(row1)
        row1_layout.setContentsMargins(0, 0, 0, 0)
        self._page_layout(p).addWidget(row1, stretch=1)
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

        # ── Card: Conexão ──
        card1 = _make_card(row1)
        _card_title(card1, "\U0001f50c CONEXAO", C.NEON_CYAN)
        row1_layout.addWidget(card1)

        self._dash_conn_status = QLabel("Desconectado", card1)
        self._dash_conn_status.setStyleSheet(f"color: #ff4d4d; font: bold 14px 'Inter'; background: {C.BG_INPUT};")
        card1._clayout.addWidget(self._dash_conn_status)

        self._dash_conn_host = QLabel("Host: ---", card1)
        self._dash_conn_host.setStyleSheet(self._css_label(C.FG_DIM, C.BG_INPUT, 11))
        card1._clayout.addWidget(self._dash_conn_host)
        card1._clayout.addStretch()

        # ── Card: VNFs ──
        card2 = _make_card(row1)
        _card_title(card2, "\U0001f4e1 VNFs", C.NEON_MAG)
        row1_layout.addWidget(card2)

        self._dash_vnf_online = QLabel("Online: 0", card2)
        self._dash_vnf_online.setStyleSheet(self._css_label(C.NEON_CYAN, C.BG_INPUT, 11))
        card2._clayout.addWidget(self._dash_vnf_online)

        self._dash_vnf_offline = QLabel("Offline: 0", card2)
        self._dash_vnf_offline.setStyleSheet(self._css_label("#ff4d4d", C.BG_INPUT, 11))
        card2._clayout.addWidget(self._dash_vnf_offline)

        self._dash_vnf_unknown = QLabel("Desconhecido: 0", card2)
        self._dash_vnf_unknown.setStyleSheet(self._css_label(C.NEON_AMBER, C.BG_INPUT, 11))
        card2._clayout.addWidget(self._dash_vnf_unknown)
        card2._clayout.addStretch()

        # ── Card: Últimas Operações ──
        card3 = _make_card(row1)
        _card_title(card3, "\U0001f4cb ULTIMAS OPERACOES", C.NEON_AMBER)
        row1_layout.addWidget(card3)

        self._dash_audit_text = QTextEdit(card3)
        self._dash_audit_text.setReadOnly(True)
        self._dash_audit_text.setStyleSheet(f"""
            QTextEdit {{
                background: {C.BG_BASE}; color: {C.FG_CODE};
                border: 1px solid {C.BORDER_NRM}; border-radius: 4px;
                padding: 4px; font: 10px 'Inter';
            }}
        """)
        self._dash_audit_text.setMinimumHeight(80)
        card3._clayout.addWidget(self._dash_audit_text, stretch=1)

        # ── Card: Atalhos Rápidos (full width) ──
        card4 = QFrame(p)
        card4.setStyleSheet(f"background: {C.BG_INPUT}; border: 1px solid {C.BORDER_NRM}; border-radius: 4px;")
        card4_layout = QVBoxLayout(card4)
        card4_layout.setContentsMargins(12, 10, 12, 10)
        card4._clayout = card4_layout  # para compatibilidade com _card_title
        self._page_layout(p).addWidget(card4)

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

    # ── Manutenção ─────────────────────────────────────────────────────
    def _build_manutencao_page(self) -> None:
        if self._access_level == "user":
            p = self._make_page("manutencao")
            self._page_title(p, "Acesso Restrito", C.NEON_AMBER)

            lbl = QLabel("\U0001f512  Esta pagina e exclusiva para usuarios Tecnico ou Admin.", p)
            lbl.setStyleSheet(self._css_label(C.FG_DIM, C.BG_CARD, 13))
            lbl.setAlignment(Qt.AlignCenter)
            self._page_layout(p).addSpacing(40)
            self._page_layout(p).addWidget(lbl)
            self._page_layout(p).addSpacing(10)

            btn = action_button(p, "\U0001f511  Autenticar como Tecnico / Admin",
                                self._show_auth_dialog, C.NEON_PURP)
            self._page_layout(p).addWidget(btn, alignment=Qt.AlignCenter)
            return

        p = self._make_page("manutencao")
        self._page_title(p, "Manutencao e Diagnostico", C.NEON_MAG,
                         "Testes + Agentes + Setup")

        top = QWidget(p)
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        self._page_layout(p).addWidget(top)
        self._page_layout(p).addSpacing(12)

        # ── Group: DEV ──
        grp_dev = QGroupBox("  DEV  ", top)
        grp_dev.setStyleSheet(f"""
            QGroupBox {{
                background: {C.BG_CARD}; color: {C.NEON_CYAN};
                font: bold 10px 'Inter'; border: 1px solid {C.BORDER_NRM};
                border-radius: 4px; margin-top: 8px; padding: 12px 4px 4px 4px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; subcontrol-position: top left;
                padding: 0 6px;
            }}
        """)
        grp_dev_layout = QHBoxLayout(grp_dev)
        grp_dev_layout.setContentsMargins(4, 4, 4, 4)
        top_layout.addWidget(grp_dev)

        btn_lint = action_button(grp_dev, "\u2699  Lint",
                                 lambda: self._run_dev_cmd("lint"), C.NEON_CYAN)
        grp_dev_layout.addWidget(btn_lint)
        grp_dev_layout.addSpacing(4)
        btn_test = action_button(grp_dev, "\U0001f9ea  Testes",
                                 lambda: self._run_dev_cmd("test"), C.NEON_MAG)
        grp_dev_layout.addWidget(btn_test)
        grp_dev_layout.addSpacing(4)
        btn_types = action_button(grp_dev, "\U0001f50d  Types",
                                  lambda: self._run_dev_cmd("typecheck"), C.NEON_PURP)
        grp_dev_layout.addWidget(btn_types)
        grp_dev_layout.addSpacing(4)
        btn_all = action_button(grp_dev, "\u25b6  Todos",
                                lambda: self._run_dev_cmd("all"), C.NEON_AMBER)
        grp_dev_layout.addWidget(btn_all)

        # ── Group: AGENTES ──
        grp_agents = QGroupBox("  AGENTES  ", top)
        grp_agents.setStyleSheet(f"""
            QGroupBox {{
                background: {C.BG_CARD}; color: {C.NEON_PURP};
                font: bold 10px 'Inter'; border: 1px solid {C.BORDER_NRM};
                border-radius: 4px; margin-top: 8px; padding: 12px 4px 4px 4px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; subcontrol-position: top left;
                padding: 0 6px;
            }}
        """)
        grp_agents_layout = QHBoxLayout(grp_agents)
        grp_agents_layout.setContentsMargins(4, 4, 4, 4)
        top_layout.addWidget(grp_agents)

        btn_agents = action_button(grp_agents, "\U0001f50d  Agora",
                                   lambda: self._run_agents(), C.NEON_PURP)
        grp_agents_layout.addWidget(btn_agents)
        grp_agents_layout.addSpacing(4)
        self._watcher_btn = action_button(grp_agents, "\U0001f504  Auto: ON",
                                          self._toggle_watcher, C.NEON_CYAN)
        grp_agents_layout.addWidget(self._watcher_btn)

        # ── Group: SETUP ──
        grp_setup = QGroupBox("  SETUP  ", top)
        grp_setup.setStyleSheet(f"""
            QGroupBox {{
                background: {C.BG_CARD}; color: {C.NEON_AMBER};
                font: bold 10px 'Inter'; border: 1px solid {C.BORDER_NRM};
                border-radius: 4px; margin-top: 8px; padding: 12px 4px 4px 4px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; subcontrol-position: top left;
                padding: 0 6px;
            }}
        """)
        grp_setup_layout = QHBoxLayout(grp_setup)
        grp_setup_layout.setContentsMargins(4, 4, 4, 4)
        top_layout.addWidget(grp_setup)

        btn_check = action_button(grp_setup, "\U0001f4cb  Check",
                                  lambda: self._run_setup("check"), C.NEON_AMBER)
        grp_setup_layout.addWidget(btn_check)
        grp_setup_layout.addSpacing(4)
        btn_install = action_button(grp_setup, "\u2699  Install",
                                    lambda: self._run_setup("install"), C.NEON_CYAN)
        grp_setup_layout.addWidget(btn_install)
        grp_setup_layout.addSpacing(4)
        btn_reset = action_button(grp_setup, "\U0001f504  Reset",
                                  lambda: self._run_setup("reset"), C.NEON_MAG)
        grp_setup_layout.addWidget(btn_reset)

        # Summary
        summary_frame = QFrame(p)
        summary_frame.setStyleSheet(f"background: {C.BG_CARD}; border: 1px solid {C.BORDER_NRM}; border-radius: 4px;")
        summary_layout = QVBoxLayout(summary_frame)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        self._page_layout(p).addWidget(summary_frame)
        self._page_layout(p).addSpacing(10)

        self._manut_summary = QTextEdit(summary_frame)
        self._manut_summary.setReadOnly(True)
        self._manut_summary.setMaximumHeight(100)
        self._manut_summary.setStyleSheet(f"""
            QTextEdit {{
                background: {C.BG_INPUT}; color: {C.FG_CODE};
                border: none; font: 11px 'Inter'; padding: 8px 10px;
            }}
        """)
        summary_layout.addWidget(self._manut_summary)

        # Filter bar
        filter_frame = QFrame(p)
        filter_frame.setStyleSheet(f"background: {C.BG_CARD}; border: 1px solid {C.BORDER_NRM}; border-radius: 4px;")
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setContentsMargins(8, 2, 8, 2)
        self._page_layout(p).addWidget(filter_frame)
        self._page_layout(p).addSpacing(4)

        filt_lbl = QLabel("  Filtro:", filter_frame)
        filt_lbl.setStyleSheet(self._css_label(C.FG_DIM, C.BG_CARD, 10, True))
        filter_layout.addWidget(filt_lbl)
        filter_layout.addSpacing(2)

        self._manut_filter = "all"
        filter_vals = [
            ("all",    "Todas",    C.FG_MAIN),
            ("error",  "Erros",    C.NEON_AMBER),
            ("warning","Avisos",   C.NEON_MAG),
            ("info",   "Info",     C.NEON_CYAN),
        ]
        self._manut_rb_group: list[QRadioButton] = []
        for fval, flbl, fcol in filter_vals:
            rb = QRadioButton(flbl, filter_frame)
            rb.setStyleSheet(f"""
                QRadioButton {{
                    color: {fcol}; background: {C.BG_CARD};
                    font: 10px 'Inter'; spacing: 2px;
                }}
                QRadioButton::indicator {{ width: 12px; height: 12px; }}
            """)
            if fval == "all":
                rb.setChecked(True)
            rb.toggled.connect(lambda checked, v=fval: self._on_manut_filter_toggled(checked, v))
            filter_layout.addWidget(rb)
            filter_layout.addSpacing(4)
            self._manut_rb_group.append(rb)
        filter_layout.addStretch()

        # Output
        output_frame = QFrame(p)
        output_frame.setStyleSheet(f"background: {C.BG_CARD}; border: 1px solid {C.BORDER_NRM}; border-radius: 4px;")
        output_layout = QVBoxLayout(output_frame)
        output_layout.setContentsMargins(8, 4, 8, 4)
        self._page_layout(p).addWidget(output_frame, stretch=1)
        self._page_layout(p).addSpacing(4)

        self._manut_output = output_text(output_frame)
        output_layout.addWidget(self._manut_output, stretch=1)

        # Bottom bar
        bottom = QWidget(p)
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        self._page_layout(p).addWidget(bottom)

        btn_limpar = action_button(bottom, "\u2716  Limpar",
                                   lambda: self._cancel_and_clear(), C.NEON_PURP)
        bottom_layout.addWidget(btn_limpar)
        bottom_layout.addStretch()

        if self._watcher_results:
            self._display_watcher_results(self._watcher_results)
        else:
            self._loading(self._manut_output, "Pronto. Clique em 'Agora' para varrer o projeto.")
            if self._watcher.is_active:
                self._loading(self._manut_output, "Watcher ativo — resultados em ate 60s...")

    def _on_manut_filter_toggled(self, checked: bool, value: str) -> None:
        if checked:
            self._manut_filter = value
            self._apply_manut_filter()

    def _run_dev_cmd(self, target: str) -> None:
        import subprocess
        import threading

        from huawei_manager._config import PROJECT_ROOT

        if getattr(self, "_dev_process", None) is not None:
            try:
                self._dev_process.kill()
            except Exception:
                pass
            self._dev_process = None

        cmds = {
            "lint":      ["make", "lint"],
            "test":      ["make", "test"],
            "typecheck": ["make", "typecheck"],
            "all":       ["make", "ci"],
        }
        cmd_list = cmds.get(target, ["true"])
        self._loading(self._manut_output, f"Executando: {' '.join(cmd_list)}...")

        def target_fn():
            buf: list[str] = []
            lock = threading.Lock()

            def _flush() -> None:
                with lock:
                    text = "\n".join(buf)
                    if text:
                        self._dispatch(lambda t=text: (
                            self._manut_output.clear(),
                            self._manut_output.setPlainText(t),
                        ))

            try:
                proc = subprocess.Popen(
                    cmd_list, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, cwd=str(PROJECT_ROOT),
                )
                self._dev_process = proc
                assert proc.stdout is not None
                for line in proc.stdout:
                    if proc.poll() is not None and not line:
                        break
                    buf.append(line.rstrip("\n"))
                    # Atualiza UI a cada 5 linhas ou a cada 500ms (batch)
                    if len(buf) % 5 == 0:
                        _flush()
                proc.wait(timeout=180)
                _flush()
                rc = proc.returncode
                prefix = "\u2705" if rc == 0 else f"\u274c (exit {rc})"
                self._dispatch(lambda p=prefix: self._manut_output.append(
                    f"\n{p}  Concluido"))
            except subprocess.TimeoutExpired:
                self._dispatch(lambda: self._manut_output.append(
                    "\n\u23f0  Timeout (180s)"))
            except Exception as e:
                self._dispatch(lambda err=str(e): self._manut_output.append(
                    f"\n\u274c  Erro: {err}"))
            finally:
                self._dev_process = None

        self._spawn_io(target_fn)

    def _run_agents(self) -> None:
        from huawei_manager.agents.runner import run_all

        self._loading(self._manut_output, "Varrendo projeto com agentes...")

        def target_fn():
            try:
                results = run_all()
                self._watcher_results = results
                self._dispatch(lambda: self._display_watcher_results(results))
            except Exception as e:
                self._write(self._manut_output, f"Erro nos agentes: {e}")

        self._spawn_cpu(target_fn)

    def _toggle_watcher(self) -> None:
        if self._watcher.is_active:
            self._watcher.stop()
            self._watcher_btn.setText("\U0001f504  Auto: OFF")
            self._write(self._manut_output, "Watcher desligado.")
        else:
            self._watcher.start()
            self._watcher_btn.setText("\U0001f504  Auto: ON")
            self._write(self._manut_output, "Watcher ligado — varredura a cada 60s.")

    def _apply_manut_filter(self) -> None:
        if self._last_manut_results:
            self._display_watcher_results(self._last_manut_results)

    def _display_watcher_results(self, results) -> None:
        self._last_manut_results = results

        counts = {"error": 0, "warning": 0, "info": 0, "ok": 0}
        for r in results:
            counts[r.status] = counts.get(r.status, 0) + 1

        lines = []
        for r in results:
            icon = {"ok": "\u2705", "warning": "\u26a0", "error": "\u274c",
                    "info": "\U0001f4a1"}.get(r.status, "\u2753")
            lines.append(f"{icon}  {r.name:<12}  {r.summary}")
        total = sum(counts.values())
        lines.insert(0, f"  Total: {total} scans | "
                        f"\u274c{counts.get('error',0)}  "
                        f"\u26a0{counts.get('warning',0)}  "
                        f"\U0001f4a1{counts.get('info',0)}  "
                        f"\u2705{counts.get('ok',0)}")
        lines.insert(1, "")

        self._manut_summary.setReadOnly(False)
        self._manut_summary.setPlainText("\n".join(lines))
        self._manut_summary.setReadOnly(True)

        filter_val = self._manut_filter
        items = []
        for r in results:
            for it in r.items:
                if filter_val != "all" and it.severity != filter_val:
                    continue
                icon = {"warning": "\u26a0", "error": "\u274c",
                        "info": "\U0001f4a1"}.get(it.severity, "\u2022")
                items.append(f"{icon}  {r.name}: {it.file}\n"
                             f"   \U0001f4cb  {it.message}\n"
                             f"   \U0001f4a1  {it.suggestion}")
        if items:
            label = {"all": "Todos", "error": "Erros", "warning": "Avisos",
                     "info": "Info"}.get(filter_val, filter_val)
            header = f"\u2500 Filtro: {label} ({len(items)} itens) \u2500\n"
            self._write(self._manut_output, header + "\n".join(items))
        else:
            self._write(self._manut_output, "\u2705  Nenhum problema encontrado para o filtro atual.")

    def _cancel_and_clear(self) -> None:
        if getattr(self, "_dev_process", None) is not None:
            try:
                self._dev_process.kill()
            except Exception:
                pass
            self._dev_process = None
            self._dispatch(lambda: self._manut_output.append("\n\u26a1  Processo cancelado"))
        else:
            self._write(self._manut_output, "")

    def _run_setup(self, mode: str) -> None:
        import subprocess
        import threading

        from huawei_manager._config import PROJECT_ROOT

        if getattr(self, "_dev_process", None) is not None:
            try:
                self._dev_process.kill()
            except Exception:
                pass
            self._dev_process = None

        setup_script = str(PROJECT_ROOT / "setup" / "setup.sh")
        self._loading(self._manut_output, f"setup.sh {mode}...")

        def target_fn():
            buf: list[str] = []
            lock = threading.Lock()

            def _flush() -> None:
                with lock:
                    text = "\n".join(buf)
                    if text:
                        self._dispatch(lambda t=text: (
                            self._manut_output.clear(),
                            self._manut_output.setPlainText(t),
                        ))

            try:
                proc = subprocess.Popen(
                    [setup_script, mode], stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True,
                    cwd=str(PROJECT_ROOT),
                )
                self._dev_process = proc
                assert proc.stdout is not None
                for line in proc.stdout:
                    if proc.poll() is not None and not line:
                        break
                    buf.append(line.rstrip("\n"))
                    # Atualiza UI a cada 5 linhas
                    if len(buf) % 5 == 0:
                        _flush()
                proc.wait(timeout=120)
                _flush()
                rc = proc.returncode
                prefix = "\u2705" if rc == 0 else f"\u274c (exit {rc})"
                self._dispatch(lambda p=prefix: self._manut_output.append(
                    f"\n{p}  setup.sh {mode} concluido"))
            except subprocess.TimeoutExpired:
                self._dispatch(lambda: self._manut_output.append(
                    "\n\u23f0  Timeout (120s)"))
            except Exception as e:
                self._dispatch(lambda err=str(e): self._manut_output.append(
                    f"\n\u274c  Erro: {err}"))
            finally:
                self._dev_process = None

        self._spawn_io(target_fn)

    # ── Backup helper ─────────────────────────────────────────────────
    def _choose_backup_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(
            None, "Escolha o diretorio", self.backup_path)
        if d:
            self.backup_path = d
            self._backup_entry.setText(d)
