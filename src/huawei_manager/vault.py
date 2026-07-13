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

import base64
import json
import logging
import os
import secrets
import subprocess
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger("huawei.vault")

# ── Rotation timestamp ────────────────────────────────────────────────
_TS_FILE: Path | None = None

def _set_ts_path(path: str | Path) -> None:
    """Define o caminho do arquivo de timestamp de rotacao de chave SSH."""
    global _TS_FILE
    _TS_FILE = Path(path)


def _generate_ed25519() -> tuple[str, str]:
    """Gera par de chaves ED25519. Retorna (pem_privada, openssh_pública)."""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            NoEncryption,
            PrivateFormat,
            PublicFormat,
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
        """Retorna o valor da chave ou default se nao encontrada."""
        raise NotImplementedError

    def put(self, key: str, value: str) -> None:
        """Persiste uma chave/valor no backend."""
        raise NotImplementedError

    @property
    def backend_name(self) -> str:
        """Nome legivel do backend (para exibicao na UI)."""
        return "base"

    @property
    def last_rotation(self) -> str | None:
        """ISO timestamp da última rotação de chave SSH, ou None."""
        ts = _TS_FILE
        if ts and ts.exists():
            return ts.read_text().strip()
        return None

    def _record_rotation(self) -> None:
        """Grava o timestamp atual no arquivo de rotacao."""
        ts = _TS_FILE
        if ts:
            ts.write_text(datetime.now(UTC).isoformat())


# ═══════════════════════════════════════════════════════════════════════
#  ENV BACKEND (padrão lab)
# ═══════════════════════════════════════════════════════════════════════
class EnvBackend(SecretsBackend):
    """Lê variáveis do .env / ambiente. Padrão para lab."""

    def __init__(self, env_path: str | Path | None = None) -> None:
        """Carrega variaveis do .env. Aceita caminho customizado."""
        from dotenv import load_dotenv
        if env_path:
            load_dotenv(dotenv_path=env_path, override=True)
            self._env_path = Path(env_path)
        else:
            load_dotenv(override=True)
            self._env_path = Path(".env")
        log.info("Secrets backend: %s", self.backend_name)

    def get(self, key: str, default: str = "") -> str:
        """Retorna variavel de ambiente ou default."""
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
        """Nome legivel do backend."""
        return "env (.env)"


# ═══════════════════════════════════════════════════════════════════════
#  CRYPTO BACKEND (AES-256-GCM local)
# ═══════════════════════════════════════════════════════════════════════


