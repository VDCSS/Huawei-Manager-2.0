"""Testes para DeviceDialog — formulário Qt de cadastro/edição de Device.

Estes testes requerem um servidor gráfico (DISPLAY) ou Qt offscreen.
"""
from __future__ import annotations

import os

import pytest
from PySide6.QtWidgets import QDialog

from huawei_manager.widgets.device_dialog import DeviceDialog

# Skip all tests if Qt is not available
pytestmark = pytest.mark.skipif(
    not os.environ.get("QT_QPA_PLATFORM"),
    reason="Requires Qt platform (e.g., offscreen)",
)


@pytest.fixture
def dialog(qtbot) -> DeviceDialog:
    """Cria um DeviceDialog vazio (modo cadastro)."""
    dlg = DeviceDialog(device_types=["ROUTER", "SWITCH", "FIREWALL"])
    qtbot.addWidget(dlg)
    return dlg


@pytest.fixture
def edit_dialog(qtbot) -> DeviceDialog:
    """Cria um DeviceDialog com Device existente (modo edição)."""
    from huawei_manager.device_models import Device

    device = Device(
        id="dev-001",
        name="gw-01",
        host="10.0.0.1",
        port=22,
        type="ROUTER",
        username="admin",
        password="secret",
    )
    dlg = DeviceDialog(device=device, device_types=["ROUTER", "SWITCH"])
    qtbot.addWidget(dlg)
    return dlg


# ══════════════════════════════════════════════════════════════════════════
#  Construction
# ══════════════════════════════════════════════════════════════════════════


class TestConstruction:
    def test_create_dialog(self, dialog: DeviceDialog):
        assert dialog.windowTitle() == "Cadastrar Dispositivo"
        assert dialog.isModal()

    def test_create_edit_dialog(self, edit_dialog: DeviceDialog):
        assert edit_dialog.windowTitle() == "Editar Dispositivo"


# ══════════════════════════════════════════════════════════════════════════
#  Get Data
# ══════════════════════════════════════════════════════════════════════════


class TestGetData:
    def test_get_data_raises_before_exec(self, dialog: DeviceDialog):
        """get_data() antes de exec() deve levantar RuntimeError."""
        with pytest.raises(RuntimeError, match="get_data"):
            _ = dialog.get_data()

    def test_get_data_after_accept(self, dialog: DeviceDialog, qtbot):
        """Preenche campos e aceita — get_data retorna dict."""
        dialog._name_entry.setText("test-device")
        dialog._form_fields["host"].setText("10.0.0.1")
        dialog._form_fields["port"].setText("22")
        dialog._form_fields["username"].setText("admin")
        dialog._form_fields["password"].setText("secret")
        dialog._form_fields["ssh_key"].setText("")
        dialog._form_fields["location"].setText("lab")
        if dialog._type_cb is not None:
            dialog._type_cb.setCurrentText("SWITCH")

        # Simular clique em Salvar
        dialog._on_save()
        assert dialog.result() == QDialog.DialogCode.Accepted

        data = dialog.get_data()
        assert isinstance(data, dict)
        assert data["name"] == "test-device"
        assert data["host"] == "10.0.0.1"
        assert data["port"] == 22
        assert data["username"] == "admin"
        assert data["password"] == "secret"
        assert data["location"] == "lab"
        assert data["type"] == "SWITCH"


# ══════════════════════════════════════════════════════════════════════════
#  Validation
# ══════════════════════════════════════════════════════════════════════════


class TestValidation:
    def test_empty_name_rejected(self, dialog: DeviceDialog, qtbot):
        """Nome vazio deve impedir aceitação."""
        dialog._name_entry.setText("")
        dialog._form_fields["host"].setText("10.0.0.1")
        dialog._on_save()
        assert dialog.result() != QDialog.DialogCode.Accepted

    def test_empty_host_rejected(self, dialog: DeviceDialog, qtbot):
        """Host vazio deve impedir aceitação."""
        dialog._name_entry.setText("test-device")
        dialog._form_fields["host"].setText("")
        dialog._on_save()
        assert dialog.result() != QDialog.DialogCode.Accepted

    def test_invalid_port_falls_back_to_22(self, dialog: DeviceDialog, qtbot):
        """Porta inválida deve usar 22 como fallback."""
        dialog._name_entry.setText("test-device")
        dialog._form_fields["host"].setText("10.0.0.1")
        dialog._form_fields["port"].setText("invalid")
        dialog._on_save()
        assert dialog.result() == QDialog.DialogCode.Accepted
        # Fallback para 22
        assert dialog._port_val == 22


# ══════════════════════════════════════════════════════════════════════════
#  Edit Mode
# ══════════════════════════════════════════════════════════════════════════


class TestEditMode:
    def test_populated_fields(self, edit_dialog: DeviceDialog):
        """Campos devem estar preenchidos no modo edição."""
        assert edit_dialog._name_entry.text() == "gw-01"
        assert edit_dialog._form_fields["host"].text() == "10.0.0.1"
        assert edit_dialog._form_fields["port"].text() == "22"
        assert edit_dialog._form_fields["username"].text() == "admin"
        assert edit_dialog._form_fields["password"].text() == "secret"
        if edit_dialog._type_cb is not None:
            assert edit_dialog._type_cb.currentText() == "ROUTER"
