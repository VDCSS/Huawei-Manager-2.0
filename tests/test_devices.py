"""Testes para _clear_device_target — TypeError fix (B3)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from huawei_manager.handlers.devices import DevicesMixin


class TestClearDeviceTarget:
    """_clear_device_target não deve lançar TypeError por _set_status sem color."""

    @pytest.fixture(autouse=True)
    def _app(self):
        app = QApplication.instance() or QApplication([])
        yield app

    def test_clear_device_target_calls_set_status_with_color(self):
        """_clear_device_target deve chamar _set_status com texto e color."""
        mixin = DevicesMixin()
        mixin._target_device = MagicMock()
        mixin.session = MagicMock()
        mixin.session.override_host = "10.0.0.1"
        mixin.session.override_port = 22
        mixin.session.override_username = "admin"
        mixin.session.override_password = "secret"
        mixin.session.override_ssh_key = None
        mixin._topo_canvas = MagicMock()
        mixin._device_target_lbl = MagicMock()
        mixin._device_info_lbl = MagicMock()
        mixin._sb = MagicMock()
        mixin._sb.is_alive.return_value = True
        mixin._set_status = MagicMock()
        mixin._set_conn_btn = MagicMock()
        mixin._event_queue = MagicMock()
        mixin._refresh_service_list = MagicMock()

        mixin._clear_device_target()

        # Verifica que _set_status foi chamado com 2 argumentos (texto + color)
        mixin._set_status.assert_called_once()
        args, kwargs = mixin._set_status.call_args
        assert len(args) == 2
        assert args[0] == "Desconectado"
        # C.NEON_RED = '#ff4d4d' — verifica que a cor vermelha foi passada
        assert args[1] == "#ff4d4d"

    def test_clear_device_target_disconnects_sb(self):
        """Deve desconectar _sb se estiver vivo."""
        mixin = DevicesMixin()
        mixin._target_device = MagicMock()
        mixin.session = MagicMock()
        mixin.session.override_host = "10.0.0.1"
        mixin.session.override_port = 22
        mixin.session.override_username = "admin"
        mixin.session.override_password = "secret"
        mixin.session.override_ssh_key = None
        mixin._topo_canvas = MagicMock()
        mixin._device_target_lbl = MagicMock()
        mixin._device_info_lbl = MagicMock()
        mixin._sb = MagicMock()
        mixin._sb.is_alive.return_value = True
        mixin._set_status = MagicMock()
        mixin._set_conn_btn = MagicMock()
        mixin._event_queue = MagicMock()
        mixin._refresh_service_list = MagicMock()

        mixin._clear_device_target()

        mixin._sb.disconnect.assert_called_once()

    def test_clear_device_target_puts_disconnect_event(self):
        """Deve colocar evento DEVICE_DISCONNECTED na queue."""
        mixin = DevicesMixin()
        mixin._target_device = MagicMock()
        mixin.session = MagicMock()
        mixin.session.override_host = "10.0.0.1"
        mixin.session.override_port = 22
        mixin.session.override_username = "admin"
        mixin.session.override_password = "secret"
        mixin.session.override_ssh_key = None
        mixin._topo_canvas = MagicMock()
        mixin._device_target_lbl = MagicMock()
        mixin._device_info_lbl = MagicMock()
        mixin._sb = MagicMock()
        mixin._sb.is_alive.return_value = True
        mixin._set_status = MagicMock()
        mixin._set_conn_btn = MagicMock()
        mixin._event_queue = MagicMock()
        mixin._refresh_service_list = MagicMock()

        mixin._clear_device_target()

        mixin._event_queue.put.assert_called_once()
        args = mixin._event_queue.put.call_args[0]
        event = args[0]
        assert event.type.name == "DEVICE_DISCONNECTED"
        assert event.payload.reason == "target_cleared"

    def test_clear_device_target_noop_when_sb_not_alive(self):
        """Não deve chamar _set_status se _sb não estiver vivo."""
        mixin = DevicesMixin()
        mixin._target_device = MagicMock()
        mixin.session = MagicMock()
        mixin._topo_canvas = MagicMock()
        mixin._device_target_lbl = MagicMock()
        mixin._device_info_lbl = MagicMock()
        mixin._sb = MagicMock()
        mixin._sb.is_alive.return_value = False
        mixin._set_status = MagicMock()
        mixin._set_conn_btn = MagicMock()
        mixin._event_queue = MagicMock()
        mixin._refresh_service_list = MagicMock()

        mixin._clear_device_target()

        mixin._set_status.assert_not_called()
        mixin._sb.disconnect.assert_not_called()
        mixin._event_queue.put.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])