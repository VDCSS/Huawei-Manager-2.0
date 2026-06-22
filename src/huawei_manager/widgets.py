from __future__ import annotations

import tkinter as tk
from tkinter import scrolledtext
from typing import Literal

import huawei_manager.constants as C
from huawei_manager.constants import (
    FONT_LARGE,
    FONT_MEDIUM,
    FONT_MEDIUM_B,
)


def neon_button(parent, text, command, color=C.NEON_CYAN, icon="") -> tk.Frame:
    """Cria um botão lateral neon com hover e estado ativo."""
    label_text = f"{icon}  {text}" if icon else text
    frame = tk.Frame(parent, bg=C.BG_SIDEBAR, cursor="hand2")
    lbl = tk.Label(frame, text=label_text, bg=C.BG_SIDEBAR, fg=C.FG_DIM,
                   font=FONT_MEDIUM, anchor="w", padx=16, pady=10)
    lbl.pack(fill="x")

    accent_bar = tk.Frame(frame, bg=C.BG_SIDEBAR, width=3)
    accent_bar.place(x=0, y=0, relheight=1)

    def on_enter(_):
        """Destaca o botão ao passar o mouse."""
        lbl.configure(fg=color, bg="#14142e")
        frame.configure(bg="#14142e")
        accent_bar.configure(bg=color)

    def on_leave(_):
        """Retorna o botão ao estado normal ao remover o mouse."""
        lbl.configure(fg=C.FG_DIM, bg=C.BG_SIDEBAR)
        frame.configure(bg=C.BG_SIDEBAR)
        accent_bar.configure(bg=C.BG_SIDEBAR)

    def activate():
        """Marca o botão como ativo (página selecionada)."""
        lbl.configure(fg=color, bg="#1a1a3a", font=FONT_MEDIUM_B)

    def deactivate():
        """Desmarca o botão como ativo."""
        lbl.configure(fg=C.FG_DIM, bg=C.BG_SIDEBAR, font=FONT_MEDIUM)
        frame.configure(bg=C.BG_SIDEBAR)
        accent_bar.configure(bg=C.BG_SIDEBAR)

    for w in (frame, lbl):
        w.bind("<Enter>",    on_enter)
        w.bind("<Leave>",    on_leave)
        w.bind("<Button-1>", lambda _: command())

    frame._activate   = activate   # type: ignore[attr-defined]
    frame._deactivate = deactivate # type: ignore[attr-defined]
    frame._label      = lbl        # type: ignore[attr-defined]
    frame._bar        = accent_bar # type: ignore[attr-defined]
    frame._color      = color      # type: ignore[attr-defined]
    return frame


def styled_text(parent, **kw) -> scrolledtext.ScrolledText:
    """Cria um widget ScrolledText com tema neon escuro."""
    return scrolledtext.ScrolledText(
        parent,
        bg=C.BG_INPUT, fg=C.FG_CODE,
        insertbackground=C.NEON_CYAN,
        selectbackground=C.NEON_PURP,
        font=FONT_LARGE,
        relief="flat", borderwidth=0,
        wrap=tk.WORD,
        **kw,
    )


def output_text(parent, **kw) -> scrolledtext.ScrolledText:
    """Cria um ScrolledText somente leitura para exibir saídas."""
    return styled_text(parent, state="disabled", **kw)


def neon_entry(parent, textvariable: tk.Variable | None = None, width=30,
               state: Literal["normal", "disabled", "readonly"] = "normal") -> tk.Entry:
    """Cria um campo de entrada com tema neon escuro."""
    return tk.Entry(
        parent,
        textvariable=textvariable,  # type: ignore[arg-type]
        bg=C.BG_INPUT, fg=C.NEON_CYAN,
        insertbackground=C.NEON_CYAN,
        relief="flat", bd=0,
        font=FONT_MEDIUM,
        width=width,
        state=state,
        highlightthickness=1,
        highlightbackground=C.BORDER_NRM,
        highlightcolor=C.NEON_CYAN,
    )


def action_button(parent, text, command, color=C.NEON_CYAN) -> tk.Button:
    """Cria um botão de ação com efeito hover e tema neon."""
    btn = tk.Button(
        parent, text=text, command=command,
        bg=C.BG_INPUT, fg=color,
        activebackground=color, activeforeground=C.BG_BASE,
        relief="flat", bd=0,
        font=FONT_MEDIUM_B,
        padx=20, pady=6, cursor="hand2",
        highlightthickness=1,
        highlightbackground=color,
        highlightcolor=color,
    )
    btn.bind("<Enter>", lambda _, b=btn, c=color: b.configure(bg=c, fg=C.BG_BASE))
    btn.bind("<Leave>", lambda _, b=btn, c=color: b.configure(bg=C.BG_INPUT, fg=c))
    return btn



