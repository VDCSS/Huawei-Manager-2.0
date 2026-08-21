"""SecretsBackend ABC + rotation helpers."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("huawei.vault")

_TS_FILE: Path | None = None


def _set_ts_path(path: str | Path) -> None:
    global _TS_FILE
    _TS_FILE = Path(path)


def _generate_ed25519() -> tuple[str, str]:
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
        pub = key.public_key().public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH).decode()
        return priv, pub
    except ImportError:
        raise RuntimeError("cryptography não instalado: pip install cryptography")


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
    def last_rotation(self) -> str | None:
        ts = _TS_FILE
        if ts and ts.exists():
            return ts.read_text().strip()
        return None

    def _record_rotation(self) -> None:
        ts = _TS_FILE
        if ts:
            ts.write_text(datetime.now(timezone.utc).isoformat())
