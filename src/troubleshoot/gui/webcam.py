"""Webcam test: live preview (a frame every ~second) and a few questions."""

from __future__ import annotations

import os
import tempfile
import threading
import tkinter as tk

from .. import camera
from ..checks.sysinfo import collect_chassis
from ..interactive import WEBCAM_PROBLEMS, webcam_result
from . import theme as T


class WebcamTest(tk.Frame):
    def __init__(self, master, on_done):
        super().__init__(master, bg=T.BG)
        self.on_done = on_done
        self.cams = camera.cameras()
        self.laptop = collect_chassis() in ("Laptop", "Tablet")
        self.tmp = tempfile.mkdtemp(prefix="webcam-")
        self.cam_i = 0
        self.frames = 0
        self.failures = 0
        self.running = True
        self.photo = None
        if not self.cams:
            self.after(10, lambda: self.report(None, [], None))
            return

        head = tk.Frame(self, bg=T.BG)
        head.pack(fill="x", padx=T.px(2), pady=(T.px(1.2), 0))
        T.label(head, "Webcam test", "h1").pack(anchor="w")
        self.sub = T.label(head, "", "body", T.MUTED, wrap=T.px(70))
        self.sub.pack(anchor="w")
        self.view = tk.Label(self, bg="black", text="Starting camera…", fg=T.MUTED, font=T.FONTS["h2"])
        self.view.pack(fill="both", expand=True, padx=T.px(2), pady=T.px(1))
        self.hint = T.label(self, "", "body", T.WARN)
        self.hint.pack(anchor="w", padx=T.px(2))

        T.label(self, "Do you see a clear, live picture of yourself?", "h2").pack(anchor="w", padx=T.px(2))
        row = tk.Frame(self, bg=T.BG)
        row.pack(fill="x", padx=T.px(2), pady=(T.px(0.6), T.px(1.2)))
        first = T.button(row, "Yes, looks good  (Y)", lambda: self.report(True, []), "good")
        first.pack(side="left")
        for key, letter in (("black", "B"), ("blurry", "D"), ("colors", "C")):
            T.button(row, f"{WEBCAM_PROBLEMS[key][0]}  ({letter})", lambda k=key: self.report(False, [k]),
                     "bad", "small").pack(side="left", padx=(T.px(0.6), 0))
            self.bind_all(f"<KeyPress-{letter.lower()}>", lambda e, k=key: self.report(False, [k]))
        self.bind_all("<KeyPress-y>", lambda e: self.report(True, []))
        if len(self.cams) > 1:
            T.button(row, "Next camera  (N)", self.next_camera, "secondary", "small").pack(side="right")
            self.bind_all("<KeyPress-n>", lambda e: self.next_camera())
        first.focus_set()
        self.update_sub()
        self.grab_loop()

    def update_sub(self):
        cam = self.cams[self.cam_i]
        extra = f" (camera {self.cam_i + 1} of {len(self.cams)} – some laptops have a separate infrared " \
                "face-login camera that shows a grey picture)" if len(self.cams) > 1 else ""
        self.sub.configure(text=f"{cam['name']}{extra}. The picture refreshes about once a second. "
                                "Many laptop cameras show a small light when in use.")

    def next_camera(self):
        self.cam_i = (self.cam_i + 1) % len(self.cams)
        self.frames = self.failures = 0
        self.update_sub()

    def grab_loop(self):
        if not self.running:
            return
        path = os.path.join(self.tmp, f"frame{self.frames % 2}.png")
        dev = self.cams[self.cam_i]["dev"]

        def work():
            ok = camera.capture(dev, path)
            if self.running:
                self.after(0, lambda: self.show(ok, path))
        threading.Thread(target=work, daemon=True).start()

    def show(self, ok, path):
        if not self.running or not self.winfo_exists():
            return
        if ok:
            try:
                img = tk.PhotoImage(file=path)
            except tk.TclError:
                ok = False
        if ok:
            self.frames += 1
            avail_h = max(1, self.view.winfo_height())
            zoom = max(1, min(3, avail_h // max(1, img.height())))
            self.photo = img.zoom(zoom) if zoom > 1 else img
            self.view.configure(image=self.photo, text="")
            level = self.brightness(img)
            self.hint.configure(text="The picture is almost completely dark – is a privacy shutter closed?"
                                if level < 0.04 else "")
        else:
            self.failures += 1
            if self.frames == 0 and self.failures >= 3:
                self.view.configure(image="", text="No picture could be captured from this camera.")
        self.after(300, self.grab_loop)

    @staticmethod
    def brightness(img) -> float:
        w, h = img.width(), img.height()
        total, n = 0, 0
        for x in range(w // 10, w, max(1, w // 8)):
            for y in range(h // 10, h, max(1, h // 8)):
                r, g, b = img.get(x, y)[:3]
                total += (r + g + b) / 3
                n += 1
        return total / n / 255 if n else 0.0

    def report(self, seen, problems, capture_ok=True):
        if getattr(self, "_reported", False):
            return
        self._reported = True
        self.running = False
        for k in "ybdcn":
            self.unbind_all(f"<KeyPress-{k}>")
        if self.cams and self.frames == 0:
            capture_ok = False
        names = [c["name"] for c in self.cams]
        self.on_done(webcam_result(names, seen, problems, self.laptop,
                                   capture_ok if self.cams else None, camera.mipi_camera_present()))
