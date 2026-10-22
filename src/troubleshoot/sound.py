"""Background music and sound effects, synthesised in pure Python (no audio files to license).

Everything is rendered once to WAV files (at ISO build time into /usr/share/troubleshoot/sounds,
otherwise on first use into a cache directory) and played with pw-play/aplay, so PipeWire mixes
music and effects together.

    python3 -m troubleshoot.sound OUTPUT_DIR     # pre-render all sounds
"""

from __future__ import annotations

import array
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import wave

RATE = 22050
VERSION = "1"  # bump when the sounds change, so caches are rebuilt
SYSTEM_DIR = "/usr/share/troubleshoot/sounds"


# ---------------------------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------------------------

def freq(note: int) -> float:
    """MIDI note number -> Hz."""
    return 440.0 * 2 ** ((note - 69) / 12)


def osc(kind: str, phase: float, duty: float = 0.5) -> float:
    p = phase % 1.0
    if kind == "sine":
        return math.sin(2 * math.pi * p)
    if kind == "square":
        return 1.0 if p < duty else -1.0
    if kind == "triangle":
        return 4 * p - 1 if p < 0.5 else 3 - 4 * p
    if kind == "saw":
        return 2 * p - 1
    raise ValueError(kind)


def tone(buf: list, start: float, dur: float, f: float, vol: float, kind: str = "sine",
         attack: float = 0.005, release: float = 0.05, decay: float = 0.0, duty: float = 0.5,
         slide: float = 0.0, wrap: bool = False) -> None:
    """Add a note to ``buf`` (list of floats). ``decay`` > 0 gives a plucked exponential decay;
    ``slide`` glides the pitch by that many Hz over the note; ``wrap`` folds the tail to the start
    so a loop stays seamless."""
    n = len(buf)
    s0 = int(start * RATE)
    total = int((dur + release) * RATE)
    phase = 0.0
    for i in range(total):
        t = i / RATE
        if t < attack:
            env = t / attack
        elif t < dur:
            env = math.exp(-(t - attack) * decay) if decay else 1.0
        else:
            held = math.exp(-(dur - attack) * decay) if decay else 1.0
            env = held * max(0.0, 1 - (t - dur) / release) if release else 0.0
        f_now = f + slide * min(1.0, t / max(dur, 1e-6))
        phase += f_now / RATE
        idx = s0 + i
        if idx >= n:
            if not wrap:
                break
            idx -= n
        buf[idx] += vol * env * osc(kind, phase, duty)


def noise(buf: list, start: float, dur: float, vol: float, decay: float = 30.0, bright: bool = True,
          wrap: bool = False, seed: int = 1) -> None:
    rng = random.Random(seed)
    n = len(buf)
    s0 = int(start * RATE)
    last = 0.0
    for i in range(int(dur * RATE)):
        x = rng.uniform(-1, 1)
        if bright:  # crude high-pass: difference of successive samples
            x, last = x - last, x
        else:       # crude low-pass
            last = last * 0.85 + x * 0.15
            x = last * 2.5
        idx = s0 + i
        if idx >= n:
            if not wrap:
                break
            idx -= n
        buf[idx] += vol * math.exp(-i / RATE * decay) * x


def kick(buf, start, vol=0.9, wrap=False):
    n = len(buf)
    s0 = int(start * RATE)
    phase = 0.0
    for i in range(int(0.18 * RATE)):
        t = i / RATE
        f = 45 + 110 * math.exp(-t * 30)
        phase += f / RATE
        idx = s0 + i
        if idx >= n:
            if not wrap:
                break
            idx -= n
        buf[idx] += vol * math.exp(-t * 18) * math.sin(2 * math.pi * phase)


def snare(buf, start, vol=0.35, wrap=False):
    noise(buf, start, 0.16, vol, decay=22, wrap=wrap, seed=int(start * 1000) + 7)
    tone(buf, start, 0.05, 185, vol * 0.6, "triangle", release=0.04, decay=30, wrap=wrap)