class CryptoEnvBackend(SecretsBackend):
    """Backend de secrets com criptografia AES-256-GCM local.

    Criptografa valores em repouso usando AES-256-GCM com nonce aleatório.
    O storage é um dict JSON em memória, serializado para o arquivo
    .env.enc quando put() é chamado.

    Fallback: se encryption_key for None, delega para EnvBackend
    (modo lab/texto plano).
    """

    _VERSION = 1
    _STORAGE_FILE = Path(".env.enc")

    def __init__(
        self, encryption_key: str | None = None, storage_path: str | Path | None = None
    ) -> None:
        self._storage_path = Path(storage_path) if storage_path else self._STORAGE_FILE
        self._store: dict[str, str] = {}
        self._fallback: EnvBackend | None = None

        if encryption_key is not None:
            key_bytes = encryption_key.encode("utf-8")
            if len(key_bytes) < 32:
                key_bytes = key_bytes.ljust(32, b"\0")[:32]
            elif len(key_bytes) > 32:
                key_bytes = key_bytes[:32]
            self._key = key_bytes
        else:
            self._key = b""
            self._fallback = EnvBackend()

        self._load_store()
        log.info("Secrets backend: %s", self.backend_name)

    def _encrypt(self, plaintext: str) -> str:
        """Criptografa texto plano com AES-256-GCM. Retorna base64."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        aesgcm = AESGCM(self._key)
        nonce = secrets.token_bytes(12)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        # Formato: version(1) + nonce(12) + ciphertext+tag
        payload = bytes([self._VERSION]) + nonce + ciphertext
        return base64.b64encode(payload).decode("ascii")

    def _decrypt(self, token: str) -> str:
        """Descriptografa token base64 com AES-256-GCM."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        payload = base64.b64decode(token)
        version = payload[0]
        if version != self._VERSION:
            raise ValueError(f"Versão de criptografia desconhecida: {version}")
        nonce = payload[1:13]
        ciphertext = payload[13:]
        aesgcm = AESGCM(self._key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8")

    def _load_store(self) -> None:
        """Carrega o store do arquivo .env.enc se existir."""
        if self._storage_path.exists():
            try:
                raw = self._storage_path.read_text(encoding="utf-8").strip()
                if raw:
                    self._store = json.loads(raw)
            except (json.JSONDecodeError, OSError):
                log.warning("Falha ao ler %s, iniciando store vazio", self._storage_path)
                self._store = {}

    def _flush_store(self) -> None:
        """Persiste o store criptografado em disco."""
        self._storage_path.write_text(
            json.dumps(self._store, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def get(self, key: str, default: str = "") -> str:
        """Retorna valor descriptografado ou default."""
        if self._fallback is not None:
            return self._fallback.get(key, default)
        encrypted = self._store.get(key)
        if encrypted is None:
            return default
        try:
            return self._decrypt(encrypted)
        except Exception:
            log.warning("Falha ao descriptografar %s", key)
            return default

    def put(self, key: str, value: str) -> None:
        """Criptografa e persiste o valor."""
        if self._fallback is not None:
            self._fallback.put(key, value)
            return
        encrypted = self._encrypt(value)
        self._store[key] = encrypted
        self._flush_store()

    @property
    def backend_name(self) -> str:
        """Nome legivel do backend."""
        if self._fallback is not None:
            return "crypto (fallback: env)"
        return "crypto (AES-256-GCM)"


# ═══════════════════════════════════════════════════════════════════════
#  HASHICORP VAULT BACKEND (stub — requer hvac)
# ═══════════════════════════════════════════════════════════════════════
class VaultBackend(SecretsBackend):
    """HashiCorp Vault via hvac. Requer: pip install hvac"""

    def __init__(self) -> None:
        """Autentica no Vault via VAULT_ADDR/VAULT_TOKEN."""
        try:
            import hvac  # pyright: ignore[reportMissingModuleSource]
        except ImportError:
            raise RuntimeError("hvac não instalado: pip install hvac")

        addr  = os.getenv("VAULT_ADDR", "http://127.0.0.1:8200")
        token = os.getenv("VAULT_TOKEN", "")
        self._client = hvac.Client(url=addr, token=token)
        self._mount  = os.getenv("VAULT_MOUNT", "secret")
        self._path   = os.getenv("VAULT_SECRET_PATH", "huawei/manager")

        if not self._client.is_authenticated():
            raise RuntimeError("Vault auth falhou — verifique VAULT_ADDR e VAULT_TOKEN")
        log.debug("Vault backend: %s  path=%s", addr, self._path)

    def _read(self) -> dict:
        """Le todos os secrets do caminho configurado no Vault KV v2."""
        resp = self._client.secrets.kv.v2.read_secret_version(
            mount_point=self._mount, path=self._path)
        return resp["data"]["data"]

    def _write(self, data: dict) -> None:
        """Persiste dict completo no caminho configurado do Vault KV v2."""
        self._client.secrets.kv.v2.create_or_update_secret(
            mount_point=self._mount, path=self._path, secret=data)

    def get(self, key: str, default: str = "") -> str:
        """Retorna valor de uma chave no Vault."""
        return self._read().get(key, default)

    def put(self, key: str, value: str) -> None:
        """Persiste chave/valor no Vault."""
        data = self._read()
        data[key] = value
        self._write(data)

    @property
    def backend_name(self) -> str:
        """Nome legivel do backend."""
        return "HashiCorp Vault"


# ═══════════════════════════════════════════════════════════════════════
#  AWS SECRETS MANAGER BACKEND (stub — requer boto3)
# ═══════════════════════════════════════════════════════════════════════
class AWSBackend(SecretsBackend):
    """AWS Secrets Manager via boto3. Requer: pip install boto3"""

    def __init__(self) -> None:
        """Autentica na AWS Secrets Manager via boto3."""
        try:
            import boto3  # pyright: ignore[reportMissingImports]
            self._boto3 = boto3
        except ImportError:
            raise RuntimeError("boto3 não instalado: pip install boto3")

        region = os.getenv("AWS_REGION", "us-east-1")
        self._secret_name = os.getenv("AWS_SECRET_NAME", "huawei/manager/creds")
        self._client = boto3.client("secretsmanager", region_name=region)
        self._cache: dict = {}
        self._refresh()
        log.debug("AWS Secrets Manager: %s  region=%s", self._secret_name, region)

    def _refresh(self) -> None:
        """Recarrega o cache do secret da AWS Secrets Manager."""
        resp = self._client.get_secret_value(SecretId=self._secret_name)
        self._cache = json.loads(resp["SecretString"])

    def get(self, key: str, default: str = "") -> str:
        """Lê um valor do cache local do AWS Secrets Manager."""
        return self._cache.get(key, default)

    def put(self, key: str, value: str) -> None:
        """Persiste chave/valor na AWS Secrets Manager."""
        self._cache[key] = value
        self._client.update_secret(
            SecretId=self._secret_name,
            SecretString=json.dumps(self._cache),
        )

    @property
    def backend_name(self) -> str:
        """Nome legivel do backend."""
        return "AWS Secrets Manager"


# ═══════════════════════════════════════════════════════════════════════
#  SOPS BACKEND (criptografado com age)
# ═══════════════════════════════════════════════════════════════════════
class SopsBackend(SecretsBackend):
    """Le de secrets.enc.yaml descriptografado via SOPS (age)."""

    def __init__(self) -> None:
        """Carrega secrets descriptografados via CLI sops (age)."""
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
        """Descriptografa secrets.enc.yaml via sops --decrypt e carrega no cache."""
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
        """Retorna valor do cache SOPS."""
        return self._cache.get(key, default)

    def put(self, key: str, value: str) -> None:
        """Persiste chave/valor e re-criptografa o arquivo SOPS."""
        self._cache[key] = value
        self._flush()

    def _flush(self) -> None:
        """Serializa cache como YAML e re-criptografa via sops --encrypt."""
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
        """Nome legivel do backend."""
        return "SOPS (age)"


# ═══════════════════════════════════════════════════════════════════════
#  FACTORY
# ═══════════════════════════════════════════════════════════════════════
def get_backend(project_root: str = "") -> SecretsBackend:
    """Retorna o backend configurado em SECRETS_BACKEND (padrão: env)."""
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
                log.warning("Falha ao enviar chave SSH via CLI: %s", e)
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
            f"  Timestamp       : {datetime.now(UTC).isoformat()}"
        )

    except Exception as exc:
        log.error("Falha na rotação de chave: %s", exc)
        return False, f"✘  Erro na rotação de chave:\n  {exc}"
