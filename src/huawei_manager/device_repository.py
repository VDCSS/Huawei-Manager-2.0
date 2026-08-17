"""device_repository.py — SQLite CRUD repository for Device objects.

Handles encryption of password/ssh_key with Fernet (fail-closed) and
JSON serialization of extra_metadata. Uses Device.from_dict for
decryption on read, matching the pattern in device_inventory.py.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import asdict

from huawei_manager.device_crypto import _encrypt_val
from huawei_manager.device_models import Device

log = logging.getLogger("huawei.device_repo")


class DeviceRepository:
    """CRUD repositório para dispositivos no SQLite.

    Args:
        conn: Conexão SQLite thread-safe (check_same_thread=False).
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ── Internal serialization ─────────────────────────────────────────

    def _row_to_device(self, row: sqlite3.Row) -> Device:
        """Converte uma linha do DB para Device (descriptografa senha)."""
        data = {
            "id": row["id"],
            "name": row["name"],
            "host": row["host"],
            "port": row["port"],
            "type": row["type"],
            "status": row["status"],
            "version": row["version"],
            "location": row["location"],
            "username": row["username"],
            "password": row["password"],
            "password_env": row["password_env"],
            "ssh_key": row["ssh_key"],
            "extra_metadata": json.loads(row["extra_metadata"]) if row["extra_metadata"] else {},
        }
        return Device.from_dict(data)

    def _device_to_row(self, device: Device) -> dict:
        """Converte Device para dict para inserção no DB (criptografa senha)."""
        d = asdict(device)
        extra = d.pop("extra_metadata", {})
        d["extra_metadata"] = json.dumps(extra)
        if d["password"]:
            d["password"] = _encrypt_val(d["password"])
        if d["ssh_key"]:
            d["ssh_key"] = _encrypt_val(d["ssh_key"])
        return d

    # ── CRUD ───────────────────────────────────────────────────────────

    def create_device(self, device: Device) -> Device:
        """Insere ou atualiza (upsert) um dispositivo no DB."""
        d = self._device_to_row(device)
        self._conn.execute(
            """
            INSERT INTO devices (
                id, name, host, port, type, status, version,
                location, username, password, password_env, ssh_key,
                extra_metadata
            ) VALUES (
                :id, :name, :host, :port, :type, :status, :version,
                :location, :username, :password, :password_env, :ssh_key,
                :extra_metadata
            )
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                host = excluded.host,
                port = excluded.port,
                type = excluded.type,
                status = excluded.status,
                version = excluded.version,
                location = excluded.location,
                username = excluded.username,
                password = excluded.password,
                password_env = excluded.password_env,
                ssh_key = excluded.ssh_key,
                extra_metadata = excluded.extra_metadata,
                updated_at = datetime('now')
            """,
            d,
        )
        self._conn.commit()
        log.debug("create_device: %s/%s", device.id, device.name)
        return device

    def get_device(self, device_id: str) -> Device | None:
        """Busca um dispositivo pelo ID. Retorna None se não existir."""
        row = self._conn.execute(
            "SELECT * FROM devices WHERE id = ?", (device_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_device(row)

    def list_devices(self) -> list[Device]:
        """Lista todos os dispositivos ordenados por nome."""
        rows = self._conn.execute(
            "SELECT * FROM devices ORDER BY name"
        ).fetchall()
        return [self._row_to_device(r) for r in rows]

    def update_device(self, device: Device) -> Device:
        """Atualiza um dispositivo existente. Fallback para create se não existir."""
        if self.get_device(device.id) is None:
            return self.create_device(device)
        d = self._device_to_row(device)
        d["id"] = device.id
        self._conn.execute(
            """
            UPDATE devices SET
                name = :name, host = :host, port = :port,
                type = :type, status = :status, version = :version,
                location = :location, username = :username,
                password = :password, password_env = :password_env,
                ssh_key = :ssh_key, extra_metadata = :extra_metadata,
                updated_at = datetime('now')
            WHERE id = :id
            """,
            d,
        )
        self._conn.commit()
        log.debug("update_device: %s/%s", device.id, device.name)
        return device

    def delete_device(self, device_id: str) -> bool:
        """Remove um dispositivo. Retorna True se removido, False se não existia."""
        cur = self._conn.execute(
            "DELETE FROM devices WHERE id = ?", (device_id,)
        )
        self._conn.commit()
        if cur.rowcount > 0:
            log.debug("delete_device: %s", device_id)
            return True
        return False

    # ── Queries de busca ───────────────────────────────────────────────

    def search_devices(self, query: str) -> list[Device]:
        """Busca dispositivos por nome ou host (case-insensitive)."""
        pattern = f"%{query}%"
        rows = self._conn.execute(
            "SELECT * FROM devices WHERE name LIKE ? OR host LIKE ? ORDER BY name",
            (pattern, pattern),
        ).fetchall()
        return [self._row_to_device(r) for r in rows]

    def get_devices_by_type(self, device_type: str) -> list[Device]:
        """Filtra dispositivos por tipo (ex: ROUTER, SWITCH). Case-insensitive."""
        rows = self._conn.execute(
            "SELECT * FROM devices WHERE type = ? COLLATE NOCASE ORDER BY name",
            (device_type,),
        ).fetchall()
        return [self._row_to_device(r) for r in rows]

    def get_devices_by_status(self, status: str) -> list[Device]:
        """Filtra dispositivos por status (online, offline, unknown)."""
        rows = self._conn.execute(
            "SELECT * FROM devices WHERE status = ? ORDER BY name",
            (status,),
        ).fetchall()
        return [self._row_to_device(r) for r in rows]