def hat(buf, start, vol=0.12, wrap=False):
    noise(buf, start, 0.05, vol, decay=90, wrap=wrap, seed=int(start * 1000) + 3)


def to_wav(buf: list, path: str, gain: float = 1.0) -> None:
    peak = max(1e-9, max(abs(x) for x in buf))
    scale = gain * 0.95 / max(1.0, peak)  # only ever turn down, never amplify noise
    data = array.array("h", (int(max(-1.0, min(1.0, x * scale)) * 32767) for x in buf))
    tmp = path + ".tmp"
    with wave.open(tmp, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(data.tobytes())
    os.replace(tmp, path)


def blank(seconds: float) -> list:
    return [0.0] * int(seconds * RATE)


# ---------------------------------------------------------------------------------------------
# Music
# ---------------------------------------------------------------------------------------------

# Chords as MIDI notes (root position, around middle C).
C, Am, F, G, Em, Dm = (60, 64, 67, 71), (57, 60, 64, 67), (53, 57, 60, 64), (55, 59, 62, 65), \
    (52, 55, 59, 62), (50, 53, 57, 60)


def music_chill() -> list:
    """Calm lo-fi loop for menus and while the tests run: 8 bars at 88 BPM."""
    bpm, bars = 88, 8
    beat = 60 / bpm
    buf = blank(bars * 4 * beat)
    prog = [C, Am, F, G, Em, Am, Dm, G]
    melody = [  # (bar, beat, MIDI note, length in beats)
        (0, 0, 76, 1.5), (0, 2, 74, 0.5), (0, 2.5, 72, 1.5), (1, 0, 72, 1), (1, 1, 69, 2.5),
        (2, 0, 69, 1), (2, 1, 72, 1), (2, 2, 77, 1.5), (3, 0, 76, 1), (3, 1, 74, 2.5),
        (4, 0, 71, 1.5), (4, 2, 74, 0.5), (4, 2.5, 76, 1.5), (5, 0, 72, 3),
        (6, 0, 74, 1), (6, 1, 72, 1), (6, 2, 69, 2), (7, 0, 71, 1), (7, 1, 74, 2.5),
    ]
    for bar, chord in enumerate(prog):
        t0 = bar * 4 * beat
        for note in chord:  # soft pad
            tone(buf, t0, 4 * beat - 0.05, freq(note), 0.045, "triangle", attack=0.4, release=0.5, wrap=True)
        tone(buf, t0, 1.8 * beat, freq(chord[0] - 24), 0.20, "sine", attack=0.01, release=0.2, wrap=True)
        tone(buf, t0 + 2 * beat, 1.8 * beat, freq(chord[0] - 24 + (7 if bar % 2 else 0)), 0.16, "sine",
             attack=0.01, release=0.2, wrap=True)
        arp = [chord[0], chord[1], chord[2], chord[3], chord[2] + 12, chord[3], chord[2], chord[1]]
        for k, note in enumerate(arp):  # gentle plucked arpeggio in eighths
            tone(buf, t0 + k * beat / 2, beat / 2, freq(note + 12), 0.05, "sine", attack=0.003,
                 decay=6, release=0.15, wrap=True)
        for k in range(4):  # brushed beat: soft kick, rim on 2 and 4, shuffle hats
            if k in (0, 2):
                kick(buf, t0 + k * beat, 0.35, wrap=True)
            else:
                hat(buf, t0 + k * beat, 0.10, wrap=True)
            hat(buf, t0 + (k + 0.66) * beat, 0.05, wrap=True)
    for bar, b, note, length in melody:  # dreamy lead
        tone(buf, (bar * 4 + b) * beat, length * beat * 0.95, freq(note), 0.075, "triangle", attack=0.02,
             release=0.25, wrap=True)
    return buf


def music_arcade() -> list:
    """Upbeat chiptune loop for the built-in games: 8 bars at 136 BPM."""
    bpm, bars = 136, 8
    beat = 60 / bpm
    buf = blank(bars * 4 * beat)
    prog = [Am, F, C, G, Am, F, C, G]
    lead = [  # (bar, sixteenth, note, length in sixteenths)
        (0, 0, 69, 3), (0, 4, 72, 2), (0, 6, 76, 2), (0, 8, 74, 4), (0, 12, 72, 4),
        (1, 0, 72, 3), (1, 4, 69, 2), (1, 6, 72, 2), (1, 8, 77, 6), (1, 14, 76, 2),
        (2, 0, 76, 3), (2, 4, 79, 2), (2, 6, 76, 2), (2, 8, 72, 4), (2, 12, 74, 4),
        (3, 0, 74, 6), (3, 8, 71, 4), (3, 12, 74, 4),
        (4, 0, 81, 2), (4, 2, 79, 2), (4, 4, 76, 4), (4, 8, 79, 2), (4, 10, 76, 2), (4, 12, 72, 4),
        (5, 0, 77, 4), (5, 4, 76, 2), (5, 6, 74, 2), (5, 8, 72, 8),
        (6, 0, 76, 2), (6, 2, 79, 2), (6, 4, 84, 4), (6, 8, 83, 4), (6, 12, 79, 4),
        (7, 0, 79, 6), (7, 8, 74, 4), (7, 12, 71, 4),
    ]
    s16 = beat / 4
    for bar, chord in enumerate(prog):
        t0 = bar * 4 * beat
        for k in range(8):  # driving octave bass
            note = chord[0] - 24 + (12 if k % 2 else 0)
            tone(buf, t0 + k * beat / 2, beat / 2 * 0.8, freq(note), 0.16, "triangle", release=0.02,
                 wrap=True)
        for k in range(16):  # fast arpeggio, quiet square
            note = chord[[0, 1, 2, 1][k % 4]] + 12
            tone(buf, t0 + k * s16, s16 * 0.7, freq(note), 0.035, "square", duty=0.25, release=0.01,
                 wrap=True)
        for k in range(4):  # four-on-the-floor with snare on 2 and 4
            kick(buf, t0 + k * beat, 0.55, wrap=True)
            if k in (1, 3):
                snare(buf, t0 + k * beat, 0.22, wrap=True)
            hat(buf, t0 + (k + 0.5) * beat, 0.08, wrap=True)
    for bar, sixteenth, note, length in lead:
        tone(buf, (bar * 16 + sixteenth) * s16, length * s16 * 0.9, freq(note), 0.07, "square", duty=0.5,
             release=0.03, wrap=True)
        tone(buf, (bar * 16 + sixteenth) * s16 + 0.012, length * s16 * 0.9, freq(note) * 1.005, 0.03, "square",
             duty=0.25, release=0.03, wrap=True)  # slight detune = fatter chip sound
    return buf


# ---------------------------------------------------------------------------------------------
# Sound effects
# ---------------------------------------------------------------------------------------------

def _seq(notes, step, kind="square", vol=0.3, hold=0.9, tail=0.15, duty=0.5):
    buf = blank(len(notes) * step + tail + 0.1)
    for i, n in enumerate(notes):
        tone(buf, i * step, step * hold if i < len(notes) - 1 else step + tail, freq(n), vol, kind,
             release=0.05, duty=duty)
    return buf


def sfx_click():
    buf = blank(0.06)
    tone(buf, 0, 0.02, 1400, 0.25, "sine", release=0.02, decay=60)
    return buf


def sfx_coin():
    return _seq([83, 88], 0.07, vol=0.22, tail=0.2)


def sfx_pickup():
    buf = blank(0.4)
    for i, n in enumerate([84, 88, 91, 96]):
        tone(buf, i * 0.045, 0.12, freq(n), 0.16, "sine", decay=12, release=0.08)
    return buf


def sfx_merge():
    buf = blank(0.12)
    tone(buf, 0, 0.06, 320, 0.25, "sine", release=0.03, slide=380, decay=20)
    return buf


def sfx_tick():
    buf = blank(0.05)
    noise(buf, 0, 0.02, 0.25, decay=120)
    tone(buf, 0, 0.015, 900, 0.12, "sine", release=0.01, decay=80)
    return buf


def sfx_flag():
    return _seq([79, 86], 0.05, vol=0.18, tail=0.05)


def sfx_explode():
    buf = blank(0.9)
    noise(buf, 0, 0.85, 0.7, decay=5, bright=False, seed=11)
    tone(buf, 0, 0.4, 70, 0.6, "sine", slide=-35, release=0.3, decay=6)
    return buf


def sfx_bump():
    buf = blank(0.3)
    noise(buf, 0, 0.2, 0.5, decay=18, bright=False, seed=5)
    tone(buf, 0, 0.12, 95, 0.5, "sine", slide=-40, release=0.08, decay=15)
    return buf


def sfx_lose():
    return _seq([67, 64, 60, 55], 0.16, kind="triangle", vol=0.35, tail=0.35)


def sfx_win():
    buf = _seq([72, 76, 79, 84], 0.1, vol=0.18, tail=0.5)
    tone(buf, 0.3, 0.6, freq(60), 0.2, "triangle", release=0.3)
    return buf


def sfx_start():
    return _seq([60, 64, 67, 72], 0.06, vol=0.16, duty=0.25, tail=0.12)


def sfx_lap():
    return _seq([84, 84, 91], 0.1, vol=0.16, tail=0.2)


def sfx_result_pass():
    buf = _seq([72, 76, 79, 84, 88], 0.11, kind="triangle", vol=0.3, tail=0.7)
    for n in (60, 64, 67):
        tone(buf, 0.44, 0.8, freq(n), 0.1, "sine", attack=0.05, release=0.4)
    return buf


def sfx_result_warn():
    return _seq([72, 74, 79], 0.16, kind="triangle", vol=0.3, tail=0.5)


def sfx_result_fail():
    # Gentle, not alarming: something needs attention, nothing exploded.
    return _seq([76, 72, 69], 0.2, kind="sine", vol=0.32, tail=0.6)


SFX = {
    "click": sfx_click, "coin": sfx_coin, "pickup": sfx_pickup, "merge": sfx_merge, "tick": sfx_tick,
    "flag": sfx_flag, "explode": sfx_explode, "bump": sfx_bump, "lose": sfx_lose, "win": sfx_win,
    "start": sfx_start, "lap": sfx_lap, "result_pass": sfx_result_pass, "result_warn": sfx_result_warn,
    "result_fail": sfx_result_fail,
}
MUSIC = {"chill": (music_chill, 0.55), "arcade": (music_arcade, 0.5)}  # name -> (render, gain)


def render_all(out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    for name, fn in SFX.items():
        to_wav(fn(), os.path.join(out_dir, f"{name}.wav"), gain=0.8)
    for name, (fn, gain) in MUSIC.items():
        # Three passes of the (seamless) loop per file, so the player restarts only every minute or so.
        to_wav(fn() * 3, os.path.join(out_dir, f"music-{name}.wav"), gain=gain)
    with open(os.path.join(out_dir, "VERSION"), "w") as f:
        f.write(VERSION)


# ---------------------------------------------------------------------------------------------
# Playback
# ---------------------------------------------------------------------------------------------

class Player:
    """Plays looping music and one-shot effects in the background. Safe to call from the UI thread;
    does nothing at all if there's no audio player or the sounds aren't ready."""

    def __init__(self):
        self.enabled = os.environ.get("TROUBLESHOOT_SOUND", "1") != "0"
        self.dir: str | None = None
        self.cmd = self._player_cmd()
        self.want: str | None = None   # music the UI would like playing
        self.paused = False            # e.g. while an external app is open
        self.quiet = False             # no effects at all (hands-on tests use the speakers and mic)
        self._proc: subprocess.Popen | None = None
        self._playing: str | None = None
        self._last_sfx: dict[str, float] = {}
        self._started = 0.0
        self._quick_failures = 0  # player exiting immediately = no usable sound device
        self._lock = threading.Lock()
        self._wake = threading.Event()
        if self.cmd:
            threading.Thread(target=self._prepare, daemon=True).start()
            threading.Thread(target=self._music_loop, daemon=True).start()

    @staticmethod
    def _player_cmd() -> list[str] | None:
        if shutil.which("pw-play"):
            return ["pw-play", "--volume", "0.8"]
        if shutil.which("aplay"):
            return ["aplay", "-q"]
        return None

    def _prepare(self) -> None:
        def ready(d):
            try:
                with open(os.path.join(d, "VERSION")) as f:
                    return f.read().strip() == VERSION
            except OSError:
                return False
        if ready(SYSTEM_DIR):
            self.dir = SYSTEM_DIR
        else:
            cache = os.path.join(tempfile.gettempdir(), f"troubleshoot-sounds-{VERSION}")
            if not ready(cache):
                try:
                    render_all(cache)
                except OSError:
                    return
            self.dir = cache
        self._wake.set()

    # --- public API ------------------------------------------------------------------------
    def music(self, name: str | None) -> None:
        """Switch background music ('chill', 'arcade') or stop it (None)."""
        if name != self.want:
            self.want = name
            self._wake.set()

    def pause(self, paused: bool) -> None:
        self.paused = paused
        self._wake.set()

    def set_enabled(self, on: bool) -> None:
        self.enabled = on
        self._wake.set()

    def sfx(self, name: str) -> None:
        if not (self.enabled and self.cmd and self.dir) or self.paused or self.quiet:
            return
        now = time.monotonic()
        if now - self._last_sfx.get(name, 0) < 0.06:  # don't spawn a storm of identical effects
            return
        self._last_sfx[name] = now
        try:  # `timeout`: with no output device a player can wait forever; don't leave it behind
            subprocess.Popen(["timeout", "5"] + self.cmd + [os.path.join(self.dir, f"{name}.wav")],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass

    def watch(self, proc: subprocess.Popen) -> None:
        """Pause the music while an external app (with its own sound) is running."""
        self.pause(True)

        def wait():
            proc.wait()
            self.pause(False)
        threading.Thread(target=wait, daemon=True).start()

    # --- music thread ----------------------------------------------------------------------
    def _target(self) -> str | None:
        return self.want if (self.enabled and not self.paused and self.dir) else None

    def _music_loop(self) -> None:
        while True:
            target = self._target()
            if target != self._playing:
                self._stop()
                self._playing = target
            if self._proc is not None and self._proc.poll() is not None:
                if time.monotonic() - self._started < 1.0:
                    self._quick_failures += 1
                    if self._quick_failures >= 3:  # no working audio output: stop trying
                        self.cmd = None
                        return
                self._proc = None
            if target and self._proc is None:
                self._started = time.monotonic()
                try:  # (re)start the loop; the WAV is a seamless loop
                    self._proc = subprocess.Popen(
                        ["timeout", "300"] + self.cmd + [os.path.join(self.dir, f"music-{target}.wav")],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except OSError:
                    self._proc = None
            self._wake.wait(0.2)
            self._wake.clear()

    def _stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None


_player: Player | None = None


def player() -> Player:
    global _player
    if _player is None:
        _player = Player()
    return _player


def sfx(name: str) -> None:
    """Play an effect if a player has been started (the GUI starts one; tests and text mode don't)."""
    if _player is not None:
        _player.sfx(name)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    t = time.monotonic()
    render_all(sys.argv[1])
    print(f"Rendered {len(SFX)} effects and {len(MUSIC)} music loops to {sys.argv[1]} "
          f"in {time.monotonic() - t:.1f}s")
