"""device_probe.py — TCP probe, cache, and mock status simulation."""

from __future__ import annotations

import logging
import random
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from huawei_manager import _config
from huawei_manager.device_models import Device

log = logging.getLogger("huawei.topology")


class _ProbeState:
    def __init__(self) -> None:
        self.mock_last_update: float = 0.0
        self.cache: dict[str, tuple[str, float]] = {}
        self.cache_ttl: float = 25.0


_probe = _ProbeState()


def simulate_status(devices: list[Device]) -> list[Device]:
    """Simula variacao aleatoria de status dos devices (modo mock)."""
    now = time.time()
    if now - _probe.mock_last_update < 15:
        return devices
    _probe.mock_last_update = now
    for d in devices:
        if d.status == "unknown":
            if random.random() < 0.20:
                d.status = "offline"
            else:
                d.status = "online"
        elif d.status == "offline":
            if random.random() < 0.20:
                d.status = "online"
        elif d.status == "online":
            if random.random() < 0.05:
                d.status = "offline"
    return devices


def _device_cache_key(device: Device) -> str:
    return f"{device.host}:{device.port or 22}"


def _check_device(device: Device, timeout: int = 5) -> str:
    """Tenta conexao TCP ao device; retorna 'online' ou lanca excecao."""
    socket.create_connection((device.host, device.port or 22), timeout=timeout).close()
    return "online"


def probe_devices(devices: list[Device], timeout: int | None = None) -> list[Device]:
    if timeout is None:
        timeout = int(_config._s("VNF_PROBE_TIMEOUT", "5"))
    now = time.time()
    to_probe: list[Device] = []
    cache_hits = 0

    for d in devices:
        if not d.host:
            continue
        key = _device_cache_key(d)
        cached = _probe.cache.get(key)
        if cached and cached[0] == "online" and now - cached[1] < _probe.cache_ttl:
            d.status = cached[0]
            cache_hits += 1
        else:
            to_probe.append(d)

    if to_probe:
        with ThreadPoolExecutor(max_workers=min(10, len(to_probe) or 1)) as ex:
            fut = {ex.submit(_check_device, d, timeout): d for d in to_probe}
            for f in as_completed(fut):
                d = fut[f]
                try:
                    d.status = f.result()
                except (OSError, TimeoutError):
                    d.status = "offline"
                _probe.cache[_device_cache_key(d)] = (d.status, now)

    return devices


def clear_probe_cache() -> None:
    _probe.cache.clear()


def _normalize_status(raw: str) -> str:
    raw = raw.lower()
    if raw in ("online", "reachable", "active", "managed"):
        return "online"
    if raw in ("offline", "unreachable", "inactive", "unmanaged"):
        return "offline"
    return "unknown"
