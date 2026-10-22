"""Testes da aba Backup — BackupHandlers (tabs/backup/handlers.py).

Migrados de tests/test_commands_mixin.py (F2-backup): o _do_backup do
CommandsMixin virou BackupHandlers.do_backup(ctx, state); o arquivo
legado foi removido junto com o mixin.
"""
from __future__ import annotations

from unittest.mock import MagicMock, mock_open, patch

from huawei_manager.exceptions import SdnError
from huawei_manager.tabs._contract import TabContext
from huawei_manager.tabs.backup.handlers import BackupHandlers
from huawei_manager.tabs.backup.state import BackupState


def _make_ctx(**overrides) -> TabContext:
    """TabContext fake com todos os 34 campos; overrides por teste."""
    fields = dict(
        sb=MagicMock(),
        audit=None,
        event_bus=MagicMock(),
        role=lambda: "admin",
        device=lambda: None,
        dispatch=lambda fn: fn() if callable(fn) else None,
        require_access=lambda level: True,
        spawn_io=lambda fn, *args: None,
        spawn_cpu=lambda fn, *args: None,
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
        get_last_config_command=MagicMock(return_value=None),
        set_last_config_command=MagicMock(),
        drv=lambda: MagicMock(),
        devices=lambda: [],
        show_page=MagicMock(),
        svc_mode=lambda: "mock",
        ui_bridge=lambda: None,
        ensure_device_ready=MagicMock(return_value=None),
        refresh_devices=MagicMock(),
        show_device_dialog=MagicMock(),
        delete_device=MagicMock(),
        on_device_selected=MagicMock(),
        clear_device_target=MagicMock(),
    )
    fields.update(overrides)
    ctx = TabContext(**fields)
    ctx.session._host = "10.0.0.1"
    ctx.session._user = "admin"
    return ctx


def _make(**overrides) -> tuple[BackupHandlers, BackupState, TabContext]:
    """(handlers, state, ctx) — state.out é MagicMock de saída."""
    ctx = _make_ctx(**overrides)
    state = BackupState()
    state.out = MagicMock()
    state.backup_path = "/tmp/test-backup"
    return BackupHandlers(ctx, state), state, ctx


def _output_texts(out) -> str:
    """Textos escritos no painel (setPlainText/append), p/ asserts `in`."""
    texts = [c.args[0] for c in out.setPlainText.call_args_list]
    texts += [c.args[0] for c in out.append.call_args_list]
    return "\n".join(str(t) for t in texts)


class TestDoBackup:
    """BackupHandlers.do_backup characterization."""

    def test_backup_writes_file(self):
        h, st, ctx = _make()
        ctx.sb.send_command.return_value = "interface GigabitEthernet0/0/1"
        mock_audit = MagicMock()
        mock_log = MagicMock()
        with patch("huawei_manager._config.audit", mock_audit), \
             patch("huawei_manager._config.log", mock_log), \
             patch("builtins.open", mock_open()), \
             patch("os.makedirs"), \
             patch("os.path.getsize", return_value=100):
            h.do_backup(fmt="txt")
        assert "Backup concluido" in _output_texts(st.out)

    def test_backup_posts_event(self):
        h, st, ctx = _make()
        ctx.sb.send_command.return_value = "config data"
        mock_audit = MagicMock()
        mock_log = MagicMock()
        with patch("huawei_manager._config.audit", mock_audit), \
             patch("huawei_manager._config.log", mock_log), \
             patch("builtins.open", mock_open()), \
             patch("os.makedirs"), \
             patch("os.path.getsize", return_value=100):
            h.do_backup(fmt="txt")
        ctx.event_bus.put.assert_called_once()

    def test_backup_handles_runtime_error(self):
        h, st, ctx = _make()
        ctx.sb.send_command.side_effect = SdnError("connection lost")
        h.do_backup(fmt="txt")
        ctx.sb.invalidate_connection.assert_called_once()
        assert "Falha SSH" in _output_texts(st.out)
