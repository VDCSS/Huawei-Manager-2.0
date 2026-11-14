"""TDD da máquina de estados de edit_config: Ctrl+Z, commit VRP8, save em exec view.

Fluxo canônico (VRP8/NE40E):
  1. send_config_set (bloco no system-view)
  2. write_channel(b"\x1a") + read_channel_timing() — sai direto para user view
     (não usa send_command("return"), que falha com prompt matching no commit)
  3. Se VRP8/requires_commit: prompt "[Y(yes)/N(no)/C(cancel)]" → responder "y\n" (commit)
  4. Se save=True: save_cmd em exec view → prompt "[Y/N]" → responder "y\n" (save)
  5. Nunca salvar se commit não confirmado.
"""
from __future__ import annotations

import threading
from collections.abc import Iterable
from unittest.mock import MagicMock

import pytest

from huawei_manager.audit_log import AuditLogger
from huawei_manager.basic_config.vrp_version import VrpVersion
from huawei_manager.exceptions import SdnConnectionError
from huawei_manager.session_commands import SessionCommandsMixin
from huawei_manager.vault import EnvBackend


class _CtrlZSession(SessionCommandsMixin):
    """Session double que expõe canal SSH bruto (write_channel/read_channel_timing)."""

    def __init__(self, conn) -> None:
        self._conn = conn
        self._lock = threading.RLock()
        self._audit = MagicMock()
        self._host = "10.0.0.1"
        self._user = "admin"
        self._session_id = "sid"

    def _write_raw(self, data: bytes) -> None:
        self._conn.write_channel(data)

    def _read_raw_timing(self) -> str:
        return self._conn.read_channel_timing()

    def _protect_session_log(self, secrets: Iterable[str] | None = None) -> None:
        pass


class _ConnDouble:
    """Mock da conexão Netmiko com suporte a canal bruto."""

    def __init__(self, read_responses=None) -> None:
        self.read_responses = list(read_responses or [])
        self.written: list[bytes] = []
        self.send_config_set_calls: list[tuple[list[str], dict]] = []
        self.send_command_timing_calls: list[tuple[str, dict]] = []
        self.send_command_calls: list[tuple[str, dict]] = []
        self.check_config_mode_calls = 0
        self.exit_config_mode_calls = 0

    def send_config_set(self, lines, **kwargs) -> str:
        self.send_config_set_calls.append((list(lines), dict(kwargs)))
        return ""

    def write_channel(self, data: bytes) -> None:
        self.written.append(data)

    def read_channel_timing(self) -> str:
        if self.read_responses:
            return self.read_responses.pop(0)
        return "<HUAWEI>"

    def send_command(self, command: str, **kwargs) -> str:
        self.send_command_calls.append((command, dict(kwargs)))
        return "<HUAWEI>"

    def send_command_timing(self, command: str, **kwargs) -> str:
        self.send_command_timing_calls.append((command, dict(kwargs)))
        if self.read_responses:
            return self.read_responses.pop(0)
        return "<HUAWEI>"

    def check_config_mode(self) -> bool:
        self.check_config_mode_calls += 1
        return True

    def exit_config_mode(self) -> None:
        self.exit_config_mode_calls += 1


def _make_session(read_responses=None):
    conn = _ConnDouble(read_responses)
    return _CtrlZSession(conn), conn


class TestEditConfigCtrlZFlow:
    """Fluxo principal: bloco → Ctrl+Z → (commit) → (save)."""

    def test_no_conn_raises(self):
        session = _CtrlZSession.__new__(_CtrlZSession)
        session._conn = None
        with pytest.raises(SdnConnectionError):
            session.edit_config("config text")

    def test_single_send_config_set_block(self):
        """Todo o bloco vai em um único send_config_set, sem verificação de comando."""
        conn = _ConnDouble()
        session = _CtrlZSession(conn)
        session.edit_config(
            "interface GE0/0/0\nip address 10.0.0.1 255.255.255.0",
            cmd_verify=False,
        )
        assert len(conn.send_config_set_calls) == 1
        lines, kwargs = conn.send_config_set_calls[0]
        assert lines == ["interface GE0/0/0", "ip address 10.0.0.1 255.255.255.0"]
        assert kwargs["cmd_verify"] is False
        assert kwargs["exit_config_mode"] is False
        assert kwargs["read_timeout"] == 120

    def test_ctrl_z_sent_as_raw_byte_not_send_command_return(self):
        """Saída do system-view usa Ctrl+Z (byte bruto), não send_command('return')."""
        conn = _ConnDouble()
        session = _CtrlZSession(conn)
        session.edit_config("sysname RTR", cmd_verify=False)
        assert "\x1a" in conn.written, f"Ctrl+Z não enviado: {conn.written}"
        # send_command('return') não deve ser a saída primária
        assert not any(cmd == "return" for cmd, _ in conn.send_command_calls)

    def test_read_channel_timing_called_after_ctrl_z(self):
        """Após escrever Ctrl+Z, lê o canal para obter o resultado da saída."""
        conn = _ConnDouble(["<HUAWEI>"])
        session = _CtrlZSession(conn)
        session.edit_config("sysname RTR", cmd_verify=False)
        assert conn.read_responses == [], "read_channel_timing deveria ter consumido a resposta"

    def test_exec_view_detected_after_ctrl_z(self):
        """Prompt de exec view (<HUAWEI>) detectado após Ctrl+Z."""
        conn = _ConnDouble(["<HUAWEI>"])
        session = _CtrlZSession(conn)
        ok, _ = session.edit_config("sysname RTR", cmd_verify=False)
        assert ok is True


