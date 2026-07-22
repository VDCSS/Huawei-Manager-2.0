"""vnf_probe.py — TCP probe, cache, and mock status simulation."""

from __future__ import annotations

import logging
import random
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from huawei_manager import _config
from huawei_manager.vnf_models import VNF

log = logging.getLogger("huawei.topology")


class _ProbeState:
    """Estado mutavel de probe TCP e simulacao mock.

    Encapsulado em classe (em vez de bare module globals) para
    testabilidade e rastreabilidade clara de mutacao.
    """

    def __init__(self) -> None:
        self.mock_last_update: float = 0.0
        self.cache: dict[str, tuple[str, float]] = {}
        self.cache_ttl: float = 25.0


_probe = _ProbeState()


def simulate_status(vnfs: list[VNF]) -> list[VNF]:
    """Simula variacao aleatoria de status dos VNFs (modo mock)."""
    now = time.time()
    if now - _probe.mock_last_update < 15:
        return vnfs
    _probe.mock_last_update = now
    for v in vnfs:
        if v.status == "offline":
            if random.random() < 0.2:
                v.status = "online"
        elif v.status == "online":
            if random.random() < 0.05:
                v.status = random.choice(["offline", "unknown"])
    return vnfs


def _vnf_cache_key(vnf: VNF) -> str:
    return f"{vnf.host}:{vnf.port or 22}"


def _check_vnf(vnf: VNF, timeout: int = 5) -> str:
    """Tenta conexao TCP ao VNF; retorna 'online' ou lanca excecao."""
    socket.create_connection((vnf.host, vnf.port or 22), timeout=timeout).close()
    return "online"


def probe_vnfs(vnfs: list[VNF], timeout: int | None = None) -> list[VNF]:
    if timeout is None:
        timeout = int(_config._s("VNF_PROBE_TIMEOUT", "5"))
    now = time.time()
    to_probe: list[VNF] = []
    cache_hits = 0

    for v in vnfs:
        if not v.host:
            continue
        key = _vnf_cache_key(v)
        cached = _probe.cache.get(key)
        if cached and cached[0] == "online" and now - cached[1] < _probe.cache_ttl:
            v.status = cached[0]
            cache_hits += 1
        else:
            to_probe.append(v)

    if to_probe:
        with ThreadPoolExecutor(max_workers=min(10, len(to_probe) or 1)) as ex:
            fut = {ex.submit(_check_vnf, v, timeout): v for v in to_probe}
            for f in as_completed(fut):
                v = fut[f]
                try:
                    v.status = f.result()
                except (OSError, TimeoutError):
                    v.status = "offline"
                _probe.cache[_vnf_cache_key(v)] = (v.status, now)

    return vnfs


def clear_probe_cache() -> None:
    """Limpa o cache de probe (util ao recarregar inventario)."""
    _probe.cache.clear()


def _normalize_status(raw: str) -> str:
    """Normaliza string de status para online/offline/unknown."""
    raw = raw.lower()
    if raw in ("online", "reachable", "active", "managed"):
        return "online"
    if raw in ("offline", "unreachable", "inactive", "unmanaged"):
        return "offline"
    return "unknown"
