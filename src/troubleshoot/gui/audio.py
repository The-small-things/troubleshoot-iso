"""Speakers (left/right) and microphone test."""

from __future__ import annotations

import os
import tempfile
import threading
import tkinter as tk

from ..audio import Audio, make_tone, peak_level
from ..interactive import audio_result
from ..model import Result, Status
from . import theme as T

MIC_SECONDS = 4


class AudioTest(tk.Frame):
    def __init__(self, master, on_done):
        super().__init__(master, bg=T.BG)
        self.on_done = on_done
        self.tmp = tempfile.mkdtemp(prefix="audiotest-")
        self.answers: dict[str, bool | None] = {"left": None, "right": None, "mic": None}
        self.mic_level = None
        self.box = tk.Frame(self, bg=T.BG)
        self.box.place(relx=0.5, rely=0.5, anchor="center")
        self.show_message("Preparing sound…")
        threading.Thread(target=self._init_audio, daemon=True).start()

    def _init_audio(self):
        self.audio = Audio()
        if self.audio.available:
            self.audio.prepare()
            make_tone(os.path.join(self.tmp, "left.wav"), "left")
            make_tone(os.path.join(self.tmp, "right.wav"), "right")
        self.after(0, self.start)

    def start(self):
        if not self.audio.available:
            self.on_done(Result(
                "audio", "Speakers & microphone", Status.WARN, "No sound device was detected.",
                explanation="The computer didn't report any sound hardware. On recent laptops this can "
                            "mean the sound chip needs drivers this test system doesn't have; otherwise "
                            "the sound chip may be disabled in the BIOS or faulty.",
                next_steps=["Check the BIOS for a disabled audio device.",
                            "If sound works in your normal OS, you can ignore this."]))
            return
        self.ask_speaker("left")

    # --- helpers -----------------------------------------------------------------------------
    def show_message(self, text, sub=""):
        T.clear(self.box)
        T.label(self.box, "Speakers & microphone", "h1").pack(anchor="w")
        T.label(self.box, text, "h2", wrap=T.px(45)).pack(anchor="w", pady=(T.px(1), T.px(0.3)))
        if sub:
            T.label(self.box, sub, fg=T.MUTED, wrap=T.px(45)).pack(anchor="w")

    def buttons(self, spec):
        """spec: list of (text, command, kind, key)."""
        row = tk.Frame(self.box, bg=T.BG)
        row.pack(anchor="w", pady=T.px(1.2))
        first = None
        self._keys = []
        for text, cmd, kind, key in spec:
            b = T.button(row, f"{text}  ({key.upper()})", cmd, kind)
            b.pack(side="left", padx=(0, T.px(1)))
            first = first or b
            self.bind_all(f"<KeyPress-{key}>", lambda e, c=cmd: c())
            self._keys.append(key)
        first.focus_set()

    def unbind_keys(self):
        for k in getattr(self, "_keys", []):
            self.unbind_all(f"<KeyPress-{k}>")
        self._keys = []

    def in_background(self, work, then):
        def run():
            r = work()
            self.after(0, lambda: then(r))
        threading.Thread(target=run, daemon=True).start()

    # --- speakers ----------------------------------------------------------------------------
    def ask_speaker(self, side):
        self.unbind_keys()
        self.show_message(f"Playing beeps on the {side.upper()} speaker…",
                          "Make sure nothing is plugged into the headphone jack.")
        self.in_background(lambda: self.audio.play(os.path.join(self.tmp, f"{side}.wav")),
                           lambda ok: self.after_play(side))

    def after_play(self, side):
        self.show_message(f"Did you hear beeps from the {side.upper()} side?",
                          f"Device: {self.audio.description}")
        self.buttons([
            ("Yes", lambda: self.answer(side, True), "good", "y"),
            ("No", lambda: self.answer(side, False), "bad", "n"),
            ("Play again", lambda: self.ask_speaker(side), "secondary", "p"),
        ])

    def answer(self, side, heard):
        self.unbind_keys()
        self.answers[side] = heard
        if side == "left":
            self.ask_speaker("right")
        elif self.audio.inp:
            self.mic_intro()
        else:
            self.finish()

    # --- microphone --------------------------------------------------------------------------
    def mic_intro(self):
        self.show_message("Microphone test",
                          f"Press Record, then talk or clap for {MIC_SECONDS} seconds. We'll play the "
                          "recording back to you.")
        self.buttons([("Record", self.record, "primary", "r"),
                      ("Skip microphone test", self.finish, "secondary", "s")])

    def record(self):
        self.unbind_keys()
        self.show_message(f"Recording for {MIC_SECONDS} seconds – talk now!")
        path = os.path.join(self.tmp, "mic.wav")
        self.in_background(lambda: self.audio.record(path, MIC_SECONDS), lambda ok: self.playback(path))

    def playback(self, path):
        self.mic_level = peak_level(path)
        self.show_message("Playing your recording back…")
        self.in_background(lambda: self.audio.play(path), lambda ok: self.ask_mic())

    def ask_mic(self):
        level = self.mic_level
        sub = "" if level is None else f"Recorded level: {level:.0%}"
        if level is not None and level < 0.01:
            sub += " – this is basically silence."
        self.show_message("Did you hear your own voice in the recording?", sub)
        self.buttons([
            ("Yes", lambda: self.mic_answer(True), "good", "y"),
            ("No", lambda: self.mic_answer(False), "bad", "n"),
            ("Record again", self.record, "secondary", "r"),
        ])

    def mic_answer(self, ok):
        self.answers["mic"] = ok
        self.finish()

    def finish(self):
        self.unbind_keys()
        self.on_done(audio_result(self.answers["left"], self.answers["right"], self.answers["mic"],
                                  self.mic_level, self.audio.description))
