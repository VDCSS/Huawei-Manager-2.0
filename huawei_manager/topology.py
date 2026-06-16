#!/usr/bin/env python3
"""
topology.py — VNF Topology + Canvas
=======================================
Gerenciamento de VNFs via inventário local (vnf_inventory.json),
probe TCP real e simulação de status (modo mock).

O VNF selecionado no canvas é usado como alvo para conexão SSH via Netmiko.
"""
from __future__ import annotations

import json
import logging
import random
import socket
import time
import tkinter as tk
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path

from huawei_manager.constants import (
    FONT_BODY,
    FONT_H1,
    FONT_LARGE,
    FONT_LARGE_B,
    FONT_MEDIUM,
    FONT_MEDIUM_B,
    FONT_XSMALL,
)

log = logging.getLogger("huawei.topology")

VNF_INVENTORY_FILE = "vnf_inventory.json"


# ═══════════════════════════════════════════════════════════════════════
#  VNF DATACLASS
# ═══════════════════════════════════════════════════════════════════════
@dataclass
class VNF:
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
    extra:    dict    = field(default_factory=dict)

    def label(self) -> str:
        return self.name or self.id

    def address(self) -> str:
        return f"{self.host}:{self.port}"

    @classmethod
    def from_dict(cls, d: dict) -> VNF:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ═══════════════════════════════════════════════════════════════════════
#  SIMULAÇÃO DE STATUS (MOCK)
# ═══════════════════════════════════════════════════════════════════════
_mock_last_update: float = 0.0

def simulate_status(vnfs: list[VNF]) -> list[VNF]:
    global _mock_last_update
    now = time.time()
    if now - _mock_last_update < 15:
        return vnfs
    _mock_last_update = now
    for v in vnfs:
        if v.status == "offline":
            if random.random() < 0.2:
                v.status = "online"
        elif v.status == "online":
            if random.random() < 0.05:
                v.status = random.choice(["offline", "unknown"])
    return vnfs


# ═══════════════════════════════════════════════════════════════════════
#  PROBE TCP (REAL)
# ═══════════════════════════════════════════════════════════════════════
def _check_vnf(vnf: VNF, timeout: int = 3) -> str:
    socket.create_connection((vnf.host, vnf.port or 22), timeout=timeout).close()
    return "online"


def probe_vnfs(vnfs: list[VNF], timeout: int = 5) -> list[VNF]:
    with ThreadPoolExecutor(max_workers=min(10, len(vnfs) or 1)) as ex:
        fut = {ex.submit(_check_vnf, v, timeout): v for v in vnfs if v.host}
        for f in as_completed(fut):
            v = fut[f]
            try:
                v.status = f.result()
            except (OSError, TimeoutError):
                v.status = "offline"
    return vnfs


def _normalize_status(raw: str) -> str:
    raw = raw.lower()
    if raw in ("online", "reachable", "active", "managed"):
        return "online"
    if raw in ("offline", "unreachable", "inactive", "unmanaged"):
        return "offline"
    return "unknown"


# ═══════════════════════════════════════════════════════════════════════
#  INVENTÁRIO LOCAL
# ═══════════════════════════════════════════════════════════════════════
def load_vnf_inventory(filename: str = VNF_INVENTORY_FILE) -> list[VNF]:
    path = Path(filename)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [VNF.from_dict(d) for d in data.get("vnfs", [])]
    except Exception as e:
        log.warning("Erro ao ler %s: %s", filename, e)
        return []


def save_vnf_inventory(vnfs: list[VNF], filename: str = VNF_INVENTORY_FILE) -> None:
    data = {"vnfs": [asdict(v) for v in vnfs]}
    Path(filename).write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )





# ═══════════════════════════════════════════════════════════════════════
#  TOOLTIP
# ═══════════════════════════════════════════════════════════════════════
class ToolTip:
    """Tooltip flutuante que mostra informações do VNF ao passar o mouse."""

    def __init__(self, canvas, theme: dict) -> None:
        self._canvas = canvas
        self._theme  = theme
        self._win: tk.Toplevel | None = None
        self._label: tk.Label | None  = None
        self._after_id: str | None    = None

    def show(self, vnf: VNF, x: int, y: int, admin: bool = False) -> None:
        self.hide()
        self._win = tk.Toplevel(self._canvas)
        self._win.wm_overrideredirect(True)
        self._win.wm_geometry(f"+{x + 12}+{y + 12}")
        self._win.attributes("-topmost", True)
        self._win.configure(bg=self._theme["BORDER_NRM"])

        lines = [
            f"  {vnf.name}",
            f"  IP: {vnf.host}",
            f"  Tipo: {vnf.type}",
            f"  Status: {vnf.status}",
        ]
        if admin:
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

        inner = tk.Frame(self._win, bg=self._theme["BG_INPUT"],
                         highlightthickness=1, highlightbackground=self._theme["BORDER_NRM"])
        inner.pack(padx=1, pady=1)
        for line in lines:
            tk.Label(inner, text=line, bg=self._theme["BG_INPUT"],
                     fg=self._theme["FG_MAIN"], font=FONT_BODY,
                     anchor="w", justify="left").pack(fill="x", padx=8, pady=1)

    def hide(self) -> None:
        if self._win:
            self._win.destroy()
            self._win = None


