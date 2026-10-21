"""Check that a real graphics driver is loaded (not software rendering)."""

from __future__ import annotations

import os
import re

from .. import util
from ..model import Context, Result, Status, timed

NAME = "Graphics driver"


def classify(renderer: str) -> Status:
    r = renderer.lower()
    if any(s in r for s in ("llvmpipe", "softpipe", "swrast", "software rasterizer")):
        return Status.WARN
    return Status.PASS


@timed
def run(ctx: Context) -> Result:
    if not os.environ.get("DISPLAY"):
        return Result("graphics", NAME, Status.SKIP,
                      "Skipped: no graphical session (text mode).",
                      explanation="This check needs the graphical interface to be running.")
    res = util.run(["glxinfo", "-B"], timeout=20)
    if res.returncode != 0:
        return Result("graphics", NAME, Status.SKIP, "Could not query the graphics driver.",
                      [res.stderr.strip()[:300]])
    m = re.search(r"OpenGL renderer string:\s*(.+)", res.stdout)
    renderer = m.group(1).strip() if m else "unknown"
    details = [f"Renderer: {renderer}"]
    vm = re.search(r"OpenGL version string:\s*(.+)", res.stdout)
    if vm:
        details.append(f"OpenGL: {vm.group(1).strip()}")
    status = classify(renderer)
    if status is Status.WARN:
        return Result(
            "graphics", NAME, Status.WARN,
            "The graphics chip is running in slow software mode.", details,
            explanation="Linux could not load a hardware driver for the graphics chip, so the "
                        "processor is drawing the screen instead. On brand-new or NVIDIA hardware "
                        "this can simply mean the free driver doesn't support the chip yet. If "
                        "your normal operating system also has display glitches, black screens or "
                        "crashes, the graphics chip itself may be faulty.",
            next_steps=[
                "If your normal OS works fine, you can ignore this.",
                "Otherwise, update your graphics driver and BIOS in your normal OS.",
                "Repeated display corruption on every OS points to a hardware graphics fault – "
                "contact the manufacturer or a repair shop.",
            ])
    return Result("graphics", NAME, Status.PASS, f"Hardware graphics driver is working ({renderer}).",
                  details,
                  explanation="The graphics chip was detected and its driver loaded correctly.")
