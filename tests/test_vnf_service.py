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
#  password_env Resolution
# ══════════════════════════════════════════════════════════════════════════


class TestPasswordEnvResolution:
    def test_resolves_password_env(self, inventory_path: str):
        """VNF com password_env → resolver preenche password."""
        vnfs = [VNF(id="v1", name="r1", host="10.0.0.1", port=22,
                     password_env="ROUTER_PASSWORD")]
        with open(inventory_path, "w") as f:
            json.dump({"vnfs": [vars(v) for v in vnfs]}, f)

        resolver = lambda k: "s3cret" if k == "ROUTER_PASSWORD" else ""
        svc = VnfService(inventory_path, resolve_env=resolver)
        loaded = svc.load_inventory()
        assert loaded[0].password == "s3cret"

    def test_explicit_password_overrides_env(self, inventory_path: str):
        """Se password já está no JSON, password_env não sobrescreve."""
        vnfs = [VNF(id="v1", name="r1", host="10.0.0.1", port=22,
                     password="manual_pass", password_env="ROUTER_PASSWORD")]
        with open(inventory_path, "w") as f:
            json.dump({"vnfs": [vars(v) for v in vnfs]}, f)

        resolver = lambda k: "env_pass" if k == "ROUTER_PASSWORD" else ""
        svc = VnfService(inventory_path, resolve_env=resolver)
        loaded = svc.load_inventory()
        assert loaded[0].password == "manual_pass"

    def test_empty_password_env_stays_empty(self, inventory_path: str):
        """VNF sem password e sem password_env → password continua vazio."""
        vnfs = [VNF(id="v1", name="r1", host="10.0.0.1", port=22)]
        with open(inventory_path, "w") as f:
            json.dump({"vnfs": [vars(v) for v in vnfs]}, f)

        svc = VnfService(inventory_path)
        loaded = svc.load_inventory()
        assert loaded[0].password == ""

    def test_unresolvable_env_stays_empty(self, inventory_path: str):
        """password_env aponta para var inexistente → password continua vazio."""
        vnfs = [VNF(id="v1", name="r1", host="10.0.0.1", port=22,
                     password_env="NONEXISTENT_VAR")]
        with open(inventory_path, "w") as f:
            json.dump({"vnfs": [vars(v) for v in vnfs]}, f)

        svc = VnfService(inventory_path)  # noop resolver
        loaded = svc.load_inventory()
        assert loaded[0].password == ""

    def test_default_noop_resolver(self, inventory_path: str):
        vnfs = [VNF(id="v1", name="r1", host="10.0.0.1", port=22,
                     password_env="ROUTER_PASSWORD")]
        with open(inventory_path, "w") as f:
            json.dump({"vnfs": [vars(v) for v in vnfs]}, f)

        svc = VnfService(inventory_path)
        loaded = svc.load_inventory()
        assert loaded[0].password == ""

    def test_save_clears_resolved_password_when_env_exists(self, inventory_path: str):
        vnfs = [VNF(id="v1", name="r1", host="10.0.0.1", port=22,
                     password_env="ROUTER_PASSWORD")]
        with open(inventory_path, "w") as f:
            json.dump({"vnfs": [vars(v) for v in vnfs]}, f)

        resolver = lambda k: "s3cret" if k == "ROUTER_PASSWORD" else ""
        svc = VnfService(inventory_path, resolve_env=resolver)
        loaded = svc.load_inventory()
        assert loaded[0].password == "s3cret"

        svc.save_inventory(loaded)

        with open(inventory_path) as f:
            raw = json.load(f)
        raw_vnf = raw["vnfs"][0]
        assert raw_vnf["password"] == ""
        assert raw_vnf["password_env"] == "ROUTER_PASSWORD"

    def test_save_preserves_explicit_password(self, inventory_path: str):
        vnfs = [VNF(id="v1", name="r1", host="10.0.0.1", port=22,
                     password="manual_pass")]
        with open(inventory_path, "w") as f:
            json.dump({"vnfs": [vars(v) for v in vnfs]}, f)

        svc = VnfService(inventory_path)
        loaded = svc.load_inventory()
        loaded[0].password = "manual_pass"
        svc.save_inventory(loaded)

        with open(inventory_path) as f:
            raw = json.load(f)
        raw_vnf = raw["vnfs"][0]
        assert raw_vnf["password"] == "manual_pass"

    def test_resolver_exception_isolated_per_vnf(self, inventory_path: str):
        vnfs = [
            VNF(id="v1", name="ok", host="10.0.0.1", port=22,
                password_env="GOOD_VAR"),
            VNF(id="v2", name="bad", host="10.0.0.2", port=22,
                password_env="BAD_VAR"),
            VNF(id="v3", name="also-ok", host="10.0.0.3", port=22,
                password_env="GOOD_VAR"),
        ]
        with open(inventory_path, "w") as f:
            json.dump({"vnfs": [vars(v) for v in vnfs]}, f)

        call_count = 0
        def flaky_resolver(key):
            nonlocal call_count
            if key == "BAD_VAR":
                raise RuntimeError("vault unavailable")
            call_count += 1
            return "ok_pass"

        svc = VnfService(inventory_path, resolve_env=flaky_resolver)
        loaded = svc.load_inventory()

        assert loaded[0].password == "ok_pass"
        assert loaded[1].password == ""
        assert loaded[2].password == "ok_pass"
        assert call_count == 2


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
