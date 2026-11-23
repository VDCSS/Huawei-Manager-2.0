"""Testes do núcleo de persistência dos presets de traffic policy.

Módulo puro (``huawei_manager.services.traffic_policy_presets``) — sem Qt
e sem rede: isolamento por device/fluxo, escrita atômica, falha fechada
em JSON corrompido e validação canônica dos campos.
"""
from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from huawei_manager.exceptions import SdnValidationError
from huawei_manager.services.traffic_policy_presets import (
    TrafficPolicyPreset,
    delete_preset,
    load_preset,
    preset_path,
    save_preset,
    set_applied,
)

DEVICE = "RTR-01@10.0.0.1"
KEY_INTERNET = f"{DEVICE}|internet"
KEY_SITE = f"{DEVICE}|site"


def _preset(**overrides: object) -> TrafficPolicyPreset:
    base = TrafficPolicyPreset(
        device_key=DEVICE,
        flow="internet",
        classifier="cls_internet",
        behavior="behavior_drop",
        policy="policy_internet",
        behavior_action="deny",
        acl_number=3000,
        interface="GigabitEthernet0/0/0",
        direction="outbound",
    )
    return replace(base, **overrides)  # type: ignore[arg-type]


def _record(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "device_key": DEVICE,
        "flow": "internet",
        "classifier": "cls_internet",
        "behavior": "behavior_drop",
        "policy": "policy_internet",
        "behavior_action": "deny",
        "acl_number": 3000,
        "interface": "GigabitEthernet0/0/0",
        "direction": "outbound",
        "applied": False,
        "preexisting": False,
    }
    base.update(overrides)
    return base


def _write(store: Path, payload: dict[str, object]) -> None:
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_record(
    store: Path, key: str = KEY_INTERNET, **overrides: object
) -> None:
    _write(store, {"version": 1, "presets": {key: _record(**overrides)}})