class TestEditConfigVrp8Commit:
    """Commit VRP8: após Ctrl+Z, responde 'y' ao prompt de configs não-commitadas."""

    def test_vrp8_commit_prompt_answered_with_y(self):
        """VRP8: após Ctrl+Z, commit prompt aparece e é respondido com 'y\n'."""
        conn = _ConnDouble([
            "Warning: Uncommitted configurations found, commit them before exiting? "
            "[Y(yes)/N(no)/C(cancel)]:",
            "<HUAWEI>",
        ])
        session = _CtrlZSession(conn)
        ok, _ = session.edit_config(
            "sysname RTR",
            cmd_verify=False,
            vrp_version=VrpVersion.VRP8,
        )
        assert ok is True
        # send_command_timing('y\n') responde ao prompt de commit
        assert any(
            cmd == "y\n" for cmd, _ in conn.send_command_timing_calls
        ), f"Esperado 'y\\n' em send_command_timing, obtido: {conn.send_command_timing_calls}"

    def test_vrp8_commit_before_save(self):
        """Ordem: commit (y) deve vir ANTES do save all virtual-systems."""
        conn = _ConnDouble([
            "Warning: Uncommitted configurations found, commit them before exiting? "
            "[Y(yes)/N(no)/C(cancel)]:",
            "<HUAWEI>",
            "save all virtual-systems\n"
            "Warning: The current configuration will be written. Continue? [Y/N]:",
            "<HUAWEI>",
        ])
        session = _CtrlZSession(conn)
        session.edit_config(
            "sysname RTR",
            cmd_verify=False,
            save=True,
            vrp_version=VrpVersion.VRP8,
        )
        cmds = [cmd for cmd, _ in conn.send_command_timing_calls]
        y_index = cmds.index("y\n")  # primeira resposta y (commit)
        save_index = cmds.index("save all virtual-systems")
        second_y_index = cmds.index("y\n", y_index + 1)  # segunda resposta y (save)
        assert y_index < save_index < second_y_index, (
            f"Ordem incorreta: {cmds}"
        )

    def test_vrp8_no_commit_no_save(self):
        """Se commit não é confirmado (prompt persiste após 'y'), save não é executado."""
        conn = _ConnDouble([
            "Warning: Uncommitted configurations found, commit them before exiting? "
            "[Y(yes)/N(no)/C(cancel)]:",
            # Após 'y', o prompt persiste → commit não confirmado
            "[Y(yes)/N(no)/C(cancel)]:",
        ])
        session = _CtrlZSession(conn)
        ok, msg = session.edit_config(
            "sysname RTR",
            cmd_verify=False,
            save=True,
            vrp_version=VrpVersion.VRP8,
        )
        assert ok is False
        assert "não confirmado" in msg.lower()
        save_cmds = [cmd for cmd, _ in conn.send_command_timing_calls if cmd == "save all virtual-systems"]
        assert len(save_cmds) == 0, "Save não deve ser executado sem commit confirmado"


class TestEditConfigVrp5:
    """VRP5 não exige commit."""

    def test_vrp5_no_commit_prompt(self):
        """VRP5: não há prompt de commit após Ctrl+Z, vai direto para exec."""
        conn = _ConnDouble(["<HUAWEI>"])
        session = _CtrlZSession(conn)
        ok, _ = session.edit_config(
            "sysname RTR",
            cmd_verify=False,
            vrp_version=VrpVersion.VRP5,
        )
        assert ok is True
        # Nenhuma resposta 'y' necessária para commit
        y_calls = [cmd for cmd, _ in conn.send_command_timing_calls if cmd == "y\n"]
        assert len(y_calls) == 0, f"VRP5 não deve enviar 'y' para commit: {y_calls}"


