"""Webcam detection (V4L2) and single-frame capture with fswebcam."""

from __future__ import annotations

import glob
import os
import re

from . import util


def cameras() -> list[dict]:
    """Video capture devices. Each camera usually exposes a capture node (index 0) plus
    metadata nodes; only the capture nodes are returned."""
    out = []
    for d in sorted(glob.glob(util.sys_path("class", "video4linux", "video*")),
                    key=lambda p: int(re.sub(r"\D", "", os.path.basename(p)) or 0)):
        if util.read(os.path.join(d, "index"), "0") != "0":
            continue
        name = util.read(os.path.join(d, "name")) or "camera"
        if re.search(r"ipu|isys|capture \d+|metadata", name, re.I):
            continue  # raw ISP nodes of MIPI cameras, not usable directly
        out.append({"dev": f"/dev/{os.path.basename(d)}", "name": name})
    return out


def mipi_camera_present() -> bool:
    """Intel IPU6 / MIPI cameras (many 2022+ laptops) need a special driver stack."""
    return bool(glob.glob(util.sys_path("bus", "pci", "drivers", "intel-ipu6*"))) or \
        any("ipu" in (util.read(os.path.join(d, "name")) or "").lower()
            for d in glob.glob(util.sys_path("class", "video4linux", "video*")))


def capture(dev: str, path: str, width: int = 640, height: int = 480) -> bool:
    """Grab one frame into a PNG. Skips a few frames so auto-exposure can settle."""
    res = util.run(["fswebcam", "-q", "-d", dev, "-r", f"{width}x{height}", "-S", "5",
                    "--no-banner", "--png", "1", path], timeout=20)
    return res.returncode == 0 and os.path.exists(path) and os.path.getsize(path) > 0
