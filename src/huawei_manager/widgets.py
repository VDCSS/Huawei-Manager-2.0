from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import scrolledtext
from typing import Any, Literal

import huawei_manager.constants as C
from huawei_manager.constants import (
    FONT_LARGE,
    FONT_UI_MEDIUM,
    FONT_UI_MEDIUM_B,
)

# ── Canvas helper ────────────────────────────────────────────────────

def _rounded_rect(canvas: tk.Canvas, x1: float, y1: float,
                  x2: float, y2: float, r: float = 8,
                  **kwargs: Any) -> int:  # type: ignore[explicit-any]
    """Desenha um retângulo arredondado via polygon smooth."""
    points = [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


# ── Neon Button (sidebar navigation) ─────────────────────────────────

def neon_button(parent: tk.Misc, text: str,
                command: Callable[[], object],
                color: str = C.NEON_CYAN, icon: str = "") -> tk.Frame:
    """Botão lateral com cantos arredondados, hover e estado ativo."""
    label_text = f"{icon}  {text}" if icon else text
    R = 8  # corner radius

    frame = tk.Frame(parent, bg=C.BG_SIDEBAR, cursor="hand2")
    canvas = tk.Canvas(frame, bg=C.BG_SIDEBAR, highlightthickness=0,
                       cursor="hand2", height=36)
    canvas.pack(fill="x")

    state = {"hover": False, "active": False}

    def _draw() -> None:
        w = canvas.winfo_width() or 220
        h = canvas.winfo_height() or 36
        canvas.delete("all")

        if state["active"]:
            bg = "#1a1a3a"
            _rounded_rect(canvas, 4, 2, w - 2, h - 2, R, fill=bg, outline="")
            # accent bar
            canvas.create_rectangle(0, 4, 4, h - 4, fill=color, outline="")
        elif state["hover"]:
            bg = "#1a1a3e"
            _rounded_rect(canvas, 4, 2, w - 2, h - 2, R, fill=bg, outline="")
        else:
            _rounded_rect(canvas, 4, 2, w - 2, h - 2, R,
                          fill=C.BG_SIDEBAR, outline="")

        fg = color if (state["active"] or state["hover"]) else C.FG_DIM
        ft = FONT_UI_MEDIUM_B if state["active"] else FONT_UI_MEDIUM
        canvas.create_text(16, h / 2, text=label_text, anchor="w",
                           fill=fg, font=ft)

    def on_enter(_: object = None) -> None:
        state["hover"] = True
        _draw()

    def on_leave(_: object = None) -> None:
        state["hover"] = False
        _draw()

    def on_click(_: object = None) -> None:
        command()

    def activate() -> None:
        state["active"] = True
        _draw()

    def deactivate() -> None:
        state["active"] = False
        _draw()

    canvas.bind("<Button-1>", on_click)
    canvas.bind("<Enter>", on_enter)
    canvas.bind("<Leave>", on_leave)
    canvas.bind("<Configure>", lambda _: _draw())

    frame._activate = activate        # type: ignore[attr-defined]
    frame._deactivate = deactivate    # type: ignore[attr-defined]
    return frame

# ── Styled Text ──────────────────────────────────────────────────────

def styled_text(parent: tk.Misc, **kw: object) -> scrolledtext.ScrolledText:
    """Cria um widget ScrolledText com tema neon escuro."""
    return scrolledtext.ScrolledText(
        parent,
        bg=C.BG_INPUT, fg=C.FG_CODE,
        insertbackground=C.NEON_CYAN,
        selectbackground=C.NEON_PURP,
        font=FONT_LARGE,
        relief="flat", borderwidth=0,
        wrap=tk.WORD,
        **kw,  # type: ignore[arg-type]
    )


def output_text(parent: tk.Misc, **kw: object) -> scrolledtext.ScrolledText:
    """Cria um ScrolledText somente leitura para exibir saídas."""
    return styled_text(parent, state="disabled", **kw)


# ── Entry ────────────────────────────────────────────────────────────

def neon_entry(parent: tk.Misc,
               textvariable: tk.Variable | None = None,
               width: int = 30,
               state: Literal["normal", "disabled", "readonly"] = "normal"
               ) -> tk.Entry:
    """Cria um campo de entrada com tema neon escuro."""
    return tk.Entry(
        parent,
        textvariable=textvariable,  # type: ignore[arg-type]
        bg=C.BG_INPUT, fg=C.NEON_CYAN,
        insertbackground=C.NEON_CYAN,
        relief="flat", bd=0,
        font=FONT_UI_MEDIUM,
        width=width,
        state=state,
        highlightthickness=1,
        highlightbackground=C.BORDER_NRM,
        highlightcolor=C.NEON_CYAN,
    )


# ── Action Button (Canvas-based, rounded) ────────────────────────────

class ActionButton(tk.Canvas):
    """Botão de ação com cantos arredondados, hover e suporte a configure()."""

    def __init__(self, parent: tk.Misc, text: str,
                 command: Callable[[], object],
                 color: str = C.NEON_CYAN) -> None:
        self._text = text
        self._command = command
        self._color = color
        self._disabled = False

        super().__init__(
            parent, bg=C.BG_INPUT, highlightthickness=0,
            cursor="hand2", height=32,
        )

        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", lambda _: self._draw(hover=True))
        self.bind("<Leave>", lambda _: self._draw())
        self.bind("<Configure>", lambda _: self._draw())
        self._draw()

    def _draw(self, hover: bool = False) -> None:
        w = self.winfo_width() or 120
        h = self.winfo_height() or 32
        r = 8
        self.delete("all")

        if self._disabled:
            bg = C.BG_INPUT
            fg = "#555566"
            border = C.BORDER_NRM
        elif hover:
            bg = self._color
            fg = C.BG_BASE
            border = self._color
        else:
            bg = C.BG_INPUT
            fg = self._color
            border = self._color

        # outer border
        _rounded_rect(self, 0, 0, w, h, r, fill=border, outline="")
        # inner fill (2px border effect)
        _rounded_rect(self, 2, 2, w - 2, h - 2, r - 1, fill=bg, outline="")
        # text
        self.create_text(w / 2, h / 2, text=self._text,
                         fill=fg, font=FONT_UI_MEDIUM_B)

    def _on_click(self, _: object = None) -> None:
        if not self._disabled:
            self._command()

    def configure(self, **kwargs: Any) -> None:  # type: ignore[override]
        """Atualiza texto/estado e redesenha."""
        if "text" in kwargs:
            self._text = str(kwargs.pop("text"))
        if "state" in kwargs:
            self._disabled = kwargs.pop("state") == "disabled"
            kwargs["cursor"] = "arrow" if self._disabled else "hand2"
        if kwargs:
            super().configure(**kwargs)
        self._draw()


def action_button(parent: tk.Misc, text: str,
                  command: Callable[[], object],
                  color: str = C.NEON_CYAN) -> ActionButton:
    """Cria um botão de ação com cantos arredondados e tema neon."""
    return ActionButton(parent, text, command, color)
