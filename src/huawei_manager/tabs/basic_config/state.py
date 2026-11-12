"""Estado privado da aba Config Básica (F2)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import (
        QCheckBox,
        QLabel,
        QLineEdit,
        QPushButton,
        QTextEdit,
    )


@dataclass
class BasicConfigState:
    """Campos e widgets da aba Config Básica."""

    # Cabeçalho / status
    device_lbl: QLabel | None = None
    type_lbl: QLabel | None = None
    status_lbl: QLabel | None = None

    # Hostname
    hostname_chk: QCheckBox | None = None
    hostname_input: QLineEdit | None = None

    # Interface L3
    iface_l3_chk: QCheckBox | None = None
    iface_l3_name: QLineEdit | None = None
    iface_l3_ip: QLineEdit | None = None
    iface_l3_mask: QLineEdit | None = None
    iface_l3_desc: QLineEdit | None = None
    iface_l3_shutdown: QCheckBox | None = None
    iface_l3_undo_portswitch: QCheckBox | None = None

    # L2 Access + Vlanif
    l2_chk: QCheckBox | None = None
    l2_vlan_id: QLineEdit | None = None
    l2_iface: QLineEdit | None = None
    l2_ip: QLineEdit | None = None
    l2_mask: QLineEdit | None = None
    l2_vlan_desc: QLineEdit | None = None
    l2_iface_desc: QLineEdit | None = None
    l2_vlanif_desc: QLineEdit | None = None

    # SSH / VTY / AAA
    ssh_chk: QCheckBox | None = None
    ssh_user: QLineEdit | None = None
    ssh_pass: QLineEdit | None = None
    ssh_pass_confirm: QLineEdit | None = None
    ssh_vty: QLineEdit | None = None

    # Usuário administrativo
    admin_chk: QCheckBox | None = None
    admin_user: QLineEdit | None = None
    admin_pass: QLineEdit | None = None
    admin_pass_confirm: QLineEdit | None = None
    admin_priv: QLineEdit | None = None

    # Botões de Ação
    btn_preview: QPushButton | None = None
    btn_apply: QPushButton | None = None
    btn_rollback: QPushButton | None = None
    btn_clear: QPushButton | None = None

    # Opção de persistência (save all virtual-systems / save) — opcional
    save_chk: QCheckBox | None = None

    # Saída / Console
    output: QTextEdit | None = None
