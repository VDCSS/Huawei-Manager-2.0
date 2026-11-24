"""Testes para MockSshDevice — device simulado para testes offline.

O MockSshDevice substitui a conexão SSH real durante testes,
respondendo comandos CLI com outputs pré-gravados de dispositivos Huawei.
"""

from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "huawei-outputs"


def _load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


class TestPreRecordedFixtures:
    """Os arquivos de fixture com outputs CLI devem existir e ter conteúdo."""

    REQUIRED = [
        "display_version.txt",
        "display_interface_brief.txt",
        "display_current_configuration.txt",
        "display_lldp_neighbor.txt",
        "display_ip_routing_table.txt",
    ]

    def test_fixtures_directory_exists(self) -> None:
        assert FIXTURES_DIR.exists(), f"Diretório não encontrado: {FIXTURES_DIR}"

    def test_all_required_fixtures_exist(self) -> None:
        for name in self.REQUIRED:
            p = FIXTURES_DIR / name
            assert p.exists(), f"Fixture ausente: {name}"
            assert len(p.read_text(encoding="utf-8")) > 50, f"Fixture vazia: {name}"

    def test_display_version_contains_vrp(self) -> None:
        content = _load_fixture("display_version.txt")
        assert "VRP" in content and "Software" in content

    def test_display_interface_brief_has_interface(self) -> None:
        content = _load_fixture("display_interface_brief.txt")
        assert "GigabitEthernet" in content or "interface" in content.lower()

    def test_display_current_config_has_sysname(self) -> None:
        content = _load_fixture("display_current_configuration.txt")
        assert "sysname" in content

    def test_display_lldp_neighbor_has_neighbor(self) -> None:
        content = _load_fixture("display_lldp_neighbor.txt")
        assert "GigabitEthernet" in content or "neighbor" in content.lower() or "lldp" in content.lower()

    def test_display_routing_table_has_route(self) -> None:
        content = _load_fixture("display_ip_routing_table.txt")
        assert "0.0.0.0" in content or "Destination" in content or "Route" in content or "Proto" in content


class TestMockSshDevice:
    """Testa o MockSshDevice como substituto de sessão SSH em testes.

    O MockSshDevice deve:
    - Responder comandos conhecidos com fixtures reais
    - Suportar connect/disconnect/is_alive
    - Simular timeout para comandos desconhecidos
    - Aceitar modo de falha
    """

    def test_can_instantiate(self) -> None:
        from tests.fixtures import MockSshDevice

        dev = MockSshDevice(host="10.0.0.1", port=22, device_type="router")
        assert dev.host == "10.0.0.1"
        assert dev.port == 22
        assert dev.device_type == "router"

    def test_connect_and_disconnect(self) -> None:
        from tests.fixtures import MockSshDevice

        dev = MockSshDevice(host="10.0.0.1", port=22)
        assert not dev.is_connected
        dev.connect()
        assert dev.is_connected
        dev.disconnect()
        assert not dev.is_connected

    def test_send_command_known(self) -> None:
        from tests.fixtures import MockSshDevice

        dev = MockSshDevice(host="10.0.0.1", port=22)
        dev.connect()
        output = dev.send_command("display version")
        assert "VRP" in output

    def test_send_command_unknown_returns_error(self) -> None:
        from tests.fixtures import MockSshDevice

        dev = MockSshDevice(host="10.0.0.1", port=22)
        dev.connect()
        output = dev.send_command("display nonexistent-command")
        assert "Error" in output or "Unknown" in output or "unrecognized" in output

    def test_send_command_timeout_simulation(self) -> None:
        from tests.fixtures import MockSshDevice

        dev = MockSshDevice(host="10.0.0.1", port=22, simulate_timeout=True)
        dev.connect()
        import time
        t0 = time.monotonic()
        output = dev.send_command("display version")
        elapsed = time.monotonic() - t0
        assert elapsed >= 2.0, f"Timeout simulado deve levar >=2s, levou {elapsed:.1f}s"
        assert output is None or "timeout" in output.lower()

    def test_send_command_failure_simulation(self) -> None:
        from tests.fixtures import MockSshDevice

        dev = MockSshDevice(host="10.0.0.1", port=22, simulate_failure=True)
        dev.connect()
        result = dev.send_command("display version")
        assert result is None

    def test_is_alive_reflects_connection(self) -> None:
        from tests.fixtures import MockSshDevice

        dev = MockSshDevice(host="10.0.0.1", port=22)
        assert not dev.is_alive()
        dev.connect()
        assert dev.is_alive()
        dev.disconnect()
        assert not dev.is_alive()

    def test_send_config(self) -> None:
        from tests.fixtures import MockSshDevice

        dev = MockSshDevice(host="10.0.0.1", port=22)
        dev.connect()
        ok, msg = dev.send_config(["sysname R1", "interface GigabitEthernet0/0/0"])
        assert ok is True
        assert msg == ""
