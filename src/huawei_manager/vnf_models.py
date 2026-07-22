"""vnf_models.py — VNF data model only.

Extraído de topology.py para separar modelo de dados (puro, testável
sem Qt) da view Qt (TopologyCanvas, _VNFNodeRect, _TopoView).
Probe TCP, inventory I/O e crypto foram extraídos para módulos
separados (vnf_probe.py, vnf_inventory.py, vnf_crypto.py).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from huawei_manager.vnf_crypto import _decrypt_val

log = logging.getLogger("huawei.topology")


@dataclass
class VNF:
    """Representa um dispositivo VNF com dados de conexao e status."""
    id:       str
    name:     str
    host:     str
    port:     int     = 22
    type:     str     = "ROUTER"
    status:   str     = "unknown"
    version:  str     = ""
    location: str     = ""
    username: str     = ""
    password: str     = ""
    ssh_key:  str     = ""
    extra_metadata: dict = field(default_factory=dict)

    def label(self) -> str:
        """Retorna o nome legivel do VNF (name ou id)."""
        return self.name or self.id

    def address(self) -> str:
        """Retorna host:porta como string."""
        return f"{self.host}:{self.port}"

    @classmethod
    def from_dict(cls, data: dict) -> VNF:
        v = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        if v.password:
            v.password = _decrypt_val(v.password)
        if v.ssh_key:
            v.ssh_key = _decrypt_val(v.ssh_key)
        return v
