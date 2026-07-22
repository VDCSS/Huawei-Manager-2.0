"""SopsBackend — criptografado com age via SOPS CLI."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from huawei_manager.vault_backends.base import SecretsBackend

log = logging.getLogger("huawei.vault")


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
