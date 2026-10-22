"""Testes da aba Editor de Comandos — CmdHandlers (tabs/cmd/handlers.py).

Split de tests/test_commands_mixin.py (F2-cmd): os caminhos de exec_cmd,
exec_config (snapshot fail-closed) e rollback migraram para a classe
injetada CmdHandlers(ctx, state); _do_backup permanece no arquivo legado.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from huawei_manager.command import ConfigCommand
from huawei_manager.exceptions import SdnError
from huawei_manager.sdn_controller.event_queue import EventType
from huawei_manager.tabs._contract import TabContext
from huawei_manager.tabs.cmd.handlers import CmdHandlers
from huawei_manager.tabs.cmd.state import CmdState


def _make_ctx(**overrides) -> TabContext:
    """TabContext fake com todos os 29 campos; overrides por teste."""
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
    )
    fields.update(overrides)
    ctx = TabContext(**fields)
    ctx.session._host = "10.0.0.1"
    ctx.session._user = "admin"
    return ctx


def _make(**overrides) -> tuple[CmdHandlers, CmdState, TabContext]:
    """(handlers, state, ctx) — state.out é MagicMock de saída."""
    ctx = _make_ctx(**overrides)
    state = CmdState()
    state.out = MagicMock()
    return CmdHandlers(ctx, state), state, ctx


def _output_texts(out) -> str:
    """Textos escritos no painel (setPlainText/append), p/ asserts `in`."""
    texts = [c.args[0] for c in out.setPlainText.call_args_list]
    texts += [c.args[0] for c in out.append.call_args_list]
    return "\n".join(str(t) for t in texts)


class TestExecCmd:
    """CmdHandlers.exec_cmd characterization."""

    def test_empty_cmd_writes_error(self):
        h, st, ctx = _make()
        h.exec_cmd("")
        assert "vazio" in _output_texts(st.out)
        ctx.touch_session.assert_called_once()

    def test_sends_command_when_not_sysview(self):
        h, st, ctx = _make()
        ctx.sb.send_command.return_value = "OK"
        h.exec_cmd("display version")
        ctx.sb.send_command.assert_called_once_with("display version")
        assert "OK" in _output_texts(st.out)

    def test_uses_send_config_when_sysview(self):
        h, st, ctx = _make()
        st.sysview_var = True
        ctx.sb.send_config.return_value = (True, "OK")
        h.exec_cmd("interface GigabitEthernet0/0/1")
        ctx.sb.send_config.assert_called_once()

    def test_validator_blocks_command(self):
        validator = MagicMock()
        vr = MagicMock()
        vr.allowed = False
        vr.reason = "blocked"
        validator.validate.return_value = vr
        h, st, ctx = _make(cmd_validator=validator)
        h.exec_cmd("configure terminal")
        assert "Comando bloqueado" in _output_texts(st.out)
        ctx.sb.send_command.assert_not_called()

    def test_validator_allows_command(self):
        validator = MagicMock()
        vr = MagicMock()
        vr.allowed = True
        validator.validate.return_value = vr
        h, st, ctx = _make(cmd_validator=validator)
        ctx.sb.send_command.return_value = "OK"
        h.exec_cmd("display version")
        ctx.sb.send_command.assert_called_once()

    def test_runtime_error_invalidates_connection(self):
        h, st, ctx = _make()
        ctx.sb.send_command.side_effect = SdnError("connection lost")
        h.exec_cmd("display version")
        ctx.sb.invalidate_connection.assert_called_once()
        assert "Falha SSH" in _output_texts(st.out)

    def test_posts_event_on_success(self):
        h, st, ctx = _make()
        ctx.sb.send_command.return_value = "OK"
        h.exec_cmd("display version")
        ctx.event_bus.put.assert_called_once()


class TestExecConfig:
    """CmdHandlers.exec_config characterization."""

    def test_empty_cmd_writes_error(self):
        h, st, ctx = _make()
        h.exec_config("")
        assert "vazio" in _output_texts(st.out)

    def test_applies_config(self):
        h, st, ctx = _make()
        ctx.sb.send_config.return_value = (True, "OK")
        h.exec_config("interface GigabitEthernet0/0/1")
        ctx.sb.send_config.assert_called_once()

    def test_config_blocked_by_validator(self):
        validator = MagicMock()
        vr = MagicMock()
        vr.allowed = False
        vr.reason = "blocked"
        validator.validate.return_value = vr
        h, st, ctx = _make(cmd_validator=validator)
        h.exec_config("configure terminal")
        assert "Config bloqueada" in _output_texts(st.out)

    def test_runtime_error_invalidates_connection(self):
        h, st, ctx = _make()
        ctx.sb.send_config.side_effect = SdnError("connection lost")
        h.exec_config("interface GigabitEthernet0/0/1")
        ctx.sb.invalidate_connection.assert_called_once()


# ══════════════════════════════════════════════════════════════════════
#  Command pattern: snapshot pré-mudança em exec_config
# ══════════════════════════════════════════════════════════════════════
class TestExecConfigSnapshot:
    """exec_config só aplica com snapshot (fail-closed)."""

    def test_snapshot_failure_aborts_apply(self):
        h, st, ctx = _make()
        ctx.sb.send_command.side_effect = SdnError("conexão caiu")
        with patch("huawei_manager._config.audit", MagicMock()):
            h.exec_config("interface GigabitEthernet0/0/1")
        ctx.sb.send_config.assert_not_called()
        ctx.sb.invalidate_connection.assert_called_once()
        assert "NÃO aplicada" in _output_texts(st.out)
        ctx.set_last_config_command.assert_not_called()

    def test_success_stores_command_with_snapshot(self):
        h, st, ctx = _make()
        ctx.sb.send_command.return_value = "baseline cfg"
        ctx.sb.send_config.return_value = (True, "OK")
        mock_audit = MagicMock()
        with patch("huawei_manager._config.audit", mock_audit):
            h.exec_config("interface GigabitEthernet0/0/1")
        command = ctx.set_last_config_command.call_args.args[0]
        assert isinstance(command, ConfigCommand)
        assert command.snapshot == "baseline cfg"
        ctx.sb.send_command.assert_called_once_with(
            "display current-configuration")
        mock_audit.log_operation.assert_called_once()
        assert mock_audit.log_operation.call_args.args == ("config_apply",)

    def test_apply_failure_keeps_command_for_rollback(self):
        h, st, ctx = _make()
        ctx.sb.send_command.return_value = "baseline cfg"
        ctx.sb.send_config.side_effect = SdnError("ssh morreu")
        with patch("huawei_manager._config.audit", MagicMock()):
            h.exec_config("interface GigabitEthernet0/0/1")
        ctx.sb.invalidate_connection.assert_called_once()
        # snapshot sobreviveu → rollback disponível após reconectar
        command = ctx.set_last_config_command.call_args.args[0]
        assert isinstance(command, ConfigCommand)
        assert command.snapshot == "baseline cfg"
        assert "Falha SSH" in _output_texts(st.out)


# ══════════════════════════════════════════════════════════════════════
#  Command pattern: rollback da última configuração
# ══════════════════════════════════════════════════════════════════════
SNAP = "hostname R1\nntp server 1.1.1.1\n"
CHANGED = "hostname R1\n"


def _make_command(read_states) -> ConfigCommand:
    read = MagicMock(side_effect=list(read_states))
    return ConfigCommand(
        ["ntp server 1.1.1.1"],
        read_state=read,
        apply_fn=lambda lines: (True, "restaurado"),
    )


class TestRollbackEntryPoint:
    """rollback_last_config (UI) e do_rollback_config (IO)."""

    def test_nothing_to_undo_writes_info(self):
        h, st, ctx = _make()
        h.rollback_last_config()
        assert "Nada a desfazer" in _output_texts(st.out)
        ctx.run.assert_not_called()

    def test_dispatches_to_io_thread(self):
        h, st, ctx = _make(
            get_last_config_command=MagicMock(return_value=MagicMock()))
        h.rollback_last_config()
        ctx.run.assert_called_once()

    def test_rollback_ok_clears_command_and_audits(self):
        command = _make_command([SNAP, CHANGED, SNAP])
        command.capture_snapshot()
        h, st, ctx = _make()
        mock_audit = MagicMock()
        with patch("huawei_manager._config.audit", mock_audit):
            h.do_rollback_config(command)
        # restaurado por completo → snapshot descartado
        ctx.set_last_config_command.assert_called_once_with(None)
        assert "Rollback concluído" in _output_texts(st.out)
        assert mock_audit.log_operation.call_args.args == ("config_rollback",)
        assert mock_audit.log_operation.call_args.kwargs["status"] == "ok"
        ev = ctx.event_bus.put.call_args[0][0]
        assert ev.type is EventType.CONFIG_CHANGED

    def test_rollback_ssh_failure_keeps_command(self):
        command = _make_command([SNAP, SdnError("caiu")])
        command.capture_snapshot()
        h, st, ctx = _make()
        mock_audit = MagicMock()
        with patch("huawei_manager._config.audit", mock_audit):
            h.do_rollback_config(command)
        # mantido para retry após reconectar
        ctx.set_last_config_command.assert_not_called()
        assert "Falha SSH no rollback" in _output_texts(st.out)
        ctx.sb.invalidate_connection.assert_called_once()
        kwargs = mock_audit.log_operation.call_args.kwargs
        assert kwargs["status"] == "error"
