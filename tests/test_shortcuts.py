"""Testes para atalhos de navegação por abas — Ctrl+0 abre Serviços (B5)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QObject
from PySide6.QtGui import QShortcut
from PySide6.QtWidgets import QApplication

from huawei_manager.app_shortcuts import ShortcutsMixin

PAGE_KEYS = [
    "home", "topology", "config", "route", "arp",
    "info", "cmd", "backup", "manutencao", "services",
]


@pytest.fixture(autouse=True)
def _app():
    app = QApplication.instance() or QApplication([])
    yield app


class _QObjectHost(ShortcutsMixin, QObject):
    """Host QObject local — ShortcutsMixin puro não é mais um QObject."""


def _mixin() -> _QObjectHost:
    mixin = _QObjectHost()
    mixin._PAGE_KEYS = PAGE_KEYS
    mixin._show_page = MagicMock()
    mixin._toggle_command_palette = MagicMock()
    mixin.zoom_control = MagicMock()
    mixin._setup_bindings()
    return mixin


def _shortcut_for(mixin: _QObjectHost, seq: str) -> QShortcut:
    for sc in mixin.findChildren(QShortcut):
        if sc.key().toString() == seq:
            return sc
    raise AssertionError(f"shortcut {seq} not found")


class TestPageShortcuts:
    def test_ctrl0_maps_to_services(self):
        mixin = _mixin()
        sc = _shortcut_for(mixin, "Ctrl+0")
        sc.activated.emit()
        mixin._show_page.assert_called_once_with("services")

    def test_ctrl9_maps_to_manutencao(self):
        mixin = _mixin()
        sc = _shortcut_for(mixin, "Ctrl+9")
        sc.activated.emit()
        mixin._show_page.assert_called_once_with("manutencao")

    def test_ctrl1_maps_to_home(self):
        mixin = _mixin()
        sc = _shortcut_for(mixin, "Ctrl+1")
        sc.activated.emit()
        mixin._show_page.assert_called_once_with("home")

    def test_all_ten_page_shortcuts_exist(self):
        mixin = _mixin()
        seqs = {sc.key().toString() for sc in mixin.findChildren(QShortcut)}
        for i in range(1, 10):
            assert f"Ctrl+{i}" in seqs
        assert "Ctrl+0" in seqs


class TestZoomShortcuts:
    def test_ctrl_plus_and_equal_increase_zoom(self):
        mixin = _mixin()
        for seq in ("Ctrl+=", "Ctrl++"):
            mixin.zoom_control.step.reset_mock()
            _shortcut_for(mixin, seq).activated.emit()
            mixin.zoom_control.step.assert_called_once_with(10)

    def test_ctrl_minus_decreases_zoom(self):
        mixin = _mixin()
        _shortcut_for(mixin, "Ctrl+-").activated.emit()
        mixin.zoom_control.step.assert_called_once_with(-10)

    def test_ctrl_shift_zero_resets_zoom(self):
        """Ctrl+0 continua abrindo Serviços; reset usa Ctrl+Shift+0."""
        mixin = _mixin()
        _shortcut_for(mixin, "Ctrl+Shift+0").activated.emit()
        mixin.zoom_control.reset.assert_called_once_with()

    def test_ctrl_d_removes_nothing(self):
        """Regressão: atalho de conexão continua registrado."""
        mixin = _mixin()
        mixin._toggle_connect = MagicMock()
        mixin._setup_bindings()
        _shortcut_for(mixin, "Ctrl+D").activated.emit()
        mixin._toggle_connect.assert_called()
