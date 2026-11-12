"""TDD do caminho de execução de bloco de configuração (F0)."""
from __future__ import annotations

import threading
from collections.abc import Iterable
from unittest.mock import MagicMock

import pytest

from huawei_manager.audit_log import AuditLogger
from huawei_manager.basic_config.vrp_version import VrpVersion
from huawei_manager.exceptions import SdnAuthError
from huawei_manager.sdn_controller.southbound import SSHSouthbound
from huawei_manager.session_commands import SessionCommandsMixin
from huawei_manager.vault import EnvBackend


class _Session(SessionCommandsMixin):
    def __init__(self, conn) -> None:
        self._conn = conn
        self._lock = threading.RLock()
        self._audit = MagicMock()
        self._host = "10.0.0.1"
        self._user = "admin"
        self._session_id = "sid"
        self._reset_protect_session_log()

    def _write_raw(self, data: bytes) -> None:
        self._conn.write_channel(data)

    def _read_raw_timing(self) -> str:
        result = self._conn.read_channel_timing()
        return result if isinstance(result, str) else "<HUAWEI>"

    def _protect_session_log(self, secrets: Iterable[str] | None = None) -> None:
        """Registra chamada para verificação em testes (não há session_log real no mock)."""
        self._protect_session_log_called = True
        self._protect_session_log_secrets = list(secrets or [])

    def _reset_protect_session_log(self) -> None:
        self._protect_session_log_called = False
        self._protect_session_log_secrets = []


class TestEditConfigBlock:
    def test_block_uses_one_send_config_set_without_cmd_verify(self):
        conn = MagicMock()
        conn.send_config_set.return_value = "ok"
        conn.read_channel_timing.return_value = "<HUAWEI>"
        session = _Session(conn)
        ok, msg = session.edit_config(
            "interface GE0/0/0\nip address 10.0.0.1 255.255.255.0\nquit",
            cmd_verify=False,
            detect_errors=True,
        )
        assert ok is True
        conn.send_config_set.assert_called_once()
        kwargs = conn.send_config_set.call_args.kwargs
        assert kwargs["cmd_verify"] is False
        assert kwargs["read_timeout"] == 120
        assert kwargs["exit_config_mode"] is False
        args = conn.send_config_set.call_args.args[0]
        assert args == [
            "interface GE0/0/0",
            "ip address 10.0.0.1 255.255.255.0",
            "quit",
        ]
        # Saída do config mode usa Ctrl+Z (byte bruto), não send_command('return')
        conn.write_channel.assert_called_once_with("\x1a")
        conn.read_channel_timing.assert_called_once()
        assert isinstance(msg, str)

    def test_vrp_error_makes_failure_and_does_not_save(self):
        conn = MagicMock()
        conn.send_config_set.return_value = "% Unrecognized command found at '^'"
        session = _Session(conn)
        ok, msg = session.edit_config(
            "bad-command", save=True, cmd_verify=False, detect_errors=True
        )
        assert ok is False
        assert "recusada" in msg.lower()
        conn.save_config.assert_not_called()

    def test_save_only_after_successful_verify(self):
        conn = MagicMock()
        conn.send_config_set.return_value = "ok"
        conn.send_command_timing.return_value = "save ok"
        session = _Session(conn)
        ok, _ = session.edit_config(
            "sysname RTR-01", save=True, cmd_verify=False, detect_errors=True
        )
        assert ok is True
        # save é feito via send_command_timing com o comando apropriado,
        # não via save_config().
        conn.send_command_timing.assert_called_once()
        assert conn.send_command_timing.call_args.args[0] == "save"
        conn.save_config.assert_not_called()

    def test_secret_is_redacted_in_output(self):
        conn = MagicMock()
        conn.send_config_set.return_value = "echo S3nh@ForteCom12"
        session = _Session(conn)
        ok, msg = session.edit_config(
            "local-user admin password irreversible-cipher S3nh@ForteCom12",
            cmd_verify=False,
            detect_errors=True,
            secrets=["S3nh@ForteCom12"],
        )
        assert ok is True
        assert "S3nh@ForteCom12" not in msg
        assert "[REDACTED]" in msg

    def test_secret_added_to_session_log_no_log(self):
        conn = MagicMock()
        conn.send_config_set.return_value = "ok"
        session = _Session(conn)
        session._reset_protect_session_log()
        session.edit_config(
            "local-user admin password irreversible-cipher S3nh@ForteCom12",
            cmd_verify=False,
            detect_errors=True,
            secrets=["S3nh@ForteCom12"],
        )
        assert session._protect_session_log_called is True
        assert "S3nh@ForteCom12" in session._protect_session_log_secrets

    def test_legacy_path_keeps_historical_success(self):
        conn = MagicMock()
        conn.send_config_set.return_value = "% Unrecognized command"
        session = _Session(conn)
        ok, _ = session.edit_config("bad-command")
        assert ok is True

    def test_interactive_prompt_is_answered_with_y(self):
        """Prompt de uncommitted configs do VRP8 deve ser respondido com 'y'
        (commit automático) independentemente de save."""
        conn = MagicMock()
        conn.send_config_set.return_value = (
            "undo portswitch\n"
            "Warning: Uncommitted configurations found, commit them before exiting? "
            "[Y(yes)/N(no)/C(cancel)]:"
        )
        conn.send_command_timing.return_value = "undo portswitch completed.\n"
        session = _Session(conn)
        ok, msg = session.edit_config(
            "undo portswitch",
            cmd_verify=False,
            detect_errors=True,
            save=True,
            vrp_version=VrpVersion.VRP8,
        )
        assert ok is True
        # send_command_timing é chamado pelo menos duas vezes:
        # 1) resposta "y\n" ao prompt de uncommitted configs (commit VRP8)
        # 2) comando "save all virtual-systems" para persistir na startup
        call_args_list = conn.send_command_timing.call_args_list
        assert any(call.args[0] == "y\n" for call in call_args_list), (
            f"Esperado chamada com 'y\\n', obtido: {[c.args for c in call_args_list]}"
        )
        assert any(
            call.args[0] == "save all virtual-systems" for call in call_args_list
        ), (
            f"Esperado chamada com 'save all virtual-systems', obtido: "
            f"{[c.args for c in call_args_list]}"
        )
        assert "completed" in msg

