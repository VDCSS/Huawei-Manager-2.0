import json

from huawei_manager.topology import (
    VNF,
    _normalize_status,
    load_vnf_inventory,
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
