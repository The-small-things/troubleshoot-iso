"""Touchpad / mouse test: reach targets, left/right click, scroll and drag."""

from __future__ import annotations

import re
import tkinter as tk

from .. import util
from ..interactive import pointer_result
from . import theme as T

STEPS = ["move", "left", "right", "scroll", "drag"]
INSTRUCTIONS = {
    "move": "Move the pointer over every circle until they are all green.",
    "left": "Left-click (or tap the touchpad) on the circle.",
    "right": "Right-click on the circle (touchpads: two-finger tap, or click the bottom-right corner).",
    "scroll": "Scroll down or up (mouse wheel, or two fingers on the touchpad) until the bar is full.",
    "drag": "Hold the button down on the blue square, drag it into the dashed box, and let go.",
}
SCROLL_NEEDED = 12


def pointing_devices() -> list[str]:
    text = util.read(f"{util.PROC}/bus/input/devices") or ""
    names = re.findall(r'^N: Name="(.+)"$', text, re.M)
    return [n for n in names if re.search(r"touchpad|mouse|trackpoint|glidepoint|trackpad|synaptics|elan|alps", n, re.I)
            and not re.search(r"keyboard|consumer control|system control|hotkey", n, re.I)]


class PointerTest(tk.Frame):
    def __init__(self, master, on_done):
        super().__init__(master, bg=T.BG)
        self.on_done = on_done
        self.done: set[str] = set()
        self.step_i = 0
        self.scrolls = 0
        self.last = None
        self.devices = pointing_devices()

        head = tk.Frame(self, bg=T.BG)
        head.pack(fill="x", padx=T.px(2), pady=(T.px(1.2), 0))
        self.title = T.label(head, "Touchpad / mouse test", "h1")
        self.title.pack(anchor="w")
        self.instr = T.label(head, "", "h2", T.ACCENT_HI)
        self.instr.pack(anchor="w", pady=(T.px(0.3), 0))
        T.label(head, "Can't do a step? Press S on the keyboard to skip it (it will be reported as not working). "
                      f"Detected: {', '.join(self.devices) or 'no touchpad/mouse reported'}",
                "small", T.MUTED, wrap=T.px(70)).pack(anchor="w")
        self.canvas = tk.Canvas(self, bg="#0b1220", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True, padx=T.px(2), pady=T.px(1))
        c = self.canvas
        c.bind("<Motion>", self.on_motion)
        c.bind("<Button-1>", self.on_left)
        c.bind("<Button-3>", self.on_right)
        c.bind("<Button-4>", self.on_scroll)
        c.bind("<Button-5>", self.on_scroll)
        c.bind("<MouseWheel>", self.on_scroll)
        c.bind("<B1-Motion>", self.on_drag)
        c.bind("<ButtonRelease-1>", self.on_release)
        c.bind("<KeyPress-s>", lambda e: self.next_step(False))
        c.bind("<KeyPress-S>", lambda e: self.next_step(False))
        self.after(100, c.focus_force)
        self.after(150, self.setup_step)

    @property
    def step(self):
        return STEPS[self.step_i] if self.step_i < len(STEPS) else None

    def setup_step(self):
        c = self.canvas
        c.delete("target")
        c.delete("trail")
        w, h = c.winfo_width(), c.winfo_height()
        r = max(T.px(1.5), min(w, h) // 14)
        self.r = r
        if self.step is None:
            return self.questions()
        self.instr.configure(text=f"Step {self.step_i + 1} of {len(STEPS)}: {INSTRUCTIONS[self.step]}")
        if self.step == "move":
            self.targets = {}
            for fx in (0.06, 0.5, 0.94):
                for fy in (0.08, 0.5, 0.92):
                    x, y = w * fx, h * fy
                    t = c.create_oval(x - r / 2, y - r / 2, x + r / 2, y + r / 2, fill=T.PANEL_HI,
                                      outline=T.ACCENT_HI, width=3, tags="target")
                    self.targets[t] = (x, y, False)
        elif self.step in ("left", "right"):
            self.circle = c.create_oval(w / 2 - r, h / 2 - r, w / 2 + r, h / 2 + r, fill=T.ACCENT,
                                        outline="white", width=3, tags="target")
            c.create_text(w / 2, h / 2, text="LEFT\nclick" if self.step == "left" else "RIGHT\nclick",
                          fill="white", font=T.FONTS["h2"], justify="center", tags="target")
        elif self.step == "scroll":
            self.scrolls = 0
            bw, bh = T.px(3), h * 0.7
            self.bar = (w / 2 - bw / 2, h * 0.15, w / 2 + bw / 2, h * 0.15 + bh)
            c.create_rectangle(*self.bar, outline="white", width=2, tags="target")
            self.fill = c.create_rectangle(self.bar[0], self.bar[3], self.bar[2], self.bar[3], fill=T.GOOD,
                                           outline="", tags="target")
        elif self.step == "drag":
            s = r * 1.2
            self.box = (w * 0.7 - s, h / 2 - s, w * 0.7 + s, h / 2 + s)
            c.create_rectangle(*self.box, outline="white", dash=(6, 4), width=3, tags="target")
            self.sq = c.create_rectangle(w * 0.2 - s / 2, h / 2 - s / 2, w * 0.2 + s / 2, h / 2 + s / 2,
                                         fill=T.ACCENT, outline="white", width=2, tags="target")
            self.grab = None

    def next_step(self, ok: bool):
        if self.step is None:
            return
        if ok:
            self.done.add(self.step)
        self.step_i += 1
        delay = 500 if ok else 50
        self.after(delay, self.setup_step)

    # --- events ------------------------------------------------------------------------------
    def on_motion(self, e):
        c = self.canvas
        if self.last:
            c.create_line(*self.last, e.x, e.y, fill="#475569", width=2, tags="trail")
        self.last = (e.x, e.y)
        if self.step == "move":
            for t, (x, y, hit) in list(self.targets.items()):
                if not hit and (e.x - x) ** 2 + (e.y - y) ** 2 <= (self.r / 2 + 4) ** 2:
                    c.itemconfigure(t, fill=T.GOOD, outline="white")
                    self.targets[t] = (x, y, True)
            if all(v[2] for v in self.targets.values()):
                self.step_i_guard("move")

    def step_i_guard(self, name):
        if self.step == name and name not in self.done:
            self.next_step(True)

    def _inside_circle(self, e):
        x0, y0, x1, y1 = self.canvas.coords(self.circle)
        cx, cy, r = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2
        return (e.x - cx) ** 2 + (e.y - cy) ** 2 <= r * r

    def on_left(self, e):
        if self.step == "left" and self._inside_circle(e):
            self.canvas.itemconfigure(self.circle, fill=T.GOOD)
            self.step_i_guard("left")
        elif self.step == "drag":
            x0, y0, x1, y1 = self.canvas.coords(self.sq)
            if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                self.grab = (e.x, e.y)

    def on_right(self, e):
        if self.step == "right" and self._inside_circle(e):
            self.canvas.itemconfigure(self.circle, fill=T.GOOD)
            self.step_i_guard("right")

    def on_scroll(self, e):
        if self.step != "scroll":
            return
        self.scrolls += 1
        x0, y0, x1, y1 = self.bar
        frac = min(1, self.scrolls / SCROLL_NEEDED)
        self.canvas.coords(self.fill, x0, y1 - (y1 - y0) * frac, x1, y1)
        if self.scrolls >= SCROLL_NEEDED:
            self.step_i_guard("scroll")

    def on_drag(self, e):
        self.on_motion(e)
        if self.step == "drag" and self.grab:
            dx, dy = e.x - self.grab[0], e.y - self.grab[1]
            self.canvas.move(self.sq, dx, dy)
            self.grab = (e.x, e.y)

    def on_release(self, e):
        if self.step == "drag" and self.grab:
            self.grab = None
            x0, y0, x1, y1 = self.canvas.coords(self.sq)
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            bx0, by0, bx1, by1 = self.box
            if bx0 <= cx <= bx1 and by0 <= cy <= by1:
                self.canvas.itemconfigure(self.sq, fill=T.GOOD)
                self.step_i_guard("drag")

    # --- final question ----------------------------------------------------------------------
    def questions(self):
        T.clear(self)
        box = tk.Frame(self, bg=T.BG)
        box.place(relx=0.5, rely=0.5, anchor="center")
        T.label(box, "One last question", "h1").pack(anchor="w")
        T.label(box, "While you were moving the pointer, did it ever jump, drift, or move by itself?",
                wrap=T.px(40)).pack(anchor="w", pady=T.px(1))
        row = tk.Frame(box, bg=T.BG)
        row.pack(anchor="w")
        b = T.button(row, "No, it was smooth  (N)", lambda: self.finish(False), "good")
        b.pack(side="left")
        T.button(row, "Yes, it jumped / moved on its own  (Y)", lambda: self.finish(True), "bad").pack(
            side="left", padx=T.px(1))
        b.focus_set()
        self.bind_all("<KeyPress-n>", lambda e: self.finish(False))
        self.bind_all("<KeyPress-y>", lambda e: self.finish(True))

    def finish(self, jumpy: bool):
        self.unbind_all("<KeyPress-n>")
        self.unbind_all("<KeyPress-y>")
        if getattr(self, "_reported", False):
            return
        self._reported = True
        self.on_done(pointer_result(self.done, ", ".join(self.devices), False, jumpy))
