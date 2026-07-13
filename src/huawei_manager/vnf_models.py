"""vnf_models.py — VNF data model, probe TCP, inventory I/O.

Extraído de topology.py para separar modelo de dados (puro, testável
sem Qt) da view Qt (TopologyCanvas, _VNFNodeRect, _TopoView).
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import random
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import Lock

from cryptography.fernet import Fernet

from huawei_manager import _config

log = logging.getLogger("huawei.topology")

VNF_INVENTORY_FILE = "vnf_inventory.json"
_INV_LOCK = Lock()

# ═══════════════════════════════════════════════════════════════════════
#  FERNET ENCRYPTION HELPERS  (C4)
# ═══════════════════════════════════════════════════════════════════════


def _get_fernet_encrypt() -> Fernet:
    """Retorna Fernet para *criptografia* — exige VNF_ENCRYPT_KEY, SEM fallback.

    Se VNF_ENCRYPT_KEY nao estiver configurada, dados sensiveis serao
    salvos em plaintext (log.warning).
    """
    raw = _config._s("VNF_ENCRYPT_KEY")
    if not raw:
        log.warning(
            "VNF_ENCRYPT_KEY nao configurada — senhas/chaves VNF "
            "serao salvas em plaintext! "
            "Defina VNF_ENCRYPT_KEY no .env (gere com: "
            "python3 -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\")"
        )
        raise ValueError("VNF_ENCRYPT_KEY nao configurada")
    try:
        return Fernet(raw.encode())
    except Exception as exc:
        log.warning("VNF_ENCRYPT_KEY invalida: %s", exc)
        raise


def _get_fernet_decrypt() -> Fernet | None:
    """Retorna Fernet para *descriptografia* — tenta VNF_ENCRYPT_KEY,
    depois fallback HMAC (compatibilidade reversa com dados antigos)."""
    raw = _config._s("VNF_ENCRYPT_KEY")
    if raw:
        try:
            return Fernet(raw.encode())
        except Exception:
            log.warning("VNF_ENCRYPT_KEY invalida, tentando fallback HMAC")
            raw = ""
    if not raw:
        raw = _config._s("AUDIT_HMAC_KEY", "")
    if raw:
        return Fernet(base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest()))
    return None


def _encrypt_val(text: str) -> str:
    """Criptografa valor com VNF_ENCRYPT_KEY.

    Se a chave nao existir (ValueError), retorna plaintext com log.warning
    (design intencional — aceita chave opcional).
    Se a chave existir mas a criptografia falhar, PROPAGA o erro (fail fast).
    """
    try:
        f = _get_fernet_encrypt()
    except ValueError:
        # Chave nao configurada — fallback plaintext (log ja emitido em _get_fernet_encrypt)
        return text
    try:
        return f.encrypt(text.encode()).decode()
    except Exception as exc:
        log.error("Falha ao criptografar senha VNF: %s", exc)
        raise


def _decrypt_val(enc: str) -> str:
    """Descriptografa valor; tenta VNF_ENCRYPT_KEY, fallback HMAC."""
    f = _get_fernet_decrypt()
    if f is None:
        log.warning("VNF_ENCRYPT_KEY ausente — dados descriptografados em plaintext")
        return enc
    try:
        return f.decrypt(enc.encode()).decode()
    except Exception:
        log.warning("Falha ao decriptar senha VNF — usando valor original")
        return enc


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
        v = cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        if v.password:
            v.password = _decrypt_val(v.password)
        if v.ssh_key:
            v.ssh_key = _decrypt_val(v.ssh_key)
        return v


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


def _check_vnf(vnf: VNF, timeout: int = 5) -> str:
    """Tenta conexao TCP ao VNF; retorna 'online' ou lanca excecao."""
    socket.create_connection((vnf.host, vnf.port or 22), timeout=timeout).close()
    return "online"


def probe_vnfs(vnfs: list[VNF], timeout: int | None = None) -> list[VNF]:
    if timeout is None:
        timeout = int(_config._s("VNF_PROBE_TIMEOUT", "5"))
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
    data = {"vnfs": []}
    for v in vnfs:
        d = asdict(v)
        if d["password"]:
            d["password"] = _encrypt_val(d["password"])
        if d["ssh_key"]:
            d["ssh_key"] = _encrypt_val(d["ssh_key"])
        data["vnfs"].append(d)
    with _INV_LOCK:
        Path(filename).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
