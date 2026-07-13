import inspect
import json

from cryptography.fernet import Fernet

from huawei_manager.vnf_models import (
    VNF,
    _check_vnf,
    _normalize_status,
    load_vnf_inventory,
    probe_vnfs,
    save_vnf_inventory,
)


class TestVNF:
    def test_create(self):
        v = VNF(id="r1", name="R1", host="10.0.0.1", port=22, type="ROUTER", status="online", username="admin")
        assert v.name == "R1"

    def test_label_returns_name(self):
        v = VNF(id="r1", name="R1", host="10.0.0.1", port=22, type="ROUTER", status="online", username="admin")
        assert v.label() == "R1"

    def test_address_returns_host_port(self):
        v = VNF(id="r1", name="R1", host="10.0.0.1", port=2222, type="ROUTER", status="online", username="admin")
        assert "10.0.0.1" in v.address()
        assert "2222" in v.address()

    def test_from_dict(self):
        data = dict(id="r1", name="R1", host="10.0.0.1", port=22,
                    type="ROUTER", status="online", username="admin")
        v = VNF.from_dict(data)
        assert v.name == "R1"
        assert v.host == "10.0.0.1"


class TestLoadVnfInventory:
    def test_file_not_found_returns_empty(self, tmp_path):
        vnfs = load_vnf_inventory(str(tmp_path / "nonexistent.json"))
        assert vnfs == []

    def test_malformed_json_returns_empty(self, tmp_path):
        p = tmp_path / "inventory.json"
        p.write_text("{invalid}", encoding="utf-8")
        vnfs = load_vnf_inventory(str(p))
        assert vnfs == []

    def test_valid_json(self, tmp_path):
        data = {"vnfs": [dict(id="r1", name="R1", host="10.0.0.1",
                              port=22, type="ROUTER", status="online",
                              username="admin")]}
        p = tmp_path / "inventory.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        vnfs = load_vnf_inventory(str(p))
        assert len(vnfs) == 1
        assert vnfs[0].name == "R1"


class TestSaveVnfInventory:
    def test_roundtrip(self, tmp_path):
        vnfs = [VNF(id="r1", name="R1", host="10.0.0.1", port=22, type="ROUTER", status="online", username="admin")]
        p = tmp_path / "inventory.json"
        save_vnf_inventory(vnfs, str(p))
        loaded = load_vnf_inventory(str(p))
        assert len(loaded) == 1
        assert loaded[0].name == "R1"

    def test_json_structure(self, tmp_path):
        vnfs = [VNF(id="r1", name="R1", host="10.0.0.1", port=22, type="ROUTER", status="online", username="admin")]
        p = tmp_path / "inventory.json"
        save_vnf_inventory(vnfs, str(p))
        raw = json.loads(p.read_text())
        assert "vnfs" in raw
        assert len(raw["vnfs"]) == 1


class TestNormalizeStatus:
    def test_online(self):
        assert _normalize_status("online") == "online"

    def test_offline(self):
        assert _normalize_status("offline") == "offline"

    def test_unknown_becomes_unknown(self):
        assert _normalize_status("something") == "unknown"


class TestVnfPasswordEncryption:
    def test_password_encrypted_on_disk(self, tmp_path, monkeypatch):
        key = Fernet.generate_key().decode()
        def fake_s(k, d=""):
            return key if k == "VNF_ENCRYPT_KEY" else d
        monkeypatch.setattr("huawei_manager._config._s", fake_s)

        v = VNF(id="r1", name="R1", host="10.0.0.1", password="my_secret_pass")
        p = tmp_path / "inventory.json"
        save_vnf_inventory([v], str(p))

        raw = json.loads(p.read_text())
        saved_pw = raw["vnfs"][0]["password"]
        assert saved_pw != "my_secret_pass"
        assert saved_pw.startswith("gAAAAA")

        loaded = load_vnf_inventory(str(p))
        assert loaded[0].password == "my_secret_pass"

    def test_password_fallback_no_key(self, tmp_path, monkeypatch):
        monkeypatch.setattr("huawei_manager._config._s", lambda k, d="": "")

        v = VNF(id="r1", name="R1", host="10.0.0.1", password="secret123")
        p = tmp_path / "inventory.json"
        save_vnf_inventory([v], str(p))

        raw = json.loads(p.read_text())
        assert raw["vnfs"][0]["password"] == "secret123"

        loaded = load_vnf_inventory(str(p))
        assert loaded[0].password == "secret123"


    def test_ssh_key_encrypted_on_disk(self, tmp_path, monkeypatch):
        key = Fernet.generate_key().decode()
        def fake_s(k, d=""):
            return key if k == "VNF_ENCRYPT_KEY" else d
        monkeypatch.setattr("huawei_manager._config._s", fake_s)

        v = VNF(id="r1", name="R1", host="10.0.0.1",
                ssh_key="-----BEGIN OPENSSH PRIVATE KEY-----\nfake")
        p = tmp_path / "inventory.json"
        save_vnf_inventory([v], str(p))

        raw = json.loads(p.read_text())
        saved_sk = raw["vnfs"][0]["ssh_key"]
        assert saved_sk != v.ssh_key
        assert saved_sk.startswith("gAAAAA")

        loaded = load_vnf_inventory(str(p))
        assert loaded[0].ssh_key == v.ssh_key

    def test_ssh_key_fallback_no_key(self, tmp_path, monkeypatch):
        monkeypatch.setattr("huawei_manager._config._s", lambda k, d="": "")

        v = VNF(id="r1", name="R1", host="10.0.0.1",
                ssh_key="-----BEGIN OPENSSH PRIVATE KEY-----\nfake")
        p = tmp_path / "inventory.json"
        save_vnf_inventory([v], str(p))

        raw = json.loads(p.read_text())
        assert raw["vnfs"][0]["ssh_key"] == v.ssh_key

        loaded = load_vnf_inventory(str(p))
        assert loaded[0].ssh_key == v.ssh_key


class TestProbeTimeout:
    def test_timeout_configurable(self):
        sig = inspect.signature(probe_vnfs)
        assert "timeout" in sig.parameters

    def test_default_timeout_reasonable(self):
        sig = inspect.signature(_check_vnf)
        default = sig.parameters["timeout"].default
        assert isinstance(default, int) and default >= 3
