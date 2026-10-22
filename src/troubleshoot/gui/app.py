"""Main window: profile choice → hands-on tests → automatic tests → results."""

from __future__ import annotations

import os
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox

from .. import catalog, report, util
from ..checks import sysinfo
from ..model import Context, Result, Status
from ..runner import run_one
from . import theme as T
from .audio import AudioTest
from .keyboard import KeyboardTest
from .mascot import Bubble, Mascot, Pulse
from .picker import GamePicker
from .pointer import PointerTest
from .screen import ScreenTest
from .webcam import WebcamTest

INTERACTIVE_PAGES = {"screen": ScreenTest, "keyboard": KeyboardTest, "pointer": PointerTest,
                     "webcam": WebcamTest, "audio": AudioTest}

# What Chip says while each automatic test runs.
CHATTER = {
    "sysinfo": "Getting to know this computer…",
    "graphics": "Checking the graphics chip has a proper driver…",
    "battery": "Checking how healthy the battery is…",
    "network": "Listening for Wi-Fi networks…",
    "bluetooth": "Saying hello to Bluetooth gadgets nearby…",
    "storage": "Reading the drives' health diaries. I only read – I never change anything!",
    "memory": "Writing patterns into the memory and checking every one comes back the same…",
    "cpu": "Giving the processor a proper workout. It's supposed to get warm and loud!",
    "kernel_log": "Checking whether any hardware complained while I was testing…",
}

VERDICT_FACE = {Status.PASS: "excited", Status.WARN: "thinking", Status.FAIL: "worried"}
VERDICT_LINE = {
    Status.PASS: "Great news – everything I tested looks healthy!",
    Status.WARN: "Mostly good! A few things could use some attention.",
    Status.FAIL: "I found some problems. Don't worry – I'll explain each one and what to do.",
}


