"""Detecção de versão VRP (Versatile Routing Platform) do dispositivo.

A VRP (Huawei) tem diferenças significativas entre versões principais (VRP5
vs VRP8). Comandos como ``local-user``, ``ssh user``, ``undo portswitch`` e
mesmo a sintaxe de ACL podem variar. Este módulo extrai a versão do output de
``display version`` e permite adaptar o bloco de configuração antes do envio.
"""
from __future__ import annotations

import re
from enum import StrEnum


class VrpVersion(StrEnum):
    """Versões principais da VRP suportadas."""

    VRP5 = "VRP5"
    VRP8 = "VRP8"
    UNKNOWN = "UNKNOWN"


# Captura "Version 5.xxx" ou "Version 8.xxx" do output de display version.
_VERSION_RE = re.compile(
    r"Version\s+([58])\.\d{3}", re.IGNORECASE
)


def detect_vrp_version(output: str) -> VrpVersion:
    """Extrai a versão principal da VRP a partir do output de ``display version``.

    Args:
        output: Texto bruto do comando ``display version``.

    Returns:
        ``VrpVersion.VRP5``, ``VrpVersion.VRP8`` ou ``VrpVersion.UNKNOWN``
        quando não é possível identificar.
    """
    if not output:
        return VrpVersion.UNKNOWN
    match = _VERSION_RE.search(output)
    if not match:
        return VrpVersion.UNKNOWN
    major = match.group(1)
    if major == "5":
        return VrpVersion.VRP5
    if major == "8":
        return VrpVersion.VRP8
    return VrpVersion.UNKNOWN


def is_vrp5(version: VrpVersion) -> bool:
    return version == VrpVersion.VRP5


def is_vrp8(version: VrpVersion) -> bool:
    return version == VrpVersion.VRP8


def requires_commit(version: VrpVersion) -> bool:
    """Retorna True quando a VRP exige commit explícito das mudanças
    não-commitadas antes de sair do system-view (ex.: VRP8/NE40E).

    VRP5 não exige commit; as mudanças são aplicadas diretamente no
    running-config ao sair da visão de configuração.
    """
    return version == VrpVersion.VRP8


def save_command(version: VrpVersion) -> str:
    """Retorna o comando de persistência adequado para a versão VRP.

    VRP8/NE40E: ``save all virtual-systems`` (exec mode, não system-view).
    Outras VRP: ``save`` genérico.
    """
    if version == VrpVersion.VRP8:
        return "save all virtual-systems"
    return "save"
