"""Testes para VnfService — domínio puro, sem Qt."""
from __future__ import annotations

import json
import tempfile
from unittest.mock import patch

import pytest

from huawei_manager.services.vnf_service import SessionOverrides, VnfService
from huawei_manager.vnf_models import VNF

# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def inventory_path() -> str:
    """Cria um arquivo JSON temporário com inventário vazio."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump([], f)
        return f.name


@pytest.fixture
def service(inventory_path: str) -> VnfService:
    return VnfService(inventory_path=inventory_path)


@pytest.fixture
def sample_vnfs() -> list[VNF]:
    return [
        VNF(id="vnf-001", name="gw-01", host="10.0.0.1", port=22,
            type="ROUTER", username="admin", password="secret"),
        VNF(id="vnf-002", name="sw-01", host="10.0.0.2", port=22,
            type="SWITCH", username="admin", password="secret"),
    ]


# ══════════════════════════════════════════════════════════════════════════
#  Inventory
# ══════════════════════════════════════════════════════════════════════════


class TestInventory:
    def test_load_empty(self, service: VnfService):
        assert service.load_inventory() == []

    def test_save_and_load(self, service: VnfService, sample_vnfs: list[VNF]):
        service.save_inventory(sample_vnfs)
        loaded = service.load_inventory()
        assert len(loaded) == 2
        assert loaded[0].id == "vnf-001"

    def test_save_persists_to_disk(self, inventory_path: str, sample_vnfs: list[VNF]):
        service = VnfService(inventory_path=inventory_path)
        service.save_inventory(sample_vnfs)
        with open(inventory_path) as f:
            data = json.load(f)
        items = data["vnfs"] if isinstance(data, dict) and "vnfs" in data else data
        assert len(items) == 2
        assert items[0]["id"] == "vnf-001"


# ══════════════════════════════════════════════════════════════════════════
#  Add Device
# ══════════════════════════════════════════════════════════════════════════


class TestAddDevice:
    def test_add_valid_device(self, service: VnfService):
        vnf = service.add_device({
            "name": "fw-01",
            "host": "10.0.0.3",
            "type": "FIREWALL",
        })
        assert vnf.id == "vnf-001-fw-01"
        assert vnf.name == "fw-01"
        assert vnf.host == "10.0.0.3"
        assert vnf.port == 22  # default
        assert vnf.type == "FIREWALL"

    def test_add_increments_id(self, service: VnfService):
        service.add_device({"name": "a", "host": "10.0.0.1"})
        vnf2 = service.add_device({"name": "b", "host": "10.0.0.2"})
        assert vnf2.id == "vnf-002-b"

    def test_add_missing_name_raises(self, service: VnfService):
        with pytest.raises(ValueError, match="Nome é obrigatório"):
            service.add_device({"host": "10.0.0.1"})

    def test_add_missing_host_raises(self, service: VnfService):
        with pytest.raises(ValueError, match="IP/Host é obrigatório"):
            service.add_device({"name": "x"})

    def test_add_invalid_port_raises(self, service: VnfService):
        with pytest.raises(ValueError, match="Porta deve estar entre"):
            service.add_device({"name": "x", "host": "10.0.0.1", "port": 99999})


# ══════════════════════════════════════════════════════════════════════════
#  Update Device
# ══════════════════════════════════════════════════════════════════════════


class TestUpdateDevice:
    def test_update_name(self, service: VnfService, sample_vnfs: list[VNF]):
        service.save_inventory(sample_vnfs)
        updated = service.update_device(sample_vnfs[0], {"name": "gw-01-updated"})
        assert updated.name == "gw-01-updated"
        assert updated.id == "vnf-001"  # ID unchanged

    def test_update_host(self, service: VnfService, sample_vnfs: list[VNF]):
        service.save_inventory(sample_vnfs)
        updated = service.update_device(sample_vnfs[0], {"host": "10.0.0.99"})
        assert updated.host == "10.0.0.99"

    def test_update_persists(self, service: VnfService, sample_vnfs: list[VNF]):
        service.save_inventory(sample_vnfs)
        service.update_device(sample_vnfs[0], {"name": "gw-changed"})
        loaded = service.load_inventory()
        assert loaded[0].name == "gw-changed"


# ══════════════════════════════════════════════════════════════════════════
#  Delete Device
# ══════════════════════════════════════════════════════════════════════════


class TestDeleteDevice:
    def test_delete_existing(self, service: VnfService, sample_vnfs: list[VNF]):
        remaining, removed = service.delete_device("vnf-001", sample_vnfs)
        assert removed is not None
        assert removed.id == "vnf-001"
        assert len(remaining) == 1
        assert remaining[0].id == "vnf-002"

    def test_delete_nonexistent(self, service: VnfService, sample_vnfs: list[VNF]):
        remaining, removed = service.delete_device("vnf-999", sample_vnfs)
        assert removed is None
        assert len(remaining) == 2

    def test_delete_persists(self, service: VnfService, sample_vnfs: list[VNF]):
        service.save_inventory(sample_vnfs)
        service.delete_device("vnf-001", sample_vnfs)
        loaded = service.load_inventory()
        assert len(loaded) == 1
        assert loaded[0].id == "vnf-002"


# ══════════════════════════════════════════════════════════════════════════
#  Probe / Simulate
# ══════════════════════════════════════════════════════════════════════════


class TestProbeOrSimulate:
    def test_simulate_mock_mode(self, service: VnfService, sample_vnfs: list[VNF]):
        with patch("huawei_manager.services.vnf_service.simulate_status") as mock_sim:
            mock_sim.return_value = sample_vnfs
            result = service.probe_or_simulate(sample_vnfs, mock_mode=True)
            mock_sim.assert_called_once_with(sample_vnfs)
            assert result is sample_vnfs

    def test_probe_real_mode(self, service: VnfService, sample_vnfs: list[VNF]):
        with patch("huawei_manager.services.vnf_service.probe_vnfs") as mock_probe:
            mock_probe.return_value = sample_vnfs
            result = service.probe_or_simulate(sample_vnfs, mock_mode=False)
            mock_probe.assert_called_once_with(sample_vnfs)
            assert result is sample_vnfs


# ══════════════════════════════════════════════════════════════════════════
#  Target
# ══════════════════════════════════════════════════════════════════════════


class TestTarget:
    def test_set_target(self, service: VnfService):
        vnf = VNF(id="x", name="x", host="10.0.0.1", port=22,
                  username="admin", password="secret", ssh_key="/key")
        overrides = service.set_target(vnf)
        assert isinstance(overrides, SessionOverrides)
        assert overrides.host == "10.0.0.1"
        assert overrides.port == 22
        assert overrides.username == "admin"
        assert overrides.password == "secret"
        assert overrides.ssh_key == "/key"

    def test_clear_target(self):
        overrides = VnfService.clear_target()
        assert isinstance(overrides, SessionOverrides)
        assert overrides.host is None
        assert overrides.port is None
        assert overrides.username is None
        assert overrides.password is None
        assert overrides.ssh_key is None
