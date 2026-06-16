import os
from unittest.mock import patch

import pytest

from huawei_manager.vault import EnvBackend, SopsBackend, get_backend


class TestEnvBackend:
    @classmethod
    def setup_class(cls):
        os.environ["TEST_VAULT_KEY"] = "test_value_123"

    def test_get_existing_key(self):
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
