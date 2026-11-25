"""DeviceService — Servico de dominio para gestao de devices."""
from __future__ import annotations

import ipaddress
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from huawei_manager.device_inventory import load_devices, save_devices
from huawei_manager.device_models import Device
from huawei_manager.device_probe import probe_devices, simulate_status
from huawei_manager.device_repository import DeviceRepository


@dataclass
class SessionOverrides:
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    ssh_key: str | None = None


def _next_id(devices: list[Device], name: str) -> str:
    slug = name.lower().replace(" ", "-")
    # Baseado no MAIOR numero existente, não em len(devices): apos uma
    # delecao, len() subestima e colidiria com um ID ainda em uso
    # (ex.: [dev-001, dev-003] com len=2 geraria dev-003 de novo).
    max_num = 0
    for d in devices:
        parts = d.id.split("-")
        if len(parts) >= 2 and parts[0] == "dev" and parts[1].isdigit():
            max_num = max(max_num, int(parts[1]))
    return f"dev-{max_num + 1:03d}-{slug}"


log = logging.getLogger("huawei.device_service")


def _noop_resolver(key: str, default: str = "") -> str:
    return default


# ── Tipos de device permitidos ───────────────────────────────────────────

_ALLOWED_DEVICE_TYPES = frozenset(
    {"ROUTER", "SWITCH", "FIREWALL", "LOAD-BALANCER", "WAN-ACCEL", "AP"}
)

# Regex para domínio RFC1035 simplificado: rótulos de até 63 chars,
# alfanumérico + hífen, separados por ponto, não começando/terminando com hífen.
_DOMAIN_LABEL = r"(?!-)[A-Za-z0-9-]{1,63}(?<!-)"
_DOMAIN_RE = re.compile(
    rf"^{_DOMAIN_LABEL}(\.{_DOMAIN_LABEL})*$"
)


def _is_valid_host(host: str) -> bool:
    """Retorna True se ``host`` for IPv4, IPv6 ou domínio RFC1035 válido.

    Rejeita CIDR (ex.: 10.0.0.1/24), strings vazias, espaços à esquerda/direita
    e qualquer lixo que não seja um endpoint de rede válido.
    """
    if not host or host != host.strip():
        return False
    # IPv4 / IPv6 (ipaddress rejeita CIDR quando strict=True)
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    # Domínio RFC1035
    return bool(_DOMAIN_RE.match(host))


def _find_duplicate(
    devices: list[Device], name: str, host: str, exclude_id: str | None = None
) -> Device | None:
    """Retorna o device duplicado por name ou host, ou None se não houver."""
    for d in devices:
        if d.id == exclude_id:
            continue
        if d.name == name or d.host == host:
            return d
    return None


