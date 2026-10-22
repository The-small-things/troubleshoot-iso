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


# One colour per test profile, used for its card icon on the welcome screen.
PROFILE_STYLE = {
    "quick": ("⚡", "#f59e0b"),
    "standard": ("✚", "#3b82f6"),
    "full": ("☾", "#a855f7"),
    "custom": ("☰", "#14b8a6"),
}


def setup(root: tk.Tk) -> None:
    """Create the named fonts with pixel sizes proportional to the screen height."""
    global UNIT
    h = root.winfo_screenheight()
    UNIT = max(14, min(40, int(h / 50)))
    families = set(tkfont.families(root))
    body = "DejaVu Sans"
    # A rounded, friendly typeface for headings (Debian package fonts-comfortaa).
    display = "Comfortaa" if "Comfortaa" in families else body
    for name, fam, mult, weight in (("body", body, 1.0, "normal"), ("small", body, 0.8, "normal"),
                                    ("bold", body, 1.0, "bold"), ("h2", display, 1.35, "bold"),
                                    ("h1", display, 2.0, "bold"), ("huge", display, 3.0, "bold"),
                                    ("mono", "DejaVu Sans Mono", 0.8, "normal"), ("key", body, 0.75, "bold"),
                                    ("icon", body, 1.6, "bold")):
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


def rounded(canvas: tk.Canvas, x0, y0, x1, y1, r, **kw) -> int:
    """A rounded rectangle polygon on a canvas."""
    from ..art import rounded_rect
    pts = rounded_rect(x0, y0, x1, y1, min(r, (x1 - x0) / 2, (y1 - y0) / 2), 6)
    return canvas.create_polygon([v for p in pts for v in p], **kw)


class Card(tk.Canvas):
    """A rounded, clickable panel. Put widgets in ``card.body``; they inherit hover colours."""

    def __init__(self, parent, command=None, fill=PANEL, hover=PANEL_HI, radius=None, pad=None):
        super().__init__(parent, bg=parent["bg"], highlightthickness=0, bd=0,
                         takefocus=1 if command else 0, cursor="hand2" if command else "")
        self.fill, self.hover, self.command = fill, hover, command
        self.r = radius if radius is not None else px(0.9)
        self.pad = pad if pad is not None else px(0.9)
        self.shape = None
        self.body = tk.Frame(self, bg=fill)
        self.win = self.create_window(self.pad, self.pad, window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda e: self._layout())
        self.bind("<Configure>", lambda e: self._layout())
        if command:
            self.bind("<Return>", lambda e: command())
            self.bind("<space>", lambda e: command())
            self.bind("<FocusIn>", lambda e: self._paint(True, focus=True))
            self.bind("<FocusOut>", lambda e: self._paint(False))
            self.after_idle(self._bind_children)

    def _bind_children(self):
        def walk(w):
            w.bind("<Button-1>", lambda e: self.command(), add="+")
            w.bind("<Enter>", lambda e: self._paint(True), add="+")
            w.bind("<Leave>", lambda e: self._paint(self.focus_get() is self), add="+")
            for ch in w.winfo_children():
                walk(ch)
        if self.winfo_exists():
            walk(self)

    def _layout(self):
        w = self.winfo_width()
        if w > 2 * self.pad:
            self.itemconfigure(self.win, width=w - 2 * self.pad)
        h = self.body.winfo_reqheight() + 2 * self.pad
        if int(self["height"]) != h:
            self.configure(height=h)
        self._paint(False)

    def _paint(self, hot: bool, focus: bool = False):
        if self.shape:
            self.delete(self.shape)
        w, h = self.winfo_width(), int(self["height"])
        color = self.hover if hot else self.fill
        self.shape = rounded(self, 1, 1, max(2, w - 1), max(2, h - 1), self.r, fill=color,
                             outline="white" if focus else color, width=2)
        self.tag_lower(self.shape)

        def recolor(widget):
            try:
                if widget.cget("bg") in (self.fill, self.hover):
                    widget.configure(bg=color)
            except tk.TclError:
                pass
            for ch in widget.winfo_children():
                recolor(ch)
        recolor(self.body)
