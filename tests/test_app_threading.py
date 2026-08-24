"""Unit tests for ThreadingMixin (app_threading.py).

Tests are headless — no Qt dependency.  Uses a minimal
``FakeApp`` that provides the ``AppCoreProtocol`` attributes.
"""

from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest
from PySide6.QtGui import QCloseEvent

from huawei_manager.app_notify import NotifyMixin  # noqa: E402
from huawei_manager.app_shortcuts import ShortcutsMixin  # noqa: E402
from huawei_manager.app_threading import ThreadingMixin  # noqa: E402
from huawei_manager import app_threading as _ath  # noqa: E402
from huawei_manager.sdn_controller.event_queue import Event, EventType  # noqa: E402


class _FakeApp(ThreadingMixin):
    """Minimal AppCoreProtocol implementation for testing."""

    def __init__(self) -> None:
        super().__init__()
        self._ui_queue: deque = deque(maxlen=1000)
        self._event_queue = _FakeEventQueue()
        self._io_executor = ThreadPoolExecutor(max_workers=2)
        self._cpu_executor = ThreadPoolExecutor(max_workers=2)
        self._sb = MagicMock()
        self._sb.is_alive.return_value = True
        self._on_sdn_event = MagicMock()
        self._event_drop_count = 0

    @property
    def _ui_queue_maxlen(self) -> int | None:
        return self._ui_queue.maxlen

    def close(self) -> None:
        self._io_executor.shutdown(wait=False)
        self._cpu_executor.shutdown(wait=False)


class _FakeEventQueue:
    """Simplified EventQueue for testing — no threading."""

    def __init__(self) -> None:
        self._events: list[Event] = []

    def put(self, event: Event) -> None:
        self._events.append(event)

    def get(self, block: bool = True) -> Event | None:
        if self._events:
            return self._events.pop(0)
        if block:
            return None  # simplified: real EventQueue blocks; stub returns None
        return None

    def poll(self, timeout: float = 0.1, max_events: int = 100) -> list[Event]:
        """Simplified poll — return up to max_events."""
        results: list[Event] = []
        while self._events and len(results) < max_events:
            results.append(self._events.pop(0))
        return results


# ═══════════════════════════════════════════════════════════════════
#  Fixtures
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def app() -> _FakeApp:
    a = _FakeApp()
    yield a
    a.close()


# ═══════════════════════════════════════════════════════════════════
#  _dispatch
# ═══════════════════════════════════════════════════════════════════

class TestDispatch:
    def test_appends_callback(self, app: _FakeApp) -> None:
        fn = lambda: None  # noqa: E731
        app._dispatch(fn)
        assert len(app._ui_queue) == 1
        assert app._ui_queue[0] is fn

    def test_multiple_callbacks(self, app: _FakeApp) -> None:
        fns = [lambda: i for i in range(3)]  # noqa: E731
        for fn in fns:
            app._dispatch(fn)
        assert len(app._ui_queue) == 3

    def test_appends_respects_maxlen(self, app: _FakeApp) -> None:
        app._ui_queue = deque(maxlen=2)
        app._dispatch(lambda: 1)
        app._dispatch(lambda: 2)
        app._dispatch(lambda: 3)  # should be dropped
        assert len(app._ui_queue) == 2

    def test_unlimited_queue(self, app: _FakeApp) -> None:
        app._ui_queue = deque()  # no maxlen
        for _ in range(100):
            app._dispatch(lambda: None)
        assert len(app._ui_queue) == 100

    def test_sdn_kwarg_appends_when_room(self, app: _FakeApp) -> None:
        fn = lambda: 1  # noqa: E731
        app._dispatch(fn, sdn=True)
        assert len(app._ui_queue) == 1
        assert app._event_drop_count == 0

    def test_sdn_kwarg_drop_counted_when_full(self, app: _FakeApp) -> None:
        app._ui_queue = deque(maxlen=1)
        app._dispatch(lambda: 1)
        app._dispatch(lambda: 2, sdn=True)  # queue full → drop
        assert len(app._ui_queue) == 1
        assert app._event_drop_count == 1


# ═══════════════════════════════════════════════════════════════════
#  _poll_queue
# ═══════════════════════════════════════════════════════════════════

