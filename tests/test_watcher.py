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

    @patch("huawei_manager.agents.watcher.QTimer")
    def test_start_sets_active(self, mock_qtimer: MagicMock) -> None:
        parent = MagicMock()
        w = Watcher(parent, on_update=lambda r: None)
        with patch("huawei_manager.agents.watcher.run_all", return_value=[]):
            w.start()
        assert w._active is True

    @patch("huawei_manager.agents.watcher.QTimer")
    def test_start_calls_tick(self, mock_qtimer: MagicMock) -> None:
        parent = MagicMock()
        w = Watcher(parent, on_update=lambda r: None)
        w._active = False
        with patch.object(w._executor, "submit") as mock_submit:
            w.start()
        mock_submit.assert_called_once()

    @patch("huawei_manager.agents.watcher.QTimer")
    def test_start_starts_timer(self, mock_qtimer: MagicMock) -> None:
        parent = MagicMock()
        timer_inst = mock_qtimer.return_value
        timer_inst.isActive.return_value = False
        w = Watcher(parent, on_update=lambda r: None)
        with patch("huawei_manager.agents.watcher.run_all", return_value=[]):
            w.start(interval_s=30)
        timer_inst.start.assert_called_once_with(30_000)

    @patch("huawei_manager.agents.watcher.QTimer")
    def test_start_ignores_if_already_active(self, mock_qtimer: MagicMock) -> None:
        parent = MagicMock()
        timer_inst = mock_qtimer.return_value
        w = Watcher(parent, on_update=lambda r: None)
        w._active = True
        w.start()
        timer_inst.start.assert_not_called()

    @patch("huawei_manager.agents.watcher.QTimer")
    def test_stop_stops_timer(self, mock_qtimer: MagicMock) -> None:
        parent = MagicMock()
        timer_inst = mock_qtimer.return_value
        timer_inst.isActive.return_value = True
        w = Watcher(parent, on_update=lambda r: None)
        w._active = True
        w.stop()
        timer_inst.stop.assert_called_once()

    @patch("huawei_manager.agents.watcher.QTimer")
    def test_is_active_returns_true_after_start(self, mock_qtimer: MagicMock) -> None:
        parent = MagicMock()
        w = Watcher(parent, on_update=lambda r: None)
        with patch("huawei_manager.agents.watcher.run_all", return_value=[]):
            w.start()
        assert w.is_active is True

    @patch("huawei_manager.agents.watcher.QTimer")
    def test_is_active_returns_false_after_stop(self, mock_qtimer: MagicMock) -> None:
        parent = MagicMock()
        w = Watcher(parent, on_update=lambda r: None)
        w._active = True
        w.stop()
        assert w.is_active is False

    @patch("huawei_manager.agents.watcher.QTimer")
    def test_shutdown_calls_stop(self, mock_qtimer: MagicMock) -> None:
        parent = MagicMock()
        timer_inst = mock_qtimer.return_value
        timer_inst.isActive.return_value = False
        w = Watcher(parent, on_update=lambda r: None)
        w._active = True
        with patch.object(w._executor, "shutdown") as mock_shutdown:
            w.shutdown()
        mock_shutdown.assert_called_once_with(wait=True)
        assert w._active is False
        assert w._scanning is False

    @patch("huawei_manager.agents.watcher.run_all")
    @patch("huawei_manager.agents.watcher.QTimer")
    def test_tick_submits_run_scan(self, mock_qtimer: MagicMock, mock_run_all: MagicMock) -> None:
        mock_run_all.return_value = []
        parent = MagicMock()
        w = Watcher(parent, on_update=lambda r: None)
        w._active = True
        with patch.object(w._executor, "submit") as mock_submit:
            w._tick()
        mock_submit.assert_called_once()

    @patch("huawei_manager.agents.watcher.QTimer")
    def test_tick_skips_if_scanning(self, mock_qtimer: MagicMock) -> None:
        parent = MagicMock()
        w = Watcher(parent, on_update=lambda r: None)
        w._active = True
        w._scanning = True
        w._tick()
        assert w._scanning is True

    @patch("huawei_manager.agents.watcher.run_all")
    @patch("huawei_manager.agents.watcher.QTimer")
    def test_run_scan_calls_on_update_on_change(
        self, mock_qtimer: MagicMock, mock_run_all: MagicMock
    ) -> None:
        results = [MagicMock()]
        mock_run_all.return_value = results
        on_update = MagicMock()
        parent = MagicMock()
        w = Watcher(parent, on_update=on_update)
        w._run_scan()
        on_update.assert_called_once_with(results)

    @patch("huawei_manager.agents.watcher.run_all")
    @patch("huawei_manager.agents.watcher.QTimer")
    def test_run_scan_skips_on_update_if_cache_unchanged(
        self, mock_qtimer: MagicMock, mock_run_all: MagicMock
    ) -> None:
        results = [MagicMock()]
        on_update = MagicMock()
        parent = MagicMock()
        w = Watcher(parent, on_update=on_update)
        w._cache = results
        mock_run_all.return_value = results
        w._run_scan()
        on_update.assert_not_called()

    @patch("huawei_manager.agents.watcher.run_all")
    @patch("huawei_manager.agents.watcher.QTimer")
    def test_run_scan_resets_scanning_flag(
        self, mock_qtimer: MagicMock, mock_run_all: MagicMock
    ) -> None:
        mock_run_all.return_value = []
        parent = MagicMock()
        w = Watcher(parent, on_update=lambda r: None)
        w._scanning = True
        w._run_scan()
        assert w._scanning is False
