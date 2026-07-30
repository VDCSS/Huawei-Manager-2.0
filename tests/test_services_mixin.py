"""Testes de caracterização — ServicesMixin (handlers/services.py).

Testa caminhos de _run_service (mock, cli, param validation).
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from huawei_manager.handlers.services import ServicesMixin
from huawei_manager.services import ServiceDef


def _make_svc(**overrides) -> ServiceDef:
    defaults = dict(
        id="svc-001",
        name="Test Service",
        description="test command <param1>",
        category="test",
        vnf_types=["ROUTER"],
        cli_commands=["test command <param1>"],
        config_mode=False,
    )
    defaults.update(overrides)
    return ServiceDef(**defaults)


def _make_mixin(**attrs) -> ServicesMixin:
    mixin = ServicesMixin()
    defaults = dict(
        _svc_mode_var="mock",
        _target_vnf=None,
        _svc_vnf_lbl=MagicMock(),
        _svc_output=MagicMock(),
        _svc_param_entries={},
        _sb=MagicMock(),
        _write=MagicMock(),
        _loading=MagicMock(),
        _event_queue=MagicMock(),
        _spawn_io=MagicMock(),
    )
    for k, v in defaults.items():
        setattr(mixin, k, v)
    for k, v in attrs.items():
        setattr(mixin, k, v)
    return mixin


class TestRunService:
    def test_sets_label_without_vnf(self):
        mixin = _make_mixin()
        svc = _make_svc()
        mixin._run_service(svc)
        mixin._svc_vnf_lbl.setText.assert_called_once()
        label = mixin._svc_vnf_lbl.setText.call_args[0][0]
        assert "Test Service" in label

    def test_sets_label_with_vnf(self):
        vnf = MagicMock()
        vnf.name = "MyVNF"
        vnf.host = "10.0.0.1"
        mixin = _make_mixin(_target_vnf=vnf)
        svc = _make_svc()
        mixin._run_service(svc)
        label = mixin._svc_vnf_lbl.setText.call_args[0][0]
        assert "MyVNF" in label

    def test_spawns_io(self):
        mixin = _make_mixin()
        svc = _make_svc()
        mixin._run_service(svc)
        mixin._spawn_io.assert_called_once()

    def test_param_rejects_injection(self):
        mixin = _make_mixin(
            _svc_param_entries={"param1": MagicMock(text=MagicMock(return_value="evil; rm -rf /"))}
        )
        svc = _make_svc(config_mode=True)
        mixin._run_service(svc)
        written = mixin._write.call_args[0][1]
        assert "caracteres invalidos" in written

    def test_param_substitutes_value(self):
        entry = MagicMock()
        entry.text.return_value = "hello world"
        mixin = _make_mixin(_svc_param_entries={"param1": entry})
        svc = _make_svc(config_mode=True)
        mixin._run_service(svc)
        mixin._spawn_io.assert_called_once()

    def test_mock_mode_writes_result(self):
        mixin = _make_mixin()
        svc = _make_svc()

        def _capture_spawn(fn):
            fn()

        mixin._spawn_io = _capture_spawn
        mixin._run_service(svc)
        mixin._write.assert_called()

    def test_cli_no_ssh_writes_error(self):
        mixin = _make_mixin(_svc_mode_var="cli")
        mixin._sb.is_alive.return_value = False
        svc = _make_svc()

        def _capture_spawn(fn):
            fn()

        mixin._spawn_io = _capture_spawn
        mixin._run_service(svc)
        written = mixin._write.call_args[0][1]
        assert "Sem sessao SSH" in written

    def test_unknown_mode_writes_message(self):
        mixin = _make_mixin(_svc_mode_var="unknown")
        mixin._sb.is_alive.return_value = True
        svc = _make_svc()

        def _capture_spawn(fn):
            fn()

        mixin._spawn_io = _capture_spawn
        mixin._run_service(svc)
        written = mixin._write.call_args[0][1]
        assert "desconhecido" in written

    @pytest.mark.parametrize("dangerous_char", [";", "&", "|", "`", "$", "(", ")", "{", "}"])
    def test_param_rejects_all_dangerous_chars(self, dangerous_char):
        mixin = _make_mixin(
            _svc_param_entries={"param1": MagicMock(text=MagicMock(return_value=f"value{dangerous_char}injection"))}
        )
        svc = _make_svc(config_mode=True)
        mixin._run_service(svc)
        written = mixin._write.call_args[0][1]
        assert "caracteres invalidos" in written
