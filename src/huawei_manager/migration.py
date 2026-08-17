"""migration.py — Migrate devices from JSON inventory to SQLite.

Reads the legacy ``vnf_inventory.json`` (or any JSON inventory file),
decrypts any encrypted secrets (password, ssh_key), and stores them
into the SQLite ``devices`` table via ``DeviceRepository``.

Usage::

    from huawei_manager.db import get_connection, init_database
    from huawei_manager.migration import migrate_json_inventory

    conn = get_connection()
    init_database(conn)
    migrate_json_inventory("path/to/vnf_inventory.json", conn)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from huawei_manager.db import get_connection, init_database
from huawei_manager.device_crypto import _decrypt_val
from huawei_manager.device_models import Device
from huawei_manager.device_repository import DeviceRepository

log = logging.getLogger("huawei.migration")


def load_json_inventory(json_path: str | Path) -> list[dict[str, Any]]:
    """Read a JSON inventory file and return the device list.

    Supports both ``"vnfs"`` and ``"devices"`` keys for the array
    of device dicts.

    Returns an empty list if the file does not exist or is empty.
    """
    path = Path(json_path)
    if not path.exists():
        log.warning("JSON inventory not found: %s", path)
        return []

    raw = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(raw, list):
        return raw

    if isinstance(raw, dict):
        for key in ("vnfs", "devices"):
            if key in raw and isinstance(raw[key], list):
                return raw[key]

    log.warning("JSON inventory has unrecognized structure: %s", path)
    return []


def _decrypt_if_present(value: str) -> str:
    """Decrypt a Fernet-encrypted value, or return empty string."""
    if not value:
        return ""
    try:
        return _decrypt_val(value)
    except Exception:
        log.warning("Failed to decrypt value (may be plaintext)")
        return value


def migrate_json_inventory(json_path: str | Path, conn=None) -> int:
    """Migrate devices from a JSON inventory file into SQLite.

    Uses ``DeviceRepository.create_device`` (which re-encrypts passwords
    with the current Fernet key on insert).

    Args:
        json_path: Path to the JSON inventory file.
        conn: Optional SQLite connection. If ``None``, uses the default
            database path via ``get_connection()``.

    Returns:
        Number of devices migrated.
    """
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
        init_database(conn)

    repository = DeviceRepository(conn)
    devices = load_json_inventory(json_path)

    count = 0
    for raw in devices:
        d = Device(
            id=str(raw.get("id", "")),
            name=str(raw.get("name", "")),
            host=str(raw.get("host", "")),
            port=int(raw.get("port", 22)),
            type=str(raw.get("type", "ROUTER")),
            status=str(raw.get("status", "unknown")),
            version=str(raw.get("version", "")),
            location=str(raw.get("location", "")),
            username=str(raw.get("username", "")),
            password=_decrypt_if_present(str(raw.get("password", "") or "")),
            password_env=str(raw.get("password_env", "")),
            ssh_key=_decrypt_if_present(str(raw.get("ssh_key", "") or "")),
            extra_metadata=raw.get("extra_metadata", {}) or {},
        )
        repository.create_device(d)
        count += 1

    if own_conn:
        conn.close()

    if count:
        log.info("Migrated %d devices from JSON to SQLite", count)
    else:
        log.info("No devices to migrate (JSON inventory empty or not found)")
    return count


def dry_run_json_migration(json_path: str | Path) -> list[str]:
    """Parse a JSON inventory and return list of device IDs (no DB write).

    Useful for verifying the inventory before migrating.
    """
    devices = load_json_inventory(json_path)
    return [str(d.get("id", "")) for d in devices]
