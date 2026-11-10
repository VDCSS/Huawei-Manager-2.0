"""Testes para vnf_crypto — funções puras de criptografia Fernet para VNFs.

Testa criptografia real (sem mock de cryptography) usando chaves Fernet
geradas em runtime. Config controlada via monkeypatch em _config._s.
"""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet, InvalidToken

from huawei_manager.device_crypto import (
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
    """Retorna apenas AUDIT_HMAC_KEY (não deve servir para decriptar)."""
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
        monkeypatch.setattr("huawei_manager.device_crypto._config._s", _fake_config)
        result = _get_fernet_encrypt()
        assert isinstance(result, Fernet)

    def test_missing_key_raises_valueerror(self, monkeypatch):
        monkeypatch.setattr("huawei_manager.device_crypto._config._s", _no_config)
        with pytest.raises(ValueError, match="VNF_ENCRYPT_KEY"):
            _get_fernet_encrypt()

    def test_invalid_key_propagates_error(self, monkeypatch):
        monkeypatch.setattr("huawei_manager.device_crypto._config._s", _invalid_config)
        with pytest.raises(Exception):
            _get_fernet_encrypt()


# ══════════════════════════════════════════════════════════════════════════
#  _get_fernet_decrypt
# ══════════════════════════════════════════════════════════════════════════


class TestGetFernetDecrypt:
    """_get_fernet_decrypt retorna Fernet apenas com VNF_ENCRYPT_KEY."""

    def test_valid_key_returns_fernet(self, monkeypatch):
        monkeypatch.setattr("huawei_manager.device_crypto._config._s", _fake_config)
        result = _get_fernet_decrypt()
        assert isinstance(result, Fernet)

    def test_audit_key_not_used_when_no_encrypt_key(self, monkeypatch):
        """AUDIT_HMAC_KEY não serve como chave de decriptação (fail-closed)."""
        monkeypatch.setattr("huawei_manager.device_crypto._config._s", _hmac_only_config)
        result = _get_fernet_decrypt()
        assert result is None

    def test_returns_none_when_no_keys(self, monkeypatch):
        monkeypatch.setattr("huawei_manager.device_crypto._config._s", _no_config)
        result = _get_fernet_decrypt()
        assert result is None


# ══════════════════════════════════════════════════════════════════════════
#  _encrypt_val
# ══════════════════════════════════════════════════════════════════════════


class TestEncryptVal:
    """_encrypt_val criptografa texto com VNF_ENCRYPT_KEY — fail-closed."""

    def test_normal_text_returns_encrypted(self, monkeypatch):
        monkeypatch.setattr("huawei_manager.device_crypto._config._s", _fake_config)
        result = _encrypt_val("hello world")
        assert result != "hello world"
        assert isinstance(result, str)

    def test_missing_key_raises_valueerror(self, monkeypatch):
        monkeypatch.setattr("huawei_manager.device_crypto._config._s", _no_config)
        with pytest.raises(ValueError, match="VNF_ENCRYPT_KEY"):
            _encrypt_val("sensitive-data")

    def test_encryption_roundtrip(self, monkeypatch):
        monkeypatch.setattr("huawei_manager.device_crypto._config._s", _fake_config)
        original = "my-secret-password-123"
        encrypted = _encrypt_val(original)
        decrypted = _decrypt_val(encrypted)
        assert decrypted == original

    def test_different_inputs_produce_different_outputs(self, monkeypatch):
        monkeypatch.setattr("huawei_manager.device_crypto._config._s", _fake_config)
        a = _encrypt_val("input-a")
        b = _encrypt_val("input-b")
        assert a != b


# ══════════════════════════════════════════════════════════════════════════
#  _decrypt_val
# ══════════════════════════════════════════════════════════════════════════


class TestDecryptVal:
    """_decrypt_val descriptografa valor — fail-closed simétrico."""

    def test_roundtrip_encrypt_decrypt(self, monkeypatch):
        monkeypatch.setattr("huawei_manager.device_crypto._config._s", _fake_config)
        original = "admin-password-2026"
        encrypted = _encrypt_val(original)
        assert _decrypt_val(encrypted) == original

    def test_no_key_raises_valueerror(self, monkeypatch):
        monkeypatch.setattr("huawei_manager.device_crypto._config._s", _no_config)
        with pytest.raises(ValueError, match="VNF_ENCRYPT_KEY"):
            _decrypt_val("some-ciphertext")

    def test_invalid_ciphertext_raises(self, monkeypatch):
        monkeypatch.setattr("huawei_manager.device_crypto._config._s", _fake_config)
        with pytest.raises(InvalidToken):
            _decrypt_val("this-is-not-valid-fernet-data")

    def test_audit_key_not_used_for_decrypt(self, monkeypatch):
        """Dados cifrados com ferramentas HMAC não decriptam mais (C.6.1)."""
        monkeypatch.setattr("huawei_manager.device_crypto._config._s", _hmac_only_config)
        with pytest.raises(ValueError, match="VNF_ENCRYPT_KEY"):
            _decrypt_val("some-ciphertext")


# ══════════════════════════════════════════════════════════════════════════
#  Interação com vnf_inventory (fail-closed na escrita)
# ══════════════════════════════════════════════════════════════════════════


class TestFailClosedIntegration:
    """C.6.1 — nunca degrada segredo para plaintext, em nenhuma direção."""

    def test_plaintext_never_returned_on_encrypt_failure(self, monkeypatch):
        monkeypatch.setattr("huawei_manager.device_crypto._config._s", _no_config)
        with pytest.raises(ValueError):
            _encrypt_val("top-secret")

    def test_ciphertext_never_returned_as_plaintext(self, monkeypatch):
        monkeypatch.setattr("huawei_manager.device_crypto._config._s", _fake_config)
        encrypted = _encrypt_val("top-secret")
        monkeypatch.setattr("huawei_manager.device_crypto._config._s", _no_config)
        with pytest.raises(ValueError):
            _decrypt_val(encrypted)


# ═══════════════════════════════════════════════════════════════════════════
#  ensure_encrypt_key — auto-geração no primeiro boot
# ═══════════════════════════════════════════════════════════════════════════


class TestEnsureEncryptKey:
    """ensure_encrypt_key() gera, persiste e é idempotente."""

    def test_generates_and_persists_when_missing(self, monkeypatch):
        from huawei_manager.device_crypto import ensure_encrypt_key

        captured = {}

        def fake_s(key: str, default: str = "") -> str:
            return ""

        mock_secrets = type("MockSecrets", (), {"put": lambda self, k, v: captured.update({"key": k, "value": v})})()

        monkeypatch.setattr("huawei_manager.device_crypto._config._s", fake_s)
        monkeypatch.setattr("huawei_manager.device_crypto._config._secrets", mock_secrets)

        key = ensure_encrypt_key()

        assert isinstance(key, str)
        assert len(key) > 0
        # Fernet key é base64 url-safe de 32 bytes = 44 chars
        assert len(key) == 44
        assert captured["key"] == "VNF_ENCRYPT_KEY"
        assert captured["value"] == key

    def test_idempotent_returns_existing(self, monkeypatch):
        from huawei_manager.device_crypto import ensure_encrypt_key

        existing_key = Fernet.generate_key().decode()

        def fake_s(key: str, default: str = "") -> str:
            if key == "VNF_ENCRYPT_KEY":
                return existing_key
            return ""

        put_called = {"called": False}

        mock_secrets = type("MockSecrets", (), {"put": lambda self, k, v: put_called.update({"called": True})})()

        monkeypatch.setattr("huawei_manager.device_crypto._config._s", fake_s)
        monkeypatch.setattr("huawei_manager.device_crypto._config._secrets", mock_secrets)

        key = ensure_encrypt_key()

        assert key == existing_key
        assert not put_called["called"]

    def test_put_failure_logs_warning_and_raises(self, monkeypatch, caplog):
        from huawei_manager.device_crypto import ensure_encrypt_key

        def fake_s(key: str, default: str = "") -> str:
            return ""

        mock_secrets = type("MockSecrets", (), {"put": lambda self, k, v: (_ for _ in ()).throw(RuntimeError("backend unavailable"))})()

        monkeypatch.setattr("huawei_manager.device_crypto._config._s", fake_s)
        monkeypatch.setattr("huawei_manager.device_crypto._config._secrets", mock_secrets)

        with pytest.raises(RuntimeError, match="backend unavailable"):
            ensure_encrypt_key()

        # Warning deve ter sido logado
        assert any("VNF_ENCRYPT_KEY gerada mas nao persistida" in r.message for r in caplog.records)
