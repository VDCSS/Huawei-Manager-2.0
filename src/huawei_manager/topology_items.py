"""
topology_items.py — Graphics item helpers for TopologyCanvas.
=============================================================
Shared constants, color helpers, and font conversion used by
topology.py and topology_nodes.py.
"""
from __future__ import annotations

from PySide6.QtGui import QFont

import huawei_manager.constants as C
from huawei_manager.vnf_models import VNF

ITEM_DATA_KEY = 0  # item.setData(ITEM_DATA_KEY, vnf_id)


def _to_qfont(tk_font: tuple) -> QFont:
    """Converte tupla de fonte (family, size, [bold]) → QFont."""
    family = tk_font[0] if len(tk_font) > 0 else "Consolas"
    size   = tk_font[1] if len(tk_font) > 1 else 11
    bold   = len(tk_font) > 2 and tk_font[2] == "bold"
    qf = QFont(family, size)
    qf.setBold(bold)
    return qf


def _build_tooltip_text(vnf: VNF, show_admin_info: bool = False) -> str:
    """Constrói o texto do tooltip com informações do VNF."""
    lines = [
        f"  {vnf.name}",
        f"  IP: {vnf.host}",
        f"  Tipo: {vnf.type}",
        f"  Status: {vnf.status}",
    ]
    if show_admin_info:
        lines += [
            f"  Porta: {vnf.port}",
            f"  Usuário: {vnf.username or '(padrão .env)'}",
            f"  Senha: {'****' if vnf.password else '(padrão .env)'}",
            f"  Chave SSH: {vnf.ssh_key or '(padrão .env)'}",
        ]
        if vnf.location:
            lines.append(f"  Local: {vnf.location}")
        if vnf.version:
            lines.append(f"  Versão: {vnf.version}")
    return "\n".join(lines)


_TYPE_COLORS: dict[str, str] = {
    "ROUTER":        C.NEON_CYAN,
    "SWITCH":        C.NEON_MAG,
    "FIREWALL":      C.NEON_RED,
    "LOAD-BALANCER": C.NEON_AMBER,
    "WAN-ACCEL":     "#00e676",
    "SDN-CONTROLLER": C.NEON_PURP,
    "AP":            "#ff9100",
    "unknown":       C.FG_DIM,
}


def _color_for(vnf: VNF) -> str:
    return _TYPE_COLORS.get(vnf.type, _TYPE_COLORS["unknown"])


def _status_color(vnf: VNF, type_color: str) -> str:
    return {
        "online":  type_color,
        "offline": C.NEON_RED,
        "unknown": C.NEON_AMBER,
    }.get(vnf.status, C.NEON_AMBER)
