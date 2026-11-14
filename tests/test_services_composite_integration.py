"""Teste de integração do fluxo composto de Serviços → edit_config.

Valida a cadeia completa do serviço composto (ACL/rota) contra um device
scriptado que emite os prompts reais da VRP8:

1. bloco de configuração no system-view;
2. ``Ctrl+Z`` (byte bruto) — sem prompt matching;
3. commit: ``y`` no prompt ``[Y(yes)/N(no)/C(cancel)]``;
4. save (opcional): ``save all virtual-systems`` + ``y`` no prompt ``[Y/N]``.

Prova que o caminho de envio/confirmação dos serviços é **o mesmo** da aba
Config Básica.
"""
from __future__ import annotations

import threading
from collections.abc import Iterable
from unittest.mock import MagicMock

from huawei_manager.basic_config.vrp_version import VrpVersion
from huawei_manager.sdn_controller.southbound import SSHSouthbound
from huawei_manager.session_commands import SessionCommandsMixin


class _ScriptedDevice:
    """Device fake que emite os prompts reais da VRP8, em ordem."""

    def __init__(self, read_responses: list[str]) -> None:
        self.read_responses = list(read_responses)
        self.written: list[str] = []
        self.config_blocks: list[list[str]] = []
        self.commands: list[str] = []

    def send_config_set(self, lines, **kwargs) -> str:
        self.config_blocks.append(list(lines))
        return ""

    def write_channel(self, data) -> None:
        self.written.append(data if isinstance(data, str) else data.decode())

    def read_channel_timing(self) -> str:
        if self.read_responses:
            return self.read_responses.pop(0)
        return "<HUAWEI>"

    def send_command(self, command: str, **kwargs) -> str:
        self.commands.append(command)
        return "<HUAWEI>"

    def send_command_timing(self, command: str, **kwargs) -> str:
        self.commands.append(command)
        if self.read_responses:
            return self.read_responses.pop(0)
        return "<HUAWEI>"

    def check_config_mode(self) -> bool:
        return True

    def exit_config_mode(self) -> None:
        return None


class _Session(SessionCommandsMixin):
    """Session mínima sobre o device scriptado."""

    def __init__(self, conn) -> None:
        self._conn = conn
        self._lock = threading.RLock()
        self._audit = MagicMock()
        self._host = "10.0.0.1"
        self._user = "admin"
        self._session_id = "sid"

    def _write_raw(self, data: str) -> None:
        self._conn.write_channel(data)

    def _read_raw_timing(self) -> str:
        return self._conn.read_channel_timing()

    def _protect_session_log(self, secrets: Iterable[str] | None = None) -> None:
        return None


def _southbound(session: _Session) -> SSHSouthbound:
    sb = SSHSouthbound.__new__(SSHSouthbound)
    sb._session = session  # pyright: ignore[reportAttributeAccessIssue]
    sb._connected = True  # pyright: ignore[reportAttributeAccessIssue]
    sb._validator = None  # pyright: ignore[reportAttributeAccessIssue]
    sb._access_role = "admin"  # pyright: ignore[reportAttributeAccessIssue]
    return sb


class TestCompositeSendFlow:
    def test_acl_block_is_sent_then_ctrl_z_then_commit_then_save(self):
        device = _ScriptedDevice([
            # saída do Ctrl+Z: prompt de commit do VRP8
            "Warning: Uncommitted configurations found, commit them before "
            "exiting? [Y(yes)/N(no)/C(cancel)]:",
            # resposta ao 'y' do commit: volta ao prompt de exec
            "<HUAWEI>",
            # saída do save: prompt de confirmação
            "save all virtual-systems\n"
            "Warning: The current configuration for all the virtual systems "
            "will be written to the device. Continue? [Y/N]:",
            "<HUAWEI>",
        ])
        session = _Session(device)
        sb = _southbound(session)

        ok, _msg = sb.send_config_block(
            [
                "acl number 3000",
                "rule 5 permit ip source 10.0.0.0 0.0.0.255",
                "quit",
            ],
            save=True,
            vrp_version=VrpVersion.VRP8,
        )

        assert ok is True
        # 1. bloco único no system-view
        assert device.config_blocks == [[
            "acl number 3000",
            "rule 5 permit ip source 10.0.0.0 0.0.0.255",
            "quit",
        ]]
        # 2. saída por Ctrl+Z (byte bruto)
        assert "\x1a" in device.written
        # 3. commit (y) antes do save
        assert device.commands.index("y\n") < device.commands.index(
            "save all virtual-systems")
        # 4. save confirmado com 'y'
        assert device.commands.count("y\n") == 2
        assert device.commands[-1] == "y\n"

    def test_acl_block_without_save_does_not_save(self):
        device = _ScriptedDevice([
            "Warning: Uncommitted configurations found, commit them before "
            "exiting? [Y(yes)/N(no)/C(cancel)]:",
            "<HUAWEI>",
        ])
        session = _Session(device)
        sb = _southbound(session)

        ok, _msg = sb.send_config_block(
            ["acl number 3000", "rule 5 permit ip source 10.0.0.0 0.0.0.255",
             "quit"],
            save=False,
            vrp_version=VrpVersion.VRP8,
        )

        assert ok is True
        assert "save all virtual-systems" not in device.commands
        # commit continua happening (é obrigatório na VRP8)
        assert device.commands.count("y\n") == 1

    def test_static_route_block_flow(self):
        device = _ScriptedDevice([
            "Warning: Uncommitted configurations found, commit them before "
            "exiting? [Y(yes)/N(no)/C(cancel)]:",
            "<HUAWEI>",
        ])
        session = _Session(device)
        sb = _southbound(session)

        ok, _msg = sb.send_config_block(
            ["ip route-static 0.0.0.0 0.0.0.0 10.0.12.2"],
            save=False,
            vrp_version=VrpVersion.VRP8,
        )

        assert ok is True
        assert device.config_blocks == [
            ["ip route-static 0.0.0.0 0.0.0.0 10.0.12.2"]]
        assert device.commands.count("y\n") == 1

    def test_vrp5_does_not_send_commit_confirmation(self):
        device = _ScriptedDevice(["<HUAWEI>"])
        session = _Session(device)
        sb = _southbound(session)

        ok, _msg = sb.send_config_block(
            ["acl number 2000", "rule 5 permit source 10.0.0.0 0.0.0.255",
             "quit"],
            save=False,
            vrp_version=VrpVersion.VRP5,
        )

        assert ok is True
        assert device.commands == []
