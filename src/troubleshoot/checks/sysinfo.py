"""Collect a hardware inventory. Never fails; it gives the report its header."""

from __future__ import annotations

import json
import os
import re

from .. import util
from ..model import Context, Result, Status, timed


def collect() -> dict:
    info: dict = {}
    dmi = util.sys_path("class", "dmi", "id")
    info["vendor"] = util.read(os.path.join(dmi, "sys_vendor")) or "Unknown"
    info["product"] = util.read(os.path.join(dmi, "product_name")) or "Unknown"
    version = util.read(os.path.join(dmi, "product_version")) or ""
    if version and version.lower() not in ("none", "to be filled by o.e.m.", "default string"):
        info["product"] += f" ({version})"
    if info["vendor"] == "Unknown" and info["product"] == "Unknown":
        info["vendor"], info["product"] = "Unknown", "computer"
    info["serial"] = util.read(os.path.join(dmi, "product_serial")) or ""
    info["bios"] = " ".join(filter(None, [
        util.read(os.path.join(dmi, "bios_vendor")),
        util.read(os.path.join(dmi, "bios_version")),
        util.read(os.path.join(dmi, "bios_date")),
    ])) or "Unknown"
    info["chassis"] = _chassis(util.read(os.path.join(dmi, "chassis_type")))

    cpuinfo = util.read(os.path.join(util.PROC, "cpuinfo")) or ""
    m = re.search(r"^model name\s*:\s*(.+)$", cpuinfo, re.M)
    info["cpu"] = re.sub(r"\s+", " ", m.group(1)) if m else "Unknown"
    info["cpu_threads"] = os.cpu_count() or 0

    mem = util.meminfo()
    info["ram_total"] = util.human_bytes(mem.get("MemTotal", 0) * 1024)

    disks = []
    res = util.run(["lsblk", "-J", "-d", "-b", "-o", "NAME,SIZE,MODEL,TRAN,ROTA,RM,TYPE"])
    if res.returncode == 0:
        try:
            for d in json.loads(res.stdout).get("blockdevices", []):
                if d.get("type") != "disk" or d["name"].startswith(("loop", "zram", "ram")):
                    continue
                kind = "HDD" if d.get("rota") in (True, "1", 1) else "SSD"
                if (d.get("tran") or "") == "nvme" or d["name"].startswith("nvme"):
                    kind = "NVMe SSD"
                if d.get("rm") in (True, "1", 1) or d.get("tran") == "usb":
                    kind = "USB/removable"
                disks.append(f"{d['name']}: {(d.get('model') or '').strip() or 'disk'} "
                             f"– {util.human_bytes(int(d.get('size') or 0))} ({kind})")
        except (ValueError, KeyError):
            pass
    info["disks"] = disks

    gpus = []
    res = util.run(["lspci", "-mm"])
    for line in res.stdout.splitlines():
        if re.search(r'"(VGA compatible controller|3D controller|Display controller)"', line):
            fields = re.findall(r'"([^"]*)"', line)
            if len(fields) >= 3:
                gpus.append(f"{fields[1]} {fields[2]}")
    info["gpus"] = gpus

    info["battery"] = bool(_batteries())
    return info


def _batteries() -> list[str]:
    base = util.sys_path("class", "power_supply")
    try:
        names = os.listdir(base)
    except OSError:
        return []
    return [n for n in names if util.read(os.path.join(base, n, "type")) == "Battery"
            and util.read(os.path.join(base, n, "scope")) != "Device"]


def collect_chassis() -> str:
    return _chassis(util.read(os.path.join(util.sys_path("class", "dmi", "id"), "chassis_type")))


def _chassis(code: str | None) -> str:
    laptops = {"8", "9", "10", "14", "31", "32"}
    desktops = {"3", "4", "5", "6", "7", "13", "15", "16", "35", "36"}
    if code in laptops:
        return "Laptop"
    if code in desktops:
        return "Desktop"
    if code == "30":
        return "Tablet"
    return "Computer"


@timed
def run(ctx: Context) -> Result:
    info = collect()
    details = [
        f"Model: {info['vendor']} {info['product']}",
        f"Type: {info['chassis']}",
        f"Processor: {info['cpu']} ({info['cpu_threads']} threads)",
        f"Memory: {info['ram_total']}",
        f"BIOS/UEFI firmware: {info['bios']}",
    ]
    if info["serial"] and info["serial"].lower() not in ("to be filled by o.e.m.", "default string", "none"):
        details.append(f"Serial number: {info['serial']}")
    details += [f"Graphics: {g}" for g in info["gpus"]] or ["Graphics: not detected"]
    details += [f"Disk {d}" for d in info["disks"]] or ["Disks: none detected"]
    return Result(
        "sysinfo", "System information", Status.INFO,
        f"{info['vendor']} {info['product']} · {info['cpu']} · {info['ram_total']} RAM",
        details,
        explanation="This is what the computer reports about itself. Check that it matches what you "
                    "expect (for example the amount of RAM you paid for, and that every disk shows up). "
                    "A disk that is physically installed but missing here usually means a loose "
                    "connection, a dead drive, or a BIOS setting (e.g. RAID/Intel RST mode) hiding it.",
        next_steps=["Note the model and serial number if you need to contact the manufacturer."],
    )
