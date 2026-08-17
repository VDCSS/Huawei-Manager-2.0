"""Testes de caracterização — ServicesMixin (handlers/services.py).

Testa caminhos de _run_service (mock, cli, param validation),
confirmação de operação destrutiva e auditoria de bloqueio.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from huawei_manager.handlers.services import ServicesMixin
from huawei_manager.services import ServiceDef


def _make_svc(**overrides) -> ServiceDef:
    defaults = dict(
        id="svc-001",
        name="Test Service",
        description="test command <param1>",
        category="test",
        device_types=["ROUTER"],
        cli_commands=["test command <param1>"],
        config_mode=False,
    )
    defaults.update(overrides)
    return ServiceDef(**defaults)


def _make_mixin(**attrs) -> ServicesMixin:
    mixin = ServicesMixin()
    defaults = dict(
        _svc_mode_var="mock",
        _target_device=None,
        _svc_device_lbl=MagicMock(),
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
    def test_sets_label_without_device(self):
        mixin = _make_mixin()
        svc = _make_svc()
        mixin._run_service(svc)
        mixin._svc_device_lbl.setText.assert_called_once()
        label = mixin._svc_device_lbl.setText.call_args[0][0]
        assert "Test Service" in label

    def test_sets_label_with_device(self):
        device = MagicMock()
        device.name = "MyDevice"
        device.host = "10.0.0.1"
        mixin = _make_mixin(_target_device=device)
        svc = _make_svc()
        mixin._run_service(svc)
        label = mixin._svc_device_lbl.setText.call_args[0][0]
        assert "MyDevice" in label

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


class TestDestructiveConfirmation:

    def test_cancel_writes_and_does_not_spawn(self):
        mixin = _make_mixin()
        svc = _make_svc(config_mode=True, cli_commands=["reset saved-configuration"])
        with patch("PySide6.QtWidgets.QMessageBox") as msgbox:
            msgbox.question.return_value = msgbox.StandardButton.No
            mixin._run_service(svc)
        msgbox.question.assert_called_once()
        mixin._spawn_io.assert_not_called()
        written = mixin._write.call_args[0][1]
        assert "cancelada" in written

    def test_confirm_spawns(self):
        mixin = _make_mixin()
        svc = _make_svc(config_mode=True, cli_commands=["shutdown"])
        with patch("PySide6.QtWidgets.QMessageBox") as msgbox:
            msgbox.question.return_value = msgbox.StandardButton.Yes
            mixin._run_service(svc)
        msgbox.question.assert_called_once()
        mixin._spawn_io.assert_called_once()

    def test_confirm_does_not_bypass_hard_deny(self):
        mixin = _make_mixin()
        svc = _make_svc(config_mode=True, cli_commands=["reset saved-configuration"])
        with patch("PySide6.QtWidgets.QMessageBox") as msgbox:
            msgbox.question.return_value = msgbox.StandardButton.Yes
            mixin._run_service(svc)
        msgbox.question.assert_called_once()
        mixin._spawn_io.assert_not_called()
        written = mixin._write.call_args[0][1]
        assert "bloqueado" in written

    def test_non_destructive_no_dialog(self):
        mixin = _make_mixin()
        svc = _make_svc(config_mode=True)
        with patch("PySide6.QtWidgets.QMessageBox") as msgbox:
            mixin._run_service(svc)
        msgbox.question.assert_not_called()


class TestAuditDenied:

    def test_logs_operation_when_rejected(self):
        logger = MagicMock()
        mixin = _make_mixin(audit_logger=logger)
        svc = _make_svc(cli_commands=["delete flash:/file.cfg"])
        mixin._run_service(svc)
        logger.log_operation.assert_called_once()
        kwargs = logger.log_operation.call_args.kwargs
        assert kwargs.get("status") == "blocked"
        assert kwargs.get("service") == "Test Service"

    def test_skips_audit_when_no_logger(self):
        mixin = _make_mixin()
        svc = _make_svc(cli_commands=["delete flash:/file.cfg"])
        mixin._run_service(svc)
        mixin._spawn_io.assert_not_called()
        written = mixin._write.call_args[0][1]
        assert "bloqueado" in written
