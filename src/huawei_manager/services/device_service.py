"""DeviceService — Servico de dominio para gestao de devices."""
from __future__ import annotations

import logging
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
    return f"dev-{len(devices) + 1:03d}-{slug}"


log = logging.getLogger("huawei.device_service")


def _noop_resolver(key: str, default: str = "") -> str:
    return default


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

    def save_inventory(self, devices: list[Device]) -> None:
        """Salva dispositivos no repositório SQLite se disponível, senão no JSON."""
        if self._repository is not None:
            existing = {d.id for d in self._repository.list_devices()}
            current = {d.id for d in devices}
            for d in devices:
                self._repository.create_device(d)
            for removed_id in existing - current:
                self._repository.delete_device(removed_id)
        else:
            for d in devices:
                if d.password_env:
                    d.password = ""
            save_devices(devices, self._inventory_path)

    def add_device(self, data: dict[str, Any]) -> Device:
        name = str(data.get("name", "")).strip()
        host = str(data.get("host", "")).strip()
        if not name:
            raise ValueError("Nome e obrigatorio.")
        if not host:
            raise ValueError("IP/Host e obrigatorio.")
        port = int(data.get("port", 22))
        if not (1 <= port <= 65535):
            raise ValueError("Porta deve estar entre 1 e 65535.")

        devices = self.load_inventory()
        device = Device(
            id=_next_id(devices, name),
            name=name,
            host=host,
            port=port,
            type=str(data.get("type", "ROUTER")),
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
        port = int(data.get("port", device.port))
        if not (1 <= port <= 65535):
            port = device.port

        updated = Device(
            id=device.id,
            name=name,
            host=host,
            port=port,
            type=str(data.get("type", device.type)),
            username=str(data.get("username", device.username)),
            password=str(data.get("password", device.password)),
            password_env=str(data.get("password_env", device.password_env)),
            ssh_key=str(data.get("ssh_key", device.ssh_key)),
            location=str(data.get("location", device.location)),
        )

        devices = self.load_inventory()
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
        self.save_inventory(remaining)
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
