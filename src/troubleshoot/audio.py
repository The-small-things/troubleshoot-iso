"""Speaker / microphone helpers. Uses PipeWire when running, plain ALSA otherwise."""

from __future__ import annotations

import array
import math
import re
import wave

from . import util

RATE = 44100


def _alsa_devices(tool: str) -> list[tuple[str, str]]:
    """[(plughw:C,D, description)] from `aplay -l` / `arecord -l`."""
    out = util.run([tool, "-l"]).stdout
    devs = []
    for m in re.finditer(r"^card (\d+): [^[]*\[([^\]]*)\], device (\d+): [^[]*\[([^\]]*)\]", out, re.M):
        devs.append((f"plughw:{m.group(1)},{m.group(3)}", f"{m.group(2)} – {m.group(4)}"))
    return devs


def _pick(devs: list[tuple[str, str]]) -> tuple[str, str] | None:
    analog = [d for d in devs if not re.search(r"hdmi|displayport|\bdp\b", d[1], re.I)]
    return (analog or devs or [None])[0]


def pipewire_running() -> bool:
    return util.have("pw-play") and util.run(["wpctl", "status"], timeout=5).returncode == 0


class Audio:
    def __init__(self):
        self.pw = pipewire_running()
        self.out = _pick(_alsa_devices("aplay"))
        self.inp = _pick(_alsa_devices("arecord"))

    @property
    def available(self) -> bool:
        return self.out is not None

    @property
    def description(self) -> str:
        return (self.out[1] if self.out else "none") + (" (via PipeWire)" if self.pw else "")

    def prepare(self) -> None:
        """Unmute and set sensible volumes – a muted mixer is the #1 cause of "no sound"."""
        if self.pw:
            util.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"])
            util.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "0.8"])
            util.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SOURCE@", "0"])
            util.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SOURCE@", "1.0"])
        for dev in filter(None, (self.out, self.inp)):
            card = dev[0].split(":")[1].split(",")[0]
            controls = util.run(["amixer", "-c", card, "scontrols"]).stdout
            for name in re.findall(r"'([^']+)',\d+", controls):
                if re.fullmatch(r"Master|Speaker|Headphone|PCM|Front", name):
                    util.run(["amixer", "-q", "-c", card, "sset", name, "85%", "unmute"])
                elif re.search(r"Capture|Mic", name) and "Boost" not in name:
                    util.run(["amixer", "-q", "-c", card, "sset", name, "80%", "cap"])

    def play(self, path: str) -> bool:
        if self.pw:
            return util.run(["pw-play", path], timeout=30).returncode == 0
        if not self.out:
            return False
        return util.run(["aplay", "-q", "-D", self.out[0], path], timeout=30).returncode == 0

    def record(self, path: str, seconds: int) -> bool:
        if self.pw:
            res = util.run(["timeout", str(seconds), "pw-record", "--channels", "1", "--rate", str(RATE),
                            path], timeout=seconds + 10)
            return res.returncode in (0, 124)
        if not self.inp:
            return False
        return util.run(["arecord", "-q", "-D", self.inp[0], "-f", "S16_LE", "-r", str(RATE), "-c", "1",
                         "-d", str(seconds), path], timeout=seconds + 10).returncode == 0


def make_tone(path: str, channel: str, seconds: float = 2.4, freq: float = 660.0) -> None:
    """Three beeps on one channel ('left'/'right') of a stereo WAV."""
    n = int(RATE * seconds)
    data = array.array("h")
    for i in range(n):
        t = i / RATE
        on = (t % 0.8) < 0.5
        s = int(0.6 * 32767 * math.sin(2 * math.pi * freq * t)) if on else 0
        data.extend((s, 0) if channel == "left" else (0, s))
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(data.tobytes())


def peak_level(path: str) -> float | None:
    try:
        with wave.open(path, "rb") as w:
            if w.getsampwidth() != 2:
                return None
            frames = array.array("h", w.readframes(w.getnframes()))
    except (OSError, wave.Error, EOFError):
        return None
    if not frames:
        return 0.0
    skip = len(frames) // 10  # ignore the click at the start of a recording
    return max(abs(s) for s in frames[skip:] or frames) / 32768
