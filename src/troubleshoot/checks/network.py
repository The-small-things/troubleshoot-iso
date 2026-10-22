"""Network adapters: are Ethernet and Wi-Fi detected, with drivers, and can Wi-Fi see networks?"""

from __future__ import annotations

import os
import re

from .. import util
from ..model import Context, Result, Status, timed

NAME = "Network adapters"


def interfaces() -> list[dict]:
    base = util.sys_path("class", "net")
    out = []
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return out
    for n in names:
        p = os.path.join(base, n)
        if n == "lo" or not os.path.exists(os.path.join(p, "device")):
            continue  # skip loopback and virtual interfaces
        wireless = os.path.isdir(os.path.join(p, "wireless")) or os.path.isdir(os.path.join(p, "phy80211"))
        driver = os.path.basename(os.path.realpath(os.path.join(p, "device", "driver"))) \
            if os.path.exists(os.path.join(p, "device", "driver")) else None
        out.append({
            "name": n, "wireless": wireless, "driver": driver,
            "carrier": util.read(os.path.join(p, "carrier")) == "1",
            "speed": util.read_int(os.path.join(p, "speed")),
        })
    return out


def missing_firmware() -> list[str]:
    log = util.run(["dmesg"]).stdout
    return sorted(set(re.findall(r"(?:firmware: failed to load|Direct firmware load for) (\S+)", log)))


def rfkill_blocked() -> list[str]:
    blocked = []
    out = util.run(["rfkill", "-n", "-o", "TYPE,SOFT,HARD"]).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0] in ("wlan", "bluetooth"):
            if parts[2] == "blocked":
                blocked.append(f"{parts[0]} is switched off by a hardware switch/key")
            elif parts[1] == "blocked":
                blocked.append(f"{parts[0]} is switched off in software")
    return blocked


def scan_wifi(ifname: str) -> int | None:
    util.run(["rfkill", "unblock", "wifi"])
    util.run(["ip", "link", "set", ifname, "up"])
    for _ in range(3):
        res = util.run(["iw", "dev", ifname, "scan"], timeout=30)
        if res.returncode == 0:
            return len(set(re.findall(r"^\s*SSID: (.+)$", res.stdout, re.M)))
    return None


@timed
def run(ctx: Context) -> Result:
    ifs = interfaces()
    details = []
    problems = []
    steps = []
    explanation = []
    for i in ifs:
        kind = "Wi-Fi" if i["wireless"] else "Ethernet"
        line = f"{kind} {i['name']} (driver: {i['driver'] or 'none'})"
        if not i["wireless"]:
            if not i["carrier"]:
                line += " – cable not connected"
            elif i["speed"] and i["speed"] > 0:
                line += f" – cable connected at {i['speed']} Mb/s"
            else:
                line += " – cable connected"
        details.append(line)

    wifi = [i for i in ifs if i["wireless"]]
    if wifi and ctx.params.get("scan", True) and util.is_root():
        ctx.progress(None, "Scanning for Wi-Fi networks")
        count = scan_wifi(wifi[0]["name"])
        if count is None:
            problems.append("Wi-Fi could not scan for networks")
            explanation.append("The Wi-Fi adapter is detected but couldn't scan for networks.")
            steps.append("Check that Wi-Fi isn't disabled with a keyboard key, a switch, or in the BIOS.")
        else:
            details.append(f"Wi-Fi scan found {count} network(s) nearby")
            if count == 0:
                problems.append("Wi-Fi found no networks nearby")
                explanation.append(
                    "The Wi-Fi adapter works but couldn't see any networks. If there are networks "
                    "around you, the Wi-Fi antenna cables inside the laptop may be loose or damaged "
                    "(common after a screen repair).")
                steps.append("Make sure you are within range of a working Wi-Fi network and test again.")

    for b in rfkill_blocked():
        details.append(b)
    fw = missing_firmware()
    if fw:
        details.append("Missing firmware: " + ", ".join(fw[:5]))

    if not ifs:
        return Result("network", NAME, Status.WARN, "No network adapters were found.", details,
                      explanation="Neither a wired nor a wireless network adapter was detected. It may be "
                                  "disabled in the BIOS, or – for newer hardware – not yet supported "
                                  "by this test system.",
                      next_steps=["Check the BIOS for disabled onboard LAN / wireless.",
                                  "If your normal OS can't see the adapter either, it may be faulty; a "
                                  "USB Wi-Fi or Ethernet adapter is a cheap workaround."])
    if not wifi and any(f for f in fw if "iwlwifi" in f or "rtw" in f or "ath" in f or "brcm" in f):
        problems.append("Wi-Fi adapter needs firmware that isn't included")
    if problems:
        return Result("network", NAME, Status.WARN, "; ".join(problems).capitalize() + ".", details,
                      " ".join(explanation) or
                      "Some network hardware needs firmware this test system doesn't include. That "
                      "doesn't mean the hardware is broken.",
                      steps or ["If networking works in your normal OS, you can ignore this."])
    kinds = sorted({"Wi-Fi" if i["wireless"] else "Ethernet" for i in ifs})
    return Result("network", NAME, Status.PASS, f"Detected: {', '.join(kinds)}.", details,
                  explanation="The network adapters were detected and their drivers loaded. This test "
                              "checks the hardware, not your internet connection or router.")
