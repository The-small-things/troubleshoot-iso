"""Screen test: full-screen colours, gradients, edges and a brightness check."""

from __future__ import annotations

import tkinter as tk

from .. import backlight
from ..interactive import SCREEN_PROBLEMS, screen_result
from . import theme as T

PATTERNS = [
    ("black", "Black – look for bright dots (stuck pixels) and light leaking at the edges"),
    ("white", "White – look for dark dots (dead pixels), dark corners and stains"),
    ("red", "Red"), ("green", "Green"), ("blue", "Blue"),
    ("#808080", "Grey – look for blotches and uneven brightness"),
    ("gradient", "Gradient – should be smooth, without strong stripes or bands"),
    ("edges", "Edges – the white frame should be visible on all four sides"),
]


class ScreenTest(tk.Frame):
    def __init__(self, master, on_done):
        super().__init__(master, bg=T.BG)
        self.on_done = on_done
        self.index = -1
        self.hint_job = None
        self.bl = backlight.device()
        self.bl_original = backlight.get(self.bl)[0] if self.bl else None
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0, bg="black", cursor="none")
        self.intro()

    def destroy(self):
        if self.hint_job:
            self.after_cancel(self.hint_job)
        if self.bl and self.bl_original is not None:
            backlight.set_raw(self.bl, self.bl_original)
        super().destroy()

    # --- intro -------------------------------------------------------------------------------
    def intro(self):
        T.clear(self)
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0, bg="black", cursor="none")
        box = tk.Frame(self, bg=T.BG)
        box.place(relx=0.5, rely=0.5, anchor="center")
        T.label(box, "Screen test", "h1").pack(anchor="w")
        T.label(box, "The screen will fill with solid colours one after another. Look closely at each "
                     "one for:\n\n  •  dots that are always black, white or one colour\n"
                     "  •  lines or stripes\n  •  dark patches, uneven brightness or light bleeding at the edges\n"
                     "  •  flickering\n\nGo to the next colour with Space, Enter or a click. "
                     "Go back with Backspace or the left arrow.", wrap=T.px(40)).pack(anchor="w", pady=T.px(1))
        btn = T.button(box, "Start  (Space)", self.start)
        btn.pack(anchor="w", pady=T.px(1))
        btn.focus_set()

    def start(self):
        T.clear(self)
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0, bg="black", cursor="none")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.focus_set()
        for seq in ("<space>", "<Return>", "<Right>", "<Button-1>"):
            self.canvas.bind(seq, lambda e: self.step(1))
        for seq in ("<BackSpace>", "<Left>", "<Button-3>"):
            self.canvas.bind(seq, lambda e: self.step(-1))
        self.index = -1
        self.after(50, lambda: self.step(1))

    # --- patterns ----------------------------------------------------------------------------
    def step(self, delta):
        self.index = max(0, self.index + delta)
        if self.index >= len(PATTERNS):
            if self.bl and self.index == len(PATTERNS):
                self.brightness_check()
            else:
                self.questions()
            return
        self.draw(self.index)

    def draw(self, i):
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        kind, text = PATTERNS[i]
        if kind == "gradient":
            c.configure(bg="black")
            steps = 256
            band_h = h / 4
            for row, (rm, gm, bm) in enumerate([(1, 1, 1), (1, 0, 0), (0, 1, 0), (0, 0, 1)]):
                for s in range(steps):
                    v = s
                    color = f"#{v * rm:02x}{v * gm:02x}{v * bm:02x}"
                    x0 = w * s / steps
                    c.create_rectangle(x0, row * band_h, w * (s + 1) / steps + 1, (row + 1) * band_h,
                                       fill=color, outline="")
        elif kind == "edges":
            c.configure(bg="black")
            c.create_rectangle(0, 0, w - 1, h - 1, outline="white", width=1)
            c.create_rectangle(4, 4, w - 5, h - 5, outline="#ff0000", width=1)
            for x in range(0, w, max(20, w // 40)):
                c.create_line(x, 0, x, h, fill="#333333")
            for y in range(0, h, max(20, w // 40)):
                c.create_line(0, y, w, y, fill="#333333")
            c.create_oval(w / 2 - h / 3, h / 6, w / 2 + h / 3, h * 5 / 6, outline="white", width=2)
        else:
            c.configure(bg=kind)
        self.show_hint(f"{i + 1}/{len(PATTERNS)}  ·  {text}")

    def show_hint(self, text):
        c = self.canvas
        if self.hint_job:
            self.after_cancel(self.hint_job)
        c.delete("hint")
        pad = T.px(0.6)
        t = c.create_text(pad * 2, pad * 2, text=text, anchor="nw", fill="white", font=T.FONTS["body"],
                          tags="hint")
        x0, y0, x1, y1 = c.bbox(t)
        r = c.create_rectangle(x0 - pad, y0 - pad, x1 + pad, y1 + pad, fill="#000000", outline="#888888", tags="hint")
        c.tag_raise(t, r)
        self.hint_job = self.after(2500, lambda: c.winfo_exists() and c.delete("hint"))

    # --- brightness --------------------------------------------------------------------------
    def brightness_check(self):
        c = self.canvas
        c.delete("all")
        c.configure(bg="white")
        self.show_hint("Brightness test – the screen should dim, then get bright again")
        seq = [0.15, 0.5, 1.0]
        for n, frac in enumerate(seq):
            self.after(1500 * (n + 1), lambda f=frac: backlight.set_fraction(self.bl, f))
        self.after(1500 * (len(seq) + 1), self.restore_and_ask)

    def restore_and_ask(self):
        if self.bl and self.bl_original is not None:
            backlight.set_raw(self.bl, self.bl_original)
        self.index = len(PATTERNS) + 1
        self.questions()

    # --- questions ---------------------------------------------------------------------------
    def questions(self):
        T.clear(self)
        box = tk.Frame(self, bg=T.BG)
        box.place(relx=0.5, rely=0.5, anchor="center")
        T.label(box, "Did you notice any of these?", "h1").pack(anchor="w", pady=(0, T.px(1)))
        self.vars = {}
        for key, (text, _, _) in SCREEN_PROBLEMS.items():
            if key == "brightness" and not self.bl:
                continue
            if key == "brightness":
                text = "The brightness did NOT change during the brightness test"
            v = tk.BooleanVar(value=False)
            cb = tk.Checkbutton(box, text=text, variable=v, font=T.FONTS["body"], bg=T.BG, fg=T.FG,
                                selectcolor=T.PANEL_HI, activebackground=T.BG, activeforeground=T.FG,
                                highlightthickness=2, highlightcolor="white", highlightbackground=T.BG,
                                anchor="w", padx=T.px(0.3), pady=T.px(0.2))
            cb.pack(anchor="w", fill="x")
            self.vars[key] = v
        row = tk.Frame(box, bg=T.BG)
        row.pack(anchor="w", pady=T.px(1.2))
        self.done_btn = T.button(row, "Everything looked fine", self.finish, "good")
        self.done_btn.pack(side="left")
        T.button(row, "Show the colours again", self.start, "secondary").pack(side="left", padx=T.px(1))
        for v in self.vars.values():
            v.trace_add("write", lambda *a: self.update_done())
        T.label(box, "Tip: use Tab to move between options and Space to tick them.", "small",
                T.MUTED).pack(anchor="w")
        self.done_btn.focus_set()

    def update_done(self):
        any_ticked = any(v.get() for v in self.vars.values())
        self.done_btn.configure(text="Report the ticked problems" if any_ticked else "Everything looked fine",
                                bg="#b91c1c" if any_ticked else "#15803d")

    def finish(self):
        problems = [k for k, v in self.vars.items() if v.get()]
        self.on_done(screen_result(problems, bool(self.bl)))
