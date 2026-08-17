"""Testes para vnf_inventory — I/O do inventário JSON com fail-closed.

Cobre load/save com e sem VNF_ENCRYPT_KEY. Todos os testes usam
arquivos temporários; config controlada via monkeypatch em _config._s.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import pytest
from cryptography.fernet import Fernet

from huawei_manager.device_inventory import (
    DEVICE_INVENTORY_FILE,
    load_devices,
    save_devices,
)
from huawei_manager.device_models import Device

_VALID_KEY = Fernet.generate_key().decode()


def _with_key(key: str, default: str = "") -> str:
    if key == "VNF_ENCRYPT_KEY":
        return _VALID_KEY
    if key == "AUDIT_HMAC_KEY":
        return "test-hmac-secret"
    return default


def _no_key(key: str, default: str = "") -> str:
    return ""


def _make_device(**overrides: Any) -> Device:
    defaults: dict[str, Any] = dict(
        id="dev-001",
        name="gw-01",
        host="10.0.0.1",
        port=22,
        type="ROUTER",
        username="admin",
        password="secret",
    )
    defaults.update(overrides)
    return Device(**defaults)


def _tmp_file() -> str:
    """Cria um caminho temporário (não existente) para o inventário."""
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.unlink(path)
    return path


# ══════════════════════════════════════════════════════════════════════════
#  Load
# ══════════════════════════════════════════════════════════════════════════


class TestLoad:
    def test_missing_file_returns_empty(self):
        assert load_devices("/nonexistent/does-not-exist.json") == []

    def test_empty_object_returns_empty(self):
        path = _tmp_file()
        Path(path).write_text("{}", encoding="utf-8")
        assert load_devices(path) == []

    def test_roundtrip_with_key(self, monkeypatch):
        monkeypatch.setattr("huawei_manager.device_crypto._config._s", _with_key)
        path = _tmp_file()
        devices = [_make_device(password="super-secret")]
        save_devices(devices, path)
        loaded = load_devices(path)
        assert len(loaded) == 1
        assert loaded[0].password == "super-secret"

    def test_load_without_key_plaintext_raises(self, monkeypatch):
        """C.6.1 — password em plaintext sem chave → ValueError (fail-closed)."""
        monkeypatch.setattr("huawei_manager.device_crypto._config._s", _no_key)
        path = _tmp_file()
        Path(path).write_text(
            json.dumps({"devices": [_make_device().__dict__]}), encoding="utf-8"
        )
        with pytest.raises(ValueError):
            load_devices(path)

    def test_no_password_loads_without_key(self, monkeypatch):
        monkeypatch.setattr("huawei_manager.device_crypto._config._s", _no_key)
        path = _tmp_file()
        device = _make_device(password="")
        Path(path).write_text(
            json.dumps({"devices": [device.__dict__]}), encoding="utf-8"
        )
        loaded = load_devices(path)
        assert loaded[0].password == ""


# ══════════════════════════════════════════════════════════════════════════
#  Save
# ══════════════════════════════════════════════════════════════════════════


class TestSave:
    def test_save_without_key_password_raises(self, monkeypatch):
        """C.6.1 — nunca grava password em plaintext; sem chave → ValueError."""
        monkeypatch.setattr("huawei_manager.device_crypto._config._s", _no_key)
        path = _tmp_file()
        with pytest.raises(ValueError):
            save_devices([_make_device()], path)
        # R4 — nada gravado em caso de falha
        assert not Path(path).exists()

    def test_save_without_key_no_password_succeeds(self, monkeypatch):
        monkeypatch.setattr("huawei_manager.device_crypto._config._s", _no_key)
        path = _tmp_file()
        save_devices([_make_device(password="")], path)
        assert Path(path).exists()
        loaded = load_devices(path)
        assert len(loaded) == 1
        assert loaded[0].password == ""

    def test_save_encrypts_password_on_disk(self, monkeypatch):
        monkeypatch.setattr("huawei_manager.device_crypto._config._s", _with_key)
        path = _tmp_file()
        save_devices([_make_device(password="super-secret")], path)
        raw = Path(path).read_text(encoding="utf-8")
        assert "super-secret" not in raw
        data = json.loads(raw)
        assert data["devices"][0]["password"] != "super-secret"


# ══════════════════════════════════════════════════════════════════════════
#  Constantes
# ══════════════════════════════════════════════════════════════════════════


class TestConstants:
    def test_inventory_file_name(self):
        assert DEVICE_INVENTORY_FILE == "vnf_inventory.json"


# ══════════════════════════════════════════════════════════════════════════
#  Bug #1: JSON key mismatch — legacy "vnfs" vs current "devices"
# ══════════════════════════════════════════════════════════════════════════


class TestLegacyVnfsKey:
    """load_devices() should read legacy 'vnfs' key for backward compat."""

    def test_load_reads_devices_key(self):
        path = _tmp_file()
        Path(path).write_text(
            json.dumps({"devices": [_make_device(password="").__dict__]}), encoding="utf-8"
        )
        loaded = load_devices(path)
        assert len(loaded) == 1

    def test_load_reads_legacy_vnfs_key(self):
        path = _tmp_file()
        Path(path).write_text(
            json.dumps({"vnfs": [_make_device(password="").__dict__]}), encoding="utf-8"
        )
        loaded = load_devices(path)
        assert len(loaded) == 1
