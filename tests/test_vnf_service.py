"""Testes para DeviceService — domínio puro, sem Qt."""
from __future__ import annotations

import json
import tempfile
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

from huawei_manager.services.device_service import SessionOverrides, DeviceService
from huawei_manager.device_crypto import _encrypt_val
from huawei_manager.device_models import Device

# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def crypto_key(monkeypatch) -> None:
    """Injeta VNF_ENCRYPT_KEY válida para testes que persistem senhas."""
    key = Fernet.generate_key().decode()

    def _s(name: str, default: str = "") -> str:
        return key if name == "VNF_ENCRYPT_KEY" else default

    monkeypatch.setattr("huawei_manager.device_crypto._config._s", _s)


@pytest.fixture
def inventory_path() -> str:
    """Cria um arquivo JSON temporário com inventário vazio."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump([], f)
        return f.name


@pytest.fixture
def service(inventory_path: str) -> DeviceService:
    return DeviceService(inventory_path=inventory_path)


@pytest.fixture
def sample_devices() -> list[Device]:
    return [
        Device(id="dev-001", name="gw-01", host="10.0.0.1", port=22,
               type="ROUTER", username="admin", password="secret"),
        Device(id="dev-002", name="sw-01", host="10.0.0.2", port=22,
               type="SWITCH", username="admin", password="secret"),
    ]


# ══════════════════════════════════════════════════════════════════════════
#  Inventory
# ══════════════════════════════════════════════════════════════════════════


class TestInventory:
    def test_load_empty(self, service: DeviceService):
        assert service.load_inventory() == []

    def test_save_and_load(self, service: DeviceService, sample_devices: list[Device],
                           crypto_key):
        service.save_inventory(sample_devices)
        loaded = service.load_inventory()
        assert len(loaded) == 2
        assert loaded[0].id == "dev-001"

    def test_save_persists_to_disk(self, inventory_path: str,
                                    sample_devices: list[Device], crypto_key):
        service = DeviceService(inventory_path=inventory_path)
        service.save_inventory(sample_devices)
        with open(inventory_path) as f:
            data = json.load(f)
        items = data["devices"] if isinstance(data, dict) and "devices" in data else data
        assert len(items) == 2
        assert items[0]["id"] == "dev-001"
        assert items[0]["password"] != "secret"


# ══════════════════════════════════════════════════════════════════════════
#  Add Device
# ══════════════════════════════════════════════════════════════════════════


class TestAddDevice:
    def test_add_valid_device(self, service: DeviceService):
        device = service.add_device({
            "name": "fw-01",
            "host": "10.0.0.3",
            "type": "FIREWALL",
        })
        assert device.id == "dev-001-fw-01"
        assert device.name == "fw-01"
        assert device.host == "10.0.0.3"
        assert device.port == 22  # default
        assert device.type == "FIREWALL"

    def test_add_increments_id(self, service: DeviceService):
        service.add_device({"name": "a", "host": "10.0.0.1"})
        dev2 = service.add_device({"name": "b", "host": "10.0.0.2"})
        assert dev2.id == "dev-002-b"

    def test_add_missing_name_raises(self, service: DeviceService):
        with pytest.raises(ValueError, match="Nome e obrigatorio"):
            service.add_device({"host": "10.0.0.1"})

    def test_add_missing_host_raises(self, service: DeviceService):
        with pytest.raises(ValueError, match="IP/Host e obrigatorio"):
            service.add_device({"name": "x"})

    def test_add_invalid_port_raises(self, service: DeviceService):
        with pytest.raises(ValueError, match="Porta deve estar entre"):
            service.add_device({"name": "x", "host": "10.0.0.1", "port": 99999})


# ══════════════════════════════════════════════════════════════════════════
#  Update Device
# ══════════════════════════════════════════════════════════════════════════


class TestUpdateDevice:
    def test_update_name(self, service: DeviceService, sample_devices: list[Device],
                         crypto_key):
        service.save_inventory(sample_devices)
        updated = service.update_device(sample_devices[0], {"name": "gw-01-updated"})
        assert updated.name == "gw-01-updated"
        assert updated.id == "dev-001"  # ID unchanged

    def test_update_host(self, service: DeviceService, sample_devices: list[Device],
                         crypto_key):
        service.save_inventory(sample_devices)
        updated = service.update_device(sample_devices[0], {"host": "10.0.0.99"})
        assert updated.host == "10.0.0.99"

    def test_update_persists(self, service: DeviceService, sample_devices: list[Device],
                             crypto_key):
        service.save_inventory(sample_devices)
        service.update_device(sample_devices[0], {"name": "gw-changed"})
        loaded = service.load_inventory()
        assert loaded[0].name == "gw-changed"


# ══════════════════════════════════════════════════════════════════════════
#  Delete Device
# ══════════════════════════════════════════════════════════════════════════


class TestDeleteDevice:
    def test_delete_existing(self, service: DeviceService, sample_devices: list[Device],
                             crypto_key):
        remaining, removed = service.delete_device("dev-001", sample_devices)
        assert removed is not None
        assert removed.id == "dev-001"
        assert len(remaining) == 1
        assert remaining[0].id == "dev-002"

    def test_delete_nonexistent(self, service: DeviceService, sample_devices: list[Device],
                                crypto_key):
        remaining, removed = service.delete_device("dev-999", sample_devices)
        assert removed is None
        assert len(remaining) == 2

    def test_delete_persists(self, service: DeviceService, sample_devices: list[Device],
                             crypto_key):
        service.save_inventory(sample_devices)
        service.delete_device("dev-001", sample_devices)
        loaded = service.load_inventory()
        assert len(loaded) == 1
        assert loaded[0].id == "dev-002"


# ══════════════════════════════════════════════════════════════════════════
#  Probe / Simulate
# ══════════════════════════════════════════════════════════════════════════


class TestProbeOrSimulate:
    def test_simulate_mock_mode(self, service: DeviceService, sample_devices: list[Device]):
        with patch("huawei_manager.services.device_service.simulate_status") as mock_sim:
            mock_sim.return_value = sample_devices
            result = service.probe_or_simulate(sample_devices, mock_mode=True)
            mock_sim.assert_called_once_with(sample_devices)
            assert result is sample_devices

    def test_probe_real_mode(self, service: DeviceService, sample_devices: list[Device]):
        with patch("huawei_manager.services.device_service.probe_devices") as mock_probe:
            mock_probe.return_value = sample_devices
            result = service.probe_or_simulate(sample_devices, mock_mode=False)
            mock_probe.assert_called_once_with(sample_devices)
            assert result is sample_devices


# ══════════════════════════════════════════════════════════════════════════
#  password_env Resolution
# ══════════════════════════════════════════════════════════════════════════


class TestPasswordEnvResolution:
    def test_resolves_password_env(self, inventory_path: str):
        """Device com password_env → resolver preenche password."""
        devices = [Device(id="d1", name="r1", host="10.0.0.1", port=22,
                     password_env="ROUTER_PASSWORD")]
        with open(inventory_path, "w") as f:
            json.dump({"devices": [vars(d) for d in devices]}, f)

        def resolver(k: str) -> str:
            return "s3cret" if k == "ROUTER_PASSWORD" else ""

        svc = DeviceService(inventory_path, resolve_env=resolver)
        loaded = svc.load_inventory()
        assert loaded[0].password == "s3cret"

    def test_explicit_password_overrides_env(self, inventory_path: str,
                                             crypto_key):
        """Se password criptografado já está no JSON, password_env não sobrescreve."""
        devices = [Device(id="d1", name="r1", host="10.0.0.1", port=22,
                     password=_encrypt_val("manual_pass"),
                     password_env="ROUTER_PASSWORD")]
        with open(inventory_path, "w") as f:
            json.dump({"devices": [vars(d) for d in devices]}, f)

        def resolver(k: str) -> str:
            return "env_pass" if k == "ROUTER_PASSWORD" else ""

        svc = DeviceService(inventory_path, resolve_env=resolver)
        loaded = svc.load_inventory()
        assert loaded[0].password == "manual_pass"

    def test_empty_password_env_stays_empty(self, inventory_path: str):
        """Device sem password e sem password_env → password continua vazio."""
        devices = [Device(id="d1", name="r1", host="10.0.0.1", port=22)]
        with open(inventory_path, "w") as f:
            json.dump({"devices": [vars(d) for d in devices]}, f)

        svc = DeviceService(inventory_path)
        loaded = svc.load_inventory()
        assert loaded[0].password == ""

    def test_unresolvable_env_stays_empty(self, inventory_path: str):
        """password_env aponta para var inexistente → password continua vazio."""
        devices = [Device(id="d1", name="r1", host="10.0.0.1", port=22,
                     password_env="NONEXISTENT_VAR")]
        with open(inventory_path, "w") as f:
            json.dump({"devices": [vars(d) for d in devices]}, f)

        svc = DeviceService(inventory_path)  # noop resolver
        loaded = svc.load_inventory()
        assert loaded[0].password == ""

    def test_default_noop_resolver(self, inventory_path: str):
        devices = [Device(id="d1", name="r1", host="10.0.0.1", port=22,
                     password_env="ROUTER_PASSWORD")]
        with open(inventory_path, "w") as f:
            json.dump({"devices": [vars(d) for d in devices]}, f)

        svc = DeviceService(inventory_path)
        loaded = svc.load_inventory()
        assert loaded[0].password == ""

    def test_save_clears_resolved_password_when_env_exists(self, inventory_path: str):
        devices = [Device(id="d1", name="r1", host="10.0.0.1", port=22,
                     password_env="ROUTER_PASSWORD")]
        with open(inventory_path, "w") as f:
            json.dump({"devices": [vars(d) for d in devices]}, f)

        def resolver(k: str) -> str:
            return "s3cret" if k == "ROUTER_PASSWORD" else ""

        svc = DeviceService(inventory_path, resolve_env=resolver)
        loaded = svc.load_inventory()
        assert loaded[0].password == "s3cret"

        svc.save_inventory(loaded)

        with open(inventory_path) as f:
            raw = json.load(f)
        raw_dev = raw["devices"][0]
        assert raw_dev["password"] == ""
        assert raw_dev["password_env"] == "ROUTER_PASSWORD"

    def test_save_persists_no_plaintext_password(self, inventory_path: str,
                                                 crypto_key):
        svc = DeviceService(inventory_path)
        devices = [Device(id="d1", name="r1", host="10.0.0.1", port=22,
                     password="manual_pass")]
        svc.save_inventory(devices)

        with open(inventory_path) as f:
            raw = json.load(f)
        raw_dev = raw["devices"][0]
        assert raw_dev["password"] != "manual_pass"

        loaded = svc.load_inventory()
        assert loaded[0].password == "manual_pass"

    def test_resolver_exception_isolated_per_device(self, inventory_path: str):
        devices = [
            Device(id="d1", name="ok", host="10.0.0.1", port=22,
                password_env="GOOD_VAR"),
            Device(id="d2", name="bad", host="10.0.0.2", port=22,
                password_env="BAD_VAR"),
            Device(id="d3", name="also-ok", host="10.0.0.3", port=22,
                password_env="GOOD_VAR"),
        ]
        with open(inventory_path, "w") as f:
            json.dump({"devices": [vars(d) for d in devices]}, f)

        call_count = 0
        def flaky_resolver(key):
            nonlocal call_count
            if key == "BAD_VAR":
                raise RuntimeError("vault unavailable")
            call_count += 1
            return "ok_pass"

        svc = DeviceService(inventory_path, resolve_env=flaky_resolver)
        loaded = svc.load_inventory()

        assert loaded[0].password == "ok_pass"
        assert loaded[1].password == ""
        assert loaded[2].password == "ok_pass"
        assert call_count == 2


class TestTarget:
    def test_set_target(self, service: DeviceService):
        device = Device(id="x", name="x", host="10.0.0.1", port=22,
                   username="admin", password="secret", ssh_key="/key")
        overrides = service.set_target(device)
        assert isinstance(overrides, SessionOverrides)
        assert overrides.host == "10.0.0.1"
        assert overrides.port == 22
        assert overrides.username == "admin"
        assert overrides.password == "secret"
        assert overrides.ssh_key == "/key"

    def test_clear_target(self):
        overrides = DeviceService.clear_target()
        assert isinstance(overrides, SessionOverrides)
        assert overrides.host is None
        assert overrides.port is None
        assert overrides.username is None
        assert overrides.password is None
        assert overrides.ssh_key is None


# ══════════════════════════════════════════════════════════════════════════
#  Bug #3: save_inventory no-delete with repository
# ══════════════════════════════════════════════════════════════════════════


class TestSaveInventoryWithRepository:
    def test_delete_removes_from_repository(self, monkeypatch):
        from unittest.mock import MagicMock
        from huawei_manager.services.device_service import DeviceService

        repo = MagicMock()
        d1 = Device(id="dev-001", name="r1", host="10.0.0.1", port=22, type="ROUTER")
        d2 = Device(id="dev-002", name="r2", host="10.0.0.2", port=22, type="SWITCH")
        repo.list_devices.return_value = [d1, d2]

        svc = DeviceService(inventory_path="/tmp/unused.json", repository=repo)
        remaining, removed = svc.delete_device("dev-001", [d1, d2])

        assert removed.id == "dev-001"
        assert len(remaining) == 1

        repo.delete_device.assert_called_once_with("dev-001")

    def test_save_inventory_deletes_removed_devices(self, monkeypatch):
        from unittest.mock import MagicMock
        from huawei_manager.services.device_service import DeviceService

        repo = MagicMock()
        d1 = Device(id="dev-001", name="r1", host="10.0.0.1", port=22, type="ROUTER")
        d2 = Device(id="dev-002", name="r2", host="10.0.0.2", port=22, type="SWITCH")
        repo.list_devices.return_value = [d1, d2]

        svc = DeviceService(inventory_path="/tmp/unused.json", repository=repo)

        svc.save_inventory([d1])

        repo.create_device.assert_called_once_with(d1)
        repo.delete_device.assert_called_once_with("dev-002")
