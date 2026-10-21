"""Laptop screen backlight control via /sys/class/backlight."""

from __future__ import annotations

import glob
import os

from . import util


def device() -> str | None:
    devs = glob.glob(util.sys_path("class", "backlight", "*"))
    # Prefer firmware/platform interfaces over raw ones, like desktop environments do.
    devs.sort(key=lambda d: {"firmware": 0, "platform": 1, "raw": 2}.get(util.read(os.path.join(d, "type")) or "", 3))
    for d in devs:
        if os.access(os.path.join(d, "brightness"), os.W_OK):
            return d
    return None


def get(dev: str) -> tuple[int, int]:
    return util.read_int(os.path.join(dev, "brightness")) or 0, util.read_int(os.path.join(dev, "max_brightness")) or 1


def set_fraction(dev: str, frac: float) -> None:
    _, mx = get(dev)
    set_raw(dev, max(1, int(mx * frac)))


def set_raw(dev: str, value: int) -> None:
    try:
        with open(os.path.join(dev, "brightness"), "w") as f:
            f.write(str(value))
    except OSError:
        pass
