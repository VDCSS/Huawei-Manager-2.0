"""EnvBackend — lê variáveis do .env / ambiente."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from huawei_manager.vault_backends.base import SecretsBackend

log = logging.getLogger("huawei.vault")


class EnvBackend(SecretsBackend):
    """Lê variáveis do .env / ambiente. Padrão para lab."""

    def __init__(self, env_path: str | Path | None = None) -> None:
        from dotenv import load_dotenv
        if env_path:
            load_dotenv(dotenv_path=env_path, override=True)
            self._env_path = Path(env_path)
        else:
            load_dotenv(override=True)
            self._env_path = Path(".env")
        log.info("Secrets backend: %s", self.backend_name)

    def get(self, key: str, default: str = "") -> str:
        return os.getenv(key, default)

    def put(self, key: str, value: str) -> None:
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
