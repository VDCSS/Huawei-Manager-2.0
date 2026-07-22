"""Unit tests for ThreadingMixin (app_threading.py).

Tests are headless — no Qt dependency.  Uses a minimal
``FakeApp`` that provides the ``AppCoreProtocol`` attributes.
"""

from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest

from huawei_manager.app_threading import ThreadingMixin  # noqa: E402
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
        app._event_queue.put(Event(EventType.DEVICE_CONNECTED, source="test"))
        app._poll_queue()
        assert app._event_queue.get(block=False) is None


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