class TestEditConfigSave:
    """Save só em exec view, após sair do system-view."""

    def test_save_all_virtual_systems_for_vrp8(self):
        """VRP8 + save: envia 'save all virtual-systems' em exec view."""
        conn = _ConnDouble(["<HUAWEI>", "<HUAWEI>"])
        session = _CtrlZSession(conn)
        ok, _ = session.edit_config(
            "sysname RTR",
            cmd_verify=False,
            save=True,
            vrp_version=VrpVersion.VRP8,
        )
        assert ok is True
        assert any(
            cmd == "save all virtual-systems" for cmd, _ in conn.send_command_timing_calls
        ), f"Esperado 'save all virtual-systems': {conn.send_command_timing_calls}"

    def test_save_generic_for_other_vrp(self):
        """Outras VRP + save: envia 'save' em exec view."""
        conn = _ConnDouble(["<HUAWEI>", "<HUAWEI>"])
        session = _CtrlZSession(conn)
        ok, _ = session.edit_config(
            "sysname RTR",
            cmd_verify=False,
            save=True,
            vrp_version=VrpVersion.VRP5,
        )
        assert ok is True
        assert any(
            cmd == "save" for cmd, _ in conn.send_command_timing_calls
        ), f"Esperado 'save': {conn.send_command_timing_calls}"

    def test_save_prompt_answered_with_y(self):
        """Prompt de confirmação do save '[Y/N]' é respondido com 'y\n'."""
        conn = _ConnDouble([
            "<HUAWEI>",
            "save all virtual-systems\n"
            "Warning: The current configuration will be written. Continue? [Y/N]:",
            "<HUAWEI>",
        ])
        session = _CtrlZSession(conn)
        ok, _ = session.edit_config(
            "sysname RTR",
            cmd_verify=False,
            save=True,
            vrp_version=VrpVersion.VRP8,
        )
        assert ok is True
        y_calls = [cmd for cmd, _ in conn.send_command_timing_calls if cmd == "y\n"]
        assert len(y_calls) >= 1, f"Esperado pelo menos um 'y\\n' para save: {conn.send_command_timing_calls}"

    def test_no_save_by_default(self):
        """save=False por padrão: nenhum comando de save é enviado."""
        conn = _ConnDouble(["<HUAWEI>"])
        session = _CtrlZSession(conn)
        session.edit_config("sysname RTR", cmd_verify=False)
        save_cmds = [cmd for cmd, _ in conn.send_command_timing_calls if "save" in cmd]
        assert len(save_cmds) == 0, f"Save não deve ser enviado por padrão: {save_cmds}"


class TestEditConfigFallback:
    """Fallback: se Ctrl+Z falhar, tenta 'return' então 'quit'."""

    def test_ctrl_z_read_failure_falls_back_to_return(self):
        """Se read_channel_timing falhar após Ctrl+Z, tenta send_command('return')."""
        conn = _ConnDouble([])
        conn.read_channel_timing = MagicMock(side_effect=RuntimeError("canal fechado"))
        session = _CtrlZSession(conn)
        # Deve tentar fallback, não levantar exceção não tratada
        try:
            session.edit_config("sysname RTR", cmd_verify=False)
        except Exception:
            pytest.fail("edit_config não deve lançar exceção não tratada no fallback")

    def test_exit_config_best_effort_on_exception(self):
        """Exceção no envio dispara _exit_config_best_effort (check_config_mode + exit_config_mode)."""
        conn = _ConnDouble([])
        conn.send_config_set = MagicMock(side_effect=RuntimeError("falha de envio"))
        session = _CtrlZSession(conn)
        try:
            session.edit_config("sysname RTR", cmd_verify=False, detect_errors=False)
        except RuntimeError:
            pass
        assert conn.check_config_mode_calls >= 1
        assert conn.exit_config_mode_calls >= 1


class TestEditConfigSecrets:
    """Segredos são protegidos e redigidos."""

    def test_protect_session_log_called_with_secrets(self):
        """_protect_session_log é chamado quando detect_errors=True com secrets."""
        conn = _ConnDouble(["<HUAWEI>"])
        session = _CtrlZSession(conn)
        protected = []
        original = session._protect_session_log
        def tracking(secrets=None):
            protected.append(list(secrets or []))
            original(secrets)
        session._protect_session_log = tracking
        session.edit_config(
            "local-user admin password S3nh@Forte",
            cmd_verify=False,
            detect_errors=True,
            secrets=["S3nh@Forte"],
        )
        assert len(protected) == 1
        assert "S3nh@Forte" in protected[0]

    def test_secret_redacted_in_output(self):
        """Saída final não contém segredos em texto claro."""
        conn = _ConnDouble(["echo S3nh@ForteCom12", "<HUAWEI>"])
        session = _CtrlZSession(conn)
        ok, msg = session.edit_config(
            "local-user admin password S3nh@ForteCom12",
            cmd_verify=False,
            detect_errors=True,
            secrets=["S3nh@ForteCom12"],
        )
        assert ok is True
        assert "S3nh@ForteCom12" not in msg

