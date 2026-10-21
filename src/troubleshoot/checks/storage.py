"""Disk health: SMART status and attributes, optional drive self-test and a read-speed test.

Strictly read-only: nothing is ever written to or mounted from the computer's disks.
"""

from __future__ import annotations

import json
import os
import re
import time

from .. import util
from ..model import Context, Result, Status, timed

NAME = "Storage drives"

# Why each kind of problem matters and what to do; keyed by problem id.
ADVICE = {
    "smart_failed": (
        "The drive's own self-monitoring says it is failing. Drives that report this usually die "
        "within days or weeks.",
        ["Back up your files IMMEDIATELY – copy the most important ones first.",
         "Replace the drive before it stops working completely."]),
    "bad_sectors": (
        "Parts of the disk surface (or flash cells) can no longer be read reliably. This causes slow "
        "or failed file opens, freezes, and corrupted files, and it usually gets worse over time.",
        ["Back up your files now.",
         "Plan to replace the drive soon – the number of bad sectors usually keeps growing."]),
    "remapped": (
        "The drive has replaced some worn-out sectors with spares. A handful is not an emergency, "
        "but it's an early sign of wear.",
        ["Make sure your backups are up to date.",
         "Re-run this test in a few weeks; if the number grows, replace the drive."]),
    "crc": (
        "Data got corrupted on its way between the drive and the motherboard. This is almost always "
        "the cable or connector, not the drive itself.",
        ["Reseat or replace the SATA data cable (desktops) or the drive's connector/ribbon (laptops).",
         "If the number keeps rising after replacing the cable, try another SATA port."]),
    "nvme_critical": (
        "The SSD raised a critical warning (spare space exhausted, overheating, or read-only mode).",
        ["Back up your files IMMEDIATELY.", "Replace the SSD."]),
    "worn": (
        "SSDs can only be written a limited number of times. This one has used up most of its "
        "rated lifespan.",
        ["Back up your files and plan to replace the SSD."]),
    "selftest_failed": (
        "The drive's built-in self-test found an error it could not recover from.",
        ["Back up your files now.", "Replace the drive."]),
    "read_error": (
        "Reading from the drive failed. The drive may have unreadable areas or may be dropping "
        "off the bus.",
        ["Back up your files now.", "Replace the drive (or its cable on a desktop)."]),
    "slow": (
        "The drive reads much slower than drives of its kind normally do. Causes include a failing "
        "drive retrying reads, a damaged or slow cable/port, or an SSD that is overheating.",
        ["On a desktop, try a different SATA cable and port.",
         "If the computer feels slow when opening files, consider replacing the drive."]),
    "hot": (
        "The drive is running hotter than recommended, which shortens its life and can make it "
        "slow down.",
        ["Improve airflow (clean dust, check case fans). NVMe SSDs may benefit from a heatsink."]),
    "no_smart": (
        "The drive didn't provide health data. This is common for drives behind RAID controllers, "
        "some USB adapters, or when the BIOS uses Intel RST/RAID mode.",
        ["If this is your main drive, check the BIOS storage mode (AHCI shows the most information)."]),
    "no_disks": (
        "No internal storage drive was found. If the computer says \"no bootable device\" or "
        "can't find Windows/macOS/Linux, this is why.",
        ["Check that the drive is installed and firmly seated (M.2 screw, SATA cables).",
         "Look in the BIOS to see whether the drive is detected there.",
         "In the BIOS, try switching the storage mode from RAID/RST to AHCI (only if you know your "
         "OS supports it).",
         "If the BIOS doesn't see it either, the drive (or its slot) has likely failed."]),
}

SEVERITY = {
    "smart_failed": Status.FAIL, "bad_sectors": Status.FAIL, "nvme_critical": Status.FAIL,
    "selftest_failed": Status.FAIL, "read_error": Status.FAIL,
    "remapped": Status.WARN, "crc": Status.WARN, "worn": Status.WARN, "slow": Status.WARN,
    "hot": Status.WARN, "no_smart": Status.SKIP, "no_disks": Status.WARN,
}


