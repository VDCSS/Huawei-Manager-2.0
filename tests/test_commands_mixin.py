"""Testes de caracterização — CommandsMixin (handlers/commands.py).

Testa caminhos de _exec_cmd, _exec_config, _do_backup com mocks.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, mock_open, patch, call

from huawei_manager.handlers.commands import CommandsMixin


def _make_mixin(**attrs) -> CommandsMixin:
    mixin = CommandsMixin()
    defaults = dict(
        _cmd_editor=MagicMock(),
        _session_tracker=MagicMock(),
        _sb=MagicMock(),
        _write=MagicMock(),
        _loading=MagicMock(),
        _dispatch=MagicMock(side_effect=lambda fn: fn() if callable(fn) else None),
        _event_queue=MagicMock(),
        _cmd_validator=None,
        _dry_run=None,
        _sysview_var=False,
        _access_level="admin",
        _set_status=MagicMock(),
        out_cmd=MagicMock(),
        out_backup=MagicMock(),
        backup_path="/tmp/test-backup",
    )
    for k, v in defaults.items():
        setattr(mixin, k, v)
    for k, v in attrs.items():
        setattr(mixin, k, v)
    mixin.session = MagicMock()
    mixin.session._host = "10.0.0.1"
    mixin.session._user = "admin"
    return mixin


class TestGetEditorCmd:
    """_get_editor_cmd retorna texto limpo do editor."""

    def test_returns_stripped_text(self):
        mixin = _make_mixin()
        mixin._cmd_editor.toPlainText.return_value = "  display version  "
        assert mixin._get_editor_cmd() == "display version"

    def test_returns_empty_string_when_blank(self):
        mixin = _make_mixin()
        mixin._cmd_editor.toPlainText.return_value = "   "
        assert mixin._get_editor_cmd() == ""


class TestExecCmd:
    """_exec_cmd characterization."""

    def test_empty_cmd_writes_error(self):
        mixin = _make_mixin()
        mixin._exec_cmd("")
        mixin._write.assert_called_once()
        assert "vazio" in str(mixin._write.call_args)

    def test_sends_command_when_not_sysview(self):
        mixin = _make_mixin()
        mixin._sb.send_command.return_value = "OK"
        mixin._exec_cmd("display version")
        mixin._sb.send_command.assert_called_once_with("display version")
        mixin._write.assert_called_once()

    def test_uses_send_config_when_sysview(self):
        mixin = _make_mixin(_sysview_var=True)
        mixin._sb.send_config.return_value = (True, "OK")
        mixin._exec_cmd("interface GigabitEthernet0/0/1")
        mixin._sb.send_config.assert_called_once()

    def test_validator_blocks_command(self):
        validator = MagicMock()
        vr = MagicMock()
        vr.allowed = False
        vr.reason = "blocked"
        validator.validate.return_value = vr
        mixin = _make_mixin(_cmd_validator=validator)
        mixin._exec_cmd("configure terminal")
        mixin._write.assert_called_once()
        assert "Comando bloqueado" in str(mixin._write.call_args)

    def test_validator_allows_command(self):
        validator = MagicMock()
        vr = MagicMock()
        vr.allowed = True
        validator.validate.return_value = vr
        mixin = _make_mixin(_cmd_validator=validator)
        mixin._sb.send_command.return_value = "OK"
        mixin._exec_cmd("display version")
        mixin._sb.send_command.assert_called_once()

    def test_runtime_error_invalidates_connection(self):
        mixin = _make_mixin()
        mixin._sb.send_command.side_effect = RuntimeError("connection lost")
        mixin._exec_cmd("display version")
        mixin._sb.invalidate_connection.assert_called_once()

    def test_posts_event_on_success(self):
        mixin = _make_mixin()
        mixin._sb.send_command.return_value = "OK"
        mixin._exec_cmd("display version")
        mixin._event_queue.put.assert_called_once()


class TestExecConfig:
    """_exec_config characterization."""

    def test_empty_cmd_writes_error(self):
        mixin = _make_mixin()
        mixin._exec_config("")
        mixin._write.assert_called_once()
        assert "vazio" in str(mixin._write.call_args)

    def test_applies_config(self):
        mixin = _make_mixin()
        mixin._sb.send_config.return_value = (True, "OK")
        mixin._exec_config("interface GigabitEthernet0/0/1")
        mixin._sb.send_config.assert_called_once()

    def test_config_blocked_by_validator(self):
        validator = MagicMock()
        vr = MagicMock()
        vr.allowed = False
        vr.reason = "blocked"
        validator.validate.return_value = vr
        mixin = _make_mixin(_cmd_validator=validator)
        mixin._exec_config("configure terminal")
        assert "Config bloqueada" in str(mixin._write.call_args)

    def test_runtime_error_invalidates_connection(self):
        mixin = _make_mixin()
        mixin._sb.send_config.side_effect = RuntimeError("connection lost")
        mixin._exec_config("interface GigabitEthernet0/0/1")
        mixin._sb.invalidate_connection.assert_called_once()


class TestDoBackup:
    """_do_backup characterization."""

    def test_backup_writes_file(self):
        mixin = _make_mixin()
        mixin._sb.send_command.return_value = "interface GigabitEthernet0/0/1"
        mock_audit = MagicMock()
        mock_log = MagicMock()
        with patch("huawei_manager.handlers.commands.audit", mock_audit), \
             patch("huawei_manager.handlers.commands.log", mock_log), \
             patch("builtins.open", mock_open()), \
             patch("os.makedirs"), \
             patch("os.path.getsize", return_value=100):
            mixin._do_backup(fmt="txt")
        mixin._write.assert_called_once()

    def test_backup_posts_event(self):
        mixin = _make_mixin()
        mixin._sb.send_command.return_value = "config data"
        mock_audit = MagicMock()
        mock_log = MagicMock()
        with patch("huawei_manager.handlers.commands.audit", mock_audit), \
             patch("huawei_manager.handlers.commands.log", mock_log), \
             patch("builtins.open", mock_open()), \
             patch("os.makedirs"), \
             patch("os.path.getsize", return_value=100):
            mixin._do_backup(fmt="txt")
        mixin._event_queue.put.assert_called_once()

    def test_backup_handles_runtime_error(self):
        mixin = _make_mixin()
        mixin._sb.send_command.side_effect = RuntimeError("connection lost")
        mixin._do_backup(fmt="txt")
        mixin._sb.invalidate_connection.assert_called_once()
