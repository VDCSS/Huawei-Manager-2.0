from __future__ import annotations

import tkinter as tk
from tkinter import scrolledtext
from typing import Literal

from huawei_manager.constants import (
    BG_BASE,
    BG_INPUT,
    BG_SIDEBAR,
    BORDER_NRM,
    FG_CODE,
    FG_DIM,
    FONT_LARGE,
    FONT_MEDIUM,
    FONT_MEDIUM_B,
    FONT_SMALL_B,
    NEON_CYAN,
    NEON_PURP,
)


def neon_button(parent, text, command, color=NEON_CYAN, icon="") -> tk.Frame:
    label_text = f"{icon}  {text}" if icon else text
    frame = tk.Frame(parent, bg=BG_SIDEBAR, cursor="hand2")
    lbl = tk.Label(frame, text=label_text, bg=BG_SIDEBAR, fg=FG_DIM,
                   font=FONT_MEDIUM, anchor="w", padx=16, pady=10)
    lbl.pack(fill="x")

    accent_bar = tk.Frame(frame, bg=BG_SIDEBAR, width=3)
    accent_bar.place(x=0, y=0, relheight=1)

    def on_enter(_):
        lbl.configure(fg=color, bg="#14142e")
        frame.configure(bg="#14142e")
        accent_bar.configure(bg=color)

    def on_leave(_):
        lbl.configure(fg=FG_DIM, bg=BG_SIDEBAR)
        frame.configure(bg=BG_SIDEBAR)
        accent_bar.configure(bg=BG_SIDEBAR)

    def activate():
        lbl.configure(fg=color, bg="#1a1a3a", font=FONT_MEDIUM_B)

    def deactivate():
        lbl.configure(fg=FG_DIM, bg=BG_SIDEBAR, font=FONT_MEDIUM)
        frame.configure(bg=BG_SIDEBAR)
        accent_bar.configure(bg=BG_SIDEBAR)

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
    return scrolledtext.ScrolledText(
        parent,
        bg=BG_INPUT, fg=FG_CODE,
        insertbackground=NEON_CYAN,
        selectbackground=NEON_PURP,
        font=FONT_LARGE,
        relief="flat", borderwidth=0,
        wrap=tk.WORD,
        **kw,
    )


def neon_entry(parent, textvariable: tk.Variable | None = None, width=30,
               state: Literal["normal", "disabled", "readonly"] = "normal") -> tk.Entry:
    return tk.Entry(
        parent,
        textvariable=textvariable,  # type: ignore[arg-type]
        bg=BG_INPUT, fg=NEON_CYAN,
        insertbackground=NEON_CYAN,
        relief="flat", bd=0,
        font=FONT_MEDIUM,
        width=width,
        state=state,
        highlightthickness=1,
        highlightbackground=BORDER_NRM,
        highlightcolor=NEON_CYAN,
    )


def action_button(parent, text, command, color=NEON_CYAN) -> tk.Button:
    btn = tk.Button(
        parent, text=text, command=command,
        bg=BG_INPUT, fg=color,
        activebackground=color, activeforeground=BG_BASE,
        relief="flat", bd=0,
        font=FONT_MEDIUM_B,
        padx=20, pady=6, cursor="hand2",
        highlightthickness=1,
        highlightbackground=color,
        highlightcolor=color,
    )
    btn.bind("<Enter>", lambda _: btn.configure(bg=color, fg=BG_BASE))
    btn.bind("<Leave>", lambda _: btn.configure(bg=BG_INPUT, fg=color))
    return btn


def status_badge(parent, text, color) -> tk.Label:
    return tk.Label(parent, text=f"  {text}  ",
                    bg=color, fg=BG_BASE,
                    font=FONT_SMALL_B,
                    padx=4, pady=2)
