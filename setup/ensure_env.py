#!/usr/bin/env python3
"""ensure_env.py — Gera/garante as chaves de criptografia do Huawei Manager 2.0.

Cria (ou completa) `~/.config/huawei-manager/.env` com as chaves:

  - VNF_ENCRYPT_KEY  (Fernet — senhas de devices no SQLite)
  - AUDIT_HMAC_KEY   (HMAC-SHA256 — cadeia de auditoria)
  - SECRETS_KEY      (AES-256-GCM — backend crypto / .env.enc)

Idempotente: chaves existentes NUNCA são sobrescritas (regenerar quebraria
dados já criptografados). NÃO cria devices nem toca no banco — apenas o .env.

Uso:
  python3 setup/ensure_env.py            # gera/garante o .env do usuário
  python3 setup/ensure_env.py --dry-run  # mostra o que faria, sem escrever

Stdlib-only (secrets/base64/pathlib) para rodar no install sem depender do
venv; o formato de VNF_ENCRYPT_KEY é idêntico ao de Fernet.generate_key()
(32 bytes random → urlsafe base64), aceito por device_crypto._get_fernet_encrypt().
"""

from __future__ import annotations

import argparse
import base64
import secrets
import sys
from pathlib import Path
from typing import TypedDict

# Espelha src/huawei_manager/_config.py (USER_CONFIG_DIR / USER_ENV_PATH)
USER_CONFIG_DIR = Path.home() / ".config" / "huawei-manager"
USER_ENV_PATH = USER_CONFIG_DIR / ".env"

# Mesmo template de _config.py._ENV_TEMPLATE (mantém compatibilidade de leitura)
_ENV_TEMPLATE = """\
# Huawei Manager 2.0 — Configuration

# --- SSH defaults -------------------------------------------------
ROUTER_SSH_KEY=
ROUTER_HOSTKEY_VERIFY=strict

# --- Crypto -------------------------------------------------------
VNF_ENCRYPT_KEY={vnf_encrypt_key}
AUDIT_HMAC_KEY={audit_hmac_key}

# --- Behavior -----------------------------------------------------
HW_ADAPTIVE_POLLING=0
SSH_TIMEOUT=90

# --- Secrets backend: env | crypto | sops | vault | aws -----------
SECRETS_BACKEND=env
"""

# Chaves gerenciadas por este script (ordem de exibição)
MANAGED_KEYS: tuple[str, ...] = ("VNF_ENCRYPT_KEY", "AUDIT_HMAC_KEY", "SECRETS_KEY")


class EnvReport(TypedDict):
    env_path: str
    created: bool
    generated: list[str]
    kept: list[str]


def generate_vnf_encrypt_key() -> str:
    """Chave Fernet válida (44 chars urlsafe base64) — mesmo formato de Fernet.generate_key()."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")


def generate_audit_hmac_key() -> str:
    """Chave HMAC-SHA256 (64 chars hex) — mesmo formato de _config._ensure_user_env()."""
    return secrets.token_hex(32)


def generate_secrets_key() -> str:
    """Chave AES-256-GCM (44 chars urlsafe base64) — mesmo formato do secrets_key legado."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")


def _read_existing_keys(env_path: Path) -> dict[str, str]:
    """Lê KEY=value existentes no .env (ignora comentários e linhas vazias)."""
    keys: dict[str, str] = {}
    if not env_path.exists():
        return keys
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if key:
            keys[key] = value.strip()
    return keys


def ensure_env(env_path: Path | None = None, dry_run: bool = False) -> EnvReport:
    """Garante o .env com as chaves gerenciadas. Idempotente.

    Retorna relatório: {"env_path", "created", "generated": [keys], "kept": [keys]}.
    """
    target = env_path or USER_ENV_PATH
    existing = _read_existing_keys(target)

    generated: list[str] = []
    kept: list[str] = []
    for key in MANAGED_KEYS:
        if key in existing and existing[key]:
            kept.append(key)
        else:
            generated.append(key)

    if dry_run:
        return EnvReport(
            env_path=str(target),
            created=not target.exists(),
            generated=generated,
            kept=kept,
        )

    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        content = _ENV_TEMPLATE.format(
            vnf_encrypt_key=generate_vnf_encrypt_key(),
            audit_hmac_key=generate_audit_hmac_key(),
        )
        # SECRETS_KEY não está no template do app; anexa no fim
        content += f"SECRETS_KEY={generate_secrets_key()}\n"
        target.write_text(content, encoding="utf-8")
        return EnvReport(
            env_path=str(target),
            created=True,
            generated=list(MANAGED_KEYS),
            kept=[],
        )

    # .env já existe: completa apenas as chaves ausentes, preservando o resto
    if not generated:
        return EnvReport(env_path=str(target), created=False, generated=[], kept=kept)

    new_values: dict[str, str] = {
        "VNF_ENCRYPT_KEY": generate_vnf_encrypt_key(),
        "AUDIT_HMAC_KEY": generate_audit_hmac_key(),
        "SECRETS_KEY": generate_secrets_key(),
    }
    lines = target.read_text(encoding="utf-8").splitlines()
    if lines and lines[-1].strip() != "":
        lines.append("")
    lines.append("# --- Chaves adicionadas por setup/ensure_env.py ---")
    for key in MANAGED_KEYS:
        if key in generated:
            lines.append(f"{key}={new_values[key]}")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return EnvReport(env_path=str(target), created=False, generated=generated, kept=kept)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gera/garante as chaves de criptografia do Huawei Manager 2.0 no .env do usuário."
    )
    parser.add_argument("--dry-run", action="store_true", help="mostra o que faria sem escrever")
    args = parser.parse_args(argv)

    report = ensure_env(dry_run=args.dry_run)
    action = "criaria" if args.dry_run else "criou"
    print(f"[ensure_env] .env: {report['env_path']}")
    if report["created"]:
        print(f"[ensure_env] {action} o arquivo com chaves novas: {', '.join(report['generated'])}")
    elif report["generated"]:
        print(f"[ensure_env] adicionou chaves ausentes: {', '.join(report['generated'])}")
        print(f"[ensure_env] manteve chaves existentes: {', '.join(report['kept'])}")
    else:
        print(f"[ensure_env] nada a fazer — chaves já presentes: {', '.join(report['kept'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())