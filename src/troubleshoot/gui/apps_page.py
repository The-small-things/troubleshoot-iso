"""Games & apps page (from the welcome screen) and the Wi-Fi setup page."""

from __future__ import annotations

import threading
import tkinter as tk

from .. import apps
from . import theme as T
from .mascot import Mascot
from .picker import app_specs, builtin_specs, grid


class AppsPage(tk.Frame):
    def __init__(self, master, on_back, on_play_builtin, on_wifi):
        super().__init__(master, bg=T.BG)
        self.on_wifi = on_wifi
        top = tk.Frame(self, bg=T.BG)
        top.pack(fill="x", padx=T.px(1.5), pady=(T.px(1), T.px(0.4)))
        T.button(top, "◀  Back", on_back, "secondary", "small").pack(side="left")
        Mascot(top, T.px(3), "excited").pack(side="left", padx=(T.px(1), T.px(0.5)))
        T.label(top, "Games & apps", "h1").pack(side="left")
        T.button(top, "Wi-Fi & internet", on_wifi, "secondary", "small").pack(side="right", padx=(0, T.px(7)))
        self.status = T.label(self, "Apps open in their own window – close it (✕ at the top right) to come back "
                                    "here. Nothing you do in these apps affects the test results.",
                              "small", T.MUTED, wrap=T.px(80))
        self.status.pack(anchor="w", padx=T.px(1.5))

        scroll = T.ScrollFrame(self)
        scroll.pack(fill="both", expand=True, padx=T.px(1.5), pady=T.px(0.6))
        body = scroll.inner
        cols = 4
        self.section(body, "Chip's Arcade", grid(body, builtin_specs(on_play_builtin), cols))
        for key, title in apps.CATEGORIES:
            specs = app_specs(self, key, self.launch, T.px(2.2))
            if specs:
                self.section(body, title, grid(body, specs, cols))
        if not apps.installed():
            T.label(body, "No extra apps are installed on this system.", fg=T.MUTED).pack(anchor="w")

    def section(self, body, title, content):
        T.label(body, title, "h2").pack(anchor="w", pady=(T.px(0.8), T.px(0.2)))
        content.pack(fill="x")

    def launch(self, app: apps.App):
        if app.category == "internet" and not apps.online():
            self.on_wifi(then=app)
            return
        err = apps.launch(app)
        self.status.configure(text=err or f"Starting {app.name}… it opens in its own window. "
                                          "Close it to come back here.", fg=T.BAD if err else T.GOOD)


class WifiPage(tk.Frame):
    """Connect to Wi-Fi with NetworkManager (Ethernet connects by itself)."""

    def __init__(self, master, on_back, then: apps.App | None = None):
        super().__init__(master, bg=T.BG)
        self.on_back, self.then = on_back, then
        top = tk.Frame(self, bg=T.BG)
        top.pack(fill="x", padx=T.px(1.5), pady=(T.px(1), T.px(0.4)))
        T.button(top, "◀  Back", on_back, "secondary", "small").pack(side="left")
        T.label(top, "   Wi-Fi & internet", "h1").pack(side="left")
        self.refresh_btn = T.button(top, "Scan again", self.scan, "secondary", "small")
        self.refresh_btn.pack(side="right", padx=(0, T.px(7)))
        self.status = T.label(self, "", "body", T.MUTED, wrap=T.px(70))
        self.status.pack(anchor="w", padx=T.px(1.5))
        if then is not None:
            row = tk.Frame(self, bg=T.BG)
            row.pack(anchor="w", padx=T.px(1.5), pady=(T.px(0.3), 0))
            T.button(row, f"Open {then.name} anyway", lambda: (apps.launch(then), on_back()), "secondary",
                     "small").pack(side="left")
        self.list = T.ScrollFrame(self)
        self.list.pack(fill="both", expand=True, padx=T.px(1.5), pady=T.px(0.6))
        self.form = tk.Frame(self, bg=T.BG)
        self.form.pack(fill="x", padx=T.px(1.5), pady=(0, T.px(1)))
        self.scan()

    def scan(self):
        self.status.configure(text="Looking for Wi-Fi networks…", fg=T.MUTED)
        T.clear(self.list.inner)

        def work():
            if not apps.which("nmcli"):
                return None, False
            return apps.wifi_networks(), apps.online()
        threading.Thread(target=lambda: self._done(*work()), daemon=True).start()

    def _done(self, nets, online):
        self.after(0, lambda: self.show(nets, online))

    def show(self, nets, online):
        if not self.winfo_exists():
            return
        if nets is None:
            self.status.configure(text="The networking service isn't running, so Wi-Fi can't be set up here.",
                                  fg=T.BAD)
            return
        msg = "You're online! " if online else "Not connected yet. Plugging in a network cable also works. "
        self.status.configure(text=msg + ("Pick a network:" if nets else "No Wi-Fi networks found."),
                              fg=T.GOOD if online else T.MUTED)
        for n in nets:
            bars = "▂▄▆█"[: max(1, min(4, n["signal"] // 25 + 1))]
            label = f"{bars}   {n['ssid']}" + ("   (password)" if n["secure"] else "   (open)") + ("   ✔ connected" if n["connected"] else "")
            c = T.Card(self.list.inner, command=lambda n=n: self.choose(n), pad=T.px(0.5))
            T.label(c.body, label, "body", bg=T.PANEL).pack(anchor="w")
            c.pack(fill="x", pady=T.px(0.15))
        if online and self.then is not None:
            T.button(self.form, f"Open {self.then.name}", self.open_then, "good").pack(anchor="w")

    def choose(self, net):
        T.clear(self.form)
        T.label(self.form, f"Connect to “{net['ssid']}”", "h2").pack(anchor="w")
        row = tk.Frame(self.form, bg=T.BG)
        row.pack(anchor="w", pady=T.px(0.4))
        entry = None
        if net["secure"]:
            T.label(row, "Password: ", bg=T.BG).pack(side="left")
            entry = tk.Entry(row, show="•", font=T.FONTS["body"], width=28, bg=T.PANEL, fg=T.FG,
                             insertbackground=T.FG, relief="flat")
            entry.pack(side="left", ipady=T.px(0.3))
            entry.focus_set()
            entry.bind("<Return>", lambda e: self.connect(net, entry))
        T.button(row, "Connect", lambda: self.connect(net, entry)).pack(side="left", padx=T.px(0.6))

    def connect(self, net, entry):
        pw = entry.get() if entry is not None else None
        self.status.configure(text=f"Connecting to {net['ssid']}…", fg=T.MUTED)

        def work():
            ok, msg = apps.wifi_connect(net["ssid"], pw)
            self.after(0, lambda: self.connected(ok, msg))
        threading.Thread(target=work, daemon=True).start()

    def connected(self, ok, msg):
        if not self.winfo_exists():
            return
        if ok:
            T.clear(self.form)
            self.status.configure(text="Connected! You're online.", fg=T.GOOD)
            if self.then is not None:
                T.button(self.form, f"Open {self.then.name}", self.open_then, "good").pack(anchor="w")
        else:
            self.status.configure(text="Couldn't connect – check the password and try again. " + msg, fg=T.BAD)

    def open_then(self):
        apps.launch(self.then)
        self.on_back()