def _attr(smart: dict, attr_id: int) -> tuple[int, int] | None:
    """(raw, normalized) value of an ATA SMART attribute."""
    for a in smart.get("ata_smart_attributes", {}).get("table", []):
        if a.get("id") == attr_id:
            raw = a.get("raw", {}).get("value", 0)
            return int(raw) & 0xFFFFFFFF, int(a.get("value", 100))
    return None


def analyze_smart(smart: dict, rc: int) -> tuple[list[tuple[str, str]], list[str]]:
    """Return (problems as (id, text), informational detail lines)."""
    problems: list[tuple[str, str]] = []
    info: list[str] = []

    hours = smart.get("power_on_time", {}).get("hours")
    if hours is not None:
        info.append(f"powered on for {hours:,} hours (~{hours / 24 / 365:.1f} years of use)")
    temp = smart.get("temperature", {}).get("current")
    if temp is not None:
        info.append(f"temperature {temp} °C")
        if temp >= 70:
            problems.append(("hot", f"running hot ({temp} °C)"))

    status = smart.get("smart_status", {})
    if status.get("passed") is False or rc & 0x08:
        problems.append(("smart_failed", "SMART overall health: FAILED"))

    # ATA/SATA drives
    realloc = _attr(smart, 5)
    pending = _attr(smart, 197)
    offline_unc = _attr(smart, 198)
    reported_unc = _attr(smart, 187)
    crc = _attr(smart, 199)
    if pending and pending[0] > 0:
        problems.append(("bad_sectors", f"{pending[0]} sectors waiting to be remapped (unreadable)"))
    if offline_unc and offline_unc[0] > 0:
        problems.append(("bad_sectors", f"{offline_unc[0]} uncorrectable sectors"))
    if realloc and realloc[0] > 0:
        sev = "bad_sectors" if realloc[0] >= 100 else "remapped"
        problems.append((sev, f"{realloc[0]} reallocated (replaced) sectors"))
    if reported_unc and reported_unc[0] > 0:
        problems.append(("remapped", f"{reported_unc[0]} reported uncorrectable errors"))
    if crc and crc[0] > 0:
        problems.append(("crc", f"{crc[0]} interface CRC errors"))
    for wear_id in (231, 233, 169, 177, 202):
        wear = _attr(smart, wear_id)
        if wear and 0 < wear[1] <= 10:
            problems.append(("worn", f"SSD life remaining indicator at {wear[1]}%"))
            break

    # NVMe drives
    nv = smart.get("nvme_smart_health_information_log")
    if nv:
        if nv.get("critical_warning", 0):
            problems.append(("nvme_critical", f"critical warning flags: {nv['critical_warning']:#x}"))
        spare, thresh = nv.get("available_spare"), nv.get("available_spare_threshold")
        if spare is not None and thresh is not None and spare < thresh:
            problems.append(("nvme_critical", f"spare blocks {spare}% (below the {thresh}% limit)"))
        used = nv.get("percentage_used")
        if used is not None:
            info.append(f"{min(used, 100)}% of rated write endurance used")
            if used >= 90:
                problems.append(("worn", f"{used}% of rated lifespan used"))
        if nv.get("media_errors", 0) > 0:
            problems.append(("bad_sectors", f"{nv['media_errors']} media/data integrity errors"))
    return problems, info


def expected_speed(smart: dict, name: str) -> float:
    """Minimum sequential read MB/s we'd expect from a healthy drive of this kind."""
    if name.startswith("nvme"):
        return 400
    if smart.get("rotation_rate", 1) == 0:  # SATA SSD reports 0 RPM
        return 150
    return 40


def boot_device() -> str | None:
    """The disk the live system booted from, so we don't test the USB stick itself."""
    for mnt in ("/run/live/medium", "/lib/live/mount/medium"):
        src = util.run(["findmnt", "-no", "SOURCE", mnt]).stdout.strip()
        if src:
            parent = util.run(["lsblk", "-no", "PKNAME", src]).stdout.strip().splitlines()
            return (parent[0] if parent and parent[0] else os.path.basename(src)).strip()
    return None


