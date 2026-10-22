"""Draw and animate Chip on a Tk canvas."""

from __future__ import annotations

import random
import tkinter as tk

from .. import art
from . import theme as T


def draw(canvas: tk.Canvas, x: float, y: float, size: float, expression: str = "happy",
         glow: float = 1.0, tag: str = "chip") -> None:
    """Draw the mascot with its top-left corner at (x, y)."""
    canvas.delete(tag)
    sc = lambda pts: [c for px, py in pts for c in (x + px * size, y + py * size)]  # noqa: E731
    for shape in art.chip(expression, glow):
        kind = shape[0]
        if kind == "poly":
            _, pts, fill, outline, w = shape
            canvas.create_polygon(sc(pts), fill=fill, outline=outline or "", width=max(1, w * size), tags=tag)
        elif kind == "line":
            _, pts, color, w = shape
            canvas.create_line(sc(pts), fill=color, width=max(1, w * size), capstyle="round",
                               joinstyle="round", tags=tag)
        else:
            _, (cx, cy, rx, ry), fill, outline, w = shape
            canvas.create_oval(x + (cx - rx) * size, y + (cy - ry) * size, x + (cx + rx) * size,
                               y + (cy + ry) * size, fill=fill, outline=outline or "",
                               width=max(1, w * size) if outline else 0, tags=tag)


class Mascot(tk.Canvas):
    """An animated Chip: blinks now and then and its antenna pulses."""

    def __init__(self, master, size: int, expression: str = "happy", bg: str | None = None):
        super().__init__(master, width=size, height=size, bg=bg or master["bg"], highlightthickness=0)
        self.size = size
        self.expression = expression
        self.phase = 0
        self.blinking = 0
        self.job = None
        self.animate()

    def set(self, expression: str) -> None:
        self.expression = expression
        self.redraw()

    def redraw(self):
        glow = 0.5 + 0.5 * abs((self.phase % 20) - 10) / 10
        expr = "blink" if self.blinking and self.expression in ("happy", "thinking") else self.expression
        draw(self, 0, 0, self.size, expr, glow)

    def animate(self):
        self.phase += 1
        if self.blinking:
            self.blinking -= 1
        elif random.random() < 0.03:
            self.blinking = 2
        self.redraw()
        self.job = self.after(120, self.animate)

    def destroy(self):
        if self.job:
            self.after_cancel(self.job)
        super().destroy()


class Bubble(tk.Canvas):
    """A rounded speech bubble whose tail points at Chip (``tail`` = "left" or "top")."""

    def __init__(self, parent, text: str = "", wrap: int = 400, font: str = "body", fill: str | None = None,
                 tail: str = "left"):
        super().__init__(parent, bg=parent["bg"], highlightthickness=0)
        self.wrap, self.font, self.fill, self.tail = wrap, font, fill or T.PANEL, tail
        self.set(text)

    def set(self, text: str) -> None:
        self.delete("all")
        pad, t_len = T.px(0.9), T.px(1.0)
        ox, oy = (t_len, 0) if self.tail == "left" else (0, t_len)
        t = self.create_text(ox + pad, oy + pad, text=text, anchor="nw", width=self.wrap, fill=T.FG,
                             font=T.FONTS[self.font])
        _, _, x1, y1 = self.bbox(t)
        w, h = max(x1 + pad, ox + pad * 3), y1 + pad
        T.rounded(self, ox, oy + 1, w, h, T.px(0.9), fill=self.fill, outline=T.PANEL_HI, width=2)
        half = T.px(0.45)
        if self.tail == "left":
            mid = min(h / 2, T.px(1.8))
            pts = (ox + 2, mid - half, 1, mid + T.px(0.2), ox + 2, mid + half)
        else:
            mid = T.px(2.5)
            pts = (mid - half, oy + 3, mid + T.px(0.3), 1, mid + half, oy + 3)
        self.create_polygon(*pts, fill=self.fill, outline="")
        self.create_line(*pts, fill=T.PANEL_HI, width=2)
        self.tag_raise(t)
        self.configure(width=w + 2, height=h + 2)


class Pulse(tk.Canvas):
    """A scrolling heartbeat line – the troubleshooter's signature."""

    def __init__(self, parent, height: int, color: str = T.ACCENT_HI):
        super().__init__(parent, bg=parent["bg"], height=height, highlightthickness=0)
        self.color, self.phase, self.job = color, 0.0, None
        self.tick()

    def tick(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w > 2:
            pts = [v for x, y in art.pulse_line(self.phase, 90) for v in (x * w, 2 + y * (h - 4))]
            self.create_line(pts, fill=self.color, width=max(2, h // 12), joinstyle="round", capstyle="round")
        self.phase = (self.phase + 0.012) % 1.0
        self.job = self.after(60, self.tick)

    def destroy(self):
        if self.job:
            self.after_cancel(self.job)
        super().destroy()
