"""CryptoEnvBackend — AES-256-GCM local."""

from __future__ import annotations

import base64
import json
import logging
import secrets
from pathlib import Path

from huawei_manager.vault_backends.backends_env import EnvBackend
from huawei_manager.vault_backends.base import SecretsBackend

log = logging.getLogger("huawei.vault")


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
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        aesgcm = AESGCM(self._key)
        nonce = secrets.token_bytes(12)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        payload = bytes([self._VERSION]) + nonce + ciphertext
        return base64.b64encode(payload).decode("ascii")

    def _decrypt(self, token: str) -> str:
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
        if self._storage_path.exists():
            try:
                raw = self._storage_path.read_text(encoding="utf-8").strip()
                if raw:
                    self._store = json.loads(raw)
            except (json.JSONDecodeError, OSError):
                log.warning("Falha ao ler %s, iniciando store vazio", self._storage_path)
                self._store = {}

    def _flush_store(self) -> None:
        self._storage_path.write_text(
            json.dumps(self._store, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def get(self, key: str, default: str = "") -> str:
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
        if self._fallback is not None:
            self._fallback.put(key, value)
            return
        encrypted = self._encrypt(value)
        self._store[key] = encrypted
        self._flush_store()

    @property
    def backend_name(self) -> str:
        if self._fallback is not None:
            return "crypto (fallback: env)"
        return "crypto (AES-256-GCM)"
