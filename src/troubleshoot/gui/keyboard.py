"""Keyboard test: an on-screen keyboard where each physical key lights up when pressed.

Keys are identified by their X keycode (evdev code + 8), i.e. by physical position, so the
test works the same whatever the keyboard's language layout is.
"""

from __future__ import annotations

import tkinter as tk

from ..interactive import keyboard_result
from . import theme as T

# (label, evdev code, width in key units). None = gap.
ROWS = [
    [("Esc", 1, 1), None, ("F1", 59, 1), ("F2", 60, 1), ("F3", 61, 1), ("F4", 62, 1), None,
     ("F5", 63, 1), ("F6", 64, 1), ("F7", 65, 1), ("F8", 66, 1), None,
     ("F9", 67, 1), ("F10", 68, 1), ("F11", 87, 1), ("F12", 88, 1), None, ("Del", 111, 1)],
    [("`", 41, 1), ("1", 2, 1), ("2", 3, 1), ("3", 4, 1), ("4", 5, 1), ("5", 6, 1), ("6", 7, 1),
     ("7", 8, 1), ("8", 9, 1), ("9", 10, 1), ("0", 11, 1), ("-", 12, 1), ("=", 13, 1), ("Backspace", 14, 2.25)],
    [("Tab", 15, 1.5), ("Q", 16, 1), ("W", 17, 1), ("E", 18, 1), ("R", 19, 1), ("T", 20, 1), ("Y", 21, 1),
     ("U", 22, 1), ("I", 23, 1), ("O", 24, 1), ("P", 25, 1), ("[", 26, 1), ("]", 27, 1), ("\\", 43, 1.75)],
    [("Caps", 58, 1.85), ("A", 30, 1), ("S", 31, 1), ("D", 32, 1), ("F", 33, 1), ("G", 34, 1), ("H", 35, 1),
     ("J", 36, 1), ("K", 37, 1), ("L", 38, 1), (";", 39, 1), ("'", 40, 1), ("Enter", 28, 2.4)],
    [("Shift", 42, 1.4), ("<>", 86, 1), ("Z", 44, 1), ("X", 45, 1), ("C", 46, 1), ("V", 47, 1), ("B", 48, 1),
     ("N", 49, 1), ("M", 50, 1), (",", 51, 1), (".", 52, 1), ("/", 53, 1), ("Shift", 54, 2.85)],
    [("Ctrl", 29, 1.3), ("Win", 125, 1.2), ("Alt", 56, 1.2), ("Space", 57, 5.6), ("Alt Gr", 100, 1.2),
     ("Menu", 127, 1), ("Ctrl", 97, 1.2), None, ("←", 105, 1), ("↑", 103, 1), ("↓", 108, 1), ("→", 106, 1)],
]
NAV = [("Ins", 110), ("Home", 102), ("End", 107), ("PgUp", 104), ("PgDn", 109), ("PrtSc", 99)]
# Keys that many keyboards don't have; not required for a pass.
OPTIONAL = {86, 127, 97, 110, 102, 107, 104, 109, 99, 111}
X_OFFSET = 8
LONG_NAMES = {42: "Left Shift", 54: "Right Shift", 29: "Left Ctrl", 97: "Right Ctrl", 56: "Left Alt",
              100: "Right Alt/Alt Gr", 125: "Windows/Super", 14: "Backspace", 1: "Esc", 86: "<> (ISO key)"}


