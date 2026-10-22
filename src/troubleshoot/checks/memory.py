"""RAM test using memtester, plus ECC error counters where the hardware has them."""

from __future__ import annotations

import glob
import os
import re
import subprocess
import threading
import time

from .. import util
from ..model import Cancelled, Context, Result, Status, timed

NAME = "Memory (RAM)"
TESTS_PER_LOOP = 18  # number of sub-tests memtester 4.x runs per loop
HEADROOM_MB = 350    # leave this much RAM for the live system itself
_TEST_LINE = re.compile(r"^\s{2}([A-Z][A-Za-z0-9\- ]+?)\s*:", re.M)


def clean(output: str) -> str:
    """memtester draws progress with backspaces; strip them so the text is parseable."""
    out: list[str] = []
    for ch in output:
        if ch == "\b":
            if out and out[-1] != "\n":
                out.pop()
        else:
            out.append(ch)
    return "".join(out)


def test_size_mb(avail_kb: int, fraction: float, max_mb: int | None) -> int:
    mb = int(avail_kb / 1024 * fraction) - HEADROOM_MB
    if max_mb:
        mb = min(mb, max_mb)
    return max(mb, 0)


def edac_counts() -> tuple[int, int] | None:
    mcs = glob.glob(util.sys_path("devices", "system", "edac", "mc", "mc[0-9]*"))
    if not mcs:
        return None
    ce = sum(util.read_int(os.path.join(m, "ce_count")) or 0 for m in mcs)
    ue = sum(util.read_int(os.path.join(m, "ue_count")) or 0 for m in mcs)
    return ce, ue


def evaluate(rc: int, output: str, size_mb: int, loops: int, edac: tuple[int, int] | None) -> Result:
    text = clean(output)
    failures = [l.strip() for l in text.splitlines() if "FAILURE" in l]
    details = [f"Tested {size_mb} MB of RAM, {loops} pass(es), with memtester."]
    if edac is not None:
        details.append(f"ECC corrected errors: {edac[0]}, uncorrectable: {edac[1]}")

    if rc & 0x06 or failures:
        details += failures[:12]
        if len(failures) > 12:
            details.append(f"... and {len(failures) - 12} more failures")
        return Result(
            "memory", NAME, Status.FAIL, "Memory errors were found – the RAM is faulty.", details,
            explanation="Data written to RAM did not read back the same. Even a single error like "
                        "this causes random crashes, freezes, blue screens, corrupted files and failed "
                        "updates. Faulty RAM cannot be repaired, but it is usually cheap to replace.",
            next_steps=[
                "If the computer has more than one memory stick, test them one at a time (remove "
                "the others) to find the bad one.",
                "Reseat the memory: remove each stick, clean the contacts gently, and push it back in firmly.",
                "If the RAM is soldered to the motherboard (common in thin laptops) the board must be "
                "repaired or replaced – contact the manufacturer if it's under warranty.",
                "For a second opinion, reboot and choose \"Memory test (memtest86+)\" from the boot menu.",
            ])
    if edac and edac[1] > 0:
        return Result(
            "memory", NAME, Status.FAIL, "The memory controller reported uncorrectable ECC errors.",
            details,
            explanation="This computer has error-correcting (ECC) memory, and it detected errors it "
                        "could not fix. That is a strong sign of a failing memory module.",
            next_steps=["Replace the memory module reported in your system's event log / BIOS."])
    if rc & 0x01:
        return Result("memory", NAME, Status.SKIP, "Could not reserve memory for testing.",
                      details + [text.strip().splitlines()[-1] if text.strip() else ""],
                      explanation="The test couldn't allocate enough free RAM. Try again with fewer "
                                  "programs running, or use memtest86+ from the boot menu.")
    if edac and edac[0] > 0:
        return Result(
            "memory", NAME, Status.WARN, "No errors in the test, but ECC corrected some memory errors.",
            details,
            explanation="ECC memory silently fixed some bit errors. A few over a long time is normal; "
                        "a growing number means a module is starting to fail.",
            next_steps=["Run the Full test again later and see whether the corrected-error count grows."])
    return Result(
        "memory", NAME, Status.PASS, f"No errors found in {size_mb} MB of RAM.", details,
        explanation="Test patterns were written to and read back from memory and all matched. Note "
                    "that a running system can't test the small part of RAM it uses itself – for a "
                    "100% complete test, reboot and choose \"Memory test (memtest86+)\" from the boot menu.",
    )


@timed
def run(ctx: Context) -> Result:
    if not util.have("memtester"):
        return Result("memory", NAME, Status.SKIP, "memtester is not installed.")
    avail = util.meminfo().get("MemAvailable", 0)
    size = test_size_mb(avail, ctx.params.get("fraction", 0.5), ctx.params.get("max_mb"))
    if ctx.time_scale < 1:
        size = min(size, 64)
    loops = int(ctx.params.get("loops", 1))
    if size < 64:
        return Result("memory", NAME, Status.SKIP, "Not enough free memory to run the test.",
                      [f"Available: {avail // 1024} MB"])

    cmd = ["memtester", f"{size}M", str(loops)]
    ctx.log("Running: " + " ".join(cmd))
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            start_new_session=True)
    chunks: list[bytes] = []
    reader = threading.Thread(target=lambda: chunks.extend(iter(lambda: proc.stdout.read1(4096), b"")),
                              daemon=True)
    reader.start()
    total = TESTS_PER_LOOP * loops
    start = time.monotonic()
    try:
        while proc.poll() is None:
            ctx.sleep(1.0)
            text = clean(b"".join(chunks).decode(errors="replace"))
            done = len(_TEST_LINE.findall(text))
            names = _TEST_LINE.findall(text)
            current = names[-1] if names else "starting"
            ctx.progress(min(0.99, max(0, done - 1) / total),
                         f"{current} · {util.fmt_duration(time.monotonic() - start)} elapsed")
    except Cancelled:
        util._kill(proc)
        raise
    reader.join(timeout=5)
    output = b"".join(chunks).decode(errors="replace")
    # ECC totals since boot: on a freshly booted live system that's essentially "during testing".
    return evaluate(proc.returncode, output, size, loops, edac_counts())
