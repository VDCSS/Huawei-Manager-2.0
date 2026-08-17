"""Tests for DeviceRepository (SQLite-backed CRUD)."""
from __future__ import annotations

import pytest

from huawei_manager._config import init as init_config
from huawei_manager.db import get_connection, init_database
from huawei_manager.device_models import Device
from huawei_manager.device_repository import DeviceRepository

# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def conn(tmp_path, monkeypatch):
    """Fresh in-memory-style temporary SQLite database with encryption key set."""
    monkeypatch.setenv("VNF_ENCRYPT_KEY", "gqO0FYp9kcyuWrbUKLZd-QKwpsCKASxFUF2N8L5KYFI=")
    init_config()
    db_file = tmp_path / "test.db"
    c = get_connection(str(db_file))
    init_database(c)
    yield c
    c.close()


@pytest.fixture
def repo(conn):
    return DeviceRepository(conn)


@pytest.fixture
def sample_device():
    return Device(
        id="dev-001-router",
        name="Router-Principal",
        host="10.0.0.1",
        port=22,
        type="ROUTER",
        status="online",
        username="admin",
        password="secret123",
        ssh_key="",
        location="Sala 1",
        extra_metadata={"bgp_as": 65001},
    )


# ── create_device ─────────────────────────────────────────────────────────

class TestCreateDevice:
    def test_inserts_and_returns_device(self, repo, sample_device):
        result = repo.create_device(sample_device)
        assert result.id == sample_device.id
        assert result.name == "Router-Principal"
        assert result.host == "10.0.0.1"

    def test_password_is_encrypted_in_db(self, repo, conn, sample_device):
        repo.create_device(sample_device)
        row = conn.execute(
            "SELECT password FROM devices WHERE id = ?", (sample_device.id,)
        ).fetchone()
        assert row is not None
        assert row[0] != "secret123"
        assert len(row[0]) > 20  # encrypted token is long

    def test_get_returns_decrypted_password(self, repo, sample_device):
        repo.create_device(sample_device)
        dev = repo.get_device(sample_device.id)
        assert dev is not None
        assert dev.password == "secret123"

    def test_insert_idempotent_with_same_id(self, repo, sample_device):
        repo.create_device(sample_device)
        repo.create_device(sample_device)  # same ID → upsert, no error
        dev = repo.get_device(sample_device.id)
        assert dev is not None
        assert dev.name == "Router-Principal"


# ── get_device ────────────────────────────────────────────────────────────

class TestGetDevice:
    def test_returns_device_by_id(self, repo, sample_device):
        repo.create_device(sample_device)
        dev = repo.get_device(sample_device.id)
        assert dev is not None
        assert dev.name == "Router-Principal"
        assert dev.type == "ROUTER"
        assert dev.username == "admin"

    def test_returns_none_for_nonexistent(self, repo):
        assert repo.get_device("nonexistent-id") is None

    def test_get_preserves_extra_metadata(self, repo, sample_device):
        repo.create_device(sample_device)
        dev = repo.get_device(sample_device.id)
        assert dev.extra_metadata == {"bgp_as": 65001}


# ── list_devices ──────────────────────────────────────────────────────────

class TestListDevices:
    def test_empty_list_when_no_devices(self, repo):
        assert repo.list_devices() == []

    def test_returns_all_devices_sorted_by_name(self, repo):
        d1 = Device(id="dev-002", name="Zebra", host="10.0.0.2")
        d2 = Device(id="dev-001", name="Alpha", host="10.0.0.1")
        d3 = Device(id="dev-003", name="Bravo", host="10.0.0.3")
        repo.create_device(d1)
        repo.create_device(d2)
        repo.create_device(d3)
        devices = repo.list_devices()
        assert len(devices) == 3
        assert devices[0].name == "Alpha"
        assert devices[1].name == "Bravo"
        assert devices[2].name == "Zebra"


# ── update_device ─────────────────────────────────────────────────────────