class KeyboardTest(tk.Frame):
    def __init__(self, master, on_done):
        super().__init__(master, bg=T.BG)
        self.on_done = on_done
        self.keys: dict[int, tuple[int, int, str]] = {}  # x keycode -> (rect id, text id, label)
        self.pressed: set[int] = set()
        self.extra: list[str] = []
        self.finished = False

        top = tk.Frame(self, bg=T.BG)
        top.pack(fill="x", padx=T.px(2), pady=(T.px(1.5), 0))
        T.label(top, "Keyboard test", "h1").pack(anchor="w")
        T.label(top, "Press every key on the keyboard once. Each key turns green when the computer "
                     "detects it. The \"Fn\" key can't be detected on its own – that's normal. The "
                     "layout shown is US English, but any keyboard language works.",
                wrap=T.px(60), fg=T.MUTED).pack(anchor="w", pady=(T.px(0.4), 0))

        self.canvas = tk.Canvas(self, bg=T.BG, highlightthickness=0, takefocus=1)
        self.canvas.pack(fill="both", expand=True, padx=T.px(2), pady=T.px(1))
        self.status = T.label(self, "", "body", T.MUTED)
        self.status.pack(anchor="w", padx=T.px(2))
        self.lastkey = T.label(self, "Last key: –", "small", T.MUTED)
        self.lastkey.pack(anchor="w", padx=T.px(2))

        row = tk.Frame(self, bg=T.BG)
        row.pack(fill="x", padx=T.px(2), pady=T.px(1.2))
        T.button(row, "Done – every key I pressed worked", lambda: self.finish(True), "good",
                 takefocus=0).pack(side="left")
        T.button(row, "Some keys don't work", lambda: self.finish(False), "bad",
                 takefocus=0).pack(side="left", padx=T.px(1))
        T.label(row, "(use the mouse/touchpad for these buttons)", "small", T.MUTED).pack(side="left")

        self.canvas.bind("<Configure>", lambda e: self.draw())
        self.canvas.bind("<KeyPress>", self.on_press)
        self.canvas.bind("<KeyRelease>", self.on_release)
        # Stop Tab from moving focus and Alt/F10 from triggering menus while testing.
        self.canvas.bind("<Tab>", lambda e: self.on_press(e) or "break")
        self.after(100, self.canvas.focus_force)

    @property
    def required(self) -> list[int]:
        return [kc for kc in self.keys if kc - X_OFFSET not in OPTIONAL]

    def draw(self):
        c = self.canvas
        c.delete("all")
        self.keys.clear()
        w, h = c.winfo_width(), c.winfo_height()
        units_w = 15.5 + 1.5 + 2  # main block + gap + nav column
        u = min(w / units_w, h / (len(ROWS) + 0.6))
        gap = u * 0.08
        y = 0.0
        for r, row in enumerate(ROWS):
            x = 0.0
            for key in row:
                if key is None:
                    x += 0.35 * u
                    continue
                text, code, width = key
                self._key(x, y, width * u, (0.8 if r == 0 else 1) * u, gap, text, code)
                x += width * u
            y += (0.8 if r == 0 else 1) * u + (0.25 * u if r == 0 else 0)
        nx = 16.5 * u
        for i, (text, code) in enumerate(NAV):
            self._key(nx + (i % 2) * u, 1.05 * u + (i // 2) * u, u, u, gap, text, code)
        for kc in self.pressed:
            if kc in self.keys:
                self._paint(kc, "#15803d")
        self.update_status()

    def _key(self, x, y, w, h, gap, text, code):
        kc = code + X_OFFSET
        fill = T.PANEL if code not in OPTIONAL else "#172033"
        rect = self.canvas.create_rectangle(x + gap, y + gap, x + w - gap, y + h - gap, fill=fill,
                                            outline=T.PANEL_HI, width=2)
        txt = self.canvas.create_text(x + w / 2, y + h / 2, text=text, fill=T.FG, font=T.FONTS["key"])
        if kc in self.keys:  # a second key with the same code (shouldn't happen) – keep first
            return
        self.keys[kc] = (rect, txt, LONG_NAMES.get(code, text))

    def _paint(self, kc, color):
        rect, _, _ = self.keys[kc]
        self.canvas.itemconfigure(rect, fill=color)

    def on_press(self, e):
        kc = e.keycode
        self.lastkey.configure(text=f"Last key: {e.keysym}  (code {kc})")
        if kc in self.keys:
            self.pressed.add(kc)
            self._paint(kc, T.GOOD)
        elif e.keysym not in self.extra:
            self.extra.append(e.keysym)
        self.update_status()
        return "break"

    def on_release(self, e):
        if e.keycode in self.keys:
            self._paint(e.keycode, "#15803d")
        return "break"

    def update_status(self):
        req = self.required
        done = len([k for k in req if k in self.pressed])
        txt = f"{done} of {len(req)} main keys detected."
        if self.extra:
            txt += "  Extra keys detected: " + ", ".join(self.extra[-8:])
        self.status.configure(text=txt)
        if req and done == len(req) and not self.finished:
            self.status.configure(text="All keys detected!  Finishing…", fg=T.GOOD)
            self.finished = True
            self.after(1500, lambda: self.finish(True))

    def finish(self, ok: bool):
        if getattr(self, "_reported", False):
            return
        self._reported = True
        labels = {kc: v[2] for kc, v in self.keys.items()}
        all_keys = [labels[kc] for kc in self.required]
        pressed = {labels[kc] for kc in self.pressed if kc in labels}
        res = keyboard_result(pressed, all_keys, ok)
        if self.extra:
            res.details.append("Extra keys (media, brightness…): " + ", ".join(self.extra))
        self.on_done(res)