class TestPollQueue:
    def test_polls_callbacks(self, app: _FakeApp) -> None:
        results: list[int] = []

        def cb1() -> None:
            results.append(1)

        def cb2() -> None:
            results.append(2)

        app._dispatch(cb1)
        app._dispatch(cb2)
        app._poll_queue()
        assert results == [1, 2]

    def test_polls_empty_queue(self, app: _FakeApp) -> None:
        app._poll_queue()  # should not raise

    def test_polls_exception_is_caught(self, app: _FakeApp) -> None:
        def failing() -> None:
            msg = "oops"
            raise RuntimeError(msg)

        app._dispatch(failing)
        app._dispatch(lambda: None)  # still runs after failure
        app._poll_queue()  # should not raise

    def test_drains_event_queue(self, app: _FakeApp) -> None:
        app._event_queue.put(Event(EventType.DEVICE_CONNECTED, source="r1"))
        app._poll_queue()
        assert app._event_queue.get(block=False) is None

    def test_dispatches_sdn_events(self, app: _FakeApp) -> None:
        for i in range(3):
            app._event_queue.put(Event(EventType.CONFIG_CHANGED, source=f"dev{i}"))
        app._poll_queue()  # 1ª passada: drain do bus → agenda no ui_queue
        assert len(app._ui_queue) == 3
        assert app._on_sdn_event.call_count == 0
        app._poll_queue()  # 2ª passada: processa ui_queue → executa callbacks
        assert app._on_sdn_event.call_count == 3

    def test_poll_queue_batch_limits_sdn_events(self, app: _FakeApp) -> None:
        total = _ath._EVENT_BATCH + 5
        for i in range(total):
            app._event_queue.put(Event(EventType.CONFIG_CHANGED, source=f"dev{i}"))
        app._poll_queue()
        assert len(app._ui_queue) == _ath._EVENT_BATCH  # só o batch saiu do bus
        remaining = 0
        while app._event_queue.get(block=False) is not None:
            remaining += 1
        assert remaining == 5

    def test_critical_event_processed_directly(self, app: _FakeApp) -> None:
        app._event_queue.put(
            Event(EventType.DEVICE_DISCONNECTED, source="r1", priority=0)
        )
        app._poll_queue()
        assert len(app._ui_queue) == 0  # crítico roda síncrono, sem passagem pelo ui_queue
        app._on_sdn_event.assert_called_once()

    def test_disconnect_default_priority_also_critical(self, app: _FakeApp) -> None:
        app._event_queue.put(Event(EventType.DEVICE_DISCONNECTED, source="r1"))
        app._poll_queue()
        assert len(app._ui_queue) == 0
        app._on_sdn_event.assert_called_once()


# ═══════════════════════════════════════════════════════════════════
#  _spawn_io / _spawn_cpu
# ═══════════════════════════════════════════════════════════════════

class TestSpawnIO:
    def test_spawn_io_runs(self, app: _FakeApp) -> None:
        results: list[int] = []

        def fn() -> None:
            results.append(42)

        app._spawn_io(fn)
        app._io_executor.shutdown(wait=True)
        assert results == [42]

    def test_spawn_io_catches_exception(self, app: _FakeApp) -> None:
        def failing() -> None:
            msg = "oops"
            raise RuntimeError(msg)

        app._spawn_io(failing)
        app._io_executor.shutdown(wait=True)  # should not raise


class TestSpawnCPU:
    def test_spawn_cpu_runs(self, app: _FakeApp) -> None:
        results: list[int] = []

        def fn() -> None:
            results.append(99)

        app._spawn_cpu(fn)
        app._cpu_executor.shutdown(wait=True)
        assert results == [99]


# ═══════════════════════════════════════════════════════════════════
#  _write / _loading
# ═══════════════════════════════════════════════════════════════════

class TestWrite:
    def test_write_dispatches_clear_and_set(self, app: _FakeApp) -> None:
        widget = MagicMock()
        app._write(widget, "hello")
        assert len(app._ui_queue) == 1
        # Execute the queued callback
        fn = app._ui_queue.popleft()
        fn()
        widget.clear.assert_called_once()
        widget.setPlainText.assert_called_once_with("hello")


class TestLoading:
    def test_loading_dispatches_loading_msg(self, app: _FakeApp) -> None:
        widget = MagicMock()
        app._loading(widget, "Carregando...")
        assert len(app._ui_queue) == 1
        fn = app._ui_queue.popleft()
        fn()
        widget.clear.assert_called_once()
        args = widget.setPlainText.call_args[0][0]
        assert "Carregando..." in args


# ═══════════════════════════════════════════════════════════════════
#  _run
# ═══════════════════════════════════════════════════════════════════

