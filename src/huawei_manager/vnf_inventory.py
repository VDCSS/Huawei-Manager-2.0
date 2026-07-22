"""vnf_inventory.py — VNF inventory I/O (JSON file)."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from threading import Lock

from huawei_manager.vnf_crypto import _encrypt_val
from huawei_manager.vnf_models import VNF

log = logging.getLogger("huawei.topology")

VNF_INVENTORY_FILE = "vnf_inventory.json"
_INV_LOCK = Lock()


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