class DeviceService:
    """Servico de dominio para gestao de devices.

    Args:
        inventory_path: Caminho para o arquivo JSON de inventario.
        resolve_env: Callable que resolve nome de var de ambiente -> valor.
    """

    def __init__(
        self,
        inventory_path: str,
        resolve_env: Callable[[str], str] | None = None,
        repository: DeviceRepository | None = None,
    ) -> None:
        self._inventory_path = inventory_path
        self._resolve_env = resolve_env or _noop_resolver
        self._repository = repository

    def load_inventory(self) -> list[Device]:
        """Carrega dispositivos do repositório SQLite se disponível, senão do JSON."""
        if self._repository is not None:
            devices = self._repository.list_devices()
        else:
            devices = load_devices(self._inventory_path)
        for d in devices:
            if d.password_env and not d.password:
                try:
                    resolved = self._resolve_env(d.password_env)
                except Exception:
                    log.exception(
                        "Falha ao resolver password_env '%s' para device %s",
                        d.password_env, d.name,
                    )
                    continue
                if resolved:
                    d.password = resolved
                    log.debug(
                        "Device %s: password_env '%s' resolvido",
                        d.name, d.password_env,
                    )
                else:
                    log.warning(
                        "Device %s: password_env '%s' retornou vazio",
                        d.name, d.password_env,
                    )
        return devices

    def save_inventory(
        self, devices: list[Device], allow_deletion: bool = False
    ) -> None:
        """Salva dispositivos no repositório SQLite se disponível, senão no JSON.

        Args:
            devices: Lista completa de dispositivos a persistir.
            allow_deletion: Se True, permite remover dispositivos que
                existiam mas não estao mais na lista. Se False (padrão),
                levanta ValueError se houver delecoes — evitando perda
                acidental de dados por lista parcial.
        """
        if self._repository is not None:
            existing = {d.id for d in self._repository.list_devices()}
            current = {d.id for d in devices}
            removed = existing - current
            if removed and not allow_deletion:
                raise ValueError(
                    "save_inventory: lista parcial removeria device(s) sem "
                    f"allow_deletion=True: {sorted(removed)}. Passe "
                    "allow_deletion=True apenas quando a remoção for intencional."
                )
            for d in devices:
                self._repository.create_device(d)
            for removed_id in removed:
                self._repository.delete_device(removed_id)
        else:
            # Caminho JSON: sobrescreve o arquivo, então também pode apagar
            # dispositivos que existiam mas não estão na lista.
            existing_devices = load_devices(self._inventory_path)
            existing_ids = {d.id for d in existing_devices}
            current_ids = {d.id for d in devices}
            removed = existing_ids - current_ids
            if removed and not allow_deletion:
                raise ValueError(
                    "save_inventory: lista parcial removeria device(s) sem "
                    f"allow_deletion=True: {sorted(removed)}. Passe "
                    "allow_deletion=True apenas quando a remoção for intencional."
                )
            for d in devices:
                if d.password_env:
                    d.password = ""
            save_devices(devices, self._inventory_path)

    def add_device(self, data: dict[str, Any]) -> Device:
        name = str(data.get("name", "")).strip()
        host = str(data.get("host", "")).strip()
        if not name:
            raise ValueError("nome e obrigatório.")
        if not host:
            raise ValueError("host e obrigatório.")
        if not _is_valid_host(host):
            raise ValueError(f"host invalido: '{host}' (use IPv4, IPv6 ou dominio).")
        port = int(data.get("port", 22))
        if not (1 <= port <= 65535):
            raise ValueError("porta deve estar entre 1 e 65535.")
        dev_type = str(data.get("type", "ROUTER")).upper()
        if dev_type not in _ALLOWED_DEVICE_TYPES:
            raise ValueError(
                f"tipo invalido: '{dev_type}'. Valores permitidos: "
                + ", ".join(sorted(_ALLOWED_DEVICE_TYPES))
            )

        devices = self.load_inventory()
        if _find_duplicate(devices, name, host):
            raise ValueError(
                f"Já existe device com nome '{name}' ou host '{host}'."
            )
        device = Device(
            id=_next_id(devices, name),
            name=name,
            host=host,
            port=port,
            type=dev_type,
            username=str(data.get("username", "")),
            password=str(data.get("password", "")),
            password_env=str(data.get("password_env", "")),
            ssh_key=str(data.get("ssh_key", "")),
            location=str(data.get("location", "")),
        )
        devices.append(device)
        self.save_inventory(devices)
        return device

    def update_device(self, device: Device, data: dict[str, Any]) -> Device:
        name = str(data.get("name", device.name)).strip()
        host = str(data.get("host", device.host)).strip()
        if not name:
            raise ValueError("nome e obrigatório.")
        if not host:
            raise ValueError("host e obrigatório.")
        if not _is_valid_host(host):
            raise ValueError(f"host invalido: '{host}' (use IPv4, IPv6 ou dominio).")
        port = int(data.get("port", device.port))
        if not (1 <= port <= 65535):
            raise ValueError("porta deve estar entre 1 e 65535.")
        dev_type = str(data.get("type", device.type)).upper()
        if dev_type not in _ALLOWED_DEVICE_TYPES:
            raise ValueError(
                f"tipo invalido: '{dev_type}'. Valores permitidos: "
                + ", ".join(sorted(_ALLOWED_DEVICE_TYPES))
            )

        devices = self.load_inventory()
        if _find_duplicate(devices, name, host, exclude_id=device.id):
            raise ValueError(
                f"Já existe outro device com nome '{name}' ou host '{host}'."
            )
        updated = Device(
            id=device.id,
            name=name,
            host=host,
            port=port,
            type=dev_type,
            username=str(data.get("username", device.username)),
            password=str(data.get("password", device.password)),
            password_env=str(data.get("password_env", device.password_env)),
            ssh_key=str(data.get("ssh_key", device.ssh_key)),
            location=str(data.get("location", device.location)),
        )

        for i, d in enumerate(devices):
            if d.id == device.id:
                devices[i] = updated
                break
        self.save_inventory(devices)
        return updated

    def delete_device(
        self, device_id: str, devices: list[Device]
    ) -> tuple[list[Device], Device | None]:
        removed: Device | None = None
        remaining: list[Device] = []
        for d in devices:
            if d.id == device_id:
                removed = d
            else:
                remaining.append(d)
        self.save_inventory(remaining, allow_deletion=True)
        return remaining, removed

    def probe_or_simulate(self, devices: list[Device], mock_mode: bool) -> list[Device]:
        if mock_mode:
            return simulate_status(devices)
        return probe_devices(devices)

    def set_target(self, device: Device) -> SessionOverrides:
        return SessionOverrides(
            host=device.host or None,
            port=device.port or None,
            username=device.username or None,
            password=device.password or None,
            ssh_key=device.ssh_key or None,
        )

    @staticmethod
    def clear_target() -> SessionOverrides:
        return SessionOverrides()
