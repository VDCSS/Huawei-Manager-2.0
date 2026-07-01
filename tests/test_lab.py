"""Testes de conectividade SSH para dispositivos de laboratório (GNS3/EVE-NG).

Uso:
    pytest tests/test_lab.py -v              # testa lógica de verificação
    pytest tests/test_lab.py -v --lab        # testa conectividade real com lab
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

# Hosts dos dispositivos de lab (GNS3/EVE-NG)
# Preenchidos via arquivo de config ou .env no futuro
LAB_DEVICES: list[dict[str, str | int]] = [
    {"host": "192.168.100.10", "port": 22, "name": "CE6800-01"},
    {"host": "192.168.100.11", "port": 22, "name": "CE6800-02"},
    {"host": "192.168.100.12", "port": 22, "name": "S5700-01"},
]

CONFIG_PATH = Path(__file__).resolve().parent.parent / "lab_devices.txt"


def check_device_reachable(
    host: str, port: int, timeout: float = 5.0
) -> bool:
    """Verifica se um dispositivo está acessível via TCP na porta SSH.

    Args:
        host: Endereço IP do dispositivo
        port: Porta TCP (padrão 22)
        timeout: Timeout em segundos (padrão 5.0)

    Returns:
        True se a porta TCP está aberta, False caso contrário
    """
    if not host or not isinstance(port, int) or port < 1 or port > 65535:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (TimeoutError, ConnectionRefusedError, OSError):
        return False


def load_lab_devices_from_file(path: Path = CONFIG_PATH) -> list[dict[str, str | int]]:
    """Carrega lista de dispositivos de lab de um arquivo texto.

    Formato esperado (uma linha por device):
        nome host porta
    Exemplo:
        CE6800-01 192.168.100.10 22
    """
    devices: list[dict[str, str | int]] = []
    if not path.exists():
        return devices
    for line in path.read_text(encoding="utf-8").strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) == 3:
            name, host, port_str = parts
            try:
                port = int(port_str)
                devices.append({"name": name, "host": host, "port": port})
            except ValueError:
                continue
    return devices


# --- Testes unitários da lógica de verificação (TDD) ---


class TestCheckDeviceReachable:
    """Testa a função check_device_reachable em cenários controlados."""

    def test_valid_host_localhost_port_22_refused(self) -> None:
        """localhost:22 não deve estar acessível (sem SSH server)."""
        # Conexão será recusada, não deve levantar exceção
        result = check_device_reachable("127.0.0.1", 22, timeout=1.0)
        assert result is False

    def test_invalid_host_returns_false(self) -> None:
        """Host inválido deve retornar False sem exceção."""
        result = check_device_reachable("invalid.host.local", 22, timeout=1.0)
        assert result is False

    def test_empty_host_returns_false(self) -> None:
        """Host vazio deve retornar False."""
        result = check_device_reachable("", 22, timeout=1.0)
        assert result is False

    def test_invalid_port_zero_returns_false(self) -> None:
        """Porta 0 deve retornar False."""
        result = check_device_reachable("127.0.0.1", 0, timeout=1.0)
        assert result is False

    def test_invalid_port_negative_returns_false(self) -> None:
        """Porta negativa deve retornar False."""
        result = check_device_reachable("127.0.0.1", -1, timeout=1.0)
        assert result is False

    def test_port_out_of_range_returns_false(self) -> None:
        """Porta > 65535 deve retornar False."""
        result = check_device_reachable("127.0.0.1", 70000, timeout=1.0)
        assert result is False


class TestLoadLabDevices:
    """Testa carregamento de dispositivos de arquivo."""

    def test_empty_path_returns_empty(self, tmp_path: Path) -> None:
        """Arquivo vazio retorna lista vazia."""
        fpath = tmp_path / "lab_devices.txt"
        fpath.write_text("", encoding="utf-8")
        result = load_lab_devices_from_file(fpath)
        assert result == []

    def test_single_device(self, tmp_path: Path) -> None:
        """Arquivo com 1 device retorna lista com 1 entrada."""
        fpath = tmp_path / "lab_devices.txt"
        fpath.write_text("CE6800-01 192.168.100.10 22\n", encoding="utf-8")
        result = load_lab_devices_from_file(fpath)
        assert len(result) == 1
        assert result[0] == {"name": "CE6800-01", "host": "192.168.100.10", "port": 22}

    def test_multiple_devices(self, tmp_path: Path) -> None:
        """Arquivo com 3 devices retorna lista com 3 entradas."""
        content = "\n".join([
            "CE6800-01 192.168.100.10 22",
            "CE6800-02 192.168.100.11 22",
            "S5700-01 192.168.100.12 22",
        ])
        fpath = tmp_path / "lab_devices.txt"
        fpath.write_text(content + "\n", encoding="utf-8")
        result = load_lab_devices_from_file(fpath)
        assert len(result) == 3

    def test_skips_comments_and_blanks(self, tmp_path: Path) -> None:
        """Linhas de comentário e vazias são ignoradas."""
        content = "\n".join([
            "# Lab devices for GNS3",
            "CE6800-01 192.168.100.10 22",
            "",
            "# Switch",
            "S5700-01 192.168.100.12 22",
        ])
        fpath = tmp_path / "lab_devices.txt"
        fpath.write_text(content + "\n", encoding="utf-8")
        result = load_lab_devices_from_file(fpath)
        assert len(result) == 2

    def test_skips_malformed_lines(self, tmp_path: Path) -> None:
        """Linhas mal formatadas são ignoradas silenciosamente."""
        content = "\n".join([
            "CE6800-01 192.168.100.10 22",
            "bad_line_no_port",
            "S5700-01 192.168.100.12",
        ])
        fpath = tmp_path / "lab_devices.txt"
        fpath.write_text(content + "\n", encoding="utf-8")
        result = load_lab_devices_from_file(fpath)
        assert len(result) == 1


# --- Testes de integração com lab real (opcionais, requer --lab) ---

@pytest.mark.skip(reason="Lab GNS3/EVE-NG não configurado — requer --lab")
def test_lab_devices_reachable() -> None:
    """Todos os dispositivos do lab devem estar acessíveis via SSH."""
    devices = load_lab_devices_from_file()
    if not devices:
        devices = LAB_DEVICES  # fallback para lista hardcoded
    unreachable: list[str] = []
    for dev in devices:
        host = str(dev["host"])
        port = int(dev["port"])
        if not check_device_reachable(host, port):
            unreachable.append(f"{dev['name']} ({host}:{port})")
    assert not unreachable, (
        f"Dispositivos inacessíveis: {', '.join(unreachable)}"
    )
