"""Testes de caracterização — labels de estado (B6 + B9).

Verifica que o botão do watcher reflete `is_active` real (não hardcoded
"Auto: ON") e que o label de inventário mostra a contagem atual de devices
atualizada por `_update_devices_ui`.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from huawei_manager.device_models import Device
from huawei_manager.handlers.devices import DevicesMixin
from huawei_manager.tabs._contract import TabContext
from huawei_manager.tabs.manutencao.page import ManutencaoTab


class _FakeWatcher:
    """Imita Watcher real: start/stop alternam is_active."""

    def __init__(self) -> None:
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active

    def start(self) -> None:
        self._active = True

    def stop(self) -> None:
        self._active = False


@pytest.fixture(autouse=True)
def _app():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_manut_tab(watcher_active: bool = False) -> ManutencaoTab:
    """Aba real (build com widgets) sobre ctx fake — sem App."""
    watcher = _FakeWatcher()
    if watcher_active:
        watcher.start()
    ctx = TabContext(
        sb=MagicMock(),
        audit=None,
        event_bus=MagicMock(),
        role=lambda: "tecnico",
        device=lambda: None,
        dispatch=lambda fn: fn() if callable(fn) else None,
        require_access=lambda level: True,
        spawn_io=lambda fn, *args: fn(*args),
        spawn_cpu=lambda fn, *args: fn(*args),
        watcher=watcher,
        is_mock=lambda: True,
        toggle_mock=lambda: False,
        show_auth_dialog=lambda: None,
        watcher_results=lambda: [],
        set_watcher_results=MagicMock(),
        session=MagicMock(),
        run=MagicMock(),
        set_status=MagicMock(),
        touch_session=MagicMock(),
        cmd_validator=None,
        dry_run=None,
        get_last_config_command=lambda: None,
        set_last_config_command=MagicMock(),
        drv=lambda: MagicMock(),
    )
    tab = ManutencaoTab()
    tab._page = tab.build(ctx)  # mantém o QWidget vivo (sem pai Qt)
    return tab


class TestWatcherStateLabel:
    def test_button_off_when_watcher_inactive(self):
        tab = _make_manut_tab()
        assert "Auto: OFF" in tab.state.watcher_btn.text()

    def test_button_on_when_watcher_active(self):
        tab = _make_manut_tab(watcher_active=True)
        assert "Auto: ON" in tab.state.watcher_btn.text()

    def test_toggle_updates_label_both_ways(self):
        tab = _make_manut_tab()
        btn = tab.state.watcher_btn
        assert "Auto: OFF" in btn.text()

        tab._toggle_watcher()
        assert tab._ctx.watcher.is_active
        assert "Auto: ON" in btn.text()

        tab._toggle_watcher()
        assert not tab._ctx.watcher.is_active
        assert "Auto: OFF" in btn.text()


class _FakeDevicesApp(DevicesMixin):
    """App fake que carrega apenas o DevicesMixin (método sob teste)."""

    def __init__(self) -> None:
        self._devices = []
        self._controller = MagicMock()
        self._controller.sync_from_devices = MagicMock()
        self._topo_canvas = None
        self._access_level = "user"
        self._device_status_lbl = QLabel()


class TestInventoryStateLabel:
    def _make_topo_builder(self) -> _FakeDevicesApp:
        builder = _FakeDevicesApp()
        builder._device_status_lbl = QLabel()
        return builder

    def _devices(self, n: int) -> list[Device]:
        return [Device(id=f"dev-{i}", name=f"D{i}", host=f"10.0.0.{i + 1}")
                for i in range(n)]

    def test_label_starts_zero(self):
        builder = self._make_topo_builder()
        builder._update_devices_ui(self._devices(0))
        assert builder._device_status_lbl.text() == "Invent\u00e1rio: 0 devices"

    def test_label_reflects_three_devices(self):
        builder = self._make_topo_builder()
        builder._update_devices_ui(self._devices(3))
        assert builder._device_status_lbl.text() == "Invent\u00e1rio: 3 devices"

    def test_label_ignored_when_page_not_built(self):
        builder = self._make_topo_builder()
        builder._device_status_lbl = None
        builder._update_devices_ui(self._devices(2))
        assert builder._devices == self._devices(2)