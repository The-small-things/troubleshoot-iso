"""Colours, fonts and a few reusable widgets, scaled to the screen size."""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

from ..model import Status

BG = "#0f172a"
PANEL = "#1e293b"
PANEL_HI = "#334155"
FG = "#f1f5f9"
MUTED = "#94a3b8"
ACCENT = "#3b82f6"
ACCENT_HI = "#60a5fa"
GOOD = "#22c55e"
WARN = "#f59e0b"
BAD = "#ef4444"

STATUS_COLORS = {Status.PASS: GOOD, Status.WARN: WARN, Status.FAIL: BAD,
                 Status.SKIP: "#64748b", Status.INFO: ACCENT}
STATUS_ICONS = {Status.PASS: "✔", Status.WARN: "!", Status.FAIL: "✘", Status.SKIP: "–", Status.INFO: "i"}

FONTS: dict[str, tkfont.Font] = {}
UNIT = 16  # base size in pixels, set by setup()


def setup(root: tk.Tk) -> None:
    """Create the named fonts with pixel sizes proportional to the screen height."""
    global UNIT
    h = root.winfo_screenheight()
    UNIT = max(14, min(40, int(h / 50)))
    family = "DejaVu Sans"
    for name, mult, weight in (("body", 1.0, "normal"), ("small", 0.8, "normal"),
                               ("bold", 1.0, "bold"), ("h2", 1.35, "bold"), ("h1", 2.0, "bold"),
                               ("huge", 3.0, "bold"), ("mono", 0.8, "normal"), ("key", 0.75, "bold")):
        fam = "DejaVu Sans Mono" if name == "mono" else family
        FONTS[name] = tkfont.Font(root=root, family=fam, size=-int(UNIT * mult), weight=weight)
    root.option_add("*Font", FONTS["body"])
    root.configure(bg=BG)


def px(mult: float) -> int:
    return int(UNIT * mult)


def label(parent, text="", font="body", fg=FG, bg=None, wrap=0, **kw) -> tk.Label:
    return tk.Label(parent, text=text, font=FONTS[font], fg=fg, bg=bg or parent["bg"],
                    wraplength=wrap, justify="left", anchor="w", **kw)


def button(parent, text, command, kind="primary", font="bold", **kw) -> tk.Button:
    colors = {"primary": (ACCENT, ACCENT_HI, "white"), "secondary": (PANEL_HI, "#475569", FG),
              "good": ("#15803d", GOOD, "white"), "bad": ("#b91c1c", BAD, "white")}[kind]
    b = tk.Button(parent, text=text, command=command, font=FONTS[font], bg=colors[0], fg=colors[2],
                  activebackground=colors[1], activeforeground=colors[2], relief="flat", bd=0,
                  highlightthickness=max(2, px(0.15)), highlightcolor="white",
                  highlightbackground=parent["bg"], padx=px(1.2), pady=px(0.5), cursor="hand2", **kw)
    b.bind("<Return>", lambda e: b.invoke())
    return b


def clear(frame: tk.Misc) -> None:
    for w in frame.winfo_children():
        w.destroy()
