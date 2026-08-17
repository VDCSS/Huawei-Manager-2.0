"""device_inventory.py — Device inventory I/O (JSON file)."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from threading import Lock

from huawei_manager.device_crypto import _encrypt_val
from huawei_manager.device_models import Device

log = logging.getLogger("huawei.topology")

DEVICE_INVENTORY_FILE = "vnf_inventory.json"
_INV_LOCK = Lock()
load_error: str | None = None


def load_devices(filename: str = DEVICE_INVENTORY_FILE) -> list[Device]:
    """Carrega inventario de devices do arquivo JSON."""
    global load_error
    load_error = None
    path = Path(filename)
    if not path.exists():
        return []
    with _INV_LOCK:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            items = data.get("devices", data.get("vnfs", []))
            return [Device.from_dict(d) for d in items]
        except (OSError, json.JSONDecodeError) as e:
            load_error = str(e)
            log.warning("Arquivo %s nao pode ser lido/parseado: %s", filename, e)
            return []
        except ValueError:
            raise
        except Exception as e:
            load_error = str(e)
            log.warning("Erro ao ler %s: %s", filename, e)
            return []


def save_devices(devices: list[Device], filename: str = DEVICE_INVENTORY_FILE) -> None:
    data = {"devices": []}
    for v in devices:
        d = asdict(v)
        if d["password"]:
            d["password"] = _encrypt_val(d["password"])
        if d["ssh_key"]:
            d["ssh_key"] = _encrypt_val(d["ssh_key"])
        data["devices"].append(d)
    with _INV_LOCK:
        Path(filename).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