def list_disks() -> tuple[list[dict], list[str]]:
    res = util.run(["lsblk", "-J", "-d", "-b", "-o", "NAME,TYPE,TRAN,RM,MODEL,SIZE"])
    if res.returncode != 0:
        return [], []
    skipped = []
    disks = []
    boot = boot_device()
    for d in json.loads(res.stdout).get("blockdevices", []):
        name = d["name"]
        if d.get("type") != "disk" or name.startswith(("loop", "zram", "ram", "sr")):
            continue
        if name == boot:
            continue
        if d.get("tran") == "usb" or d.get("rm") in (True, 1, "1"):
            skipped.append(f"{name} ({(d.get('model') or 'USB drive').strip()}) – external/USB, not tested")
            continue
        if int(d.get("size") or 0) == 0:
            continue
        disks.append(d)
    return disks, skipped


def smart_json(dev: str, *args: str) -> tuple[dict, int]:
    res = util.run(["smartctl", "-j", *args, dev], timeout=60)
    try:
        return json.loads(res.stdout or "{}"), res.returncode
    except ValueError:
        return {}, res.returncode


def run_selftest(ctx: Context, dev: str, base_frac: float, span: float) -> tuple[str | None, str]:
    """Start a short self-test and wait for it. Returns (problem text or None, info)."""
    data, rc = smart_json(dev, "-t", "short")
    if rc & 0x06:
        return None, "self-test not supported"
    start = time.monotonic()
    limit = 15 * 60
    time.sleep(2)
    while time.monotonic() - start < limit:
        ctx.sleep(5)
        data, _ = smart_json(dev, "-c", "-l", "selftest")
        pct = None
        running = False
        ata = data.get("ata_smart_data", {}).get("self_test", {}).get("status", {})
        if ata:
            running = 240 <= ata.get("value", 0) <= 255
            pct = 100 - ata.get("remaining_percent", 100) if running else 100
        nv = data.get("nvme_self_test_log", {})
        if nv:
            op = nv.get("current_self_test_operation", {}).get("value", 0)
            running = op != 0
            pct = nv.get("current_self_test_completion_percent", 0) if running else 100
        if not ata and not nv:
            return None, "self-test status unavailable"
        ctx.progress(base_frac + span * (pct or 0) / 100,
                     f"{dev}: drive self-test {pct or 0}% ({util.fmt_duration(time.monotonic() - start)})")
        if not running:
            break
    else:
        smart_json(dev, "-X")  # abort a self-test that is taking far too long
        return None, "self-test did not finish in time"
    # Read the newest log entry.
    ata_log = data.get("ata_smart_self_test_log", {}).get("standard", {}).get("table", [])
    if ata_log:
        st = ata_log[0].get("status", {})
        return (None if st.get("passed", True) else f"self-test failed: {st.get('string', '')}"), "self-test passed"
    nv_log = data.get("nvme_self_test_log", {}).get("table", [])
    if nv_log:
        r = nv_log[0].get("self_test_result", {})
        return (None if r.get("value", 0) == 0 else f"self-test failed: {r.get('string', '')}"), "self-test passed"
    return None, "self-test finished"


def has_smart(smart: dict) -> bool:
    return any(k in smart for k in ("smart_status", "ata_smart_attributes", "nvme_smart_health_information_log"))


def read_test(ctx: Context, dev: str, mb: int) -> tuple[bool | None, float | None, str]:
    """Sequential direct read of the start of the disk.

    Returns (ok, MB/s, message); ok is None when the test couldn't run (not the drive's fault).
    """
    cmd = ["dd", f"if={dev}", "of=/dev/null", "bs=4M", f"count={max(1, mb // 4)}", "iflag=direct"]
    res = util.run_cancellable(ctx, cmd, timeout=600)
    if res.returncode != 0:
        last = (res.stderr.strip().splitlines() or ["read failed"])[-1]
        if "Input/output error" in res.stderr or res.returncode == 124:
            return False, None, last
        return None, None, f"read test not possible ({last})"
    m = re.search(r"copied,\s*([\d.,]+)\s*s,\s*([\d.,]+)\s*([kMG]B)/s", res.stderr)
    if not m:
        return True, None, "read OK"
    speed = float(m.group(2).replace(",", "."))
    speed *= {"kB": 1 / 1000, "MB": 1, "GB": 1000}[m.group(3)]
    return True, speed, f"read {mb} MB at {speed:.0f} MB/s"