# ═══════════════════════════════════════════════════════════════════════
#  TOPOLOGY CANVAS (Tkinter)
# ═══════════════════════════════════════════════════════════════════════
class TopologyCanvas:
    """
    Canvas Tkinter que renderiza nós VNF e permite selecionar um alvo SSH.
    Suporta tooltip com infos filtradas por admin e menu de contexto.
    """

    NODE_W, NODE_H = 180, 70

    def __init__(
        self,
        parent,
        theme: dict,
        on_select: Callable[[VNF], None] | None = None,
        on_edit:   Callable[[VNF], None] | None = None,
        on_delete: Callable[[VNF], None] | None = None,
    ) -> None:
        self._theme    = theme
        self._on_select = on_select
        self._edit_cb:   Callable[[VNF], None] | None = on_edit
        self._delete_cb: Callable[[VNF], None] | None = on_delete
        self._vnfs: list[VNF]     = []
        self._selected: VNF | None = None
        self._positions: dict[str, tuple[float, float]] = {}
        self._access_level: str = "user"
        self._tooltip = ToolTip(parent, theme)
        self._type_colors: dict[str, str] = {
            "ROUTER":        theme.get("NEON_CYAN",  "#00e5ff"),
            "SWITCH":        theme.get("NEON_MAG",   "#e040fb"),
            "FIREWALL":      "#ff4d4d",
            "LOAD-BALANCER": theme.get("NEON_AMBER", "#ffab00"),
            "WAN-ACCEL":     "#00e676",
            "SDN-CONTROLLER": theme.get("NEON_PURP", "#7c4dff"),
            "AP":            "#ff9100",
            "unknown":       theme.get("FG_DIM",    "#6a6a9a"),
        }

        self._frame  = tk.Frame(parent, bg=theme["BG_BASE"])
        self._canvas = tk.Canvas(
            self._frame,
            bg=theme["BG_BASE"],
            highlightthickness=0,
        )
        self._canvas.pack(fill="both", expand=True)
        self._canvas.bind("<Configure>", lambda _: self._draw())

    def set_access(self, level: str) -> None:
        self._access_level = level

    def pack(self, **kw):
        self._frame.pack(**kw)

    def grid(self, **kw):
        self._frame.grid(**kw)

    def update_vnfs(self, vnfs: list[VNF]) -> None:
        self._vnfs = vnfs
        self._draw()

    def get_selected(self) -> VNF | None:
        return self._selected

    def deselect(self) -> None:
        self._selected = None
        self._draw()

    def _color_for(self, vnf: VNF) -> str:
        return self._type_colors.get(vnf.type, self._type_colors.get("unknown") or "")

    def _layout(self) -> dict[str, tuple[float, float]]:
        positions: dict[str, tuple[float, float]] = {}
        n = len(self._vnfs)
        if n == 0:
            return positions

        w = self._canvas.winfo_width() or 800

        cols = 4
        pad_x, pad_y = 24, 24
        grid_w = cols * self.NODE_W + (cols - 1) * pad_x
        start_x = (w - grid_w) / 2 + self.NODE_W / 2
        start_y = 100

        for i, vnf in enumerate(self._vnfs):
            col = i % cols
            row = i // cols
            x = start_x + col * (self.NODE_W + pad_x)
            y = start_y + row * (self.NODE_H + pad_y)
            positions[vnf.id] = (x, y)

        return positions

    def _draw_empty_state(self) -> None:
        c = self._canvas
        w = c.winfo_width() or 800
        h = c.winfo_height() or 400
        c.create_text(w // 2, h // 2,
                      text="Nenhum dispositivo cadastrado.\n"
                           "Clique em 'Cadastrar Dispositivo' para adicionar.",
                      fill=self._theme["FG_DIM"], font=FONT_LARGE,
                      justify="center")

    def _draw_sdn_bar(self) -> None:
        c = self._canvas
        t = self._theme
        cw = c.winfo_width() or 800

        bar_w = max(cw - 40, 200)
        bar_h = 40
        bar_x = (cw - bar_w) / 2
        bar_y = 16

        c.create_rectangle(bar_x, bar_y, bar_x + bar_w, bar_y + bar_h,
                           fill=t["BG_INPUT"], outline=t["NEON_PURP"], width=2)
        c.create_text(bar_x + 20, bar_y + bar_h // 2,
                      text="⬡", fill=t["NEON_PURP"],
                      font=FONT_H1, anchor="w")
        c.create_text(bar_x + 44, bar_y + bar_h // 2,
                      text="SDN CONTROLLER", fill=t["NEON_PURP"],
                      font=FONT_LARGE_B, anchor="w")
        c.create_text(bar_x + bar_w - 20, bar_y + bar_h // 2,
                      text=f"{len(self._vnfs)} dispositivo(s) gerenciado(s)",
                      fill=t["FG_DIM"], font=FONT_BODY, anchor="e")

    def _draw_vnf_node(self, vnf: VNF, x: float, y: float, admin: bool = False) -> None:
        c = self._canvas
        t = self._theme
        nw, nh = self.NODE_W, self.NODE_H
        is_selected = self._selected and self._selected.id == vnf.id

        type_color = self._color_for(vnf)
        status_color = {
            "online":  type_color,
            "offline": "#ff4d4d",
            "unknown": t["NEON_AMBER"],
        }.get(vnf.status, t["NEON_AMBER"])

        border_w = 2
        fill_col = t["BG_CARD"]

        if is_selected:
            c.create_rectangle(
                x - nw // 2 - 6, y - nh // 2 - 6,
                x + nw // 2 + 6, y + nh // 2 + 6,
                fill="", outline=status_color, width=1, dash=(3, 3),
                tags=("node", vnf.id),
            )
            fill_col = t["BG_INPUT"]
            border_w = 3

        rect = c.create_rectangle(
            x - nw // 2, y - nh // 2,
            x + nw // 2, y + nh // 2,
            fill=fill_col, outline=status_color, width=border_w,
            tags=("node", vnf.id),
        )

        c.create_oval(x - nw // 2 + 4, y - nh // 2 + 4,
                      x - nw // 2 + 14, y - nh // 2 + 14,
                      fill=status_color, outline="", tags=("node", vnf.id))

        c.create_text(
            x, y - 18, text=vnf.label(),
            fill=status_color, font=FONT_MEDIUM_B, anchor="center",
            tags=("node", vnf.id),
        )

        addr = vnf.host if not admin else vnf.address()
        c.create_text(
            x, y + 2, text=addr,
            fill=t["FG_DIM"], font=FONT_BODY, anchor="center",
            tags=("node", vnf.id),
        )

        type_label = vnf.type.replace("-", "\n")
        c.create_text(
            x + nw // 2 - 8, y + nh // 2 - 8,
            text=type_label, fill=type_color,
            font=FONT_XSMALL, anchor="se",
            tags=("node", vnf.id),
        )

        for item in (rect,):
            c.tag_bind(item, "<Button-1>",
                       lambda e, v=vnf: self._on_click(v))
            c.tag_bind(item, "<Enter>",
                       lambda e, v=vnf, it=rect, col=status_color:
                           self._on_enter(e, v, it, col))
            c.tag_bind(item, "<Leave>",
                       lambda e, it=rect, fil=fill_col:
                           self._on_leave(e, it, fil))
            c.tag_bind(item, "<Button-3>",
                       lambda e, v=vnf: self._on_context_menu(e, v))

    def _draw(self) -> None:
        self._canvas.delete("all")

        if not self._vnfs:
            self._draw_empty_state()
            return

        self._positions = self._layout()

        self._draw_sdn_bar()

        for vnf in self._vnfs:
            x, y = self._positions[vnf.id]
            self._draw_vnf_node(vnf, x, y, admin=self._access_level in ("admin", "tecnico"))

        if self._tooltip:
            self._tooltip.hide()

    def _on_click(self, vnf: VNF) -> None:
        self._selected = vnf
        self._draw()
        if self._on_select:
            self._on_select(vnf)

    def _on_enter(self, event, vnf: VNF, item_id: int, color: str) -> None:
        self._canvas.itemconfig(item_id, fill=self._theme["BG_INPUT"])
        if self._tooltip:
            x = self._canvas.winfo_pointerx()
            y = self._canvas.winfo_pointery()
            self._tooltip.show(vnf, x, y, admin=self._access_level in ("admin", "tecnico"))

    def _on_leave(self, event, item_id: int, fill: str) -> None:
        self._canvas.itemconfig(item_id, fill=fill)
        if self._tooltip:
            self._tooltip.hide()

    def _on_context_menu(self, event, vnf: VNF) -> None:
        menu = tk.Menu(self._canvas, tearoff=0, bg=self._theme["BG_INPUT"],
                       fg=self._theme["FG_MAIN"], font=FONT_MEDIUM,
                       activebackground=self._theme["NEON_PURP"],
                       activeforeground=self._theme["BG_BASE"])
        can_edit = self._access_level in ("admin", "tecnico")
        if can_edit:
            menu.add_command(label="✏️  Editar Dispositivo",
                             command=lambda: self._on_edit(vnf))
            menu.add_command(label="🗑  Excluir Dispositivo",
                             command=lambda: self._on_delete(vnf))
            menu.post(event.x_root, event.y_root)

    def _on_edit(self, vnf: VNF) -> None:
        if self._edit_cb:
            self._edit_cb(vnf)

    def _on_delete(self, vnf: VNF) -> None:
        if self._delete_cb:
            self._delete_cb(vnf)


