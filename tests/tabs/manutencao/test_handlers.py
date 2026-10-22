"""Testes do MaintenanceHandlers (tabs/manutencao/handlers.py).

Cobrem o handler injetado da aba Manutenção (Fase 1): RBAC via
ctx.require_access, montagem dos comandos make/install.sh, streaming com
cancelamento cooperativo/timeout e a publicação dos agentes no snapshot
global (ctx.set_watcher_results). Sem Qt: estado e ctx são fakes.
"""
from __future__ import annotations

import subprocess
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from huawei_manager._config import PROJECT_ROOT
from huawei_manager.tabs._contract import TabContext
from huawei_manager.tabs.manutencao.handlers import MaintenanceHandlers
from huawei_manager.tabs.manutencao.state import ManutencaoState


class _FakeProc:
    """Subprocess.Popen fake: stdout iterável, wait/kill controláveis."""

    def __init__(self, lines, returncode=0, wait_error=None):
        self.stdout = iter(lines)
        self.returncode = returncode
        self._wait_error = wait_error
        self.killed = False

    def poll(self):
        return None

    def wait(self, timeout=None):
        if self._wait_error is not None:
            raise self._wait_error
        return self.returncode

    def kill(self):
        self.killed = True


def _make_ctx(**overrides: Any) -> TabContext:
    """TabContext fake: tudo síncrono (dispatch/spawn executam na hora)."""
    fields: dict[str, Any] = dict(
        sb=MagicMock(),
        audit=None,
        event_bus=MagicMock(),
        role=lambda: "tecnico",
        device=lambda: None,
        dispatch=lambda fn: fn() if callable(fn) else None,
        require_access=lambda level: True,
        spawn_io=lambda fn, *args: fn(*args),
        spawn_cpu=lambda fn, *args: fn(*args),
        watcher=MagicMock(),
        is_mock=lambda: False,
        toggle_mock=lambda: False,
        show_auth_dialog=lambda: None,
        watcher_results=lambda: None,
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
        devices=lambda: [],
        show_page=MagicMock(),
        svc_mode=lambda: "mock",
        ui_bridge=lambda: None,
        ensure_device_ready=MagicMock(return_value=None),
    )
    fields.update(overrides)
    return TabContext(**fields)


def _make(**ctx_overrides: Any):
    """Monta (handlers, state, display, ctx) sem Qt."""
    state = ManutencaoState()
    state.output = MagicMock()
    display = MagicMock()
    ctx = _make_ctx(**ctx_overrides)
    handlers = MaintenanceHandlers(ctx, state, display)
    return handlers, state, display, ctx


def _output_texts(out) -> list[str]:
    texts = [str(c.args[0]) for c in out.setPlainText.call_args_list]
    texts += [str(c.args[0]) for c in out.append.call_args_list]
    return texts


class TestRunDevCmd:
    def test_requires_tecnico(self):
        spawn = MagicMock()
        handlers, state, _display, _ctx = _make(
            require_access=lambda level: False, spawn_io=spawn)
        handlers.run_dev_cmd("all")
        spawn.assert_not_called()
        state.output.setPlainText.assert_not_called()

    def test_runs_make_ci_for_all(self):
        proc = _FakeProc(["linha 1\n", "linha 2\n"])
        with patch("subprocess.Popen", return_value=proc) as popen:
            handlers, state, _display, _ctx = _make()
            handlers.run_dev_cmd("all")

        popen.assert_called_once_with(
            ["make", "ci"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        texts = _output_texts(state.output)
        assert any("linha 1" in t and "linha 2" in t for t in texts)
        assert any("✅  Concluido" in t for t in texts)
        assert state.cancel_event is None

    def test_unknown_target_runs_true(self):
        proc = _FakeProc([])
        with patch("subprocess.Popen", return_value=proc) as popen:
            handlers, _state, _display, _ctx = _make()
            handlers.run_dev_cmd("inexistente")
        assert popen.call_args[0][0] == ["true"]

    def test_nonzero_exit_reported(self):
        proc = _FakeProc([], returncode=2)
        with patch("subprocess.Popen", return_value=proc):
            handlers, state, _display, _ctx = _make()
            handlers.run_dev_cmd("lint")
        assert any("exit 2" in t for t in _output_texts(state.output))

    def test_timeout_reported(self):
        proc = _FakeProc(
            [], wait_error=subprocess.TimeoutExpired("make test", 180))
        with patch("subprocess.Popen", return_value=proc):
            handlers, state, _display, _ctx = _make()
            handlers.run_dev_cmd("test")
        assert any("Timeout (180s)" in t for t in _output_texts(state.output))


class TestDevCommandMap:
    @pytest.mark.parametrize("target,expected", [
        ("lint", ["make", "lint"]),
        ("test", ["make", "test"]),
        ("typecheck", ["make", "typecheck"]),
        ("all", ["make", "ci"]),
    ])
    def test_maps_target_to_make(self, target, expected):
        proc = _FakeProc([])
        with patch("subprocess.Popen", return_value=proc) as popen:
            handlers, _state, _display, _ctx = _make()
            handlers.run_dev_cmd(target)
        assert popen.call_args[0][0] == expected


class TestRunSetup:
    def test_uses_install_script_with_setup_timeout(self):
        handlers, _state, _display, _ctx = _make()
        spawn = MagicMock()
        setattr(handlers, "spawn_stream", spawn)
        handlers.run_setup("check")
        args, kwargs = spawn.call_args
        assert args[0] == [
            str(PROJECT_ROOT / "setup" / "install.sh"), "install", "check"]
        assert kwargs["timeout_s"] == 120
        assert "install.sh install check" in kwargs["done_label"]

    def test_requires_tecnico(self):
        spawn = MagicMock()
        handlers, _state, _display, _ctx = _make(
            require_access=lambda level: False)
        setattr(handlers, "spawn_stream", spawn)
        handlers.run_setup("install")
        spawn.assert_not_called()


class TestRunAgents:
    def test_publishes_results_to_snapshot_and_display(self):
        results = [MagicMock()]
        handlers, _state, display, ctx = _make()
        with patch("huawei_manager.agents.runner.run_all",
                   return_value=results):
            handlers.run_agents()
        ctx.set_watcher_results.assert_called_once()
        assert ctx.set_watcher_results.call_args.args[0] is results
        display.assert_called_once_with(results)

    def test_failure_is_reported_to_output(self):
        handlers, state, _display, _ctx = _make()
        with patch("huawei_manager.agents.runner.run_all",
                   side_effect=RuntimeError("boom")):
            handlers.run_agents()
        assert any("Erro nos agentes" in t for t in _output_texts(state.output))

    def test_requires_tecnico(self):
        spawn = MagicMock()
        handlers, _state, _display, _ctx = _make(
            require_access=lambda level: False, spawn_cpu=spawn)
        handlers.run_agents()
        spawn.assert_not_called()


class TestCancelAndClear:
    def test_sets_existing_event_and_clears_it(self):
        event = MagicMock()
        handlers, state, _display, _ctx = _make()
        state.cancel_event = event
        handlers.cancel_and_clear()
        event.set.assert_called_once()
        assert state.cancel_event is None

    def test_clears_output_when_no_event(self):
        handlers, state, _display, _ctx = _make()
        handlers.cancel_and_clear()
        state.output.setPlainText.assert_called_once_with("")