class App:
    def __init__(self, fast: bool = False, windowed: bool = False):
        self.fast = fast
        self.root = tk.Tk(className="troubleshoot")
        self.root.title("Hardware Troubleshooter")
        T.setup(self.root)
        if windowed:
            self.root.geometry(os.environ.get("TROUBLESHOOT_GEOMETRY", "1366x768+0+0"))
        else:
            self.root.geometry(f"{self.root.winfo_screenwidth()}x{self.root.winfo_screenheight()}+0+0")
            self.root.attributes("-fullscreen", True)
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)  # only our own buttons may close it
        self.page: tk.Frame | None = None
        self.info = sysinfo.collect()
        self.welcome()
        marker = os.environ.get("TROUBLESHOOT_STARTED_FILE")
        if marker:
            open(marker, "a").close()

    def run(self):
        self.root.mainloop()

    def show(self, frame: tk.Frame):
        if self.page is not None:
            self.page.destroy()
        for seq in ("1", "2", "3", "4", "s", "S"):
            self.root.unbind(f"<KeyPress-{seq}>")
        self.page = frame
        frame.pack(fill="both", expand=True)

    # --- 1. welcome --------------------------------------------------------------------------
    def welcome(self):
        page = tk.Frame(self.root, bg=T.BG)
        self.power_bar(page)
        Pulse(page, T.px(2.2)).pack(side="top", fill="x", pady=(T.px(1), 0))
        inner = tk.Frame(page, bg=T.BG)
        inner.place(relx=0.5, rely=0.5, anchor="center")

        left = tk.Frame(inner, bg=T.BG)
        left.pack(side="left", anchor="n", padx=(0, T.px(2.5)))
        Mascot(left, T.px(12), "happy").pack(anchor="w")
        Bubble(left, "Hi, I'm Chip! I'll give this computer a full check-up and explain "
                     "everything I find in plain words.\n\nHow thorough should I be?",
               wrap=T.px(15), tail="top").pack(anchor="w", pady=(T.px(0.5), 0))

        right = tk.Frame(inner, bg=T.BG)
        right.pack(side="left", anchor="n")
        T.label(right, "Hardware Troubleshooter", "huge").pack(anchor="w")
        T.label(right, f"{self.info['vendor']} {self.info['product']}  ·  {self.info['cpu']}  ·  "
                       f"{self.info['ram_total']} RAM", fg=T.MUTED, wrap=T.px(44)).pack(anchor="w", pady=(0, T.px(1.2)))
        for n, prof in enumerate(catalog.PROFILES.values(), start=1):
            icon, color = T.PROFILE_STYLE[prof.key]
            card = T.Card(right, command=lambda p=prof: self.choose(p))
            card.pack(fill="x", pady=T.px(0.3))
            card.configure(width=T.px(36))
            row = tk.Frame(card.body, bg=T.PANEL)
            row.pack(fill="x")
            badge = tk.Canvas(row, width=T.px(2.6), height=T.px(2.6), bg=T.PANEL, highlightthickness=0)
            T.rounded(badge, 0, 0, T.px(2.6), T.px(2.6), T.px(0.7), fill=color, outline="")
            badge.create_text(T.px(1.3), T.px(1.3), text=icon, fill="white", font=T.FONTS["icon"])
            badge.pack(side="left", anchor="n", padx=(0, T.px(0.9)))
            text = tk.Frame(row, bg=T.PANEL)
            text.pack(side="left", fill="x", expand=True)
            head = tk.Frame(text, bg=T.PANEL)
            head.pack(fill="x")
            T.label(head, f"{prof.title}", "h2", bg=T.PANEL).pack(side="left")
            if prof.key == "standard":
                tk.Label(head, text=" Recommended ", font=T.FONTS["small"], bg=color, fg="white").pack(
                    side="left", padx=T.px(0.6))
            T.label(head, f"{prof.duration}   [{n}]", "small", T.MUTED, bg=T.PANEL).pack(side="right")
            T.label(text, prof.description, "small", T.MUTED, bg=T.PANEL, wrap=T.px(30)).pack(anchor="w")
        T.label(right, "Press 1–4 or click. Nothing on your disks is ever changed. For a deep memory test, "
                       "restart and pick \"Memory test\" in the boot menu.", "small", T.MUTED,
                wrap=T.px(36)).pack(anchor="w", pady=(T.px(0.6), 0))
        self.show(page)
        # Bind keys after show() (which clears old bindings).
        for n, prof in enumerate(catalog.PROFILES.values(), start=1):
            self.root.bind(f"<KeyPress-{n}>", lambda e, p=prof: self.choose(p))

    def arcade(self):
        """Just the games, no testing (from the welcome screen)."""
        page = tk.Frame(self.root, bg=T.BG)
        top = tk.Frame(page, bg=T.BG)
        top.pack(fill="x", padx=T.px(1.5), pady=(T.px(1), 0))
        T.button(top, "◀  Back", self.welcome, "secondary", "small").pack(side="left")
        T.label(top, "   Chip's Arcade", "h1").pack(side="left")
        area = tk.Frame(page, bg=T.BG)
        area.pack(fill="both", expand=True, padx=T.px(1.5), pady=T.px(1))

        def pick(cls):
            T.clear(area)
            back = tk.Frame(area, bg=T.BG)
            back.pack(fill="x", pady=(0, T.px(0.4)))
            T.button(back, "◀  All games", lambda: show_picker(), "secondary", "small").pack(side="left")
            cls(area).pack(fill="both", expand=True)

        def show_picker():
            T.clear(area)
            box = tk.Frame(area, bg=T.BG)
            box.place(relx=0.5, rely=0.45, anchor="center", relwidth=0.8)
            GamePicker(box, pick).pack(fill="x")
        show_picker()
        self.show(page)

    def power_bar(self, page):
        bar = tk.Frame(page, bg=T.BG)
        bar.pack(side="bottom", fill="x", padx=T.px(1.5), pady=T.px(1))
        T.button(bar, "Power off", lambda: self.power("poweroff"), "secondary", "small").pack(side="right")
        T.button(bar, "Restart", lambda: self.power("reboot"), "secondary", "small").pack(
            side="right", padx=T.px(0.6))
        T.button(bar, "Exit to command line", self.quit, "secondary", "small").pack(side="left")
        T.button(bar, "Chip's Arcade", self.arcade, "secondary", "small").pack(side="left", padx=T.px(0.6))

    def power(self, action):
        if not messagebox.askyesno("Confirm", "Power off the computer?" if action == "poweroff"
                                   else "Restart the computer?", parent=self.root):
            return
        if util.is_root() and not self.fast:
            util.run(["systemctl", action])
        self.root.destroy()

    def quit(self):
        self.root.destroy()

    def choose(self, prof: catalog.Profile):
        if prof.key == "custom":
            self.custom(prof)
        else:
            self.start(prof, None)

    # --- 1b. custom selection ----------------------------------------------------------------
    def custom(self, prof):
        page = tk.Frame(self.root, bg=T.BG)
        inner = tk.Frame(page, bg=T.BG)
        inner.place(relx=0.5, rely=0.5, anchor="center")
        T.label(inner, "Choose tests", "h1").pack(anchor="w", pady=(0, T.px(1)))
        vars_: dict[str, tk.BooleanVar] = {}
        for tid in catalog.ORDER:
            if tid == "sysinfo":
                continue
            spec = catalog.TESTS[tid]
            v = tk.BooleanVar(value=True)
            tk.Checkbutton(inner, text=f"{spec.name} – {spec.description}", variable=v, bg=T.BG, fg=T.FG,
                           selectcolor=T.PANEL_HI, activebackground=T.BG, activeforeground=T.FG,
                           highlightthickness=2, highlightcolor="white", highlightbackground=T.BG,
                           font=T.FONTS["body"], anchor="w").pack(anchor="w", fill="x")
            vars_[tid] = v
        row = tk.Frame(inner, bg=T.BG)
        row.pack(anchor="w", pady=T.px(1.2))
        b = T.button(row, "Start", lambda: self.start(prof, {k for k, v in vars_.items() if v.get()}))
        b.pack(side="left")
        T.button(row, "Back", self.welcome, "secondary").pack(side="left", padx=T.px(1))
        self.show(page)
        b.focus_set()

    # --- 2. running the plan -----------------------------------------------------------------
    def start(self, prof: catalog.Profile, only: set[str] | None):
        self.profile = prof
        self.plan = catalog.plan(prof, only)
        self.results: list[Result] = []
        self.idx = 0
        self.run_page = None
        has_interactive = any(spec.interactive for spec, _ in self.plan)
        if has_interactive:
            self.interactive_intro()
        else:
            self.next()

    def interactive_intro(self):
        page = tk.Frame(self.root, bg=T.BG)
        inner = tk.Frame(page, bg=T.BG)
        inner.place(relx=0.5, rely=0.5, anchor="center")
        names = [spec.name.lower() for spec, _ in self.plan if spec.interactive]
        Mascot(inner, T.px(9), "excited").pack(side="left", anchor="n", padx=(0, T.px(1.5)))
        col = tk.Frame(inner, bg=T.BG)
        col.pack(side="left")
        T.label(col, "Part 1: let's do this together", "h1").pack(anchor="w")
        Bubble(col, "First I need your eyes, ears and fingers for a few minutes – we'll check the "
                    + ", ".join(names) + ".\n\nAfter that I'll run the automatic tests on my own, and you "
                    "can walk away (or play a game). Laptops: please keep the charger plugged in.",
               wrap=T.px(30)).pack(anchor="w", pady=T.px(1))
        b = T.button(col, "Let's go!  (Enter)", self.next)
        b.pack(anchor="w")
        self.show(page)
        b.focus_set()

    def next(self):
        if self.idx >= len(self.plan):
            if self.run_page is not None and self.run_page.winfo_exists() and self.run_page.game is not None:
                return self.run_page.all_done(self.results_page)  # don't interrupt a game
            return self.results_page()
        spec, params = self.plan[self.idx]
        if spec.interactive:
            self.run_page = None
            page = INTERACTIVE_PAGES[spec.test_id](self.root, self.record)
            self.show(page)
        else:
            if self.run_page is None or not self.run_page.winfo_exists():
                self.run_page = RunPage(self.root, self)
                self.show(self.run_page)
            self.run_page.start_test(spec, params)

    def record(self, result: Result):
        self.results.append(result)
        self.idx += 1
        self.root.after(10, self.next)

    # --- 3. results --------------------------------------------------------------------------
    def results_page(self):
        self.show(ResultsPage(self.root, self))