class TestRun:
    def test_run_spawns_io_when_alive(self, app: _FakeApp, monkeypatch) -> None:
        results: list[int] = []

        def fn() -> None:
            results.append(7)

        app._run(fn)
        app._io_executor.shutdown(wait=True)
        assert results == [7]

    def test_run_returns_when_not_alive(self, app: _FakeApp, monkeypatch) -> None:
        monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.warning", MagicMock())
        app._sb.is_alive.return_value = False
        results: list[int] = []

        def fn() -> None:
            results.append(7)

        app._run(fn)
        app._io_executor.shutdown(wait=True)
        assert results == []  # fn was NOT spawned

    def test_run_handles_is_alive_exception(self, app: _FakeApp, monkeypatch) -> None:
        monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.warning", MagicMock())
        app._sb.is_alive.side_effect = RuntimeError("boom")

        def fn() -> None:
            pass

        app._run(fn)  # should not raise
        app._io_executor.shutdown(wait=True)


# ═══════════════════════════════════════════════════════════════════
#  W4 — Ciclo de vida (Ctrl+Q, closeEvent robusto, _shutdown gate)
# ═══════════════════════════════════════════════════════════════════

class _FakeBase:
    def __init__(self) -> None:
        self._super_close_called = False

    def closeEvent(self, event: QCloseEvent, /) -> None:
        self._super_close_called = True


class _NotifyFakeApp(NotifyMixin, _FakeBase):
    def __init__(self) -> None:
        _FakeBase.__init__(self)
        self._shutdown = False
        self._adaptive_timer = MagicMock()
        self._poll_timer = MagicMock()
        self._device_timer = MagicMock()
        self._dash_timer = MagicMock()
        self._session_timer = MagicMock()
        self._clock_timer = MagicMock()
        self._session_factory = None
        self._watcher = MagicMock()
        self._sb = MagicMock()
        self._io_executor = MagicMock()
        self._cpu_executor = MagicMock()


class TestCtrlQ:
    def test_ctrl_q_closes_window(self) -> None:
        fake = MagicMock()
        ShortcutsMixin._on_ctrl_q(fake)
        fake.close.assert_called_once()


class TestCloseEvent:
    def test_close_event_calls_super_when_on_close_raises(self) -> None:
        app = _NotifyFakeApp()
        app._on_close = MagicMock(side_effect=RuntimeError("boom"))
        app.closeEvent(QCloseEvent())
        assert app._super_close_called is True

    def test_close_event_calls_on_close_and_super(self) -> None:
        app = _NotifyFakeApp()
        on_close = MagicMock()
        app._on_close = on_close
        app.closeEvent(QCloseEvent())
        on_close.assert_called_once()
        assert app._super_close_called is True


class TestOnCloseLifecycle:
    def test_on_close_sets_shutdown_first_and_stops_all_timers(self) -> None:
        app = _NotifyFakeApp()
        for t in (app._adaptive_timer, app._poll_timer, app._device_timer,
                  app._dash_timer, app._session_timer, app._clock_timer):
            t.stop.assert_not_called()
        app._on_close()
        assert app._shutdown is True
        for t in (app._adaptive_timer, app._poll_timer, app._device_timer,
                  app._dash_timer, app._session_timer, app._clock_timer):
            t.stop.assert_called_once()

    def test_on_close_watcher_shutdown_wait_false(self) -> None:
        app = _NotifyFakeApp()
        app._on_close()
        app._watcher.shutdown.assert_called_once_with(wait=False)

    def test_on_close_cleanup_executors_cancel_futures(self) -> None:
        app = _NotifyFakeApp()
        app._on_close()
        app._io_executor.shutdown.assert_called_once_with(wait=False, cancel_futures=True)
        app._cpu_executor.shutdown.assert_called_once_with(wait=False, cancel_futures=True)

    def test_on_close_disconnects_sb(self) -> None:
        app = _NotifyFakeApp()
        app._on_close()
        app._sb.disconnect.assert_called_once()

    def test_on_close_handles_missing_timers(self) -> None:
        app = _NotifyFakeApp()
        app._poll_timer = None
        app._on_close()
        assert app._shutdown is True


class TestSpawnIOShutdownGate:
    def test_spawn_io_noop_after_shutdown(self, app: _FakeApp) -> None:
        app._shutdown = True
        results: list[int] = []

        def fn() -> None:
            results.append(1)

        app._spawn_io(fn)
        app._io_executor.shutdown(wait=True)
        assert results == []

    def test_spawn_io_noop_when_executor_none(self, app: _FakeApp) -> None:
        original = app._io_executor
        app._io_executor = None
        results: list[int] = []

        def fn() -> None:
            results.append(1)

        app._spawn_io(fn)
        app._io_executor = original
        assert results == []

    def test_spawn_io_runs_when_not_shutdown(self, app: _FakeApp) -> None:
        app._shutdown = False
        results: list[int] = []

        def fn() -> None:
            results.append(42)

        app._spawn_io(fn)
        app._io_executor.shutdown(wait=True)
        assert results == [42]
