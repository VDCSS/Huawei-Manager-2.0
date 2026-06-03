#!/usr/bin/env python3
"""
vault.py — Abstração de secrets (Fase 3)
==========================================
Seleciona o backend via variável SECRETS_BACKEND:
  env   → lê do .env / variáveis de ambiente  (padrão, lab)
  vault → HashiCorp Vault                      (requer: pip install hvac)
  aws   → AWS Secrets Manager                  (requer: pip install boto3)

Uso:
    from huawei_manager.vault import get_backend, rotate_ssh_key
    backend = get_backend()
    host = backend.get("ROUTER_HOST")
    rotate_ssh_key(backend, netmiko_connection=conn)
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("huawei.vault")

# ── Rotation timestamp ────────────────────────────────────────────────
_TS_FILE = Path(".ssh_rotation_ts")


def _generate_ed25519() -> tuple[str, str]:
    """Gera par de chaves ED25519. Retorna (pem_privada, openssh_pública)."""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import (
            Encoding, NoEncryption, PrivateFormat, PublicFormat,
        )
        key = Ed25519PrivateKey.generate()
        priv = key.private_bytes(Encoding.PEM, PrivateFormat.OpenSSH, NoEncryption()).decode()
        pub  = key.public_key().public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH).decode()
        return priv, pub
    except ImportError:
        raise RuntimeError("cryptography não instalado: pip install cryptography")


# ═══════════════════════════════════════════════════════════════════════
#  BASE
# ═══════════════════════════════════════════════════════════════════════
class SecretsBackend:
    """Interface comum a todos os backends."""

    def get(self, key: str, default: str = "") -> str:
        raise NotImplementedError

    def put(self, key: str, value: str) -> None:
        raise NotImplementedError

    @property
    def backend_name(self) -> str:
        return "base"

    @property
    def last_rotation(self) -> Optional[str]:
        """ISO timestamp da última rotação de chave SSH, ou None."""
        if _TS_FILE.exists():
            return _TS_FILE.read_text().strip()
        return None

    def _record_rotation(self) -> None:
        _TS_FILE.write_text(datetime.now(timezone.utc).isoformat())


# ═══════════════════════════════════════════════════════════════════════
#  ENV BACKEND (padrão lab)
# ═══════════════════════════════════════════════════════════════════════
class EnvBackend(SecretsBackend):
    """Lê variáveis do .env / ambiente. Padrão para lab."""

    def __init__(self) -> None:
        from dotenv import load_dotenv
        load_dotenv(override=True)
        self._env_path = Path(".env")
        log.info("Secrets backend: %s", self.backend_name)

    def get(self, key: str, default: str = "") -> str:
        return os.getenv(key, default)

    def put(self, key: str, value: str) -> None:
        """Persiste no .env e atualiza os.environ."""
        os.environ[key] = value
        if not self._env_path.exists():
            self._env_path.write_text("")
        lines = self._env_path.read_text().splitlines()
        new_lines: list[str] = []
        found = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
                new_lines.append(f"{key}={value}")
                found = True
            elif stripped.startswith(f"# {key}=") or stripped.startswith(f"# {key} ="):
                continue
            else:
                new_lines.append(line)
        if not found:
            new_lines.append(f"{key}={value}")
        self._env_path.write_text("\n".join(new_lines) + "\n")
        log.debug("EnvBackend: persisted %s", key)

    @property
    def backend_name(self) -> str:
        return "env (.env)"


# ═══════════════════════════════════════════════════════════════════════
#  HASHICORP VAULT BACKEND (stub — requer hvac)
# ═══════════════════════════════════════════════════════════════════════
class VaultBackend(SecretsBackend):
    """HashiCorp Vault via hvac. Requer: pip install hvac"""

    def __init__(self) -> None:
        try:
            import hvac  # noqa: F401
        except ImportError:
            raise RuntimeError("hvac não instalado: pip install hvac")

        addr  = os.getenv("VAULT_ADDR", "http://127.0.0.1:8200")
        token = os.getenv("VAULT_TOKEN", "")
        self._client = hvac.Client(url=addr, token=token)
        self._mount  = os.getenv("VAULT_MOUNT", "secret")
        self._path   = os.getenv("VAULT_SECRET_PATH", "huawei/manager")

        if not self._client.is_authenticated():
            raise RuntimeError("Vault auth falhou — verifique VAULT_ADDR e VAULT_TOKEN")
        log.info("Vault backend: %s  path=%s", addr, self._path)

    def _read(self) -> dict:
        resp = self._client.secrets.kv.v2.read_secret_version(
            mount_point=self._mount, path=self._path)
        return resp["data"]["data"]

    def _write(self, data: dict) -> None:
        self._client.secrets.kv.v2.create_or_update_secret(
            mount_point=self._mount, path=self._path, secret=data)

    def get(self, key: str, default: str = "") -> str:
        return self._read().get(key, default)

    def put(self, key: str, value: str) -> None:
        data = self._read()
        data[key] = value
        self._write(data)

    @property
    def backend_name(self) -> str:
        return "HashiCorp Vault"


# ═══════════════════════════════════════════════════════════════════════
#  AWS SECRETS MANAGER BACKEND (stub — requer boto3)
# ═══════════════════════════════════════════════════════════════════════
class AWSBackend(SecretsBackend):
    """AWS Secrets Manager via boto3. Requer: pip install boto3"""

    def __init__(self) -> None:
        try:
            import boto3  # noqa: F401
            self._boto3 = boto3
        except ImportError:
            raise RuntimeError("boto3 não instalado: pip install boto3")

        region = os.getenv("AWS_REGION", "us-east-1")
        self._secret_name = os.getenv("AWS_SECRET_NAME", "huawei/manager/creds")
        self._client = boto3.client("secretsmanager", region_name=region)
        self._cache: dict = {}
        self._refresh()
        log.info("AWS Secrets Manager: %s  region=%s", self._secret_name, region)

    def _refresh(self) -> None:
        resp = self._client.get_secret_value(SecretId=self._secret_name)
        self._cache = json.loads(resp["SecretString"])

    def get(self, key: str, default: str = "") -> str:
        return self._cache.get(key, default)

    def put(self, key: str, value: str) -> None:
        self._cache[key] = value
        self._client.update_secret(
            SecretId=self._secret_name,
            SecretString=json.dumps(self._cache),
        )

    @property
    def backend_name(self) -> str:
        return "AWS Secrets Manager"


# ═══════════════════════════════════════════════════════════════════════
#  SOPS BACKEND (criptografado com age)
# ═══════════════════════════════════════════════════════════════════════
class SopsBackend(SecretsBackend):
    """Le de secrets.enc.yaml descriptografado via SOPS (age)."""

    def __init__(self) -> None:
        self._secret_file = Path("secrets.enc.yaml")
        if not self._secret_file.exists():
            raise RuntimeError(
                "Arquivo secrets.enc.yaml nao encontrado.\n"
                "Crie com: sops --encrypt .env > secrets.enc.yaml\n"
                "Requer: sops CLI + chave age (SOPS_AGE_KEY_FILE)"
            )
        self._cache: dict = {}
        self._refresh()

    def _refresh(self) -> None:
        result = subprocess.run(
            ["sops", "--decrypt", str(self._secret_file)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Falha ao descriptografar com SOPS: {result.stderr.strip()}"
            )
        try:
            import yaml
            self._cache = yaml.safe_load(result.stdout) or {}
        except ImportError:
            raise RuntimeError("PyYAML necessario para SopsBackend: pip install pyyaml")

    def get(self, key: str, default: str = "") -> str:
        return self._cache.get(key, default)

    def put(self, key: str, value: str) -> None:
        self._cache[key] = value
        self._flush()

    def _flush(self) -> None:
        try:
            import yaml
        except ImportError:
            raise RuntimeError("PyYAML necessario para SopsBackend: pip install pyyaml")
        plain = yaml.dump(self._cache, default_flow_style=False)
        result = subprocess.run(
            ["sops", "--encrypt", "/dev/stdin"],
            input=plain, capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Falha ao criptografar com SOPS: {result.stderr.strip()}"
            )
        self._secret_file.write_text(result.stdout)

    @property
    def backend_name(self) -> str:
        return "SOPS (age)"


# ═══════════════════════════════════════════════════════════════════════
#  FACTORY
# ═══════════════════════════════════════════════════════════════════════
def get_backend() -> SecretsBackend:
    """Retorna o backend configurado em SECRETS_BACKEND (padrão: env)."""
    kind = os.getenv("SECRETS_BACKEND", "env").lower()
    if kind == "vault":
        return VaultBackend()
    if kind == "aws":
        return AWSBackend()
    if kind == "sops":
        return SopsBackend()
    return EnvBackend()


# ═══════════════════════════════════════════════════════════════════════
#  SSH KEY ROTATION (Fase 3)
# ═══════════════════════════════════════════════════════════════════════
def rotate_ssh_key(
    backend: SecretsBackend,
    netmiko_connection=None,
) -> tuple[bool, str]:
    """
    Gera novo par ED25519, persiste a chave privada localmente e no vault,
    e envia a chave pública ao roteador via CLI (Netmiko, se conectado).

    Retorna (sucesso: bool, mensagem: str).
    """
    try:
        priv, pub = _generate_ed25519()

        # ── salvar localmente ─────────────────────────────────────────
        key_path_str = backend.get("ROUTER_SSH_KEY", "").strip()
        if not key_path_str:
            key_path_str = "~/.ssh/huawei_ed25519"
        key_path = Path(key_path_str).expanduser()
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_text(priv)
        key_path.chmod(0o600)
        key_path.with_suffix(".pub").write_text(pub)

        # ── enviar ao roteador via CLI ────────────────────────────────
        deployed = False
        push_msg = "  (sem conexão SSH ativa — chave salva localmente)"
        if netmiko_connection and netmiko_connection.is_alive():
            username = backend.get("ROUTER_USERNAME", "admin")
            pub_b64  = pub.split()[1] if len(pub.split()) >= 2 else pub
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
                push_msg = f"  ⚠ Falha ao enviar via CLI: {e}"

        # ── persistir no backend APENAS se foi enviado ao roteador ─────
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