class RunPage(tk.Frame):
    """Progress screen for the unattended tests."""

    def __init__(self, master, app: App):
        super().__init__(master, bg=T.BG)
        self.app = app
        self.q: queue.Queue = queue.Queue()
        self.cancel = threading.Event()
        self.anim = 0

        left = tk.Frame(self, bg=T.PANEL, width=T.px(20))
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        self.chip = Mascot(left, T.px(7), "thinking", bg=T.PANEL)
        self.chip.pack(anchor="w", padx=T.px(1), pady=(T.px(1), 0))
        self.bubble = Bubble(left, "", wrap=T.px(15), font="small", fill=T.BG)
        self.bubble.pack(anchor="w", padx=T.px(0.6), pady=(T.px(0.4), T.px(0.8)))
        T.label(left, "Tests", "bold", T.MUTED, bg=T.PANEL).pack(anchor="w", padx=T.px(1))
        self.rows: dict[str, tuple[tk.Label, tk.Label]] = {}
        done = {r.test_id: r for r in app.results}
        for spec, _ in app.plan:
            row = tk.Frame(left, bg=T.PANEL)
            row.pack(fill="x", padx=T.px(1), pady=T.px(0.15))
            icon = T.label(row, "·", "bold", T.MUTED, bg=T.PANEL, width=2)
            icon.pack(side="left")
            name = T.label(row, spec.name, "body", T.MUTED, bg=T.PANEL)
            name.pack(side="left")
            self.rows[spec.test_id] = (icon, name)
            if spec.test_id in done:
                self.mark(spec.test_id, done[spec.test_id].status)

        right = tk.Frame(self, bg=T.BG)
        right.pack(side="left", fill="both", expand=True, padx=T.px(2), pady=T.px(1.5))
        interactive_done = any(s.interactive for s, _ in app.plan)
        T.label(right, ("Part 2: " if interactive_done else "") + "automatic tests", "small", T.ACCENT_HI).pack(anchor="w")
        self.title = T.label(right, "", "h1")
        self.title.pack(anchor="w")
        self.desc = T.label(right, "", "body", T.MUTED, wrap=T.px(45))
        self.desc.pack(anchor="w")
        self.bar = tk.Canvas(right, height=T.px(1.4), bg=T.PANEL, highlightthickness=0)
        self.bar.pack(fill="x", pady=(T.px(1.5), T.px(0.5)))
        self.msg = T.label(right, "", "body")
        self.msg.pack(anchor="w")
        self.overall = T.label(right, "", "small", T.MUTED)
        self.overall.pack(anchor="w", pady=(T.px(0.3), 0))
        self.sensors = T.label(right, "", "small", T.MUTED)
        self.sensors.pack(anchor="w")
        btns = tk.Frame(right, bg=T.BG)
        btns.pack(fill="x", pady=T.px(0.8))
        self.skip_btn = T.button(btns, "Skip this test  (S)", self.skip, "secondary", "small", takefocus=0)
        self.skip_btn.pack(side="left")
        self.games_btn = T.button(btns, "Play a game while you wait", self.show_games, "primary", "small",
                                  takefocus=0)
        self.games_btn.pack(side="right", padx=(T.px(0.5), 0))
        self.log_btn = T.button(btns, "Test log", self.show_log, "secondary", "small", takefocus=0)
        self.log_btn.pack(side="right")
        self.done_banner = tk.Frame(right, bg=T.GOOD)
        self.content = tk.Frame(right, bg=T.BG)
        self.content.pack(fill="both", expand=True)
        self.log = tk.Text(self.content, height=8, bg="#0b1220", fg=T.MUTED, font=T.FONTS["mono"], relief="flat",
                           highlightthickness=0, wrap="none", state="disabled")
        self.picker = None
        self.game = None
        self.show_games()
        self.frac: float | None = 0.0
        self.after(100, self.poll)
        self.after(500, self.update_sensors)

    def mark(self, tid: str, status: Status | None):
        icon, name = self.rows[tid]
        if status is None:
            icon.configure(text="▶", fg=T.ACCENT_HI)
            name.configure(fg=T.FG)
        else:
            icon.configure(text=T.STATUS_ICONS[status], fg=T.STATUS_COLORS[status])
            name.configure(fg=T.MUTED)

    # --- games ------------------------------------------------------------------------------
    def show_games(self):
        self.close_game()
        self.log.pack_forget()
        self.set_skip_keys(True)
        if self.picker is None:
            self.picker = tk.Frame(self.content, bg=T.BG)
            T.label(self.picker, "You can walk away now – or play something while I work:", "small",
                    T.MUTED).pack(anchor="w", pady=(0, T.px(0.3)))
            GamePicker(self.picker, self.play).pack(fill="x")
        self.picker.pack(fill="both", expand=True)

    def play(self, cls):
        self.close_game()
        self.log.pack_forget()
        if self.picker is not None:
            self.picker.pack_forget()
        self.set_skip_keys(False)  # S is a game key (WASD)
        self.game = cls(self.content)
        self.game.pack(fill="both", expand=True)

    def close_game(self):
        if self.game is not None:
            self.game.destroy()
            self.game = None

    def show_log(self):
        self.close_game()
        if self.picker is not None:
            self.picker.pack_forget()
        self.log.pack(fill="both", expand=True)
        self.set_skip_keys(True)

    def set_skip_keys(self, on: bool):
        for k in ("<KeyPress-s>", "<KeyPress-S>"):
            if on:
                self.app.root.bind(k, lambda e: self.skip())
            else:
                self.app.root.unbind(k)

    def all_done(self, show_results):
        """Tests finished while a game is open: offer the results instead of switching away."""
        self.title.configure(text="All tests are done!")
        self.chip.set("excited")
        self.bubble.set("All done! Finish your game, then let's look at the results together.")
        self.desc.configure(text="")
        self.msg.configure(text="Finish your game, then open the results.")
        self.frac = 1.0
        self.skip_btn.configure(state="disabled")
        b = self.done_banner
        b.pack(fill="x", pady=(0, T.px(0.6)), before=self.content)
        T.label(b, "✔  All tests are finished.", "bold", "white").pack(side="left", padx=T.px(1), pady=T.px(0.5))
        T.button(b, "See the results", show_results, "secondary", takefocus=0).pack(side="right", padx=T.px(0.6),
                                                                                    pady=T.px(0.4))

    def start_test(self, spec, params):
        self.set_skip_keys(self.game is None)
        self.spec = spec
        self.cancel = threading.Event()
        self.title.configure(text=spec.name)
        self.desc.configure(text=spec.description)
        self.bubble.set(CHATTER.get(spec.test_id, "Working on it…"))
        self.chip.set("thinking")
        self.msg.configure(text="Starting…")
        self.frac = 0.0
        self.started = time.monotonic()
        self.mark(spec.test_id, None)
        auto = [s for s, _ in self.app.plan if not s.interactive]
        pos = auto.index(spec) + 1
        self.overall.configure(text=f"Automatic test {pos} of {len(auto)}")
        self.skip_btn.configure(state="normal")
        ctx = Context(params=params, cancel=self.cancel,
                      progress=lambda f, m: self.q.put(("progress", f, m)),
                      log=lambda l: self.q.put(("log", l)),
                      time_scale=0.05 if self.app.fast else 1.0)
        threading.Thread(target=lambda: self.q.put(("done", run_one(spec, ctx))), daemon=True).start()

    def skip(self):
        self.cancel.set()
        self.skip_btn.configure(state="disabled")
        self.msg.configure(text="Stopping…")

    def poll(self):
        if not self.winfo_exists():
            return
        try:
            while True:
                item = self.q.get_nowait()
                if item[0] == "progress":
                    self.frac, text = item[1], item[2]
                    self.msg.configure(text=text)
                elif item[0] == "log":
                    self.log.configure(state="normal")
                    self.log.insert("end", item[1].rstrip() + "\n")
                    self.log.see("end")
                    self.log.configure(state="disabled")
                elif item[0] == "done":
                    res: Result = item[1]
                    self.mark(res.test_id, res.status)
                    self.app.record(res)
                    if not self.winfo_exists():
                        return
        except queue.Empty:
            pass
        self.draw_bar()
        self.after(100, self.poll)

    def draw_bar(self):
        c = self.bar
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if self.frac is None:  # unknown duration: bouncing block
            self.anim = (self.anim + 6) % (2 * w or 1)
            x = self.anim if self.anim < w else 2 * w - self.anim
            c.create_rectangle(max(0, x - w * 0.15), 0, min(w, x + w * 0.15), h, fill=T.ACCENT, outline="")
        else:
            c.create_rectangle(0, 0, w * max(0.0, min(1.0, self.frac)), h, fill=T.ACCENT, outline="")

    def update_sensors(self):
        if not self.winfo_exists():
            return
        temps = util.cpu_temps()
        parts = []
        if temps:
            parts.append(f"CPU temperature: {max(temps.values()):.0f} °C")
        fans = util.fan_speeds()
        if fans:
            parts.append("Fan: " + ", ".join(f"{v} RPM" for v in list(fans.values())[:3]))
        if hasattr(self, "started"):
            parts.append(f"Elapsed: {util.fmt_duration(time.monotonic() - self.started)}")
        self.sensors.configure(text="   ·   ".join(parts))
        self.after(2000, self.update_sensors)


