"""Testes para AppStateMixin._on_sdn_event (eventos SDN → UI)."""
from __future__ import annotations

from unittest.mock import MagicMock

from huawei_manager.app_state import AppStateMixin
from huawei_manager.sdn_controller.event_queue import Event, EventType


class _FakeApp(AppStateMixin):
    def __init__(self) -> None:
        self._topo_canvas = MagicMock()
        self._refresh_dashboard = MagicMock()
        self._tick_dashboard = MagicMock()
        self._current_page = "home"
        self._refresh_devices = MagicMock()
        self._spawn_io = MagicMock()


class TestOnSdnEvent:
    def test_device_disconnected_sets_offline(self) -> None:
        app = _FakeApp()
        app._on_sdn_event(Event(EventType.DEVICE_DISCONNECTED, source="r1"))
        app._topo_canvas.set_device_status.assert_called_once_with("r1", "offline")

    def test_device_connected_sets_online(self) -> None:
        app = _FakeApp()
        app._on_sdn_event(Event(EventType.DEVICE_CONNECTED, source="r1"))
        app._topo_canvas.set_device_status.assert_called_once_with("r1", "online")

    def test_config_changed_refreshes_dashboard(self) -> None:
        app = _FakeApp()
        app._on_sdn_event(Event(EventType.CONFIG_CHANGED, source="core"))
        app._tick_dashboard.assert_called_once()

    def test_none_event_ignored(self) -> None:
        app = _FakeApp()
        app._on_sdn_event(None)
        app._topo_canvas.set_device_status.assert_not_called()
        app._tick_dashboard.assert_not_called()

    def test_unmapped_event_ignored(self) -> None:
        app = _FakeApp()
        app._on_sdn_event(Event(EventType.ALERT, source="core"))
        app._topo_canvas.set_device_status.assert_not_called()
        app._tick_dashboard.assert_not_called()

    def test_canvas_exception_caught(self) -> None:
        app = _FakeApp()
        app._topo_canvas.set_device_status = MagicMock(side_effect=RuntimeError("boom"))
        app._on_sdn_event(Event(EventType.DEVICE_DISCONNECTED, source="r1"))  # não propaga