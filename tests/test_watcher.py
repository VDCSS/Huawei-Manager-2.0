"""Testes unitários para o Watcher (agents/watcher.py)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from huawei_manager.agents.watcher import Watcher


class TestWatcher:
    @patch("huawei_manager.agents.watcher.QTimer")
    def test_stop_resets_scanning(self, mock_qtimer: MagicMock) -> None:
        parent = MagicMock()
        w = Watcher(parent, on_update=lambda r: None)
        w._scanning = True
        w.stop()
        assert w._scanning is False

    @patch("huawei_manager.agents.watcher.QTimer")
    def test_stop_sets_active_false(self, mock_qtimer: MagicMock) -> None:
        parent = MagicMock()
        w = Watcher(parent, on_update=lambda r: None)
        w._active = True
        w.stop()
        assert w._active is False
