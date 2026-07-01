#!/usr/bin/env python3
"""vnf_models.py — VNF data model, probe TCP, inventory I/O.

Extraído de topology.py para separar modelo de dados (puro, testável
sem Qt) da view Qt (TopologyCanvas, _VNFNodeRect, _TopoView).
"""
from __future__ import annotations

import json
import logging
import random
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import Lock

log = logging.getLogger("huawei.topology")

VNF_INVENTORY_FILE = "vnf_inventory.json"
_INV_LOCK = Lock()

# ═══════════════════════════════════════════════════════════════════════
#  VNF DATACLASS
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class VNF:
    """Representa um dispositivo VNF com dados de conexao e status."""
    id:       str
    name:     str
    host:     str
    port:     int     = 22
    type:     str     = "ROUTER"
    status:   str     = "unknown"
    version:  str     = ""
    location: str     = ""
    username: str     = ""
    password: str     = ""
    ssh_key:  str     = ""
    extra:    dict    = field(default_factory=dict)

    def label(self) -> str:
        """Retorna o nome legivel do VNF (name ou id)."""
        return self.name or self.id

    def address(self) -> str:
        """Retorna host:porta como string."""
        return f"{self.host}:{self.port}"

    @classmethod
    def from_dict(cls, d: dict) -> VNF:
        """Cria VNF a partir de um dicionario, ignorando chaves extras."""
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ═══════════════════════════════════════════════════════════════════════
#  SIMULACAO DE STATUS (MOCK)
# ═══════════════════════════════════════════════════════════════════════
_mock_last_update: float = 0.0


def simulate_status(vnfs: list[VNF]) -> list[VNF]:
    """Simula variacao aleatoria de status dos VNFs (modo mock)."""
    global _mock_last_update
    now = time.time()
    if now - _mock_last_update < 15:
        return vnfs
    _mock_last_update = now
    for v in vnfs:
        if v.status == "offline":
            if random.random() < 0.2:
                v.status = "online"
        elif v.status == "online":
            if random.random() < 0.05:
                v.status = random.choice(["offline", "unknown"])
    return vnfs


# ═══════════════════════════════════════════════════════════════════════
#  PROBE TCP (REAL)
# ═══════════════════════════════════════════════════════════════════════
_probe_cache: dict[str, tuple[str, float]] = {}
_PROBE_CACHE_TTL: float = 25.0


def _vnf_cache_key(vnf: VNF) -> str:
    return f"{vnf.host}:{vnf.port or 22}"


def _check_vnf(vnf: VNF, timeout: int = 2) -> str:
    """Tenta conexao TCP ao VNF; retorna 'online' ou lanca excecao."""
    socket.create_connection((vnf.host, vnf.port or 22), timeout=timeout).close()
    return "online"


def probe_vnfs(vnfs: list[VNF], timeout: int = 2) -> list[VNF]:
    global _probe_cache
    now = time.time()
    to_probe: list[VNF] = []
    cache_hits = 0

    for v in vnfs:
        if not v.host:
            continue
        key = _vnf_cache_key(v)
        cached = _probe_cache.get(key)
        if cached and cached[0] == "online" and now - cached[1] < _PROBE_CACHE_TTL:
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
                _probe_cache[_vnf_cache_key(v)] = (v.status, now)

    return vnfs


def clear_probe_cache() -> None:
    """Limpa o cache de probe (util ao recarregar inventario)."""
    global _probe_cache
    _probe_cache.clear()


def _normalize_status(raw: str) -> str:
    """Normaliza string de status para online/offline/unknown."""
    raw = raw.lower()
    if raw in ("online", "reachable", "active", "managed"):
        return "online"
    if raw in ("offline", "unreachable", "inactive", "unmanaged"):
        return "offline"
    return "unknown"


# ═══════════════════════════════════════════════════════════════════════
#  INVENTARIO LOCAL
# ═══════════════════════════════════════════════════════════════════════
def load_vnf_inventory(filename: str = VNF_INVENTORY_FILE) -> list[VNF]:
    """Carrega inventario de VNFs do arquivo JSON."""
    path = Path(filename)
    if not path.exists():
        return []
    with _INV_LOCK:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return [VNF.from_dict(d) for d in data.get("vnfs", [])]
        except Exception as e:
            log.warning("Erro ao ler %s: %s", filename, e)
            return []


def save_vnf_inventory(vnfs: list[VNF], filename: str = VNF_INVENTORY_FILE) -> None:
    """Salva inventario de VNFs no arquivo JSON."""
    data = {"vnfs": [asdict(v) for v in vnfs]}
    with _INV_LOCK:
        Path(filename).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
