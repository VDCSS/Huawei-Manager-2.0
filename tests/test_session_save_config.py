"""TDD da persistência separada (``save_config``) na sessão SSH.

O fluxo dos serviços compostos é **aplica → verifica → persiste**: a
persistência na startup-config acontece em um comando próprio, executado
na visão exec (fora do system-view), com confirmação ``y``.
"""
from __future__ import annotations

import threading
from collections.abc import Iterable
from unittest.mock import MagicMock

import pytest

from huawei_manager.basic_config.vrp_version import VrpVersion
from huawei_manager.exceptions import SdnConnectionError
from huawei_manager.session_commands import SessionCommandsMixin


class _Session(SessionCommandsMixin):
    def __init__(self, conn) -> None:
        self._conn = conn
        self._lock = threading.RLock()
        self._audit = MagicMock()
        self._host = "10.0.0.1"
        self._user = "admin"
        self._session_id = "sid"

    def _protect_session_log(self, secrets: Iterable[str] | None = None) -> None:
        pass


class _Conn:
    def __init__(self, responses=None) -> None:
        self.responses = list(responses or [])
        self.sent: list[str] = []

    def send_command_timing(self, command: str, **kwargs) -> str:
        self.sent.append(command)
        if self.responses:
            return self.responses.pop(0)
        return "<HUAWEI>"


class TestSaveConfig:
    def test_no_conn_raises(self):
        session = _Session.__new__(_Session)
        session._conn = None
        with pytest.raises(SdnConnectionError):
            session.save_config(VrpVersion.VRP8)

    def test_vrp8_uses_save_all_virtual_systems(self):
        conn = _Conn(["<HUAWEI>"])
        session = _Session(conn)
        ok, _ = session.save_config(VrpVersion.VRP8)
        assert ok is True
        assert conn.sent[0] == "save all virtual-systems"

    def test_other_versions_use_plain_save(self):
        conn = _Conn(["<HUAWEI>"])
        session = _Session(conn)
        ok, _ = session.save_config(VrpVersion.VRP5)
        assert ok is True
        assert conn.sent[0] == "save"

    def test_confirmation_prompt_is_answered_with_y(self):
        conn = _Conn([
            "Warning: The current configuration for all the virtual systems "
            "will be written to the device. Continue? [Y/N]:",
            "Info: Save the configuration successfully.\n<HUAWEI>",
        ])
        session = _Session(conn)
        ok, _ = session.save_config(VrpVersion.VRP8)
        assert ok is True
        assert "y\n" in conn.sent

    def test_failure_returns_error_without_raising(self):
        conn = _Conn()
        conn.send_command_timing = MagicMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("canal fechado")
        )
        session = _Session(conn)
        ok, msg = session.save_config(VrpVersion.VRP8)
        assert ok is False
        assert "salvar" in msg.lower()

    def test_vrp_error_in_output_is_reported(self):
        conn = _Conn(["Error: The configuration is locked."])
        session = _Session(conn)
        ok, msg = session.save_config(VrpVersion.VRP8)
        assert ok is False
        assert "recusado" in msg.lower()
