"""Testes de caracterização — labels de estado (B6 + B9).

Verifica que o botão do watcher reflete `is_active` real (não hardcoded
"Auto: ON") e que o label de inventário mostra a contagem atual de devices
atualizada por `_update_devices_ui`.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QStackedWidget

from huawei_manager.device_models import Device
from huawei_manager.handlers.devices import DevicesMixin
from huawei_manager.pages.builder import PageBuilder


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


def _make_manut_builder() -> PageBuilder:
    builder = PageBuilder()
    builder._page_container = QStackedWidget()
    builder._access_level = "tecnico"
    builder._mock_mode = True
    builder._watcher_results = []
    builder._watcher = _FakeWatcher()
    builder._loading = MagicMock()
    builder._display_watcher_results = MagicMock()
    builder._run_dev_cmd = MagicMock()
    builder._run_agents = MagicMock()
    builder._toggle_probe_mode = MagicMock()
    builder._run_setup = MagicMock()
    builder._cancel_and_clear = MagicMock()
    builder._write = MagicMock()
    builder._manut_output = MagicMock()
    return builder


class TestWatcherStateLabel:
    def test_button_off_when_watcher_inactive(self):
        builder = _make_manut_builder()
        builder._watcher = _FakeWatcher()
        builder._build_manutencao_page()
        assert "Auto: OFF" in builder._watcher_btn.text()

    def test_button_on_when_watcher_active(self):
        builder = _make_manut_builder()
        watcher = _FakeWatcher()
        watcher.start()
        builder._watcher = watcher
        builder._build_manutencao_page()
        assert "Auto: ON" in builder._watcher_btn.text()

    def test_toggle_updates_label_both_ways(self):
        builder = _make_manut_builder()
        builder._build_manutencao_page()
        assert "Auto: OFF" in builder._watcher_btn.text()

        builder._toggle_watcher()
        assert builder._watcher.is_active
        assert "Auto: ON" in builder._watcher_btn.text()

        builder._toggle_watcher()
        assert not builder._watcher.is_active
        assert "Auto: OFF" in builder._watcher_btn.text()


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