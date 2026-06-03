from __future__ import annotations

import tkinter as tk
from tkinter import scrolledtext

from huawei_manager.constants import (
    BG_BASE, BG_INPUT, BG_SIDEBAR, BORDER_NRM,
    FG_CODE, FG_DIM,
    NEON_CYAN, NEON_MAG, NEON_PURP,
)


def neon_button(parent, text, command, color=NEON_CYAN, icon="") -> tk.Frame:
    label_text = f"{icon}  {text}" if icon else text
    frame = tk.Frame(parent, bg=BG_SIDEBAR, cursor="hand2")
    lbl = tk.Label(frame, text=label_text, bg=BG_SIDEBAR, fg=FG_DIM,
                   font=("Consolas", 10), anchor="w", padx=16, pady=10)
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
        lbl.configure(fg=color, bg="#1a1a3a", font=("Consolas", 10, "bold"))

    def deactivate():
        lbl.configure(fg=FG_DIM, bg=BG_SIDEBAR, font=("Consolas", 10))
        frame.configure(bg=BG_SIDEBAR)
        accent_bar.configure(bg=BG_SIDEBAR)

    for w in (frame, lbl):
        w.bind("<Enter>",    on_enter)
        w.bind("<Leave>",    on_leave)
        w.bind("<Button-1>", lambda _: command())

    frame._activate   = activate
    frame._deactivate = deactivate
    frame._label      = lbl
    frame._bar        = accent_bar
    frame._color      = color
    return frame


def styled_text(parent, **kw) -> scrolledtext.ScrolledText:
    return scrolledtext.ScrolledText(
        parent,
        bg=BG_INPUT, fg=FG_CODE,
        insertbackground=NEON_CYAN,
        selectbackground=NEON_PURP,
        font=("Consolas", 11),
        relief="flat", borderwidth=0,
        wrap=tk.WORD,
        **kw,
    )


def neon_entry(parent, textvariable=None, width=30, state="normal") -> tk.Entry:
    return tk.Entry(
        parent,
        textvariable=textvariable,
        bg=BG_INPUT, fg=NEON_CYAN,
        insertbackground=NEON_CYAN,
        relief="flat", bd=0,
        font=("Consolas", 10),
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
        font=("Consolas", 10, "bold"),
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
                    font=("Consolas", 8, "bold"),
                    padx=4, pady=2)
