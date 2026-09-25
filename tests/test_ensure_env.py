"""test_ensure_env.py — Tests for setup/ensure_env.py (key generation on install)."""

from __future__ import annotations

import base64
import sys
from pathlib import Path

import pytest

# Add setup/ to path so we can import ensure_env (same pattern as the removed
# test_migrate_credentials.py)
SETUP_DIR = Path(__file__).resolve().parent.parent / "setup"
sys.path.insert(0, str(SETUP_DIR))

import ensure_env  # noqa: E402


# ─── Key generation formats ─────────────────────────────────────────


def test_generate_vnf_encrypt_key_is_valid_fernet_format() -> None:
    """VNF_ENCRYPT_KEY deve ser 44 chars urlsafe base64 (formato Fernet)."""
    key = ensure_env.generate_vnf_encrypt_key()
    assert len(key) == 44
    decoded = base64.urlsafe_b64decode(key + "==")
    assert len(decoded) == 32


def test_generate_vnf_encrypt_key_unique() -> None:
    keys = {ensure_env.generate_vnf_encrypt_key() for _ in range(10)}
    assert len(keys) == 10


def test_generate_audit_hmac_key_is_64_hex() -> None:
    key = ensure_env.generate_audit_hmac_key()
    assert len(key) == 64
    assert all(c in "0123456789abcdef" for c in key)


def test_generate_secrets_key_is_44_urlsafe_base64() -> None:
    key = ensure_env.generate_secrets_key()
    assert len(key) == 44
    decoded = base64.urlsafe_b64decode(key + "==")
    assert len(decoded) == 32


def test_vnf_encrypt_key_accepted_by_fernet() -> None:
    """A chave gerada deve ser aceita por cryptography.fernet.Fernet (device_crypto)."""
    pytest.importorskip("cryptography")
    from cryptography.fernet import Fernet

    key = ensure_env.generate_vnf_encrypt_key()
    f = Fernet(key.encode())
    token = f.encrypt(b"segredo")
    assert f.decrypt(token) == b"segredo"


# ─── ensure_env() behavior ──────────────────────────────────────────


def test_ensure_env_creates_env_from_scratch(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    report = ensure_env.ensure_env(env_path)

    assert report["created"] is True
    assert set(report["generated"]) == set(ensure_env.MANAGED_KEYS)
    assert report["kept"] == []

    content = env_path.read_text(encoding="utf-8")
    # Chaves gerenciadas presentes
    for key in ensure_env.MANAGED_KEYS:
        assert f"{key}=" in content, key
    # Template do app preservado (compatibilidade de leitura com _config.py)
    for template_key in ("ROUTER_SSH_KEY=", "ROUTER_HOSTKEY_VERIFY=strict",
                         "HW_ADAPTIVE_POLLING=0", "SSH_TIMEOUT=90", "SECRETS_BACKEND=env"):
        assert template_key in content, template_key


def test_ensure_env_is_idempotent(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    ensure_env.ensure_env(env_path)
    before = env_path.read_text(encoding="utf-8")

    report = ensure_env.ensure_env(env_path)

    assert report["created"] is False
    assert report["generated"] == []
    assert report["kept"] == list(ensure_env.MANAGED_KEYS)
    assert env_path.read_text(encoding="utf-8") == before


def test_ensure_env_completes_existing_env_preserving_content(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("# meu comentario\nROUTER_SSH_KEY=abc\n", encoding="utf-8")

    report = ensure_env.ensure_env(env_path)

    assert report["created"] is False
    assert set(report["generated"]) == set(ensure_env.MANAGED_KEYS)
    content = env_path.read_text(encoding="utf-8")
    assert "# meu comentario" in content
    assert "ROUTER_SSH_KEY=abc" in content
    for key in ensure_env.MANAGED_KEYS:
        assert f"{key}=" in content, key


def test_ensure_env_keeps_existing_keys(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("VNF_ENCRYPT_KEY=ja_existente\n", encoding="utf-8")

    report = ensure_env.ensure_env(env_path)

    assert report["generated"] == ["AUDIT_HMAC_KEY", "SECRETS_KEY"]
    assert report["kept"] == ["VNF_ENCRYPT_KEY"]
    content = env_path.read_text(encoding="utf-8")
    assert "VNF_ENCRYPT_KEY=ja_existente" in content


def test_ensure_env_dry_run_does_not_write(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"

    report = ensure_env.ensure_env(env_path, dry_run=True)

    assert report["created"] is True
    assert set(report["generated"]) == set(ensure_env.MANAGED_KEYS)
    assert not env_path.exists()


def test_ensure_env_dry_run_existing(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("AUDIT_HMAC_KEY=abc\n", encoding="utf-8")

    report = ensure_env.ensure_env(env_path, dry_run=True)

    assert report["created"] is False
    assert report["generated"] == ["VNF_ENCRYPT_KEY", "SECRETS_KEY"]
    assert report["kept"] == ["AUDIT_HMAC_KEY"]
    # dry-run não altera o arquivo
    assert env_path.read_text(encoding="utf-8") == "AUDIT_HMAC_KEY=abc\n"


# ─── CLI ────────────────────────────────────────────────────────────


def test_main_dry_run_returns_zero(capsys: pytest.CaptureFixture[str]) -> None:
    rc = ensure_env.main(["--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "[ensure_env]" in out