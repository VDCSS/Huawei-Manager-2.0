"""VaultBackend — HashiCorp Vault via hvac."""

from __future__ import annotations

import logging
import os

from huawei_manager.vault_backends.base import SecretsBackend

log = logging.getLogger("huawei.vault")


class VaultBackend(SecretsBackend):
    """HashiCorp Vault via hvac. Requer: pip install hvac"""

    def __init__(self) -> None:
        try:
            import hvac  # pyright: ignore[reportMissingModuleSource]
        except ImportError:
            raise RuntimeError("hvac não instalado: pip install hvac")

        addr = os.getenv("VAULT_ADDR", "http://127.0.0.1:8200")
        token = os.getenv("VAULT_TOKEN", "")
        self._client = hvac.Client(url=addr, token=token)
        self._mount = os.getenv("VAULT_MOUNT", "secret")
        self._path = os.getenv("VAULT_SECRET_PATH", "huawei/manager")

        if not self._client.is_authenticated():
            raise RuntimeError("Vault auth falhou — verifique VAULT_ADDR e VAULT_TOKEN")
        log.debug("Vault backend: %s  path=%s", addr, self._path)

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