class TestSendConfigBlock:
    def _make(self):
        sb = SSHSouthbound(EnvBackend(), AuditLogger())
        mock_session = MagicMock()
        mock_session.edit_config.return_value = (True, "ok")
        sb._session = mock_session
        sb._connected = True
        return sb, mock_session

    def test_calls_edit_config_with_block_options(self):
        sb, session = self._make()
        ok, _ = sb.send_config_block(
            ["interface GE0/0/0", "quit"],
            save=True,
            secrets=["S3nh@ForteCom12"],
            vrp_version=VrpVersion.VRP8,
        )
        assert ok is True
        kwargs = session.edit_config.call_args.kwargs
        assert kwargs["save"] is True
        assert kwargs["cmd_verify"] is False
        assert kwargs["detect_errors"] is True
        assert kwargs["secrets"] == ["S3nh@ForteCom12"]
        assert kwargs["vrp_version"] == VrpVersion.VRP8

    def test_admin_required(self):
        sb, session = self._make()
        sb.set_access_role("tecnico")
        validator = MagicMock()
        validator.validate_config_block.return_value = MagicMock(
            allowed=False, reason="Configuração de device exige papel admin"
        )
        sb._validator = validator
        with pytest.raises(SdnAuthError, match="denied by policy"):
            sb.send_config_block(["interface GE0/0/0"])
        session.edit_config.assert_not_called()

    def test_success_message_is_redacted(self):
        sb, session = self._make()
        session.edit_config.return_value = (True, "echo S3nh@ForteCom12")
        ok, msg = sb.send_config_block(
            ["x"], secrets=["S3nh@ForteCom12"]
        )
        assert ok is True
        assert "S3nh@ForteCom12" not in msg
