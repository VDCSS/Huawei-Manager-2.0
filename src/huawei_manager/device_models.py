"""device_models.py — Device data model only."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from huawei_manager.device_crypto import _decrypt_val

log = logging.getLogger("huawei.device_models")


@dataclass
class Device:
    """Representa um dispositivo de rede com dados de conexao e status."""
    id:       str
    name:     str
    host:     str
    port:     int     = 22
    type:     str     = "ROUTER"
    status:   str     = "unknown"
    version:  str     = ""
    location: str     = ""
    username:     str = ""
    password:     str = ""
    password_env: str = ""
    ssh_key:      str = ""
    extra_metadata: dict = field(default_factory=dict)

    def label(self) -> str:
        return self.name or self.id

    def address(self) -> str:
        return f"{self.host}:{self.port}"

    @classmethod
    def from_dict(cls, data: dict) -> Device:
        v = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        if v.password:
            try:
                v.password = _decrypt_val(v.password)
            except ValueError:
                raise
            except Exception:
                log.warning(
                    "Falha ao descriptografar senha do device %s "
                    "(VNF_ENCRYPT_KEY pode ter mudado) — senha ignorada",
                    v.id,
                )
                v.password = ""
        if v.ssh_key:
            try:
                v.ssh_key = _decrypt_val(v.ssh_key)
            except ValueError:
                raise
            except Exception:
                log.warning(
                    "Falha ao descriptografar ssh_key do device %s — chave ignorada",
                    v.id,
                )
                v.ssh_key = ""
        return v
