"""Bluetooth: is there an adapter, does it power on, and can it see devices nearby?"""

from __future__ import annotations

import os
import re

from .. import util
from ..model import Context, Result, Status, timed
from .network import missing_firmware
from .sysinfo import collect_chassis

NAME = "Bluetooth"


def adapters() -> list[dict]:
    base = util.sys_path("class", "bluetooth")
    try:
        names = sorted(n for n in os.listdir(base) if re.fullmatch(r"hci\d+", n))
    except OSError:
        return []
    out = []
    for n in names:
        dev = os.path.join(base, n, "device")
        driver = os.path.basename(os.path.realpath(os.path.join(dev, "driver"))) \
            if os.path.exists(os.path.join(dev, "driver")) else None
        out.append({"name": n, "driver": driver})
    return out


def parse_scan(output: str) -> set[str]:
    """Unique device addresses reported by `bluetoothctl scan on`."""
    return set(re.findall(r"\[(?:NEW|CHG)\]\s+Device\s+((?:[0-9A-F]{2}:){5}[0-9A-F]{2})", output, re.I))


def bt_firmware_missing(missing: list[str]) -> list[str]:
    return [f for f in missing if re.search(r"ibt-|rtl_bt|qca/|BCM|mediatek/.*bt|btusb|brcm/.*hcd", f, re.I)]


def evaluate(adapters_: list[dict], blocked: str | None, powered: bool | None, devices: int | None,
             fw_missing: list[str], laptop: bool) -> Result:
    details = [f"Adapter {a['name']} (driver: {a['driver'] or 'none'})" for a in adapters_]
    if fw_missing:
        details.append("Missing firmware: " + ", ".join(fw_missing[:4]))
    if not adapters_:
        if fw_missing:
            return Result("bluetooth", NAME, Status.WARN,
                          "The Bluetooth chip needs firmware this test system doesn't include.", details,
                          explanation="The chip is there, but couldn't start without its firmware file. "
                                      "That isn't a hardware fault.",
                          next_steps=["If Bluetooth works in your normal OS, you can ignore this."])
        if not laptop:
            return Result("bluetooth", NAME, Status.SKIP, "No Bluetooth adapter (common on desktops).",
                          explanation="Many desktop computers don't have Bluetooth. A cheap USB Bluetooth "
                                      "dongle adds it.")
        return Result(
            "bluetooth", NAME, Status.WARN, "No Bluetooth adapter was found.", details,
            explanation="Most laptops have Bluetooth built into the Wi-Fi card. If it's missing, it may be "
                        "turned off in the BIOS, the Wi-Fi/Bluetooth card may be loose or faulty, or the "
                        "laptop may simply not have it.",
            next_steps=["Check the BIOS for a Bluetooth / wireless on-off setting.",
                        "If Wi-Fi is also missing, the combined Wi-Fi/Bluetooth card is the likely culprit.",
                        "If your normal OS can't see Bluetooth either, a USB Bluetooth dongle is a cheap fix."])
    if blocked == "hard":
        return Result("bluetooth", NAME, Status.WARN, "Bluetooth is switched off by a hardware switch or key.",
                      details,
                      explanation="The adapter works, but a physical switch, a keyboard key (often a plane "
                                  "or antenna icon) or a BIOS setting is keeping the radio off.",
                      next_steps=["Look for a wireless switch on the side of the laptop or an Fn key with an "
                                  "antenna/plane icon, then run the test again."])
    if powered is False:
        return Result("bluetooth", NAME, Status.FAIL, "The Bluetooth adapter is detected but won't turn on.",
                      details,
                      explanation="The computer sees the Bluetooth chip, but it fails to start. This can be "
                                  "missing firmware (see above) or a faulty chip.",
                      next_steps=["If Bluetooth also fails in your normal OS, update the BIOS and the Bluetooth "
                                  "driver there, then consider a USB Bluetooth dongle."])
    if devices is None:
        return Result("bluetooth", NAME, Status.PASS, "Bluetooth adapter detected and powered on.", details,
                      explanation="The adapter works. A scan for nearby devices wasn't possible on this system.")
    details.append(f"Devices found nearby: {devices}")
    if devices == 0:
        return Result("bluetooth", NAME, Status.INFO,
                      "Bluetooth works, but no devices were found nearby.", details,
                      explanation="The adapter turned on and scanned, but nothing answered. That's normal if "
                                  "no Bluetooth devices around you are in pairing/visible mode. If there are, "
                                  "the antenna cable inside the laptop may be loose.",
                      next_steps=["Open the Bluetooth settings on your phone (that makes it visible) and "
                                  "run the test again – it should then be found."])
    return Result("bluetooth", NAME, Status.PASS,
                  f"Bluetooth works – found {devices} device(s) nearby.", details,
                  explanation="The adapter turned on and received signals from nearby Bluetooth devices, so "
                              "the radio and antenna are working.")


@timed
def run(ctx: Context) -> Result:
    laptop = collect_chassis() in ("Laptop", "Tablet")
    ads = adapters()
    fw = bt_firmware_missing(missing_firmware())
    if not ads:
        return evaluate(ads, None, None, None, fw, laptop)

    blocked = None
    for line in util.run(["rfkill", "-n", "-o", "TYPE,SOFT,HARD"]).stdout.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0] == "bluetooth":
            if parts[2] == "blocked":
                blocked = "hard"
            elif parts[1] == "blocked":
                blocked = "soft"
    util.run(["rfkill", "unblock", "bluetooth"])
    if blocked == "hard":
        return evaluate(ads, blocked, None, None, fw, laptop)

    if not util.have("bluetoothctl"):
        return evaluate(ads, None, None, None, fw, laptop)
    util.run(["systemctl", "start", "bluetooth.service"], timeout=15)
    ctx.progress(None, "Turning Bluetooth on")
    util.run(["bluetoothctl", "power", "on"], timeout=15)
    powered = "Powered: yes" in util.run(["bluetoothctl", "show"], timeout=10).stdout
    if not powered:
        return evaluate(ads, None, False, None, fw, laptop)

    seconds = int(ctx.params.get("scan_seconds", 12))
    ctx.progress(None, f"Scanning for Bluetooth devices ({seconds}s)")
    res = util.run_cancellable(ctx, ["bluetoothctl", "--timeout", str(seconds), "scan", "on"],
                               timeout=seconds + 15)
    found = parse_scan(res.stdout) | parse_scan(util.run(["bluetoothctl", "devices"]).stdout.replace(
        "Device ", "[NEW] Device "))
    return evaluate(ads, None, True, len(found), fw, laptop)
