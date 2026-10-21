"""Testes de caracterização — CommandsMixin (handlers/commands.py).

Após a F2-cmd o mixin guarda só o backup de configuração; os caminhos de
editor/exec/rollback migraram para tests/tabs/cmd/test_handlers.py
(CmdHandlers(ctx, state)).
"""
from __future__ import annotations

from unittest.mock import MagicMock, mock_open, patch

from huawei_manager.exceptions import SdnError
from huawei_manager.handlers.commands import CommandsMixin
from huawei_manager.sdn_controller.event_queue import EventType


def _make_mixin(**attrs) -> CommandsMixin:
    mixin = CommandsMixin()
    defaults = dict(
        _session_tracker=MagicMock(),
        _sb=MagicMock(),
        _write=MagicMock(),
        _loading=MagicMock(),
        _dispatch=MagicMock(side_effect=lambda fn: fn() if callable(fn) else None),
        _event_queue=MagicMock(),
        _access_level="admin",
        _set_status=MagicMock(),
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


class TestDoBackup:
    """_do_backup characterization."""

    def test_backup_writes_file(self):
        mixin = _make_mixin()
        mixin._sb.send_command.return_value = "interface GigabitEthernet0/0/1"
        mock_audit = MagicMock()
        mock_log = MagicMock()
        with patch("huawei_manager._config.audit", mock_audit), \
             patch("huawei_manager._config.log", mock_log), \
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
        with patch("huawei_manager._config.audit", mock_audit), \
             patch("huawei_manager._config.log", mock_log), \
             patch("builtins.open", mock_open()), \
             patch("os.makedirs"), \
             patch("os.path.getsize", return_value=100):
            mixin._do_backup(fmt="txt")
        mixin._event_queue.put.assert_called_once()

    def test_backup_handles_runtime_error(self):
        mixin = _make_mixin()
        mixin._sb.send_command.side_effect = SdnError("connection lost")
        mixin._do_backup(fmt="txt")
        mixin._sb.invalidate_connection.assert_called_once()
