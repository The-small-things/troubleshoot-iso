"""Draw and animate Chip on a Tk canvas."""

from __future__ import annotations

import math
import random
import tkinter as tk

from .. import art
from . import theme as T


def draw(canvas: tk.Canvas, x: float, y: float, size: float, expression: str = "happy",
         glow: float = 1.0, tag: str = "chip", blink: float = 0.0, look: tuple[float, float] = (0.0, 0.0),
         parts: tuple[str, ...] = art.PARTS) -> None:
    """Draw the mascot with its top-left corner at (x, y), replacing what ``tag`` drew before."""
    canvas.delete(tag)
    sc = lambda pts: [c for px, py in pts for c in (x + px * size, y + py * size)]  # noqa: E731
    for shape in art.chip(expression, glow, blink, look, parts):
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


BLINK = (0.5, 1.0, 1.0, 0.6, 0.25, 0.0)  # eyelid per frame: quick to close, a little slower to open
FRAME_MS = 45


class Mascot(tk.Canvas):
    """An animated Chip. The body is drawn once; the face is only redrawn when it changes.

    Chip blinks every few seconds (open-eyed faces only), glances around now and then, and its
    antenna glows softly. A new expression is swapped in while the eyes are shut, so faces change
    with a blink instead of popping from one to the next.
    """

    def __init__(self, master, size: int, expression: str = "happy", bg: str | None = None):
        super().__init__(master, width=size, height=size, bg=bg or master["bg"], highlightthickness=0)
        self.size = size
        self.expression = expression
        self.pending: str | None = None   # expression to show once the eyes are shut
        self.blink_frames: list[float] = []
        self.look = [0.0, 0.0]
        self.look_target = (0.0, 0.0)
        self.t = 0.0
        self.next_blink = self.t + random.uniform(1.5, 4.0)
        self.next_look = self.t + random.uniform(2.0, 5.0)
        self.last_face = None
        self.job = None
        draw(self, 0, 0, size, tag="body", parts=("body",))
        self.redraw()
        self.job = self.after(FRAME_MS, self.animate)

    def set(self, expression: str) -> None:
        target = self.pending or self.expression
        if expression == target:
            return
        self.pending = expression
        if not self.blink_frames:
            self.blink_frames = list(BLINK)

    @property
    def blink(self) -> float:
        return self.blink_frames[0] if self.blink_frames else 0.0

    def redraw(self):
        glow = 0.5 + 0.5 * math.sin(self.t * 2.2)
        draw(self, 0, 0, self.size, glow=glow, tag="antenna", parts=("antenna",))
        face = (self.expression, self.blink, round(self.look[0], 3), round(self.look[1], 3))
        if face != self.last_face:
            self.last_face = face
            draw(self, 0, 0, self.size, self.expression, tag="face", blink=self.blink,
                 look=tuple(self.look), parts=("face",))

    def animate(self):
        self.t += FRAME_MS / 1000
        if self.pending and not self.blink_frames:
            self.blink_frames = list(BLINK)
        if self.blink_frames:
            if self.pending and self.blink >= 1.0:  # eyes shut: switch faces now
                # Keep the eyes where they are and let them drift to the new face's resting place.
                old = art.EYE_OFFSET.get(self.expression, (0.0, 0.0))
                new = art.EYE_OFFSET.get(self.pending, (0.0, 0.0))
                self.look = [old[0] + self.look[0] - new[0], old[1] + self.look[1] - new[1]]
                self.look_target = (0.0, 0.0)
                self.expression, self.pending = self.pending, None
            self.blink_frames.pop(0)
        elif self.t >= self.next_blink:
            if self.expression in art.OPEN_EYES:
                self.blink_frames = list(BLINK) + (list(BLINK) if random.random() < 0.15 else [])
            self.next_blink = self.t + random.uniform(2.5, 6.0)
        if self.t >= self.next_look:  # glance somewhere, mostly back to the middle
            self.look_target = random.choice([(0.0, 0.0), (0.0, 0.0), (-0.02, 0.0), (0.02, 0.0), (0.015, -0.012),
                                              (-0.015, 0.01)])
            self.next_look = self.t + random.uniform(2.0, 6.0)
        for i in (0, 1):  # ease towards where Chip is looking
            d = self.look_target[i] - self.look[i]
            self.look[i] = self.look_target[i] if abs(d) < 0.001 else self.look[i] + d * 0.35
        self.redraw()
        self.job = self.after(FRAME_MS, self.animate)

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