class TestUpdateDevice:
    def test_updates_name_and_host(self, repo, sample_device):
        repo.create_device(sample_device)
        updated = Device(
            id=sample_device.id,
            name="Router-Atualizado",
            host="10.0.0.99",
            port=2222,
            type="ROUTER",
            status="offline",
            username="admin",
            password="newsecret",
        )
        result = repo.update_device(updated)
        assert result.name == "Router-Atualizado"
        assert result.host == "10.0.0.99"

    def test_update_persists_to_db(self, repo, conn, sample_device):
        repo.create_device(sample_device)
        updated = Device(
            id=sample_device.id,
            name="New Name",
            host="10.0.0.50",
            port=22,
            type="ROUTER",
            status="online",
        )
        repo.update_device(updated)
        row = conn.execute(
            "SELECT name, host FROM devices WHERE id = ?", (sample_device.id,)
        ).fetchone()
        assert row[0] == "New Name"
        assert row[1] == "10.0.0.50"


# ── delete_device ─────────────────────────────────────────────────────────

class TestDeleteDevice:
    def test_deletes_existing(self, repo, sample_device):
        repo.create_device(sample_device)
        assert repo.delete_device(sample_device.id) is True
        assert repo.get_device(sample_device.id) is None

    def test_returns_false_for_nonexistent(self, repo):
        assert repo.delete_device("nonexistent") is False


# ── search_devices ────────────────────────────────────────────────────────

class TestSearchDevices:
    def test_finds_by_name(self, repo):
        repo.create_device(Device(id="d1", name="Router-Core", host="10.0.0.1"))
        repo.create_device(Device(id="d2", name="Switch-Access", host="10.0.0.2"))
        results = repo.search_devices("Router")
        assert len(results) == 1
        assert results[0].name == "Router-Core"

    def test_finds_by_host(self, repo):
        repo.create_device(Device(id="d1", name="Core", host="10.0.0.1"))
        results = repo.search_devices("10.0.0.1")
        assert len(results) == 1

    def test_case_insensitive(self, repo):
        repo.create_device(Device(id="d1", name="router", host="10.0.0.1"))
        results = repo.search_devices("ROUTER")
        assert len(results) == 1

    def test_returns_empty_when_no_match(self, repo):
        assert repo.search_devices("nonexistent") == []


# ── get_devices_by_type ──────────────────────────────────────────────────

class TestGetDevicesByType:
    def test_filters_by_type(self, repo):
        repo.create_device(Device(id="d1", name="R1", host="10.0.0.1", type="ROUTER"))
        repo.create_device(Device(id="d2", name="S1", host="10.0.0.2", type="SWITCH"))
        repo.create_device(Device(id="d3", name="R2", host="10.0.0.3", type="router"))
        results = repo.get_devices_by_type("ROUTER")
        assert len(results) == 2


# ── get_devices_by_status ────────────────────────────────────────────────

class TestGetDevicesByStatus:
    def test_filters_by_status(self, repo):
        repo.create_device(Device(id="d1", name="A", host="h1", status="online"))
        repo.create_device(Device(id="d2", name="B", host="h2", status="offline"))
        repo.create_device(Device(id="d3", name="C", host="h3", status="online"))
        results = repo.get_devices_by_status("online")
        assert len(results) == 2


# ── Round-trip test ──────────────────────────────────────────────────────

class TestRoundTrip:
    def test_create_then_update_then_get(self, repo, sample_device):
        repo.create_device(sample_device)
        dev = repo.get_device(sample_device.id)
        assert dev is not None
        dev.status = "offline"
        dev.extra_metadata["updated"] = True
        repo.update_device(dev)
        dev2 = repo.get_device(sample_device.id)
        assert dev2.status == "offline"
        assert dev2.extra_metadata == {"bgp_as": 65001, "updated": True}

    def test_create_device_without_password(self, repo):
        dev = Device(id="dev-002", name="NoPassword", host="10.0.0.2")
        result = repo.create_device(dev)
        assert result.password == ""
        fetched = repo.get_device("dev-002")
        assert fetched.password == ""
