"""Testes para vnf_crypto — funções puras de criptografia Fernet para VNFs.

Testa criptografia real (sem mock de cryptography) usando chaves Fernet
geradas em runtime. Config controlada via monkeypatch em _config._s.
"""
from __future__ import annotations

import base64
import hashlib
from unittest.mock import MagicMock

import pytest
from cryptography.fernet import Fernet

from huawei_manager.vnf_crypto import (
    _decrypt_val,
    _encrypt_val,
    _get_fernet_decrypt,
    _get_fernet_encrypt,
)


# ── Helpers ──────────────────────────────────────────────────────────────

_VALID_KEY = Fernet.generate_key().decode()


def _fake_config(key: str, default: str = "") -> str:
    """Retorna chave válida para qualquer lookup."""
    if key == "VNF_ENCRYPT_KEY":
        return _VALID_KEY
    if key == "AUDIT_HMAC_KEY":
        return "test-hmac-secret"
    return default


def _no_config(key: str, default: str = "") -> str:
    """Retorna vazio — nenhuma chave configurada."""
    return ""


def _invalid_config(key: str, default: str = "") -> str:
    """Retorna valor inválido para Fernet (não é base64 válido)."""
    if key == "VNF_ENCRYPT_KEY":
        return "not-a-valid-fernet-key!!!"
    return ""


def _hmac_only_config(key: str, default: str = "") -> str:
    """Retorna apenas AUDIT_HMAC_KEY (fallback HMAC)."""
    if key == "VNF_ENCRYPT_KEY":
        return ""
    if key == "AUDIT_HMAC_KEY":
        return "hmac-secret-key"
    return default


# ══════════════════════════════════════════════════════════════════════════
#  _get_fernet_encrypt
# ══════════════════════════════════════════════════════════════════════════


class TestGetFernetEncrypt:
    """_get_fernet_encrypt retorna Fernet para criptografia."""

    def test_valid_key_returns_fernet(self, monkeypatch):
        monkeypatch.setattr("huawei_manager.vnf_crypto._config._s", _fake_config)
        result = _get_fernet_encrypt()
        assert isinstance(result, Fernet)

    def test_missing_key_raises_valueerror(self, monkeypatch):
        monkeypatch.setattr("huawei_manager.vnf_crypto._config._s", _no_config)
        with pytest.raises(ValueError, match="VNF_ENCRYPT_KEY"):
            _get_fernet_encrypt()

    def test_invalid_key_propagates_error(self, monkeypatch):
        monkeypatch.setattr("huawei_manager.vnf_crypto._config._s", _invalid_config)
        with pytest.raises(Exception):
            _get_fernet_encrypt()


# ══════════════════════════════════════════════════════════════════════════
#  _get_fernet_decrypt
# ══════════════════════════════════════════════════════════════════════════


class TestGetFernetDecrypt:
    """_get_fernet_decrypt retorna Fernet para decriptografia."""

    def test_valid_key_returns_fernet(self, monkeypatch):
        monkeypatch.setattr("huawei_manager.vnf_crypto._config._s", _fake_config)
        result = _get_fernet_decrypt()
        assert isinstance(result, Fernet)

    def test_hmac_fallback_when_no_encrypt_key(self, monkeypatch):
        monkeypatch.setattr("huawei_manager.vnf_crypto._config._s", _hmac_only_config)
        result = _get_fernet_decrypt()
        assert isinstance(result, Fernet)

    def test_returns_none_when_no_keys(self, monkeypatch):
        monkeypatch.setattr("huawei_manager.vnf_crypto._config._s", _no_config)
        result = _get_fernet_decrypt()
        assert result is None


# ══════════════════════════════════════════════════════════════════════════
#  _encrypt_val
# ══════════════════════════════════════════════════════════════════════════


class TestEncryptVal:
    """_encrypt_val criptografa texto com VNF_ENCRYPT_KEY."""

    def test_normal_text_returns_encrypted(self, monkeypatch):
        monkeypatch.setattr("huawei_manager.vnf_crypto._config._s", _fake_config)
        result = _encrypt_val("hello world")
        assert result != "hello world"
        assert isinstance(result, str)

    def test_missing_key_returns_plaintext(self, monkeypatch):
        monkeypatch.setattr("huawei_manager.vnf_crypto._config._s", _no_config)
        result = _encrypt_val("sensitive-data")
        assert result == "sensitive-data"

    def test_encryption_roundtrip(self, monkeypatch):
        monkeypatch.setattr("huawei_manager.vnf_crypto._config._s", _fake_config)
        original = "my-secret-password-123"
        encrypted = _encrypt_val(original)
        decrypted = _decrypt_val(encrypted)
        assert decrypted == original

    def test_different_inputs_produce_different_outputs(self, monkeypatch):
        monkeypatch.setattr("huawei_manager.vnf_crypto._config._s", _fake_config)
        a = _encrypt_val("input-a")
        b = _encrypt_val("input-b")
        assert a != b


# ══════════════════════════════════════════════════════════════════════════
#  _decrypt_val
# ══════════════════════════════════════════════════════════════════════════


class TestDecryptVal:
    """_decrypt_val descriptografa valor com fallback."""

    def test_roundtrip_encrypt_decrypt(self, monkeypatch):
        monkeypatch.setattr("huawei_manager.vnf_crypto._config._s", _fake_config)
        original = "admin-password-2026"
        encrypted = _encrypt_val(original)
        assert _decrypt_val(encrypted) == original

    def test_none_fernet_returns_original(self, monkeypatch):
        monkeypatch.setattr("huawei_manager.vnf_crypto._config._s", _no_config)
        assert _decrypt_val("some-ciphertext") == "some-ciphertext"

    def test_invalid_ciphertext_returns_original(self, monkeypatch):
        monkeypatch.setattr("huawei_manager.vnf_crypto._config._s", _fake_config)
        result = _decrypt_val("this-is-not-valid-fernet-data")
        assert result == "this-is-not-valid-fernet-data"

    def test_hmac_fallback_decrypts(self, monkeypatch):
        """Se dados foram criptografados com HMAC key, decrypt deve funcionar."""
        monkeypatch.setattr("huawei_manager.vnf_crypto._config._s", _hmac_only_config)
        # Criptografa com HMAC key
        hmac_fernet = _get_fernet_decrypt()
        ciphertext = hmac_fernet.encrypt(b"test-value").decode()
        # Decriptografa com a mesma config
        assert _decrypt_val(ciphertext) == "test-value"