@pytest.fixture(autouse=True)
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isola o arquivo via ``HW_DATA_DIR`` (a API não recebe ``path``)."""
    monkeypatch.delenv("HUAWEI_MANAGER_DIR", raising=False)
    monkeypatch.setenv("HW_DATA_DIR", str(tmp_path))
    return tmp_path / "traffic_policy_presets.json"


class TestDataclass:
    def test_defaults(self) -> None:
        preset = _preset()
        assert preset.applied is False
        assert preset.preexisting is False

    def test_frozen(self) -> None:
        with pytest.raises(FrozenInstanceError):
            _preset().applied = True  # type: ignore[misc]


class TestPresetPath:
    def test_default_path_uses_home(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("HW_DATA_DIR", raising=False)
        monkeypatch.delenv("HUAWEI_MANAGER_DIR", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        path = preset_path()
        assert path == tmp_path / ".huawei_manager" / "traffic_policy_presets.json"
        assert path.parent.is_dir()

    def test_hw_data_dir_override(self, tmp_path: Path) -> None:
        assert preset_path() == tmp_path / "traffic_policy_presets.json"

    def test_huawei_manager_dir_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("HW_DATA_DIR", raising=False)
        monkeypatch.setenv("HUAWEI_MANAGER_DIR", str(tmp_path))
        assert preset_path() == tmp_path / "traffic_policy_presets.json"

    def test_hw_data_dir_takes_precedence(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HUAWEI_MANAGER_DIR", "/tmp/ignored-huawei-dir")
        assert preset_path() == tmp_path / "traffic_policy_presets.json"


class TestRoundTrip:
    def test_missing_file_returns_none(self, store: Path) -> None:
        assert load_preset(DEVICE, "internet") is None
        assert not store.exists()

    def test_save_then_load_all_fields(self, store: Path) -> None:
        save_preset(_preset(applied=True, preexisting=True))
        loaded = load_preset(DEVICE, "internet")
        assert loaded == _preset(applied=True, preexisting=True)

    def test_roundtrip_keeps_flags(self, store: Path) -> None:
        save_preset(_preset(applied=True, preexisting=True))
        loaded = load_preset(DEVICE, "internet")
        assert loaded is not None
        assert loaded.applied is True
        assert loaded.preexisting is True

    def test_internet_and_site_coexist(self, store: Path) -> None:
        save_preset(_preset(flow="internet", acl_number=3000, behavior_action="deny"))
        save_preset(_preset(flow="site", acl_number=3001, behavior_action="permit"))
        internet = load_preset(DEVICE, "internet")
        site = load_preset(DEVICE, "site")
        assert internet is not None and site is not None
        assert internet.acl_number == 3000
        assert internet.behavior_action == "deny"
        assert site.acl_number == 3001
        assert site.behavior_action == "permit"

    def test_two_devices_do_not_overwrite(self, store: Path) -> None:
        save_preset(_preset(device_key="A@1.1.1.1", acl_number=3000))
        save_preset(_preset(device_key="B@2.2.2.2", acl_number=3010))
        a = load_preset("A@1.1.1.1", "internet")
        b = load_preset("B@2.2.2.2", "internet")
        assert a is not None and b is not None
        assert a.acl_number == 3000
        assert b.acl_number == 3010
        assert load_preset("C@3.3.3.3", "internet") is None

    def test_overwrite_same_key(self, store: Path) -> None:
        save_preset(_preset(acl_number=3000))
        save_preset(_preset(acl_number=3011))
        loaded = load_preset(DEVICE, "internet")
        assert loaded is not None
        assert loaded.acl_number == 3011

    def test_save_creates_parent_dirs_and_uses_compound_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, store: Path
    ) -> None:
        nested = tmp_path / "deep" / "nested"
        monkeypatch.setenv("HW_DATA_DIR", str(nested))
        save_preset(_preset())
        target = nested / "traffic_policy_presets.json"
        assert target.exists()
        assert list(nested.glob("*.tmp")) == []
        data = json.loads(target.read_text(encoding="utf-8"))
        assert data["version"] == 1
        assert list(data["presets"]) == [KEY_INTERNET]
        assert data["presets"][KEY_INTERNET]["behavior_action"] == "deny"

    def test_empty_file_is_absent(self, store: Path) -> None:
        store.write_text("", encoding="utf-8")
        assert load_preset(DEVICE, "internet") is None


class TestDelete:
    def test_delete_existing(self, store: Path) -> None:
        save_preset(_preset())
        assert delete_preset(DEVICE, "internet") is True
        assert load_preset(DEVICE, "internet") is None

    def test_delete_missing_key_is_false(self, store: Path) -> None:
        assert delete_preset(DEVICE, "internet") is False

    def test_delete_missing_file_is_false(self, store: Path) -> None:
        save_preset(_preset())
        store.unlink()
        assert delete_preset(DEVICE, "internet") is False

    def test_delete_preserves_other_flow_and_device(self, store: Path) -> None:
        save_preset(_preset(flow="internet"))
        save_preset(_preset(flow="site"))
        save_preset(_preset(device_key="B@2.2.2.2", flow="internet"))
        assert delete_preset(DEVICE, "internet") is True
        assert load_preset(DEVICE, "internet") is None
        assert load_preset(DEVICE, "site") is not None
        assert load_preset("B@2.2.2.2", "internet") is not None


class TestSetApplied:
    def test_updates_only_applied_flag(self, store: Path) -> None:
        save_preset(_preset(preexisting=True, applied=False))
        set_applied(DEVICE, "internet", True)
        loaded = load_preset(DEVICE, "internet")
        assert loaded == _preset(preexisting=True, applied=True)

    def test_unapply(self, store: Path) -> None:
        save_preset(_preset(applied=True))
        set_applied(DEVICE, "internet", False)
        loaded = load_preset(DEVICE, "internet")
        assert loaded is not None
        assert loaded.applied is False

    def test_missing_preset_is_noop(self, store: Path) -> None:
        set_applied(DEVICE, "internet", True)
        assert load_preset(DEVICE, "internet") is None

    def test_does_not_touch_other_flow(self, store: Path) -> None:
        save_preset(_preset(flow="internet", applied=False))
        save_preset(_preset(flow="site", applied=False))
        set_applied(DEVICE, "site", True)
        internet = load_preset(DEVICE, "internet")
        site = load_preset(DEVICE, "site")
        assert internet is not None and site is not None
        assert internet.applied is False
        assert site.applied is True


class TestFailClosedJson:
    def test_corrupted_json_raises(self, store: Path) -> None:
        store.write_text("{ definitivamente não é json", encoding="utf-8")
        with pytest.raises(SdnValidationError, match="corrompido"):
            load_preset(DEVICE, "internet")

    def test_json_not_object_raises(self, store: Path) -> None:
        store.write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(SdnValidationError, match="objeto"):
            load_preset(DEVICE, "internet")

    def test_presets_not_dict_raises(self, store: Path) -> None:
        _write(store, {"version": 1, "presets": "oops"})
        with pytest.raises(SdnValidationError, match="presets"):
            load_preset(DEVICE, "internet")

    @pytest.mark.parametrize("version", [0, 2, 99, "1", None])
    def test_wrong_version_raises(self, store: Path, version: object) -> None:
        _write(store, {"version": version, "presets": {KEY_INTERNET: _record()}})
        with pytest.raises(SdnValidationError, match="versão"):
            load_preset(DEVICE, "internet")

    def test_missing_version_raises(self, store: Path) -> None:
        _write(store, {"presets": {KEY_INTERNET: _record()}})
        with pytest.raises(SdnValidationError, match="versão"):
            load_preset(DEVICE, "internet")

    def test_unknown_field_raises(self, store: Path) -> None:
        _write_record(store, campo_novo=1)
        with pytest.raises(SdnValidationError, match="desconhecidos"):
            load_preset(DEVICE, "internet")

    def test_missing_field_raises(self, store: Path) -> None:
        record = _record()
        del record["policy"]
        _write(store, {"version": 1, "presets": {KEY_INTERNET: record}})
        with pytest.raises(SdnValidationError, match="policy"):
            load_preset(DEVICE, "internet")

    def test_preset_not_object_raises(self, store: Path) -> None:
        _write(store, {"version": 1, "presets": {KEY_INTERNET: "oops"}})
        with pytest.raises(SdnValidationError, match="objeto"):
            load_preset(DEVICE, "internet")

    @pytest.mark.parametrize("field", ["acl_number", "flow", "applied", "preexisting"])
    @pytest.mark.parametrize("bad", ["3000", 1.5, [], None])
    def test_wrong_field_type_raises(
        self, store: Path, field: str, bad: object
    ) -> None:
        _write_record(store, **{field: bad})
        with pytest.raises(SdnValidationError):
            load_preset(DEVICE, "internet")

    def test_bool_is_not_acl_number(self, store: Path) -> None:
        _write_record(store, acl_number=True)
        with pytest.raises(SdnValidationError, match="acl_number"):
            load_preset(DEVICE, "internet")

    def test_key_does_not_match_record_raises(self, store: Path) -> None:
        _write_record(store, key=KEY_SITE, device_key=DEVICE, flow="internet")
        with pytest.raises(SdnValidationError, match="chave"):
            load_preset(DEVICE, "site")


class TestFailClosedValues:
    @pytest.mark.parametrize("flow", ["intranet", "", "INTERNET", 3])
    def test_invalid_flow_raises(self, store: Path, flow: object) -> None:
        _write_record(store, flow=flow)
        with pytest.raises(SdnValidationError, match="flow"):
            load_preset(DEVICE, "internet")

    @pytest.mark.parametrize("action", ["reject", "", "PERMIT", 1])
    def test_invalid_behavior_action_raises(
        self, store: Path, action: object
    ) -> None:
        _write_record(store, behavior_action=action)
        with pytest.raises(SdnValidationError, match="behavior_action"):
            load_preset(DEVICE, "internet")

    @pytest.mark.parametrize("direction", ["both", "", "IN", 2])
    def test_invalid_direction_raises(self, store: Path, direction: object) -> None:
        _write_record(store, direction=direction)
        with pytest.raises(SdnValidationError, match="dire"):
            load_preset(DEVICE, "internet")

    @pytest.mark.parametrize("number", [2999, 4000, 0, -1])
    def test_acl_number_out_of_range_raises(self, store: Path, number: int) -> None:
        _write_record(store, acl_number=number)
        with pytest.raises(SdnValidationError, match="faixa"):
            load_preset(DEVICE, "internet")

    @pytest.mark.parametrize("number", [3000, 3999])
    def test_acl_number_range_edges_ok(self, store: Path, number: int) -> None:
        _write_record(store, acl_number=number)
        loaded = load_preset(DEVICE, "internet")
        assert loaded is not None
        assert loaded.acl_number == number

    @pytest.mark.parametrize("field", ["classifier", "behavior", "policy"])
    @pytest.mark.parametrize(
        "name", ["9acl", "tem espaço", "x" * 33, "", "acl;drop", " acl"]
    )
    def test_invalid_vrp_name_raises(
        self, store: Path, field: str, name: str
    ) -> None:
        _write_record(store, **{field: name})
        with pytest.raises(SdnValidationError, match="VRP"):
            load_preset(DEVICE, "internet")

    @pytest.mark.parametrize("name", ["_acl", "A", "x" * 32, "cls-internet_01"])
    def test_valid_vrp_names(self, store: Path, name: str) -> None:
        _write_record(store, classifier=name)
        loaded = load_preset(DEVICE, "internet")
        assert loaded is not None
        assert loaded.classifier == name

    @pytest.mark.parametrize("device_key", ["", "   "])
    def test_empty_device_key_raises(self, store: Path, device_key: str) -> None:
        _write_record(store, device_key=device_key)
        with pytest.raises(SdnValidationError, match="device_key"):
            load_preset(DEVICE, "internet")

    @pytest.mark.parametrize("interface", ["", "   ", "Giga bitEthernet0/0/0"])
    def test_invalid_interface_raises(self, store: Path, interface: str) -> None:
        _write_record(store, interface=interface)
        with pytest.raises(SdnValidationError, match="interface"):
            load_preset(DEVICE, "internet")

    def test_blank_device_key_argument_raises(self) -> None:
        with pytest.raises(SdnValidationError, match="device_key"):
            load_preset("  ", "internet")

    def test_blank_flow_argument_raises(self) -> None:
        with pytest.raises(SdnValidationError, match="flow"):
            load_preset(DEVICE, "  ")


class TestValidationOnSave:
    @pytest.mark.parametrize(
        "overrides",
        [
            {"flow": "site-x"},
            {"behavior_action": "reject"},
            {"direction": "sideways"},
            {"acl_number": 2999},
            {"classifier": "9cls"},
            {"device_key": "  "},
            {"interface": ""},
        ],
    )
    def test_invalid_preset_is_not_persisted(
        self, store: Path, overrides: dict[str, object]
    ) -> None:
        with pytest.raises(SdnValidationError):
            save_preset(_preset(**overrides))
        assert not store.exists()
