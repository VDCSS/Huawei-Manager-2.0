import inspect
import json
import unittest.mock

import pytest
from cryptography.fernet import Fernet

from huawei_manager.topology import TopologyCanvas
from huawei_manager.device_inventory import load_devices, save_devices
from huawei_manager.device_models import Device
from huawei_manager.device_probe import _check_device, _normalize_status, probe_devices


class TestDevice:
    def test_create(self):
        v = Device(id="r1", name="R1", host="10.0.0.1", port=22, type="ROUTER", status="online", username="admin")
        assert v.name == "R1"

    def test_label_returns_name(self):
        v = Device(id="r1", name="R1", host="10.0.0.1", port=22, type="ROUTER", status="online", username="admin")
        assert v.label() == "R1"

    def test_address_returns_host_port(self):
        v = Device(id="r1", name="R1", host="10.0.0.1", port=2222, type="ROUTER", status="online", username="admin")
        assert "10.0.0.1" in v.address()
        assert "2222" in v.address()

    def test_from_dict(self):
        data = dict(id="r1", name="R1", host="10.0.0.1", port=22,
                    type="ROUTER", status="online", username="admin")
        v = Device.from_dict(data)
        assert v.name == "R1"
        assert v.host == "10.0.0.1"


class TestLoadDeviceInventory:
    def test_file_not_found_returns_empty(self, tmp_path):
        devices = load_devices(str(tmp_path / "nonexistent.json"))
        assert devices == []

    def test_malformed_json_returns_empty(self, tmp_path):
        p = tmp_path / "inventory.json"
        p.write_text("{invalid}", encoding="utf-8")
        devices = load_devices(str(p))
        assert devices == []

    def test_valid_json(self, tmp_path):
        data = {"devices": [dict(id="r1", name="R1", host="10.0.0.1",
                              port=22, type="ROUTER", status="online",
                              username="admin")]}
        p = tmp_path / "inventory.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        devices = load_devices(str(p))
        assert len(devices) == 1
        assert devices[0].name == "R1"


class TestSaveDeviceInventory:
    def test_roundtrip(self, tmp_path):
        devices = [Device(id="r1", name="R1", host="10.0.0.1", port=22, type="ROUTER", status="online", username="admin")]
        p = tmp_path / "inventory.json"
        save_devices(devices, str(p))
        loaded = load_devices(str(p))
        assert len(loaded) == 1
        assert loaded[0].name == "R1"

    def test_json_structure(self, tmp_path):
        devices = [Device(id="r1", name="R1", host="10.0.0.1", port=22, type="ROUTER", status="online", username="admin")]
        p = tmp_path / "inventory.json"
        save_devices(devices, str(p))
        raw = json.loads(p.read_text())
        assert "devices" in raw
        assert len(raw["devices"]) == 1


class TestNormalizeStatus:
    def test_online(self):
        assert _normalize_status("online") == "online"

    def test_offline(self):
        assert _normalize_status("offline") == "offline"

    def test_unknown_becomes_unknown(self):
        assert _normalize_status("something") == "unknown"


class TestDevicePasswordEncryption:
    def test_password_encrypted_on_disk(self, tmp_path, monkeypatch):
        key = Fernet.generate_key().decode()
        def fake_s(k, d=""):
            return key if k == "VNF_ENCRYPT_KEY" else d
        monkeypatch.setattr("huawei_manager._config._s", fake_s)

        v = Device(id="r1", name="R1", host="10.0.0.1", password="my_secret_pass")
        p = tmp_path / "inventory.json"
        save_devices([v], str(p))

        raw = json.loads(p.read_text())
        saved_pw = raw["devices"][0]["password"]
        assert saved_pw != "my_secret_pass"
        assert saved_pw.startswith("gAAAAA")

        loaded = load_devices(str(p))
        assert loaded[0].password == "my_secret_pass"

    def test_password_save_fails_without_key(self, tmp_path, monkeypatch):
        monkeypatch.setattr("huawei_manager._config._s", lambda k, d="": "")

        v = Device(id="r1", name="R1", host="10.0.0.1", password="secret123")
        p = tmp_path / "inventory.json"
        with pytest.raises(ValueError):
            save_devices([v], str(p))


    def test_ssh_key_encrypted_on_disk(self, tmp_path, monkeypatch):
        key = Fernet.generate_key().decode()
        def fake_s(k, d=""):
            return key if k == "VNF_ENCRYPT_KEY" else d
        monkeypatch.setattr("huawei_manager._config._s", fake_s)

        v = Device(id="r1", name="R1", host="10.0.0.1",
                ssh_key="-----BEGIN OPENSSH PRIVATE KEY-----\nfake")
        p = tmp_path / "inventory.json"
        save_devices([v], str(p))

        raw = json.loads(p.read_text())
        saved_sk = raw["devices"][0]["ssh_key"]
        assert saved_sk != v.ssh_key
        assert saved_sk.startswith("gAAAAA")

        loaded = load_devices(str(p))
        assert loaded[0].ssh_key == v.ssh_key

    def test_ssh_key_save_fails_without_key(self, tmp_path, monkeypatch):
        monkeypatch.setattr("huawei_manager._config._s", lambda k, d="": "")

        v = Device(id="r1", name="R1", host="10.0.0.1",
                ssh_key="-----BEGIN OPENSSH PRIVATE KEY-----\nfake")
        p = tmp_path / "inventory.json"
        with pytest.raises(ValueError):
            save_devices([v], str(p))


class TestProbeTimeout:
    def test_timeout_configurable(self):
        sig = inspect.signature(probe_devices)
        assert "timeout" in sig.parameters

    def test_default_timeout_reasonable(self):
        sig = inspect.signature(_check_device)
        default = sig.parameters["timeout"].default
        assert isinstance(default, int) and default >= 3


class TestCanvasSetDeviceStatus:
    def test_updates_node_and_redraws(self):
        canvas = unittest.mock.MagicMock()
        canvas._device_map = {"r1": Device(id="r1", name="R1", host="10.0.0.1", type="ROUTER",
                                     status="online", username="admin", port=22)}
        TopologyCanvas.set_device_status(canvas, "r1", "offline")
        assert canvas._device_map["r1"].status == "offline"
        canvas._draw.assert_called_once()

    def test_unknown_device_warns_no_crash(self, caplog):
        canvas = unittest.mock.MagicMock()
        canvas._device_map = {}
        TopologyCanvas.set_device_status(canvas, "ghost", "offline")
        canvas._draw.assert_not_called()
        assert "ghost" in caplog.text

    def test_arg_order_matches_protocol(self):
        sig = inspect.signature(TopologyCanvas.set_device_status)
        params = list(sig.parameters)
        assert params[1] == "device_id"
        assert params[2] == "status"
