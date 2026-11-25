"""Testes da integração do polling adaptativo com o app (headless).

Cobrem os critérios P0 do TODO 6/9: guard de flag/mock/svc_mode, fail-closed
sem VNF_ENCRYPT_KEY e re-arm relativo do QTimer. Nenhum teste abre SSH ou
instancia QMainWindow.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from huawei_manager import constants as C
from huawei_manager.app import (
    AppCore,
    _adaptive_polling_flag,
    _adaptive_polling_guard,
    _adaptive_rearm_delay_ms,
    _resolve_svc_mode,
)


class _FakeFuture:
    """Future mínimo para testar o re-arm após a conclusão do tick."""

    def __init__(self) -> None:
        self.callbacks: list = []

    def add_done_callback(self, cb) -> None:
        self.callbacks.append(cb)

    def fire(self) -> None:
        for cb in list(self.callbacks):
            cb(self)


class _FakePollingApp:
    """Empresta o método real de AppCore sem instanciar QMainWindow."""

    _tick_adaptive_polling = AppCore._tick_adaptive_polling
    _rearm_adaptive_timer = AppCore._rearm_adaptive_timer

    def __init__(
        self,
        *,
        enabled: bool = True,
        mock_mode: bool = False,
        svc_mode: str = "cli",
        next_due: float | None = None,
        shutdown: bool = False,
    ) -> None:
        self._polling_enabled = enabled
        self._mock_mode = mock_mode
        self._svc_mode_var = svc_mode
        self._shutdown = shutdown
        self._polling_mgr = MagicMock()
        self._polling_mgr.next_due_min.return_value = next_due
        self._adaptive_timer = MagicMock()
        self._future = _FakeFuture()
        self._spawn_io = MagicMock(return_value=self._future)
        self._dispatch = MagicMock(side_effect=lambda fn: fn())


class TestGuard:
    def test_flag_on_cli_dispatches(self) -> None:
        app = _FakePollingApp()
        app._tick_adaptive_polling()
        app._spawn_io.assert_called_once_with(app._polling_mgr.tick)
        # Timer só re-arma depois que o tick conclui (M1)
        app._adaptive_timer.start.assert_not_called()
        app._future.fire()
        app._adaptive_timer.start.assert_called_once_with(
            C.POLL_MIN_INTERVAL * 1000
        )

    def test_shutdown_does_not_dispatch_or_rearm(self) -> None:
        app = _FakePollingApp(shutdown=True)
        app._tick_adaptive_polling()
        app._spawn_io.assert_not_called()
        app._adaptive_timer.start.assert_not_called()

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"enabled": False},
            {"mock_mode": True},
            {"svc_mode": "mock"},
        ],
    )
    def test_off_mock_or_svc_mock_does_not_dispatch(
        self, kwargs: dict[str, object]
    ) -> None:
        app = _FakePollingApp(**kwargs)
        app._tick_adaptive_polling()
        app._spawn_io.assert_not_called()

    def test_timer_rearmed_even_when_disabled(self) -> None:
        app = _FakePollingApp(enabled=False)
        app._tick_adaptive_polling()
        app._adaptive_timer.start.assert_called_once_with(
            C.POLL_MIN_INTERVAL * 1000
        )


class TestRearm:
    def test_none_uses_min_interval(self) -> None:
        assert _adaptive_rearm_delay_ms(None, 1000.0, 5000) == 15000

    def test_future_uses_relative_delay(self) -> None:
        assert _adaptive_rearm_delay_ms(1100.0, 1000.0, 5000) == 100000

    def test_past_clamped_to_floor(self) -> None:
        assert _adaptive_rearm_delay_ms(900.0, 1000.0, 5000) == 5000

    def test_exception_falls_back_to_floor(self) -> None:
        app = _FakePollingApp()
        app._polling_mgr.next_due_min.side_effect = RuntimeError("boom")
        app._tick_adaptive_polling()
        app._future.fire()
        app._adaptive_timer.start.assert_called_once_with(
            C.POLL_TICK_FLOOR_MS
        )


class TestFlag:
    def test_flag_off_ignores_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(C.POLL_ENABLED_ENV, raising=False)
        assert _adaptive_polling_flag(lambda _key: "key") is False

    def test_flag_on_without_key_fails_closed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(C.POLL_ENABLED_ENV, "1")
        assert _adaptive_polling_flag(lambda _key: "") is False

    def test_flag_on_with_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(C.POLL_ENABLED_ENV, "1")
        assert _adaptive_polling_flag(lambda _key: "key") is True

    def test_guard_truth_table(self) -> None:
        assert _adaptive_polling_guard(True, False, "cli") is True
        assert _adaptive_polling_guard(True, False, "real") is True
        assert _adaptive_polling_guard(False, False, "cli") is False
        assert _adaptive_polling_guard(True, True, "cli") is False
        assert _adaptive_polling_guard(True, False, "mock") is False


class TestSvcMode:
    def test_real_is_alias_for_cli(self) -> None:
        assert _resolve_svc_mode("real") == "cli"
        assert _resolve_svc_mode("REAL") == "cli"

    def test_valid_modes(self) -> None:
        assert _resolve_svc_mode("mock") == "mock"
        assert _resolve_svc_mode("cli") == "cli"

    def test_invalid_falls_back_to_mock(self) -> None:
        assert _resolve_svc_mode("bogus") == "mock"
        assert _resolve_svc_mode("") == "mock"
