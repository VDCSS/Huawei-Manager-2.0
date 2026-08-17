"""DeviceDialog — formulário de cadastro/edição de Device.

Uso:
    dialog = DeviceDialog(parent, device=device_existente, device_types=["ROUTER", ...])
    if dialog.exec():
        data = dialog.get_data()
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import huawei_manager.constants as C

if TYPE_CHECKING:
    from huawei_manager.device_models import Device

# Definição dos campos do formulário (nome_chave, rótulo, é_secreto)
FIELD_DEFINITIONS: list[tuple[str, str, bool]] = [
    ("host",     "IP / Host",      False),
    ("port",     "Porta SSH",      False),
    ("username", "Usuario SSH",    False),
    ("password", "Senha SSH",      True),
    ("ssh_key",  "Chave SSH",      False),
    ("location", "Localizacao",    False),
]


def _style_label(text: str, fixed_width: int = 100) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {C.FG_DIM}; font: 11px 'Inter'; min-width: {fixed_width}px;"
    )
    lbl.setFixedWidth(fixed_width)
    return lbl


def _style_input(placeholder: str = "", is_secret: bool = False) -> QLineEdit:
    entry = QLineEdit()
    entry.setPlaceholderText(placeholder)
    entry.setStyleSheet(
        f"background: {C.BG_INPUT}; color: {C.NEON_CYAN}; "
        f"border: 1px solid {C.BORDER_NRM}; border-radius: 3px; "
        f"padding: 4px 8px; font: 12px 'Inter';"
    )
    if is_secret:
        entry.setEchoMode(QLineEdit.EchoMode.Password)
    return entry


class DeviceDialog(QDialog):
    """Formulário modal para cadastrar ou editar um dispositivo.

    Args:
        parent: Widget pai (opcional).
        device: Device existente para edição (None = cadastro novo).
        device_types: Lista de tipos de Device para o combobox.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        device: Device | None = None,
        device_types: list[str] | None = None,
    ) -> None:
        super().__init__(parent)
        self._device = device
        self._device_types = device_types or []
        self._form_fields: dict[str, QLineEdit] = {}
        self._type_cb: QComboBox | None = None

        self._build_ui()
        if device is not None:
            self._populate(device)

    def _build_ui(self) -> None:
        is_editing = self._device is not None
        self.setWindowTitle(
            "Editar Dispositivo" if is_editing else "Cadastrar Dispositivo"
        )
        self.setMinimumSize(500, 480)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet(f"background: {C.BG_CARD};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 12)

        # ── Nome ───────────────────────────────────────────────────
        name_row = QWidget(self)
        name_layout = QHBoxLayout(name_row)
        name_layout.setContentsMargins(0, 2, 0, 2)
        layout.addWidget(name_row)
        name_layout.addWidget(_style_label("Nome:"))
        self._name_entry = _style_input("Nome do dispositivo")
        name_layout.addWidget(self._name_entry, stretch=1)

        # ── Tipo ───────────────────────────────────────────────────
        type_row = QWidget(self)
        type_layout = QHBoxLayout(type_row)
        type_layout.setContentsMargins(0, 2, 0, 2)
        layout.addWidget(type_row)
        type_layout.addWidget(_style_label("Tipo:"))
        self._type_cb = QComboBox(self)
        self._type_cb.addItems(self._device_types)
        self._type_cb.setStyleSheet(
            f"QComboBox {{ background: {C.BG_INPUT}; color: {C.NEON_CYAN}; "
            f"border: 1px solid {C.BORDER_NRM}; border-radius: 3px; "
            f"padding: 4px 8px; font: 12px 'Inter'; }}"
            f"QComboBox::drop-down {{ border: none; }}"
            f"QComboBox QAbstractItemView {{ background: {C.BG_INPUT}; "
            f"color: {C.NEON_CYAN}; selection-background-color: {C.NEON_PURP}; }}"
        )
        type_layout.addWidget(self._type_cb, stretch=1)

        layout.addSpacing(6)

        # ── Campos de texto ───────────────────────────────────────
        for fname, flabel, is_secret in FIELD_DEFINITIONS:
            row = QWidget(self)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 2, 0, 2)
            layout.addWidget(row)

            row_layout.addWidget(_style_label(f"{flabel}:"))

            entry = _style_input(is_secret=is_secret)
            row_layout.addWidget(entry, stretch=1)
            self._form_fields[fname] = entry

            if is_secret:
                show_cb = QCheckBox("Exibir", row)
                show_cb.setStyleSheet(f"color: {C.NEON_PURP}; font: 11px 'Inter';")
                show_cb.toggled.connect(
                    lambda checked, e=entry: e.setEchoMode(
                        QLineEdit.EchoMode.Normal
                        if checked
                        else QLineEdit.EchoMode.Password
                    )
                )
                row_layout.addWidget(show_cb)

        # ── Botões ─────────────────────────────────────────────────
        layout.addSpacing(12)
        bar = QWidget(self)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(bar)

        save_btn = QPushButton("Salvar", self)
        save_btn.setStyleSheet(
            f"background: transparent; color: {C.NEON_CYAN}; "
            f"border: 1px solid {C.NEON_CYAN}; border-radius: 3px; "
            f"padding: 6px 18px; font: 12px 'Inter';"
        )
        save_btn.clicked.connect(self._on_save)
        bar_layout.addWidget(save_btn)

        bar_layout.addSpacing(8)

        cancel_btn = QPushButton("Cancelar", self)
        cancel_btn.setStyleSheet(
            f"background: transparent; color: {C.NEON_PURP}; "
            f"border: 1px solid {C.NEON_PURP}; border-radius: 3px; "
            f"padding: 6px 18px; font: 12px 'Inter';"
        )
        cancel_btn.clicked.connect(self.reject)
        bar_layout.addWidget(cancel_btn)

        self.setModal(True)

    def _populate(self, device: Device) -> None:
        """Preenche os campos com dados de um Device existente."""
        self._name_entry.setText(device.name)
        if self._type_cb is not None:
            idx = self._type_cb.findText(device.type)
            if idx >= 0:
                self._type_cb.setCurrentIndex(idx)
        self._form_fields["host"].setText(device.host)
        self._form_fields["port"].setText(str(device.port))
        self._form_fields["username"].setText(device.username)
        self._form_fields["password"].setText(device.password)
        self._form_fields["ssh_key"].setText(device.ssh_key)
        self._form_fields["location"].setText(device.location)

    def _on_save(self) -> None:
        """Valida os campos e aceita o diálogo se válidos."""
        name = self._name_entry.text().strip()
        if not name:
            self._name_entry.setFocus()
            self._name_entry.setStyleSheet(
                f"background: {C.BG_INPUT}; color: {C.NEON_RED}; "
                f"border: 1px solid {C.NEON_RED}; border-radius: 3px; "
                f"padding: 4px 8px; font: 12px 'Inter';"
            )
            return

        host = self._form_fields["host"].text().strip()
        if not host:
            self._form_fields["host"].setFocus()
            self._form_fields["host"].setStyleSheet(
                f"background: {C.BG_INPUT}; color: {C.NEON_RED}; "
                f"border: 1px solid {C.NEON_RED}; border-radius: 3px; "
                f"padding: 4px 8px; font: 12px 'Inter';"
            )
            return

        port_text = self._form_fields["port"].text().strip()
        try:
            port_val = int(port_text) if port_text else 22
            if not (1 <= port_val <= 65535):
                port_val = 22
        except ValueError:
            port_val = 22

        self._port_val = port_val
        self.accept()

    def get_data(self) -> dict[str, Any]:
        """Retorna os dados preenchidos no formulário.

        Returns:
            Dicionário com chaves: name, type, host, port, username,
            password, ssh_key, location.

        Raises:
            RuntimeError: Se chamado antes de exec() ou se o diálogo
                foi rejeitado.
        """
        if self.result() != QDialog.DialogCode.Accepted:
            raise RuntimeError("get_data() chamado antes de exec() ou diálogo rejeitado.")
        return {
            "name": self._name_entry.text().strip(),
            "type": self._type_cb.currentText() if self._type_cb else "ROUTER",
            "host": self._form_fields["host"].text().strip(),
            "port": getattr(self, "_port_val", 22),
            "username": self._form_fields["username"].text().strip(),
            "password": self._form_fields["password"].text().strip(),
            "ssh_key": self._form_fields["ssh_key"].text().strip(),
            "location": self._form_fields["location"].text().strip(),
        }
