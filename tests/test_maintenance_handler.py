"""Testes do MaintenanceMixin (handlers/maintenance.py).

A execução saiu da View (``pages/manutencao.py``) para o handler; aqui
cobrimos RBAC, montagem dos comandos, streaming/cancelamento/timeout e
delegação dos agentes.
"""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from huawei_manager._config import PROJECT_ROOT
from huawei_manager.handlers.maintenance import MaintenanceMixin


class _FakeProc:
    """Processo falso: stdout iterável + wait/kill controláveis."""

    def __init__(self, lines: list[str], returncode: int = 0,
                 wait_error: Exception | None = None) -> None:
        self.stdout = iter(lines)
        self.returncode = returncode
        self._wait_error = wait_error
        self.killed = False

    def poll(self) -> None:
        return None

    def wait(self, timeout: float | None = None) -> int:
        if self._wait_error is not None:
            raise self._wait_error
        return self.returncode

    def kill(self) -> None:
        self.killed = True


def _make_mixin(**attrs) -> MaintenanceMixin:
    mixin = MaintenanceMixin()
    defaults = {
        "_manut_output": MagicMock(),
        "_cancel_event": None,
        "_access_level": "tecnico",
        "_watcher_results": None,
        "_require_access": MagicMock(return_value=True),
        "_spawn_io": lambda fn: fn(),
        "_spawn_cpu": lambda fn: fn(),
        "_dispatch": MagicMock(side_effect=lambda fn: fn() if callable(fn) else None),
        "_write": MagicMock(),
        "_loading": MagicMock(),
        "_display_watcher_results": MagicMock(),
    }
    for key, value in defaults.items():
        setattr(mixin, key, value)
    for key, value in attrs.items():
        setattr(mixin, key, value)
    return mixin


def _output_texts(mixin: MaintenanceMixin) -> list[str]:
    out = mixin._manut_output
    texts: list[str] = []
    for call in out.setPlainText.call_args_list:
        texts.append(str(call.args[0]))
    for call in out.append.call_args_list:
        texts.append(str(call.args[0]))
    return texts


class TestRunDevCmd:
    def test_requires_tecnico(self) -> None:
        spawn = MagicMock()
        mixin = _make_mixin(
            _require_access=MagicMock(return_value=False), _spawn_io=spawn)
        mixin._run_dev_cmd("all")
        spawn.assert_not_called()
        mixin._loading.assert_not_called()

    def test_runs_make_ci_for_all(self) -> None:
        proc = _FakeProc(["linha 1\n", "linha 2\n"])
        with patch("subprocess.Popen", return_value=proc) as popen:
            mixin = _make_mixin()
            mixin._run_dev_cmd("all")

        popen.assert_called_once_with(
            ["make", "ci"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        texts = _output_texts(mixin)
        assert any("linha 1" in text and "linha 2" in text for text in texts)
        assert any("\u2705  Concluido" in text for text in texts)
        assert mixin._cancel_event is None

    def test_unknown_target_runs_true(self) -> None:
        proc = _FakeProc([])
        with patch("subprocess.Popen", return_value=proc) as popen:
            _make_mixin()._run_dev_cmd("inexistente")
        assert popen.call_args.args[0] == ["true"]

    def test_nonzero_exit_is_reported(self) -> None:
        proc = _FakeProc(["falhou\n"], returncode=2)
        with patch("subprocess.Popen", return_value=proc):
            mixin = _make_mixin()
            mixin._run_dev_cmd("lint")
        assert any("exit 2" in text for text in _output_texts(mixin))

    def test_timeout_is_reported(self) -> None:
        proc = _FakeProc(
            [], wait_error=subprocess.TimeoutExpired("make test", 180))
        with patch("subprocess.Popen", return_value=proc):
            mixin = _make_mixin()
            mixin._run_dev_cmd("test")
        assert any("Timeout (180s)" in text for text in _output_texts(mixin))


class TestRunSetup:
    def test_uses_install_script_and_setup_timeout(self) -> None:
        spawn = MagicMock()
        mixin = _make_mixin(_spawn_stream=spawn)
        mixin._run_setup("check")

        args, kwargs = spawn.call_args
        assert args[0] == [str(PROJECT_ROOT / "setup" / "install.sh"),
                           "install", "check"]
        assert kwargs["timeout_s"] == 120
        assert "install.sh install check" in kwargs["done_label"]

    def test_requires_tecnico(self) -> None:
        spawn = MagicMock()
        mixin = _make_mixin(
            _require_access=MagicMock(return_value=False), _spawn_stream=spawn)
        mixin._run_setup("install")
        spawn.assert_not_called()


class TestRunAgents:
    def test_publishes_results(self) -> None:
        results = [MagicMock()]
        mixin = _make_mixin()
        with patch("huawei_manager.agents.runner.run_all", return_value=results):
            mixin._run_agents()
        assert mixin._watcher_results is results
        mixin._display_watcher_results.assert_called_once_with(results)

    def test_failure_is_reported_to_output(self) -> None:
        mixin = _make_mixin()
        with patch("huawei_manager.agents.runner.run_all",
                   side_effect=RuntimeError("boom")):
            mixin._run_agents()
        mixin._write.assert_called_once()
        assert "Erro nos agentes" in str(mixin._write.call_args)

    def test_requires_tecnico(self) -> None:
        spawn = MagicMock()
        mixin = _make_mixin(
            _require_access=MagicMock(return_value=False), _spawn_cpu=spawn)
        mixin._run_agents()
        spawn.assert_not_called()


class TestCancelAndClear:
    def test_sets_event_when_exists(self) -> None:
        mixin = _make_mixin()
        cancel = MagicMock()
        mixin._cancel_event = cancel
        mixin._cancel_and_clear()
        cancel.set.assert_called_once()
        assert mixin._cancel_event is None

    def test_clears_output_when_no_event(self) -> None:
        mixin = _make_mixin()
        mixin._cancel_and_clear()
        mixin._write.assert_called_once_with(mixin._manut_output, "")


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("lint", ["make", "lint"]),
        ("test", ["make", "test"]),
        ("typecheck", ["make", "typecheck"]),
        ("all", ["make", "ci"]),
    ],
)
def test_dev_targets_map_to_make(target: str, expected: list[str]) -> None:
    proc = _FakeProc([])
    with patch("subprocess.Popen", return_value=proc) as popen:
        _make_mixin()._run_dev_cmd(target)
    assert popen.call_args.args[0] == expected