class ResultsPage(tk.Frame):
    def __init__(self, master, app: App):
        super().__init__(master, bg=T.BG)
        self.app = app
        results = app.results
        status, head, para = report.verdict(results)

        banner = tk.Frame(self, bg=T.STATUS_COLORS[status])
        banner.pack(fill="x")
        Mascot(banner, T.px(5.5), VERDICT_FACE.get(status, "happy")).pack(side="left", padx=(T.px(1.5), T.px(1)),
                                                                          pady=T.px(0.6))
        words = tk.Frame(banner, bg=T.STATUS_COLORS[status])
        words.pack(side="left", fill="x", expand=True, pady=T.px(0.6))
        T.label(words, head, "h1", "white").pack(anchor="w")
        line = VERDICT_LINE.get(status, "") + ("" if status is Status.PASS else " " + para)
        T.label(words, line, "body", "white", wrap=T.px(70)).pack(anchor="w")

        bar = tk.Frame(self, bg=T.BG)
        bar.pack(side="bottom", fill="x", padx=T.px(1.5), pady=T.px(1))
        T.button(bar, "Save report to USB drive", self.save).pack(side="left")
        T.button(bar, "Run another test", app.welcome, "secondary").pack(side="left", padx=T.px(1))
        T.button(bar, "Power off", lambda: app.power("poweroff"), "secondary").pack(side="right")
        T.button(bar, "Restart", lambda: app.power("reboot"), "secondary").pack(side="right", padx=T.px(1))
        self.saved = T.label(self, "", "small", T.MUTED)
        self.saved.pack(side="bottom", anchor="w", padx=T.px(1.5))

        body = tk.Frame(self, bg=T.BG)
        body.pack(fill="both", expand=True, padx=T.px(1.5), pady=(T.px(1), 0))
        left = tk.Frame(body, bg=T.BG, width=T.px(24))
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        T.label(left, "Results – select one for details", "small", T.MUTED).pack(anchor="w", pady=(0, T.px(0.3)))
        self.items: list[tuple[tk.Frame, Result | None]] = []
        self.add_item(left, None, "Summary & next steps", T.STATUS_COLORS[status], T.STATUS_ICONS[status])
        for r in report.sorted_results(results):
            self.add_item(left, r, r.name, T.STATUS_COLORS[r.status], T.STATUS_ICONS[r.status])

        self.text = tk.Text(body, bg=T.PANEL, fg=T.FG, font=T.FONTS["body"], relief="flat", wrap="word",
                            padx=T.px(1.2), pady=T.px(1), highlightthickness=0, cursor="arrow")
        sb = tk.Scrollbar(body, command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True, padx=(T.px(1), 0))
        self.text.tag_configure("h", font=T.FONTS["h2"], spacing3=T.px(0.4))
        self.text.tag_configure("sub", font=T.FONTS["bold"], spacing1=T.px(0.8), spacing3=T.px(0.2))
        self.text.tag_configure("muted", foreground=T.MUTED)
        self.text.tag_configure("bullet", lmargin1=T.px(0.6), lmargin2=T.px(1.6), spacing1=T.px(0.15))
        for s, col in T.STATUS_COLORS.items():
            self.text.tag_configure(s.value, foreground=col, font=T.FONTS["bold"])
        self.sel = 0
        self.select(0)
        self.bind_all("<Up>", lambda e: self.select(max(0, self.sel - 1)))
        self.bind_all("<Down>", lambda e: self.select(min(len(self.items) - 1, self.sel + 1)))
        self.bind("<Destroy>", lambda e: (self.unbind_all("<Up>"), self.unbind_all("<Down>")) if e.widget is self else None)

    def add_item(self, parent, result, text, color, icon):
        i = len(self.items)
        row = tk.Frame(parent, bg=T.BG, cursor="hand2")
        row.pack(fill="x", pady=1)
        a = T.label(row, icon, "bold", color, width=2)
        a.pack(side="left")
        b = T.label(row, text, "body")
        b.pack(side="left", fill="x", expand=True)
        for w in (row, a, b):
            w.bind("<Button-1>", lambda e, i=i: self.select(i))
        self.items.append((row, result))

    def select(self, i):
        self.sel = i
        for n, (row, _) in enumerate(self.items):
            bg = T.PANEL_HI if n == i else T.BG
            row.configure(bg=bg)
            for w in row.winfo_children():
                w.configure(bg=bg)
        r = self.items[i][1]
        t = self.text
        t.configure(state="normal")
        t.delete("1.0", "end")
        if r is None:
            self.render_summary()
        else:
            t.insert("end", r.name + "\n", "h")
            t.insert("end", r.status.label.upper(), r.status.value)
            t.insert("end", f"   {r.summary}\n")
            if r.details:
                t.insert("end", "What we found\n", "sub")
                for d in r.details:
                    t.insert("end", f"•  {d}\n", ("bullet", "muted"))
            if r.explanation and r.status is not Status.INFO:
                t.insert("end", "What this means\n", "sub")
                t.insert("end", r.explanation + "\n")
            if r.next_steps:
                t.insert("end", "What to do next\n", "sub")
                for n, s in enumerate(r.next_steps, 1):
                    t.insert("end", f"{n}.  {s}\n", "bullet")
            if r.duration >= 1:
                t.insert("end", f"\nTest time: {util.fmt_duration(r.duration)}\n", "muted")
        t.configure(state="disabled")

    def render_summary(self):
        t = self.text
        results = self.app.results
        status, head, para = report.verdict(results)
        t.insert("end", "Summary\n", "h")
        counts = {s: sum(1 for r in results if r.status is s) for s in Status}
        for s in (Status.FAIL, Status.WARN, Status.PASS, Status.SKIP):
            if counts[s]:
                t.insert("end", f"{counts[s]} {s.label.lower()}   ", s.value)
        t.insert("end", f"\nProfile: {self.app.profile.title}\n", "muted")
        problems = [r for r in report.sorted_results(results) if r.status in (Status.FAIL, Status.WARN)]
        if problems:
            t.insert("end", "Most important things to do\n", "sub")
            n = 1
            for r in problems:
                if r.next_steps:
                    t.insert("end", f"{n}.  {r.name}: {r.next_steps[0]}\n", "bullet")
                    n += 1
            t.insert("end", "\nSelect a test on the left for the full explanation.\n", "muted")
        else:
            t.insert("end", "Next steps\n", "sub")
            for n, s in enumerate(report.GENERIC_HEALTHY_STEPS, 1):
                t.insert("end", f"{n}.  {s}\n", "bullet")
        skipped = [r for r in results if r.status is Status.SKIP]
        if skipped:
            t.insert("end", "Not tested\n", "sub")
            for r in skipped:
                t.insert("end", f"•  {r.name}: {r.summary}\n", ("bullet", "muted"))

    def save(self):
        try:
            paths = report.save(self.app.results, self.app.profile.title)
            self.saved.configure(text="Saved: " + "  ·  ".join(paths), fg=T.GOOD)
        except OSError as e:
            self.saved.configure(text=f"Could not save the report: {e}", fg=T.BAD)


def main(fast: bool = False, windowed: bool = False) -> None:
    App(fast=fast, windowed=windowed).run()
