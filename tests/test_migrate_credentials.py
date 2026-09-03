"""test_migrate_credentials.py — Tests for credential migration script."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add setup/ to path so we can import migrate_credentials
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "setup"))

import migrate_credentials


@pytest.fixture()
def legacy_env_file(tmp_path: Path) -> Path:
    """Create a temporary legacy .env file with sample credentials."""
    env_path = tmp_path / ".env"
    env_path.write_text(
        "ROUTER_HOST=192.168.1.100\n"
        "ROUTER_PORT=22\n"
        "ROUTER_USERNAME=admin\n"
        "ROUTER_PASSWORD=secret123\n"
        "ROUTER_SSH_KEY=~/.ssh/huawei_ed25519\n"
        "ROUTER_HOSTKEY_VERIFY=strict\n"
        "SECRETS_BACKEND=env\n"
        "VNF_ENCRYPT_KEY=\n",
        encoding="utf-8",
    )
    return env_path


class TestGenerateKeys:
    """Tests for key generation functions."""

    def test_generate_vnf_encrypt_key_length(self) -> None:
        key = migrate_credentials.generate_vnf_encrypt_key()
        assert len(key) == 64  # 32 bytes hex = 64 chars

    def test_generate_vnf_encrypt_key_unique(self) -> None:
        keys = {migrate_credentials.generate_vnf_encrypt_key() for _ in range(10)}
        assert len(keys) == 10  # All unique

    def test_generate_secrets_key_length(self) -> None:
        key = migrate_credentials.generate_secrets_key()
        # base64url encoded 32 bytes = 44 chars
        assert len(key) > 0


class TestReadLegacyEnv:
    """Tests for reading legacy .env files."""

    def test_read_legacy_env_valid(self, legacy_env_file: Path) -> None:
        with patch.object(migrate_credentials, "LEGACY_ENV_PATH", legacy_env_file):
            env_vars = migrate_credentials.read_legacy_env()
        assert env_vars["ROUTER_HOST"] == "192.168.1.100"
        assert env_vars["ROUTER_PORT"] == "22"
        assert env_vars["ROUTER_USERNAME"] == "admin"
        assert env_vars["ROUTER_PASSWORD"] == "secret123"

    def test_read_legacy_env_missing(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent.env"
        with patch.object(migrate_credentials, "LEGACY_ENV_PATH", missing):
            env_vars = migrate_credentials.read_legacy_env()
        assert env_vars == {}

    def test_read_legacy_env_skips_comments(self, tmp_path: Path) -> None:
        env_path = tmp_path / ".env"
        env_path.write_text(
            "# This is a comment\n"
            "ROUTER_HOST=10.0.0.1\n"
            "# Another comment\n",
            encoding="utf-8",
        )
        with patch.object(migrate_credentials, "LEGACY_ENV_PATH", env_path):
            env_vars = migrate_credentials.read_legacy_env()
        assert env_vars == {"ROUTER_HOST": "10.0.0.1"}


class TestEnsureUserConfigDir:
    """Tests for config directory creation."""

    def test_creates_directory(self, tmp_path: Path) -> None:
        config_dir = tmp_path / ".config" / "huawei-manager"
        with patch.object(migrate_credentials, "USER_CONFIG_DIR", config_dir):
            migrate_credentials.ensure_user_config_dir(dry_run=False)
        assert config_dir.exists()

    def test_dry_run_no_creation(self, tmp_path: Path) -> None:
        config_dir = tmp_path / ".config" / "huawei-manager"
        with patch.object(migrate_credentials, "USER_CONFIG_DIR", config_dir):
            migrate_credentials.ensure_user_config_dir(dry_run=True)
        assert not config_dir.exists()


class TestCopyEnvToUserConfig:
    """Tests for copying .env to user config location."""

    def test_copies_env_file(self, tmp_path: Path) -> None:
        user_env = tmp_path / "config" / ".env"
        env_vars: dict[str, str] = {
            "ROUTER_HOST": "10.0.0.1",
            "ROUTER_PORT": "22",
        }
        with patch.object(migrate_credentials, "USER_ENV_PATH", user_env):
            migrate_credentials.copy_env_to_user_config(env_vars, dry_run=False)
        assert user_env.exists()
        content = user_env.read_text(encoding="utf-8")
        assert "ROUTER_HOST=10.0.0.1" in content

    def test_skips_if_exists(self, tmp_path: Path) -> None:
        user_env = tmp_path / ".env"
        user_env.write_text("existing", encoding="utf-8")
        with patch.object(migrate_credentials, "USER_ENV_PATH", user_env):
            migrate_credentials.copy_env_to_user_config({"KEY": "val"}, dry_run=False)
        assert user_env.read_text(encoding="utf-8") == "existing"


class TestGenerateMissingKeys:
    """Tests for automatic key generation."""

    def test_generates_missing_vnf_key(self) -> None:
        env_vars: dict[str, str] = {"ROUTER_HOST": "10.0.0.1"}
        result = migrate_credentials.generate_missing_keys(env_vars, dry_run=False)
        assert result["VNF_ENCRYPT_KEY"] != ""
        assert len(result["VNF_ENCRYPT_KEY"]) == 64

    def test_preserves_existing_vnf_key(self) -> None:
        existing = "a" * 64
        env_vars: dict[str, str] = {"VNF_ENCRYPT_KEY": existing}
        result = migrate_credentials.generate_missing_keys(env_vars, dry_run=False)
        assert result["VNF_ENCRYPT_KEY"] == existing

    def test_generates_secrets_key_for_crypto_backend(self) -> None:
        env_vars: dict[str, str] = {"SECRETS_BACKEND": "crypto"}
        result = migrate_credentials.generate_missing_keys(env_vars, dry_run=False)
        assert result["SECRETS_KEY"] != ""

    def test_skips_secrets_key_for_env_backend(self) -> None:
        env_vars: dict[str, str] = {"SECRETS_BACKEND": "env"}
        result = migrate_credentials.generate_missing_keys(env_vars, dry_run=False)
        assert "SECRETS_KEY" not in result


class TestMigrateDeviceToDb:
    """Tests for device DB migration."""

    def test_skips_when_no_host(self) -> None:
        with patch("builtins.print") as mock_print:
            migrate_credentials.migrate_device_to_db({}, dry_run=False)
        # Should print warning about missing ROUTER_HOST
        mock_print.assert_called()
        call_args = [call[0][0] for call in mock_print.call_args_list]
        assert any("ROUTER_HOST not set" in msg for msg in call_args)
