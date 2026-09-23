"""Testes de caracterização — prompt de device vazio (handlers/devices.py).

Cobre _ensure_device_ready e _prompt_no_devices: gate de acoes que exigem
device cadastrado e selecionado, dialog modal para admin e aviso para nao-admin.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from huawei_manager.handlers.devices import DevicesMixin

from ._factories import make_device as _make_device


def _make_mixin(**attrs) -> DevicesMixin:
    mixin = DevicesMixin()
    defaults = dict(
        _devices=[],
        _device_service=MagicMock(),
        _access_level="user",
        _get_selected_device=MagicMock(return_value=None),
        _set_status=MagicMock(),
        _show_device_dialog=MagicMock(),
    )
    defaults["_device_service"].load_inventory.return_value = []
    for k, v in defaults.items():
        setattr(mixin, k, v)
    for k, v in attrs.items():
        setattr(mixin, k, v)
    return mixin


class TestEnsureDeviceReady:
    def test_returns_none_and_prompts_when_no_devices(self):
        mixin = _make_mixin()
        mixin._prompt_no_devices = MagicMock()
        result = mixin._ensure_device_ready("conectar")
        assert result is None
        mixin._prompt_no_devices.assert_called_once_with("conectar")

    def test_loads_inventory_when_devices_attr_empty(self):
        device = _make_device()
        svc = MagicMock()
        svc.load_inventory.return_value = [device]
        mixin = _make_mixin(_devices=[], _device_service=svc)
        mixin._get_selected_device = MagicMock(return_value=device)
        result = mixin._ensure_device_ready("conectar")
        assert result is device
        svc.load_inventory.assert_called_once()

    def test_returns_none_and_hints_when_device_not_selected(self):
        device = _make_device()
        mixin = _make_mixin(_devices=[device])
        mixin._get_selected_device = MagicMock(return_value=None)
        result = mixin._ensure_device_ready("conectar")
        assert result is None
        mixin._set_status.assert_called_once()
        msg = mixin._set_status.call_args[0][0]
        assert "Selecione um device primeiro" in msg

    def test_returns_selected_device(self):
        device = _make_device()
        mixin = _make_mixin(_devices=[device])
        mixin._get_selected_device = MagicMock(return_value=device)
        result = mixin._ensure_device_ready("conectar")
        assert result is device
        mixin._set_status.assert_not_called()


class TestPromptNoDevices:
    def test_admin_yes_opens_dialog(self):
        mixin = _make_mixin(_access_level="admin")
        with patch("PySide6.QtWidgets.QMessageBox") as msgbox:
            msgbox.question.return_value = msgbox.StandardButton.Yes
            mixin._prompt_no_devices("conectar")
        msgbox.question.assert_called_once()
        mixin._show_device_dialog.assert_called_once()

    def test_admin_no_skips_dialog(self):
        mixin = _make_mixin(_access_level="admin")
        with patch("PySide6.QtWidgets.QMessageBox") as msgbox:
            msgbox.question.return_value = msgbox.StandardButton.No
            mixin._prompt_no_devices("conectar")
        mixin._show_device_dialog.assert_not_called()

    def test_non_admin_shows_notice(self):
        mixin = _make_mixin(_access_level="user")
        mixin._prompt_no_devices("conectar")
        mixin._show_device_dialog.assert_not_called()
        mixin._set_status.assert_called_once()
        msg = mixin._set_status.call_args[0][0]
        assert "solicite ao admin" in msg