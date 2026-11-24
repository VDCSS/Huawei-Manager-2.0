"""MockSshDevice — device simulado para testes offline do controlador SDN.

Uso:
    from tests.fixtures import MockSshDevice

    dev = MockSshDevice(host="10.0.0.1", port=22, device_type="router")
    dev.connect()
    output = dev.send_command("display version")
    dev.disconnect()

O MockSshDevice carrega outputs CLI pré-gravados do diretório
tests/fixtures/huawei-outputs/ e os serve sob demanda.
"""

from __future__ import annotations

import time
from pathlib import Path

_OUTPUTS_DIR = Path(__file__).resolve().parent / "huawei-outputs"

# Mapeamento fuzzy: comando → arquivo de fixture
_CMD_MAP: dict[str, str] = {
    "display version": "display_version.txt",
    "display interface brief": "display_interface_brief.txt",
    "display current-configuration": "display_current_configuration.txt",
    "display lldp neighbor": "display_lldp_neighbor.txt",
    "display ip routing-table": "display_ip_routing_table.txt",
}

_TIMEOUT_SIM_S = 2.5  # atraso simulado para timeout


class MockSshDevice:
    """Substituto de sessão SSH para testes offline.

    Args:
        host: Endereço IP simulado
        port: Porta SSH simulada
        device_type: Tipo de dispositivo (router|switch|firewall)
        simulate_timeout: Se True, atrasa resposta para simular timeout
        simulate_failure: Se True, retorna None em send_command
        fixture_dir: Diretório com fixtures de output (útil para testes)
    """

    def __init__(
        self,
        host: str,
        port: int = 22,
        device_type: str = "router",
        simulate_timeout: bool = False,
        simulate_failure: bool = False,
        fixture_dir: str | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.device_type = device_type
        self.simulate_timeout = simulate_timeout
        self.simulate_failure = simulate_failure
        self.is_connected = False

        output_dir = Path(fixture_dir) if fixture_dir else _OUTPUTS_DIR
        self._cache: dict[str, str] = {}
        for cmd, filename in _CMD_MAP.items():
            fpath = output_dir / filename
            if fpath.exists():
                self._cache[cmd] = fpath.read_text(encoding="utf-8")
            else:
                self._cache[cmd] = f"Error: fixture {filename} not found"

    def connect(self) -> None:
        """Simula conexão SSH."""
        self.is_connected = True

    def disconnect(self) -> None:
        """Simula desconexão SSH."""
        self.is_connected = False

    def is_alive(self) -> bool:
        """Retorna se a conexão está ativa."""
        return self.is_connected

    def send_command(self, command: str) -> str | None:
        """Executa comando e retorna output simulado.

        Retorna None se simulate_failure=True ou se o comando não
        for encontrado e simulate_timeout=True.
        """
        if not self.is_connected:
            raise RuntimeError("MockSshDevice not connected")

        if self.simulate_failure:
            return None

        # Busca exata ou parcial
        output = self._cache.get(command)
        if output is None:
            # fallback: busca fuzzy por substring
            for cmd_key in _CMD_MAP:
                if cmd_key in command or command in cmd_key:
                    output = self._cache.get(cmd_key)
                    break

        if output is None:
            output = "Error: Unrecognized command found at '^' position."

        if self.simulate_timeout:
            time.sleep(_TIMEOUT_SIM_S)
            return None

        return output

    def send_config(
        self, commands: list[str]
    ) -> tuple[bool, str]:
        """Simula envio de configuração.

        Returns:
            Tupla (sucesso, mensagem de erro vazia em caso de sucesso)
        """
        if not self.is_connected:
            raise RuntimeError("MockSshDevice not connected")
        if self.simulate_failure:
            return False, "Simulated failure"
        return True, ""


# Lista de comandos suportados para uso em testes
SUPPORTED_COMMANDS = list(_CMD_MAP.keys())
