"""Tests for migration.py (JSON to SQLite migration)."""
from __future__ import annotations

import json

import pytest

from huawei_manager._config import init as init_config
from huawei_manager.db import get_connection, init_database
from huawei_manager.device_repository import DeviceRepository
from huawei_manager.migration import (
    dry_run_json_migration,
    load_json_inventory,
    migrate_json_inventory,
)


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("VNF_ENCRYPT_KEY", "gqO0FYp9kcyuWrbUKLZd-QKwpsCKASxFUF2N8L5KYFI=")
    init_config()
    db_file = tmp_path / "test_migration.db"
    c = get_connection(str(db_file))
    init_database(c)
    yield c
    c.close()


@pytest.fixture
def repo(conn):
    return DeviceRepository(conn)


@pytest.fixture
def sample_json(tmp_path):
    path = tmp_path / "vnf_inventory.json"
    path.write_text(json.dumps({
        "vnfs": [
            {
                "id": "vnf-001",
                "name": "Router-1",
                "host": "10.0.0.1",
                "port": 22,
                "type": "ROUTER",
                "status": "online",
                "version": "V8R1C0",
                "location": "Sala 1",
                "username": "admin",
                "password": "",
                "password_env": "",
                "ssh_key": "",
                "extra_metadata": {"bgp_as": 65001},
            },
            {
                "id": "vnf-002",
                "name": "Switch-1",
                "host": "10.0.0.2",
                "port": 23,
                "type": "SWITCH",
                "status": "offline",
                "version": "",
                "location": "",
                "username": "ciscoadmin",
                "password": "",
                "password_env": "",
                "ssh_key": "",
                "extra_metadata": {},
            },
        ]
    }), encoding="utf-8")
    return path


@pytest.fixture
def empty_json(tmp_path):
    path = tmp_path / "empty.json"
    path.write_text(json.dumps({"vnfs": []}), encoding="utf-8")
    return path


class TestLoadJsonInventory:
    def test_loads_vnfs_key(self, sample_json):
        devices = load_json_inventory(sample_json)
        assert len(devices) == 2
        assert devices[0]["id"] == "vnf-001"
        assert devices[1]["name"] == "Switch-1"

    def test_loads_devices_key(self, tmp_path):
        path = tmp_path / "devices.json"
        path.write_text(json.dumps({
            "devices": [
                {"id": "d1", "name": "Dev1", "host": "1.2.3.4", "port": 22}
            ]
        }), encoding="utf-8")
        devices = load_json_inventory(path)
        assert len(devices) == 1
        assert devices[0]["id"] == "d1"

    def test_loads_list_format(self, tmp_path):
        path = tmp_path / "list.json"
        path.write_text(json.dumps([
            {"id": "d1", "name": "Dev1", "host": "1.2.3.4", "port": 22}
        ]), encoding="utf-8")
        devices = load_json_inventory(path)
        assert len(devices) == 1

    def test_returns_empty_for_nonexistent(self, tmp_path):
        path = tmp_path / "nonexistent.json"
        assert load_json_inventory(path) == []

    def test_returns_empty_for_empty_vnfs(self, empty_json):
        assert load_json_inventory(empty_json) == []


class TestMigrateJsonInventory:
    def test_migrates_vnfs_to_sqlite(self, conn, sample_json):
        count = migrate_json_inventory(sample_json, conn)
        assert count == 2
        repo = DeviceRepository(conn)
        devices = repo.list_devices()
        assert len(devices) == 2
        ids = {d.id for d in devices}
        assert "vnf-001" in ids
        assert "vnf-002" in ids

    def test_preserves_device_fields(self, conn, sample_json):
        migrate_json_inventory(sample_json, conn)
        repo = DeviceRepository(conn)
        dev = repo.get_device("vnf-001")
        assert dev is not None
        assert dev.name == "Router-1"
        assert dev.host == "10.0.0.1"
        assert dev.port == 22
        assert dev.type == "ROUTER"
        assert dev.status == "online"
        assert dev.version == "V8R1C0"
        assert dev.location == "Sala 1"
        assert dev.username == "admin"

    def test_preserves_extra_metadata(self, conn, sample_json):
        migrate_json_inventory(sample_json, conn)
        repo = DeviceRepository(conn)
        dev = repo.get_device("vnf-001")
        assert dev is not None
        assert dev.extra_metadata == {"bgp_as": 65001}

    def test_empty_inventory_migrates_zero(self, conn, empty_json):
        count = migrate_json_inventory(empty_json, conn)
        assert count == 0
        repo = DeviceRepository(conn)
        assert repo.list_devices() == []

    def test_nonexistent_file_migrates_zero(self, conn, tmp_path):
        count = migrate_json_inventory(tmp_path / "nope.json", conn)
        assert count == 0

    def test_dry_run_does_not_write(self, conn, sample_json):
        ids = dry_run_json_migration(sample_json)
        assert ids == ["vnf-001", "vnf-002"]
        repo = DeviceRepository(conn)
        assert repo.list_devices() == []

    def test_idempotent_migration(self, conn, sample_json):
        migrate_json_inventory(sample_json, conn)
        count = migrate_json_inventory(sample_json, conn)
        assert count == 2
        repo = DeviceRepository(conn)
        assert len(repo.list_devices()) == 2
