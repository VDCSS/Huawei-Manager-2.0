"""Testes do núcleo de persistência do perfil de Bloquear Internet.

Módulo puro (``huawei_manager.services.acl_presets``) — sem Qt:
isolamento por device, escrita atômica, falha fechada em JSON
corrompido e validação canônica dos campos.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from huawei_manager.exceptions import SdnValidationError
from huawei_manager.services.acl_presets import (
    ACL_BLOCK_RANGE,
    AclBlockProfile,
    delete_profile,
    device_key,
    load_profile,
    profile_path,
    save_profile,
    set_applied,
    validate_profile,
)


def _profile(**overrides) -> AclBlockProfile:
    base = dict(
        device_key="RTR-01@10.0.0.1",
        acl_name="bloqueio-padrão",
        acl_number=3000,
        destination_ip="203.0.113.10",
        destination_mask="0.0.0.0",
        interface="GigabitEthernet0/0/0",
        direction="outbound",
        created_from_snapshot=False,
        applied=False,
    )
    base.update(overrides)
    return AclBlockProfile(**base)  # type: ignore[arg-type]


@pytest.fixture()
def store(tmp_path: Path) -> Path:
    return tmp_path / "acl_presets.json"


class TestRoundTrip:
    def test_missing_file_returns_none(self, store: Path) -> None:
        assert load_profile(store, "RTR-01@10.0.0.1") is None

    def test_save_then_load(self, store: Path) -> None:
        save_profile(store, _profile())
        loaded = load_profile(store, "RTR-01@10.0.0.1")
        assert loaded is not None
        assert loaded.acl_number == 3000
        assert loaded.destination_ip == "203.0.113.10"
        assert loaded.interface == "GigabitEthernet0/0/0"
        assert loaded.direction == "outbound"
        assert loaded.applied is False

    def test_roundtrip_preserves_flags(self, store: Path) -> None:
        save_profile(
            store, _profile(created_from_snapshot=True, applied=True)
        )
        loaded = load_profile(store, "RTR-01@10.0.0.1")
        assert loaded is not None
        assert loaded.created_from_snapshot is True
        assert loaded.applied is True

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        nested = tmp_path / "deep" / "nested" / "acl_presets.json"
        save_profile(nested, _profile())
        assert nested.exists()


class TestDeviceIsolation:
    def test_profiles_are_isolated_per_device(self, store: Path) -> None:
        save_profile(store, _profile(device_key="A@1.1.1.1", acl_number=3000))
        save_profile(store, _profile(device_key="B@2.2.2.2", acl_number=3010))

        a = load_profile(store, "A@1.1.1.1")
        b = load_profile(store, "B@2.2.2.2")
        assert a is not None and b is not None
        assert a.acl_number == 3000
        assert b.acl_number == 3010

    def test_unknown_key_returns_none(self, store: Path) -> None:
        save_profile(store, _profile(device_key="A@1.1.1.1"))
        assert load_profile(store, "NADA@0.0.0.0") is None

    def test_overwrite_same_key(self, store: Path) -> None:
        save_profile(store, _profile(device_key="A@1.1.1.1", acl_number=3000))
        save_profile(store, _profile(device_key="A@1.1.1.1", acl_number=3011))
        loaded = load_profile(store, "A@1.1.1.1")
        assert loaded is not None
        assert loaded.acl_number == 3011

    def test_device_key_is_stable(self) -> None:
        assert device_key(" RTR-01 ", " 10.0.0.1 ") == "RTR-01@10.0.0.1"


class TestDelete:
    def test_delete_existing(self, store: Path) -> None:
        save_profile(store, _profile(device_key="A@1.1.1.1"))
        assert delete_profile(store, "A@1.1.1.1") is True
        assert load_profile(store, "A@1.1.1.1") is None

    def test_delete_missing_is_false_not_error(self, store: Path) -> None:
        assert delete_profile(store, "A@1.1.1.1") is False

    def test_delete_file_missing_is_false(self, store: Path) -> None:
        assert delete_profile(store, "A@1.1.1.1") is False

    def test_delete_keeps_other_devices(self, store: Path) -> None:
        save_profile(store, _profile(device_key="A@1.1.1.1"))
        save_profile(store, _profile(device_key="B@2.2.2.2"))
        delete_profile(store, "A@1.1.1.1")
        assert load_profile(store, "A@1.1.1.1") is None
        assert load_profile(store, "B@2.2.2.2") is not None

    def test_delete_empty_key_raises(self, store: Path) -> None:
        with pytest.raises(SdnValidationError):
            delete_profile(store, "   ")


class TestFailClosed:
    def test_corrupted_json_raises(self, store: Path) -> None:
        store.write_text("{ definitivamente não é json", encoding="utf-8")
        with pytest.raises(SdnValidationError, match="corrompido"):
            load_profile(store, "A@1.1.1.1")

    def test_json_not_object_raises(self, store: Path) -> None:
        store.write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(SdnValidationError, match="objeto"):
            load_profile(store, "A@1.1.1.1")

    def test_profiles_not_dict_raises(self, store: Path) -> None:
        store.write_text('{"profiles": "oops"}', encoding="utf-8")
        with pytest.raises(SdnValidationError, match="profiles"):
            load_profile(store, "A@1.1.1.1")

    def test_unknown_field_raises(self, store: Path) -> None:
        store.write_text(
            json.dumps(
                {
                    "version": 1,
                    "profiles": {
                        "A@1.1.1.1": {
                            "device_key": "A@1.1.1.1",
                            "acl_name": "x",
                            "acl_number": 3000,
                            "destination_ip": "10.0.0.1",
                            "destination_mask": "0.0.0.0",
                            "interface": "GigabitEthernet0/0/0",
                            "direction": "outbound",
                            "campo_novo": 1,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(SdnValidationError, match="desconhecidos"):
            load_profile(store, "A@1.1.1.1")

    def test_empty_file_treated_as_absent(self, store: Path) -> None:
        store.write_text("", encoding="utf-8")
        assert load_profile(store, "A@1.1.1.1") is None

    def test_missing_device_key_raises(self, store: Path) -> None:
        with pytest.raises(SdnValidationError, match="obrigat"):
            load_profile(store, None)

    def test_blank_device_key_raises(self, store: Path) -> None:
        with pytest.raises(SdnValidationError):
            load_profile(store, "  ")


class TestValidation:
    @pytest.mark.parametrize("number", [2999, 4000, 0, -1])
    def test_acl_number_out_of_range_raises(self, number: int) -> None:
        with pytest.raises(SdnValidationError, match="faixa"):
            validate_profile(_profile(acl_number=number))

    @pytest.mark.parametrize("number", list(range(*ACL_BLOCK_RANGE))[:1] + [3000, 3999])
    def test_acl_number_in_range_ok(self, number: int) -> None:
        assert validate_profile(_profile(acl_number=number)).acl_number == number

    @pytest.mark.parametrize("direction", ["inbound", "outbound"])
    def test_valid_directions(self, direction: str) -> None:
        assert validate_profile(_profile(direction=direction)).direction == direction

    @pytest.mark.parametrize("direction", ["both", "IN", "", "sideways"])
    def test_invalid_direction_raises(self, direction: str) -> None:
        with pytest.raises(SdnValidationError, match="dire"):
            validate_profile(_profile(direction=direction))

    @pytest.mark.parametrize("ip", ["999.1.1.1", "abc", "10.0.0", ""])
    def test_invalid_destination_ip_raises(self, ip: str) -> None:
        with pytest.raises(SdnValidationError):
            validate_profile(_profile(destination_ip=ip))

    def test_valid_destination_ip_normalized(self) -> None:
        out = validate_profile(_profile(destination_ip=" 203.0.113.7 "))
        assert out.destination_ip == "203.0.113.7"

    def test_mask_any_rejected(self) -> None:
        with pytest.raises(SdnValidationError, match="any"):
            validate_profile(_profile(destination_mask="any"))

    def test_empty_mask_defaults_to_host(self) -> None:
        out = validate_profile(_profile(destination_mask=""))
        assert out.destination_mask == "0.0.0.0"

    @pytest.mark.parametrize("iface", ["GigabitEthernet0/0/0", "Vlanif10", "NULL0"])
    def test_valid_interface(self, iface: str) -> None:
        assert validate_profile(_profile(interface=iface)).interface == iface

    @pytest.mark.parametrize("iface", ["", "Giga bitEthernet0/0/0", "iface!"])
    def test_invalid_interface_raises(self, iface: str) -> None:
        with pytest.raises(SdnValidationError):
            validate_profile(_profile(interface=iface))

    @pytest.mark.parametrize("name", ["bloqueio-padrão", "acl_1", "x" * 32])
    def test_valid_acl_name(self, name: str) -> None:
        assert validate_profile(_profile(acl_name=name)).acl_name == name

    @pytest.mark.parametrize("name", ["", "tem espaço", "1234", "x" * 33])
    def test_invalid_acl_name_raises(self, name: str) -> None:
        with pytest.raises(SdnValidationError):
            validate_profile(_profile(acl_name=name))

    def test_empty_device_key_raises(self) -> None:
        with pytest.raises(SdnValidationError, match="device_key"):
            validate_profile(_profile(device_key=""))

    def test_acl_ref_is_number(self) -> None:
        assert _profile().acl_ref == "3000"


class TestSetApplied:
    def test_updates_cache_only(self, store: Path) -> None:
        save_profile(store, _profile(applied=False))
        updated = set_applied(store, "RTR-01@10.0.0.1", True)
        assert updated is not None and updated.applied is True
        loaded = load_profile(store, "RTR-01@10.0.0.1")
        assert loaded is not None
        assert loaded.applied is True
        # demais campos intactos
        assert loaded.acl_number == 3000
        assert loaded.destination_ip == "203.0.113.10"

    def test_unapply(self, store: Path) -> None:
        save_profile(store, _profile(applied=True))
        set_applied(store, "RTR-01@10.0.0.1", False)
        loaded = load_profile(store, "RTR-01@10.0.0.1")
        assert loaded is not None and loaded.applied is False

    def test_no_profile_returns_none(self, store: Path) -> None:
        assert set_applied(store, "A@1.1.1.1", True) is None


class TestAtomicWrite:
    def test_no_tmp_file_left_behind(self, store: Path) -> None:
        save_profile(store, _profile())
        leftovers = list(store.parent.glob("*.tmp"))
        assert leftovers == []

    def test_written_json_is_valid(self, store: Path) -> None:
        save_profile(store, _profile())
        data = json.loads(store.read_text(encoding="utf-8"))
        assert data["version"] == 1
        assert "RTR-01@10.0.0.1" in data["profiles"]


class TestProfilePath:
    def test_default_path_location(self) -> None:
        path = profile_path()
        assert path.name == "acl_presets.json"
        assert path.parent.exists()

    def test_env_override(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("HW_DATA_DIR", str(tmp_path))
        assert profile_path() == tmp_path / "acl_presets.json"
