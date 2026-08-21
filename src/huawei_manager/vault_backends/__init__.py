"""vault_backends — Abstração de secrets (Fase 3)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from huawei_manager.vault_backends.backends_aws import AWSBackend
from huawei_manager.vault_backends.backends_crypto import CryptoEnvBackend
from huawei_manager.vault_backends.backends_env import EnvBackend
from huawei_manager.vault_backends.backends_sops import SopsBackend
from huawei_manager.vault_backends.backends_vault import VaultBackend
from huawei_manager.vault_backends.base import (
    SecretsBackend,
    _generate_ed25519,
    _set_ts_path,
)

log = logging.getLogger("huawei.vault")


def get_backend(project_root: str = "") -> SecretsBackend:
    kind = os.getenv("SECRETS_BACKEND", "env").lower()
    if kind == "vault":
        return VaultBackend()
    if kind == "aws":
        return AWSBackend()
    if kind == "sops":
        return SopsBackend()
    if kind == "crypto":
        key = os.getenv("SECRETS_KEY")
        return CryptoEnvBackend(encryption_key=key)
    env_path = Path(project_root) / ".env" if project_root else None
    return EnvBackend(env_path=env_path)


def rotate_ssh_key(
    backend: SecretsBackend,
    netmiko_connection=None,
) -> tuple[bool, str]:
    try:
        priv, pub = _generate_ed25519()

        key_path_str = backend.get("ROUTER_SSH_KEY", "").strip()
        if not key_path_str:
            key_path_str = "~/.ssh/huawei_ed25519"
        key_path = Path(key_path_str).expanduser()
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_text(priv)
        key_path.chmod(0o600)
        key_path.with_suffix(".pub").write_text(pub)

        deployed = False
        push_msg = "  (sem conexão SSH ativa — chave salva localmente)"
        if netmiko_connection and netmiko_connection.is_alive():
            username = backend.get("ROUTER_USERNAME", "admin")
            pub_b64 = pub.split()[1] if len(pub.split()) >= 2 else pub
            cmds = [
                "system-view",
                f"ssh user {username} authentication-type ed25519",
                f"ssh user {username} ed25519 public-key {pub_b64}",
                "return",
                "save",
            ]
            try:
                output = netmiko_connection.send_config_set(cmds, read_timeout=60)
                push_msg = f"  ✔ Enviada ao roteador via CLI\n  {output[:200]}"
                deployed = True
            except Exception as e:
                log.warning("Falha ao enviar chave SSH via CLI: %s", e)
                push_msg = f"  ⚠ Falha ao enviar via CLI: {e}"

        if deployed:
            backend.put("ROUTER_SSH_KEY", str(key_path))
            push_msg += "\n  🔑 Chave ativada para conexões futuras"

        backend._record_rotation()
        log.info("Chave SSH rotacionada → %s (deployed=%s)", key_path, deployed)

        return True, (
            f"✔  Chave ED25519 rotacionada com sucesso!\n"
            f"{'─' * 50}\n"
            f"  Arquivo privado : {key_path}\n"
            f"  Arquivo público : {key_path.with_suffix('.pub')}\n"
            f"  Deploy no router: {'✔' if deployed else '✘'}\n"
            f"  Backend vault   : {backend.backend_name}\n"
            f"{push_msg}\n"
            f"  Timestamp       : {datetime.now(timezone.utc).isoformat()}"
        )

    except Exception as exc:
        log.error("Falha na rotação de chave: %s", exc)
        return False, f"✘  Erro na rotação de chave:\n  {exc}"


__all__ = [
    "AWSBackend",
    "CryptoEnvBackend",
    "EnvBackend",
    "SecretsBackend",
    "SopsBackend",
    "VaultBackend",
    "_set_ts_path",
    "get_backend",
    "rotate_ssh_key",
]
