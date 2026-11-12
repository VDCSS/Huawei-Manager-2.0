"""Módulo de UI da aba Config Básica (F2)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from huawei_manager import constants as C
from huawei_manager.tabs import _ui
from huawei_manager.tabs.basic_config.handlers import BasicConfigHandlers
from huawei_manager.tabs.basic_config.state import BasicConfigState
from huawei_manager.widgets.neon_button import action_button

if TYPE_CHECKING:
    from huawei_manager.tabs._contract import TabContext


class BasicConfigTab:
    """Implementa o protocolo TabModule para a aba de Configuração Básica."""

    def __init__(self) -> None:
        self.state = BasicConfigState()
        self._ctx: TabContext | None = None
        self._handlers: BasicConfigHandlers | None = None

    def attach(self, ctx: TabContext) -> None:
        self._ctx = ctx

    def build(self, ctx: TabContext) -> QWidget | None:
        self._ctx = ctx
        self._handlers = BasicConfigHandlers(ctx, self.state)

        page = _ui.page_frame("basic-config")
        layout = _ui.page_layout(page)

        _ui.page_title(page, "CONFIGURAÇÃO BÁSICA (VRP)", C.NEON_AMBER)
        layout.addSpacing(6)

        # Barra de status do device
        self._build_device_row(page)

        # Splitter com formulário scrollável à esquerda e terminal/output à direita
        splitter = QSplitter(Qt.Orientation.Horizontal, page)
        splitter.setStyleSheet(f"QSplitter::handle {{ background: {C.BORDER_NRM}; }}")
        layout.addWidget(splitter, stretch=1)

        # Lado Esquerdo: Formulário
        scroll = QScrollArea(splitter)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ border: none; background: {C.BG_BASE}; }}")
        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)
        form_layout.setContentsMargins(4, 4, 12, 4)
        form_layout.setSpacing(10)
        scroll.setWidget(form_widget)
        splitter.addWidget(scroll)

        self._build_sections(form_widget)

        # Lado Direito: Ações e Console de Saída
        right_panel = QWidget(splitter)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(8)
        splitter.addWidget(right_panel)

        self._build_actions_and_output(right_panel)
        splitter.setSizes([450, 450])

        return page

    def dispose(self) -> None:
        self._ctx = None
        self._handlers = None

    def _build_device_row(self, parent: QWidget) -> None:
        row = QWidget(parent)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        parent_layout = parent.layout()
        if parent_layout:
            parent_layout.addWidget(row)

        dev = self._ctx.device() if self._ctx else None
        dev_name = dev.name if dev else "Nenhum"
        self.state.device_lbl = QLabel(f"Device: {dev_name}", row)
        self.state.device_lbl.setStyleSheet(_ui.css_label(C.NEON_AMBER, C.BG_BASE, 11, True))
        row_layout.addWidget(self.state.device_lbl)
        row_layout.addStretch()

    def _build_sections(self, parent: QWidget) -> None:
        p_layout = parent.layout()
        if not isinstance(p_layout, QVBoxLayout):
            return

        # 1. Hostname
        sec_h, sec_h_layout = self._create_card(parent, "1. Hostname / Identificação")
        self.state.hostname_chk = QCheckBox("Configurar Hostname", sec_h)
        self.state.hostname_chk.setStyleSheet(_ui.css_label(C.NEON_CYAN, C.BG_CARD, 11))
        sec_h_layout.addWidget(self.state.hostname_chk)
        self.state.hostname_input = QLineEdit(sec_h)
        self.state.hostname_input.setPlaceholderText("Ex: Roteador-Core-01")
        self._style_input(self.state.hostname_input)
        sec_h_layout.addWidget(self.state.hostname_input)
        p_layout.addWidget(sec_h)

        # 2. Interface L3
        sec_l3, sec_l3_layout = self._create_card(parent, "2. Interface L3")
        self.state.iface_l3_chk = QCheckBox("Configurar Interface L3", sec_l3)
        self.state.iface_l3_chk.setStyleSheet(_ui.css_label(C.NEON_CYAN, C.BG_CARD, 11))
        sec_l3_layout.addWidget(self.state.iface_l3_chk)

        self.state.iface_l3_name = QLineEdit(sec_l3)
        self.state.iface_l3_name.setPlaceholderText("Interface (ex: GigabitEthernet0/0/0)")
        self._style_input(self.state.iface_l3_name)
        sec_l3_layout.addWidget(self.state.iface_l3_name)

        row_ip = QHBoxLayout()
        self.state.iface_l3_ip = QLineEdit(sec_l3)
        self.state.iface_l3_ip.setPlaceholderText("Endereço IP (ex: 192.168.1.1)")
        self._style_input(self.state.iface_l3_ip)
        row_ip.addWidget(self.state.iface_l3_ip)

        self.state.iface_l3_mask = QLineEdit(sec_l3)
        self.state.iface_l3_mask.setPlaceholderText("Máscara (ex: 255.255.255.0 ou /24)")
        self._style_input(self.state.iface_l3_mask)
        row_ip.addWidget(self.state.iface_l3_mask)
        sec_l3_layout.addLayout(row_ip)

        self.state.iface_l3_desc = QLineEdit(sec_l3)
        self.state.iface_l3_desc.setPlaceholderText("Descrição opcional")
        self._style_input(self.state.iface_l3_desc)
        sec_l3_layout.addWidget(self.state.iface_l3_desc)

        row_opts = QHBoxLayout()
        self.state.iface_l3_shutdown = QCheckBox("Shutdown", sec_l3)
        self.state.iface_l3_shutdown.setStyleSheet(_ui.css_label(C.FG_DIM, C.BG_CARD, 10))
        row_opts.addWidget(self.state.iface_l3_shutdown)

        self.state.iface_l3_undo_portswitch = QCheckBox("undo portswitch (Switch L3)", sec_l3)
        self.state.iface_l3_undo_portswitch.setStyleSheet(_ui.css_label(C.FG_DIM, C.BG_CARD, 10))
        row_opts.addWidget(self.state.iface_l3_undo_portswitch)
        sec_l3_layout.addLayout(row_opts)
        p_layout.addWidget(sec_l3)

        # 3. L2 Access + Vlanif
        sec_l2, sec_l2_layout = self._create_card(parent, "3. L2 Access + Vlanif")
        self.state.l2_chk = QCheckBox("Configurar Porta Access e Vlanif", sec_l2)
        self.state.l2_chk.setStyleSheet(_ui.css_label(C.NEON_CYAN, C.BG_CARD, 11))
        sec_l2_layout.addWidget(self.state.l2_chk)

        row_l2_ids = QHBoxLayout()
        self.state.l2_vlan_id = QLineEdit(sec_l2)
        self.state.l2_vlan_id.setPlaceholderText("VLAN ID (ex: 10)")
        self._style_input(self.state.l2_vlan_id)
        row_l2_ids.addWidget(self.state.l2_vlan_id)

        self.state.l2_iface = QLineEdit(sec_l2)
        self.state.l2_iface.setPlaceholderText("Porta Access (ex: GE0/0/1)")
        self._style_input(self.state.l2_iface)
        row_l2_ids.addWidget(self.state.l2_iface)
        sec_l2_layout.addLayout(row_l2_ids)

        row_vlanif_ip = QHBoxLayout()
        self.state.l2_ip = QLineEdit(sec_l2)
        self.state.l2_ip.setPlaceholderText("IP da Vlanif (ex: 10.0.10.1)")
        self._style_input(self.state.l2_ip)
        row_vlanif_ip.addWidget(self.state.l2_ip)

        self.state.l2_mask = QLineEdit(sec_l2)
        self.state.l2_mask.setPlaceholderText("Máscara da Vlanif (/24)")
        self._style_input(self.state.l2_mask)
        row_vlanif_ip.addWidget(self.state.l2_mask)
        sec_l2_layout.addLayout(row_vlanif_ip)
        p_layout.addWidget(sec_l2)

        # 4. SSH / VTY / AAA
        sec_ssh, sec_ssh_layout = self._create_card(parent, "4. SSH / VTY / AAA")
        self.state.ssh_chk = QCheckBox("Habilitar SSH & VTY", sec_ssh)
        self.state.ssh_chk.setStyleSheet(_ui.css_label(C.NEON_CYAN, C.BG_CARD, 11))
        sec_ssh_layout.addWidget(self.state.ssh_chk)

        self.state.ssh_user = QLineEdit(sec_ssh)
        self.state.ssh_user.setPlaceholderText("Usuário SSH")
        self._style_input(self.state.ssh_user)
        sec_ssh_layout.addWidget(self.state.ssh_user)

        row_pass = QHBoxLayout()
        self.state.ssh_pass = QLineEdit(sec_ssh)
        self.state.ssh_pass.setPlaceholderText("Senha (mínimo 12 chars)")
        self.state.ssh_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self._style_input(self.state.ssh_pass)
        row_pass.addWidget(self.state.ssh_pass)

        self.state.ssh_pass_confirm = QLineEdit(sec_ssh)
        self.state.ssh_pass_confirm.setPlaceholderText("Confirme a Senha")
        self.state.ssh_pass_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self._style_input(self.state.ssh_pass_confirm)
        row_pass.addWidget(self.state.ssh_pass_confirm)
        sec_ssh_layout.addLayout(row_pass)

        self.state.ssh_vty = QLineEdit(sec_ssh)
        self.state.ssh_vty.setText("0 4")
        self.state.ssh_vty.setPlaceholderText("Faixa VTY (padrão: 0 4)")
        self._style_input(self.state.ssh_vty)
        sec_ssh_layout.addWidget(self.state.ssh_vty)
        p_layout.addWidget(sec_ssh)

        # 5. Usuário Administrativo
        sec_admin, sec_admin_layout = self._create_card(parent, "5. Usuário Administrativo Local")
        self.state.admin_chk = QCheckBox("Criar/Atualizar Usuário Admin", sec_admin)
        self.state.admin_chk.setStyleSheet(_ui.css_label(C.NEON_CYAN, C.BG_CARD, 11))
        sec_admin_layout.addWidget(self.state.admin_chk)

        self.state.admin_user = QLineEdit(sec_admin)
        self.state.admin_user.setPlaceholderText("Nome de Usuário")
        self._style_input(self.state.admin_user)
        sec_admin_layout.addWidget(self.state.admin_user)

        row_adm_pass = QHBoxLayout()
        self.state.admin_pass = QLineEdit(sec_admin)
        self.state.admin_pass.setPlaceholderText("Senha Forte")
        self.state.admin_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self._style_input(self.state.admin_pass)
        row_adm_pass.addWidget(self.state.admin_pass)

        self.state.admin_pass_confirm = QLineEdit(sec_admin)
        self.state.admin_pass_confirm.setPlaceholderText("Confirmar Senha")
        self.state.admin_pass_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self._style_input(self.state.admin_pass_confirm)
        row_adm_pass.addWidget(self.state.admin_pass_confirm)
        sec_admin_layout.addLayout(row_adm_pass)
        p_layout.addWidget(sec_admin)

    def _build_actions_and_output(self, parent: QWidget) -> None:
        p_layout = parent.layout()
        if not isinstance(p_layout, QVBoxLayout):
            return

        actions_card, ac_layout = self._create_card(parent, "Ações de Execução")

        # Opção de persistência (opcional): decide se faz save na startup-config.
        # O commit (VRP8) continua decidido automaticamente pela versão VRP.
        save_row = QHBoxLayout()
        self.state.save_chk = QCheckBox("Salvar na startup-config (save all virtual-systems / save)", actions_card)
        self.state.save_chk.setStyleSheet(_ui.css_label(C.FG_DIM, C.BG_CARD, 10))
        self.state.save_chk.setChecked(True)
        save_row.addWidget(self.state.save_chk)
        save_row.addStretch()
        ac_layout.addLayout(save_row)

        btn_row = QHBoxLayout()
        self.state.btn_preview = action_button(
            actions_card,
            "👁 Prévia",
            lambda: self._h().preview_plan(),
            C.NEON_PURP,
        )
        btn_row.addWidget(self.state.btn_preview)

        self.state.btn_apply = action_button(
            actions_card,
            "▶ Aplicar Bloco",
            lambda: self._h().apply_plan(),
            C.NEON_CYAN,
        )
        btn_row.addWidget(self.state.btn_apply)

        self.state.btn_rollback = action_button(
            actions_card,
            "↩ Rollback",
            lambda: self._h().rollback_plan(),
            C.NEON_RED,
        )
        btn_row.addWidget(self.state.btn_rollback)

        self.state.btn_clear = action_button(
            actions_card,
            "✖ Limpar",
            lambda: _ui.write(
                self.state.output,
                "",
                self._ctx.dispatch if self._ctx else (lambda fn: fn()),
            ),
            C.FG_DIM,
        )
        btn_row.addWidget(self.state.btn_clear)
        ac_layout.addLayout(btn_row)
        p_layout.addWidget(actions_card)

        # Console Output
        out_lbl = QLabel("SAÍDA / LOG DE EXECUÇÃO", parent)
        out_lbl.setStyleSheet(_ui.css_label(C.FG_DIM, C.BG_BASE, 10, True))
        p_layout.addWidget(out_lbl)

        self.state.output = QTextEdit(parent)
        self.state.output.setReadOnly(True)
        self.state.output.setStyleSheet(f"""
            QTextEdit {{
                background: {C.BG_INPUT}; color: {C.FG_CODE};
                border: 1px solid {C.BORDER_NRM}; border-radius: 4px;
                font-family: {C.FONT_UI_FAMILY}; font-size: 11px;
            }}
        """)
        p_layout.addWidget(self.state.output, stretch=1)

    def _create_card(self, parent: QWidget, title: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame(parent)
        card.setStyleSheet(f"""
            QFrame {{
                background: {C.BG_CARD};
                border: 1px solid {C.BORDER_NRM};
                border-radius: 4px;
            }}
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        lbl = QLabel(title, card)
        lbl.setStyleSheet(_ui.css_label(C.NEON_AMBER, C.BG_CARD, 11, True))
        layout.addWidget(lbl)
        return card, layout

    def _style_input(self, widget: QLineEdit) -> None:
        widget.setStyleSheet(f"""
            QLineEdit {{
                background: {C.BG_INPUT}; color: {C.NEON_CYAN};
                border: 1px solid {C.BORDER_NRM}; border-radius: 3px;
                padding: 4px 6px; font-family: {C.FONT_UI_FAMILY}; font-size: 11px;
            }}
            QLineEdit:focus {{
                border: 1px solid {C.NEON_CYAN};
            }}
        """)

    def _h(self) -> BasicConfigHandlers:
        if self._handlers is None:
            raise RuntimeError("BasicConfigTab não inicializado com build()")
        return self._handlers
