"""Small helpers for reading the hardware and running external tools."""

from __future__ import annotations

import glob
import os
import shutil
import signal
import subprocess
import time
from typing import Optional

from .model import Cancelled, Context

# Overridable for unit tests.
SYS = "/sys"
PROC = "/proc"


def sys_path(*parts: str) -> str:
    return os.path.join(SYS, *parts)


def read(path: str, default: Optional[str] = None) -> Optional[str]:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return default


def read_int(path: str) -> Optional[int]:
    val = read(path)
    if val is None:
        return None
    try:
        return int(val)
    except ValueError:
        return None


def have(tool: str) -> bool:
    return shutil.which(tool) is not None


def is_root() -> bool:
    return os.geteuid() == 0


def run(cmd: list[str], timeout: float = 30, check: bool = False,
        input: Optional[str] = None) -> subprocess.CompletedProcess:
    """Run a command and capture text output. Never raises for a missing tool."""
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=check,
            errors="replace", input=input,
        )
    except FileNotFoundError:
        return subprocess.CompletedProcess(cmd, 127, "", f"{cmd[0]}: not installed")
    except subprocess.TimeoutExpired as e:
        return subprocess.CompletedProcess(cmd, 124, e.stdout or "", "timed out")


def run_cancellable(ctx: Context, cmd: list[str], timeout: Optional[float] = None,
                    on_tick=None, tick: float = 1.0) -> subprocess.CompletedProcess:
    """Run a long command, polling for cancellation; ``on_tick(elapsed)`` is called every ``tick`` s."""
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, errors="replace", start_new_session=True)
    except FileNotFoundError:
        return subprocess.CompletedProcess(cmd, 127, "", f"{cmd[0]}: not installed")
    start = time.monotonic()
    try:
        while True:
            try:
                out, err = proc.communicate(timeout=tick)
                return subprocess.CompletedProcess(cmd, proc.returncode, out, err)
            except subprocess.TimeoutExpired:
                pass
            elapsed = time.monotonic() - start
            if ctx.cancel.is_set():
                raise Cancelled()
            if timeout is not None and elapsed > timeout:
                _kill(proc)
                out, err = proc.communicate()
                return subprocess.CompletedProcess(cmd, 124, out, (err or "") + "\ntimed out")
            if on_tick:
                on_tick(elapsed)
    except BaseException:
        _kill(proc)
        proc.communicate()
        raise


def _kill(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def ram_boot_status() -> str | None:
    """'ram' if the live system was copied into memory (the USB stick can be unplugged),
    'fallback' if that was requested but didn't happen (usually not enough RAM), None otherwise."""
    cmdline = (read(os.path.join(PROC, "cmdline")) or "").split()
    if not any(arg == "toram" or arg.startswith("toram=") for arg in cmdline):
        return None
    # live-boot's toram copies the boot medium into a RAM disk (tmpfs) and mounts that copy
    # where the medium was (/run/live/medium). If the medium is still the real USB/CD
    # filesystem there, the copy didn't happen (usually: not enough memory).
    for line in (read(os.path.join(PROC, "mounts")) or "").splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[1] in ("/run/live/medium", "/lib/live/mount/medium"):
            return "ram" if parts[2] in ("tmpfs", "ramfs") else "fallback"
    return "ram"  # medium not mounted at all: nothing is being read from the stick


def meminfo() -> dict[str, int]:
    """/proc/meminfo in kB."""
    out: dict[str, int] = {}
    for line in (read(os.path.join(PROC, "meminfo")) or "").splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if parts and parts[0].isdigit():
            out[key] = int(parts[0])
    return out


def cpu_temps() -> dict[str, float]:
    """Best-effort CPU/package temperatures in °C from hwmon, falling back to thermal zones."""
    temps: dict[str, float] = {}
    cpu_drivers = {"coretemp", "k10temp", "zenpower", "cpu_thermal", "acpitz", "thinkpad"}
    for hw in sorted(glob.glob(sys_path("class", "hwmon", "hwmon*"))):
        name = read(os.path.join(hw, "name")) or ""
        if name not in cpu_drivers:
            continue
        for inp in sorted(glob.glob(os.path.join(hw, "temp*_input"))):
            v = read_int(inp)
            if v is None or v <= 0:
                continue
            label = read(inp.replace("_input", "_label")) or os.path.basename(inp)
            temps[f"{name}/{label}"] = v / 1000.0
    if not temps:
        for zone in sorted(glob.glob(sys_path("class", "thermal", "thermal_zone*"))):
            v = read_int(os.path.join(zone, "temp"))
            if v and v > 0:
                temps[read(os.path.join(zone, "type")) or os.path.basename(zone)] = v / 1000.0
    return temps


def fan_speeds() -> dict[str, int]:
    fans: dict[str, int] = {}
    for inp in sorted(glob.glob(sys_path("class", "hwmon", "hwmon*", "fan*_input"))):
        v = read_int(inp)
        if v is not None:
            hw = os.path.dirname(inp)
            fans[f"{read(os.path.join(hw, 'name')) or 'fan'}/{os.path.basename(inp)[:-6]}"] = v
    return fans


def cpu_freqs_mhz() -> list[float]:
    out = []
    for p in glob.glob(sys_path("devices", "system", "cpu", "cpu[0-9]*", "cpufreq", "scaling_cur_freq")):
        v = read_int(p)
        if v:
            out.append(v / 1000.0)
    return out


def cpu_max_freq_mhz() -> Optional[float]:
    vals = []
    for p in glob.glob(sys_path("devices", "system", "cpu", "cpu[0-9]*", "cpufreq", "cpuinfo_max_freq")):
        v = read_int(p)
        if v:
            vals.append(v / 1000.0)
    return max(vals) if vals else None


def human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m"
