"""SopsBackend — criptografado com age via SOPS CLI."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from huawei_manager.vault_backends.base import SecretsBackend

log = logging.getLogger("huawei.vault")


def _default_secret_file() -> Path:
    """Caminho padrão de secrets.enc.yaml — raiz do repo, independente do CWD."""
    # src/huawei_manager/vault_backends/backends_sops.py → parents[3]
    return Path(__file__).resolve().parents[3] / "secrets.enc.yaml"


class SopsBackend(SecretsBackend):
    """Le de secrets.enc.yaml descriptografado via SOPS (age)."""

    def __init__(self, secret_file: Path | None = None) -> None:
        # Raiz do repo — não depender do CWD.
        self._secret_file = secret_file or _default_secret_file()
        if not self._secret_file.exists():
            raise RuntimeError(
                f"Arquivo {self._secret_file.name} nao encontrado em "
                f"{self._secret_file.parent}.\n"
                "Crie com: make encrypt-sops\n"
                "  (sops --encrypt --input-type dotenv --output-type yaml "
                "~/.config/huawei-manager/.env > secrets.enc.yaml)\n"
                "O --output-type yaml e obrigatorio: este backend faz "
                "yaml.safe_load() no output.\n"
                "Requer: sops CLI + chave age (SOPS_AGE_KEY_FILE)"
            )
        self._cache: dict[str, str] = {}
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