@timed
def run(ctx: Context) -> Result:
    if not util.have("smartctl"):
        return Result("storage", NAME, Status.SKIP, "smartmontools is not installed.")
    if not util.is_root():
        return Result("storage", NAME, Status.SKIP, "Needs administrator (root) rights to read drive health.")
    disks, skipped = list_disks()
    details: list[str] = []
    found: list[tuple[str, str, str]] = []  # (problem id, disk, text)
    if not disks:
        found.append(("no_disks", "", "no internal drives detected"))

    do_selftest = ctx.params.get("selftest", False)
    read_mb = int(ctx.params.get("read_mb", 0))
    if ctx.time_scale < 1:
        read_mb = min(read_mb, 256)
    for i, d in enumerate(disks):
        name = d["name"]
        dev = f"/dev/{name}"
        label = f"{name} ({(d.get('model') or 'disk').strip()}, {util.human_bytes(int(d['size']))})"
        frac, span = i / len(disks), 1 / len(disks)
        ctx.progress(frac, f"Reading health data from {name}")
        ctx.log(f"Checking {label}")
        smart, rc = smart_json(dev, "-a")
        if not has_smart(smart):
            found.append(("no_smart", label, "no health (SMART) data available"))
            info = ["no health (SMART) data"]
        else:
            problems, info = analyze_smart(smart, rc)
            found += [(pid, label, text) for pid, text in problems]
        if do_selftest and has_smart(smart):
            problem, msg = run_selftest(ctx, dev, frac, span * 0.7)
            info.append(msg)
            if problem:
                found.append(("selftest_failed", label, problem))
        if read_mb:
            ctx.progress(frac + span * 0.8, f"{name}: read-speed test ({read_mb} MB)")
            ok, speed, msg = read_test(ctx, dev, read_mb)
            info.append(msg)
            if ok is False:
                found.append(("read_error", label, msg))
            elif speed is not None and speed < expected_speed(smart, name):
                found.append(("slow", label, f"slow reads: {speed:.0f} MB/s"))
        details.append(f"{label}: " + ("; ".join(info) if info else "no extra data"))
    details += skipped
    # Problems first, except those already spelled out in the per-disk lines.
    details = [f"⚠ {label}: {text}" for pid, label, text in found
               if label and pid not in ("no_smart", "read_error")] + details

    if not found:
        return Result("storage", NAME, Status.PASS,
                      f"{len(disks)} drive(s) checked – all healthy.", details,
                      explanation="Each drive's built-in health monitoring (SMART) reports no bad "
                                  "sectors, errors or wear problems." +
                                  (" The drive self-test also passed." if do_selftest else ""))

    worst = max((SEVERITY[p] for p, _, _ in found), key=lambda s: s.rank)
    ids = []
    for p, _, _ in sorted(found, key=lambda f: -SEVERITY[f[0]].rank):
        if p not in ids:
            ids.append(p)
    explanation = " ".join(ADVICE[p][0] for p in ids)
    steps: list[str] = []
    for p in ids:
        steps += [s for s in ADVICE[p][1] if s not in steps]
    summary = {
        Status.FAIL: "A drive has serious problems – back up your data now.",
        Status.WARN: "A drive shows early warning signs.",
        Status.SKIP: "Drive health data could not be read.",
    }.get(worst, "Drive check finished.")
    if ids == ["no_disks"]:
        summary = "No internal drive was found."
    return Result("storage", NAME, worst, summary, details, explanation, steps)
