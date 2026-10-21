"""Battery wear, charging and power draw (laptops)."""

from __future__ import annotations

import os

from .. import util
from ..model import Context, Result, Status, timed

NAME = "Battery & charging"


def _supplies() -> tuple[list[str], list[str]]:
    base = util.sys_path("class", "power_supply")
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return [], []
    bats, acs = [], []
    for n in names:
        p = os.path.join(base, n)
        kind = util.read(os.path.join(p, "type"))
        if kind == "Battery" and util.read(os.path.join(p, "scope")) != "Device":
            bats.append(p)
        elif kind in ("Mains", "USB", "USB_C", "USB_PD"):
            acs.append(p)
    return bats, acs


def read_battery(path: str) -> dict:
    def num(name: str) -> int | None:
        return util.read_int(os.path.join(path, name))

    b: dict = {"name": os.path.basename(path)}
    b["status"] = util.read(os.path.join(path, "status")) or "Unknown"
    b["capacity"] = num("capacity")
    b["cycles"] = num("cycle_count")
    b["model"] = " ".join(filter(None, [util.read(os.path.join(path, "manufacturer")),
                                        util.read(os.path.join(path, "model_name"))]))
    full, design, now = num("energy_full"), num("energy_full_design"), num("energy_now")
    power = num("power_now")
    if full is None or design is None:  # charge-based reporting (µAh / µA)
        volt = num("voltage_min_design") or num("voltage_now")
        cf, cd, cn, cur = num("charge_full"), num("charge_full_design"), num("charge_now"), num("current_now")
        if volt:
            conv = lambda v: None if v is None else v * volt // 1_000_000  # noqa: E731
            full, design, now, power = conv(cf), conv(cd), conv(cn), conv(cur)
        else:
            full, design, now, power = cf, cd, cn, cur
    b["full_wh"] = full / 1e6 if full else None
    b["design_wh"] = design / 1e6 if design else None
    b["now_wh"] = now / 1e6 if now else None
    b["power_w"] = abs(power) / 1e6 if power else None
    b["health"] = (100.0 * full / design) if full and design else None
    return b


def evaluate(bats: list[dict], ac_online: bool | None) -> Result:
    if not bats:
        return Result("battery", NAME, Status.SKIP, "No battery found (desktop computer?).",
                      explanation="This computer doesn't report a battery. On a laptop, that means the "
                                  "battery is disconnected, completely dead, or not recognised.",
                      next_steps=["If this is a laptop, check that the battery is connected/seated. A "
                                  "battery that has been fully drained for months may never recover."])
    details: list[str] = []
    status = Status.PASS
    explanation: list[str] = []
    steps: list[str] = []
    summary = ""
    if ac_online is not None:
        details.append("Charger: " + ("connected" if ac_online else "not connected"))
    for b in bats:
        head = b["name"] + (f" ({b['model']})" if b["model"] else "")
        details.append(f"{head}: {b['status']}, {b['capacity']}% charged" if b["capacity"] is not None
                       else f"{head}: {b['status']}")
        if b["design_wh"]:
            details.append(f"  Capacity: {b['full_wh']:.1f} Wh now vs {b['design_wh']:.1f} Wh when new")
        if b["cycles"]:
            details.append(f"  Charge cycles: {b['cycles']}")
        if b["power_w"] and b["status"] == "Discharging":
            details.append(f"  Current power draw: {b['power_w']:.1f} W")
            if b["now_wh"]:
                details.append(f"  Estimated runtime at this load: {util.fmt_duration(3600 * b['now_wh'] / b['power_w'])}")

        h = b["health"]
        if h is None:
            details.append("  Health: not reported by this battery")
            summary = summary or "Battery found, but it doesn't report its health."
            continue
        details.append(f"  Health: {h:.0f}% of original capacity")
        if h < 60:
            status = Status.FAIL
            summary = f"The battery is worn out ({h:.0f}% of its original capacity)."
            explanation.append(
                "Batteries lose capacity as they age and with each charge cycle. Below about 60% you'll "
                "notice much shorter battery life, and the laptop may shut down suddenly even when it "
                "shows charge left.")
            steps += ["Replace the battery (use the exact model or a reputable replacement).",
                      "If the battery looks swollen or the case/trackpad is bulging, stop using the laptop "
                      "and replace the battery right away – swollen batteries are a fire risk."]
        elif h < 80:
            if status is not Status.FAIL:
                status = Status.WARN
                summary = f"The battery is showing wear ({h:.0f}% of its original capacity)."
            explanation.append(
                "The battery has lost a noticeable part of its capacity, which is normal after a few "
                "years or a few hundred charge cycles. Battery life will be shorter than when new.")
            steps += ["No action needed unless the battery life no longer fits your needs; then replace it."]
        elif not summary:
            summary = f"Battery health is good ({h:.0f}% of its original capacity)."

        if ac_online and b["status"] == "Discharging":
            status = Status.FAIL if status is Status.FAIL else Status.WARN
            summary = "The charger is connected, but the battery is draining instead of charging."
            explanation.append(
                "The laptop sees the charger, but isn't charging. This points at a too-weak or faulty "
                "charger, a damaged charging port/cable, or a fault in the laptop's charging circuit.")
            steps += ["Try a different, original-wattage charger and cable.",
                      "Check the charging port for dirt or a loose connection."]
        elif ac_online and b["status"] == "Not charging" and (b["capacity"] or 0) < 90:
            details.append("  Note: the battery reports \"not charging\" while the charger is connected.")
            explanation.append(
                "Some laptops deliberately stop charging at a set level to extend battery life (a "
                "\"charge limit\" or \"conservation mode\" in the BIOS or vendor app). If that isn't "
                "enabled, the charger or charging circuit may be faulty.")
            steps += ["Check the BIOS / vendor software for a battery charge limit setting."]
    if ac_online and not any(b["status"] == "Discharging" for b in bats):
        steps.append("Tip: unplug the charger and run the test again to also measure power draw "
                     "and estimated battery runtime.")
    if not explanation:
        explanation.append("The battery holds most of its original charge and reports no faults.")
    return Result("battery", NAME, status, summary or "Battery checked.", details,
                  " ".join(explanation), steps)


@timed
def run(ctx: Context) -> Result:
    bats, acs = _supplies()
    ac_online = None
    if acs:
        ac_online = any(util.read(os.path.join(a, "online")) == "1" for a in acs)
    return evaluate([read_battery(b) for b in bats], ac_online)
