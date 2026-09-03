#!/usr/bin/env python3
"""migrate_credentials.py — Migrate device credentials from .env to DB.

This script:
1. Reads .env from project root (legacy location)
2. Creates/updates a Device in SQLite with ROUTER_* credentials
3. Copies .env to ~/.config/huawei-manager/.env (new location)
4. Generates VNF_ENCRYPT_KEY if missing
5. Generates SECRETS_KEY if using crypto backend

Usage:
    python setup/migrate_credentials.py [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import secrets
import shutil
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dotenv import load_dotenv

# Constants
USER_CONFIG_DIR = Path.home() / ".config" / "huawei-manager"
USER_ENV_PATH = USER_CONFIG_DIR / ".env"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LEGACY_ENV_PATH = PROJECT_ROOT / ".env"


def generate_vnf_encrypt_key() -> str:
    """Generate a 32-byte hex key for VNF_ENCRYPT_KEY."""
    return secrets.token_hex(32)


def generate_secrets_key() -> str:
    """Generate a 32-byte base64 key for SECRETS_KEY (AES-256-GCM)."""
    import base64
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("utf-8")


def read_legacy_env() -> dict[str, str]:
    """Read the legacy .env file from project root."""
    if not LEGACY_ENV_PATH.exists():
        print(f"  ⚠ Legacy .env not found at {LEGACY_ENV_PATH}")
        return {}

    env_vars: dict[str, str] = {}
    with open(LEGACY_ENV_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                env_vars[key.strip()] = value.strip()
    return env_vars


def ensure_user_config_dir(dry_run: bool = False) -> None:
    """Create ~/.config/huawei-manager/ if it doesn't exist."""
    if not USER_CONFIG_DIR.exists():
        if dry_run:
            print(f"  [dry-run] Would create {USER_CONFIG_DIR}")
        else:
            USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            print(f"  ✓ Created {USER_CONFIG_DIR}")


def copy_env_to_user_config(env_vars: dict[str, str], dry_run: bool = False) -> None:
    """Copy .env to ~/.config/huawei-manager/.env."""
    if USER_ENV_PATH.exists():
        print(f"  ⚠ {USER_ENV_PATH} already exists — skipping copy")
        return

    if dry_run:
        print(f"  [dry-run] Would copy {LEGACY_ENV_PATH} → {USER_ENV_PATH}")
        return

    USER_ENV_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Write the new .env file
    lines = []
    for key, value in env_vars.items():
        lines.append(f"{key}={value}")

    USER_ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  ✓ Copied .env → {USER_ENV_PATH}")


def generate_missing_keys(env_vars: dict[str, str], dry_run: bool = False) -> dict[str, str]:
    """Generate missing VNF_ENCRYPT_KEY and SECRETS_KEY if needed."""
    new_vars = dict(env_vars)
    changes = []

    # Generate VNF_ENCRYPT_KEY if missing
    if not new_vars.get("VNF_ENCRYPT_KEY"):
        new_key = generate_vnf_encrypt_key()
        new_vars["VNF_ENCRYPT_KEY"] = new_key
        changes.append("VNF_ENCRYPT_KEY")

    # Generate SECRETS_KEY if using crypto backend
    if new_vars.get("SECRETS_BACKEND") == "crypto" and not new_vars.get("SECRETS_KEY"):
        new_key = generate_secrets_key()
        new_vars["SECRETS_KEY"] = new_key
        changes.append("SECRETS_KEY")

    if changes:
        if dry_run:
            print(f"  [dry-run] Would generate: {', '.join(changes)}")
        else:
            print(f"  ✓ Generated: {', '.join(changes)}")
    else:
        print("  ✓ All keys present")

    return new_vars


def migrate_device_to_db(env_vars: dict[str, str], dry_run: bool = False) -> None:
    """Create/update Device in SQLite with ROUTER_* credentials."""
    host = env_vars.get("ROUTER_HOST")
    if not host:
        print("  ⚠ ROUTER_HOST not set — skipping DB migration")
        return

    port = int(env_vars.get("ROUTER_PORT", "22"))
    username = env_vars.get("ROUTER_USERNAME", "")
    password = env_vars.get("ROUTER_PASSWORD", "")
    ssh_key = env_vars.get("ROUTER_SSH_KEY", "")

    if dry_run:
        print(f"  [dry-run] Would create Device: {host}:{port} (user={username})")
        return

    try:
        from huawei_manager.db import get_connection, init_database
        from huawei_manager.device_repository import DeviceRepository
        from huawei_manager.device_models import Device

        conn = get_connection()
        init_database(conn)

        repo = DeviceRepository(conn)

        # Check if device with this host already exists
        existing = repo.get_by_host(host) if hasattr(repo, "get_by_host") else None

        device = Device(
            id=f"router-{host.replace('.', '-')}",
            name=f"Router {host}",
            host=host,
            port=port,
            type="ROUTER",
            username=username,
            password=password,
            ssh_key=ssh_key,
        )

        if existing:
            repo.update(device)
            print(f"  ✓ Updated Device: {host}:{port}")
        else:
            repo.create(device)
            print(f"  ✓ Created Device: {host}:{port}")

        conn.close()
    except Exception as e:
        print(f"  ✗ DB migration failed: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate credentials from .env to DB")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    args = parser.parse_args()

    print("═══ Credential Migration ═══\n")

    # Step 1: Read legacy .env
    print("1. Reading legacy .env...")
    env_vars = read_legacy_env()
    if not env_vars:
        print("  Nothing to migrate.")
        return 0

    # Step 2: Create user config dir
    print("\n2. Ensuring config directory...")
    ensure_user_config_dir(args.dry_run)

    # Step 3: Generate missing keys
    print("\n3. Checking/generating keys...")
    env_vars = generate_missing_keys(env_vars, args.dry_run)

    # Step 4: Copy .env to new location
    print("\n4. Copying .env to user config...")
    copy_env_to_user_config(env_vars, args.dry_run)

    # Step 5: Migrate device to DB
    print("\n5. Migrating device credentials to DB...")
    migrate_device_to_db(env_vars, args.dry_run)

    print("\n═══ Migration complete ═══")
    return 0


if __name__ == "__main__":
    sys.exit(main())
