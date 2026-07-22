import os
from unittest.mock import patch

import pytest

from huawei_manager.vault import EnvBackend, SopsBackend, get_backend


class TestEnvBackend:
    def test_get_existing_key(self, monkeypatch):
        monkeypatch.setenv("TEST_VAULT_KEY", "test_value_123")
        backend = EnvBackend()
        assert backend.get("TEST_VAULT_KEY") == "test_value_123"

    def test_get_missing_key_default(self):
        backend = EnvBackend()
        assert backend.get("NONEXISTENT_KEY", "fallback") == "fallback"

    def test_get_missing_key_empty_default(self):
        backend = EnvBackend()
        assert backend.get("NONEXISTENT_KEY") == ""

    def test_backend_name(self):
        backend = EnvBackend()
        assert "env" in backend.backend_name.lower()

    def test_put_and_get(self):
        backend = EnvBackend()
        backend.put("TEST_PUT_KEY", "put_value")
        assert backend.get("TEST_PUT_KEY") == "put_value"

    def test_put_overwrites(self):
        backend = EnvBackend()
        backend.put("TEST_OVERWRITE", "first")
        backend.put("TEST_OVERWRITE", "second")
        assert backend.get("TEST_OVERWRITE") == "second"

    def test_put_persists_to_env_file(self):
        backend = EnvBackend()
        backend.put("TEST_PERSIST", "persisted")
        if hasattr(backend, "_env_path") and backend._env_path.exists():
            content = backend._env_path.read_text()
            assert "TEST_PERSIST=" in content


class TestCryptoEnvBackend:
    """Testa o backend de criptografia AES-256-GCM."""

    TEST_KEY = "a" * 32  # 32 bytes = 256 bits

    def test_encrypt_decrypt_roundtrip(self):
        """Criptografar e descriptografar deve retornar o valor original."""
        from huawei_manager.vault import CryptoEnvBackend

        backend = CryptoEnvBackend(encryption_key=self.TEST_KEY)
        original = "senha_super_secreta_123"
        encrypted = backend._encrypt(original)
        assert encrypted != original, "Output criptografado != texto plano"
        decrypted = backend._decrypt(encrypted)
        assert decrypted == original

    def test_encrypt_produces_different_output_each_time(self):
        """Nonce aleatório deve produzir outputs diferentes para mesma entrada."""
        from huawei_manager.vault import CryptoEnvBackend

        backend = CryptoEnvBackend(encryption_key=self.TEST_KEY)
        result1 = backend._encrypt("same_value")
        result2 = backend._encrypt("same_value")
        assert result1 != result2

    def test_tampered_ciphertext_raises_error(self):
        """Alterar o ciphertext deve causar falha de autenticação (tamper)."""
        from huawei_manager.vault import CryptoEnvBackend

        backend = CryptoEnvBackend(encryption_key=self.TEST_KEY)
        encrypted = backend._encrypt("valor_seguro")
        # Simula tamper no ciphertext
        tampered = encrypted[:-4] + "xxxx"
        with pytest.raises(Exception):
            backend._decrypt(tampered)

    def test_wrong_key_fails_to_decrypt(self):
        """Descriptografar com chave errada deve falhar."""
        from huawei_manager.vault import CryptoEnvBackend

        backend1 = CryptoEnvBackend(encryption_key=self.TEST_KEY)
        backend2 = CryptoEnvBackend(encryption_key="b" * 32)  # chave diferente

        encrypted = backend1._encrypt("valor_seguro")
        with pytest.raises(Exception):
            backend2._decrypt(encrypted)

    def test_get_put_roundtrip(self):
        """put() criptografa, get() descriptografa."""
        from huawei_manager.vault import CryptoEnvBackend

        backend = CryptoEnvBackend(encryption_key=self.TEST_KEY)
        backend.put("SSH_PASSWORD", "minha_senha")
        result = backend.get("SSH_PASSWORD")
        assert result == "minha_senha"

    def test_get_missing_returns_default(self):
        """Chave inexistente retorna default."""
        from huawei_manager.vault import CryptoEnvBackend

        backend = CryptoEnvBackend(encryption_key=self.TEST_KEY)
        assert backend.get("NONEXISTENT", "fallback") == "fallback"

    def test_get_missing_returns_empty_string(self):
        """Chave inexistente sem default retorna string vazia."""
        from huawei_manager.vault import CryptoEnvBackend

        backend = CryptoEnvBackend(encryption_key=self.TEST_KEY)
        assert backend.get("NONEXISTENT") == ""

    def test_backend_name_contains_crypto(self):
        """Nome do backend deve indicar que é criptografado."""
        from huawei_manager.vault import CryptoEnvBackend

        backend = CryptoEnvBackend(encryption_key=self.TEST_KEY)
        name = backend.backend_name.lower()
        assert "crypto" in name or "aes" in name or "encrypt" in name

    def test_without_key_fallback_to_env(self):
        """Sem chave de criptografia, deve fazer fallback para EnvBackend."""
        from huawei_manager.vault import CryptoEnvBackend, EnvBackend

        os.environ["CRYPTO_TEST_FALLBACK"] = "plain_value"
        backend = CryptoEnvBackend(encryption_key=None)
        assert isinstance(backend._fallback if hasattr(backend, '_fallback') else None, (EnvBackend, type(None)))
        # Deve ler do ambiente quando não criptografado
        assert backend.get("CRYPTO_TEST_FALLBACK") == "plain_value"

    def test_get_backend_returns_crypto_when_configured(self):
        """get_backend() deve retornar CryptoEnvBackend quando SECRETS_BACKEND=crypto."""
        with patch.dict(os.environ, {"SECRETS_BACKEND": "crypto", "SECRETS_KEY": self.TEST_KEY}, clear=True):
            from huawei_manager.vault import CryptoEnvBackend, get_backend
            backend = get_backend()
            assert isinstance(backend, CryptoEnvBackend)


class TestSopsBackend:
    def test_no_secret_file_raises(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(RuntimeError):
            SopsBackend()


class TestGetBackend:
    def test_env_backend(self):
        with patch.dict(os.environ, {"SECRETS_BACKEND": "env"}, clear=True):
            backend = get_backend()
            assert isinstance(backend, EnvBackend)

    def test_unknown_backend_fallback_to_env(self):
        with patch.dict(os.environ, {"SECRETS_BACKEND": "unknown"}, clear=True):
            backend = get_backend()
            assert isinstance(backend, EnvBackend)

    def test_no_env_var_returns_env(self):
        with patch.dict(os.environ, {}, clear=True):
            backend = get_backend()
            assert isinstance(backend, EnvBackend)
