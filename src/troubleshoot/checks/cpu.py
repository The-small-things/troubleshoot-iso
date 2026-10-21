"""CPU stress test with temperature, clock-speed (throttling) and fan monitoring."""

from __future__ import annotations

import glob
import os
import re

from .. import util
from ..model import Context, Result, Status, timed

NAME = "Processor stress & cooling"
HOT_C = 97.0          # sustained temperatures at/above this mean the cooling is struggling
THROTTLE_RATIO = 0.5  # clocks falling below half of max under load = heavy throttling


def _throttle_count() -> int:
    total = 0
    for p in glob.glob(util.sys_path("devices", "system", "cpu", "cpu[0-9]*", "thermal_throttle",
                                     "package_throttle_count")):
        total += util.read_int(p) or 0
    return total


def stress_failures(output: str) -> list[str]:
    """Lines where stress-ng reports a failed stressor or a wrong computation."""
    pat = re.compile(r"stress-ng: (fail|error):|\bfailed: [1-9]|verif\w* (error|fail)|miscompar", re.I)
    return [line.strip() for line in output.splitlines() if pat.search(line)]


def evaluate(rc: int, output: str, max_temp: float | None, late_freq: float | None,
             max_freq: float | None, throttle_events: int, hot_fan_zero: bool,
             duration: float) -> Result:
    details = [f"Ran full load on every core for {util.fmt_duration(duration)}."]
    if max_temp is not None:
        details.append(f"Highest temperature: {max_temp:.0f} °C")
    else:
        details.append("No temperature sensors were readable.")
    if late_freq and max_freq:
        details.append(f"Average clock speed near the end: {late_freq:.0f} MHz "
                       f"(maximum {max_freq:.0f} MHz, {100 * late_freq / max_freq:.0f}%)")
    if throttle_events:
        details.append(f"Thermal throttle events recorded by the CPU: {throttle_events}")

    failures = stress_failures(output)
    if rc != 0 or failures:
        details += [f"stress-ng: {l}" for l in failures[:10]] or [f"stress-ng exited with code {rc}"]
        return Result(
            "cpu", NAME, Status.FAIL, "The processor made errors or the stress test crashed.", details,
            explanation="Under full load the processor produced wrong results or the test process "
                        "failed. A healthy CPU never miscalculates. Common causes are overheating, an "
                        "unstable overclock/undervolt, a weak or failing power supply / VRM, or "
                        "faulty memory (which the CPU test also exercises).",
            next_steps=[
                "If you changed overclocking or undervolting settings, reset the BIOS to defaults and re-test.",
                "Run the Memory test (or memtest86+ from the boot menu) to rule out bad RAM.",
                "Clean dust out of the fans and vents, then run the Full test again.",
                "If errors persist with default settings, the CPU, motherboard or power supply needs "
                "professional diagnosis.",
            ])

    problems = []
    if max_temp is not None and max_temp >= HOT_C:
        problems.append(f"reached {max_temp:.0f} °C")
    if late_freq and max_freq and late_freq < THROTTLE_RATIO * max_freq:
        problems.append(f"slowed down to {100 * late_freq / max_freq:.0f}% of its top speed")
    if hot_fan_zero:
        problems.append("the fan reported 0 RPM while the processor was hot")

    if problems:
        return Result(
            "cpu", NAME, Status.WARN,
            "The processor is stable, but it " + " and ".join(problems) + ".", details,
            explanation="The CPU did its work correctly, but the cooling system is struggling. When a "
                        "processor gets too hot it protects itself by slowing down (\"thermal "
                        "throttling\"), which feels like lag, stutter, or loud fans. The usual causes "
                        "are dust-clogged vents and heatsinks, dried-out thermal paste (common after "
                        "3–5 years), a failing fan, or using a laptop on a soft surface like a bed.",
            next_steps=[
                "Use the computer on a hard, flat surface so air can flow underneath.",
                "Blow out the vents and fan with compressed air (hold the fan still while you do).",
                "If it is several years old, have the thermal paste replaced.",
                "If the fan never spins up or makes grinding noises, replace the fan.",
            ])

    return Result(
        "cpu", NAME, Status.PASS, "The processor ran at full load without errors or overheating.",
        details,
        explanation="Every core was pushed to 100% and checked for calculation errors while the "
                    "temperature and clock speed were monitored. Everything stayed within healthy limits.",
    )


@timed
def run(ctx: Context) -> Result:
    if not util.have("stress-ng"):
        return Result("cpu", NAME, Status.SKIP, "stress-ng is not installed.")
    seconds = int(ctx.scaled(ctx.params.get("seconds", 60)))
    max_freq = util.cpu_max_freq_mhz()
    throttle_start = _throttle_count()
    samples: list[tuple[float, float | None, float | None, int]] = []  # (t, temp, freq, fanmax)

    def tick(elapsed: float) -> None:
        temps = util.cpu_temps()
        freqs = util.cpu_freqs_mhz()
        fans = util.fan_speeds()
        t = max(temps.values()) if temps else None
        f = sum(freqs) / len(freqs) if freqs else None
        samples.append((elapsed, t, f, max(fans.values()) if fans else -1))
        msg = f"{util.fmt_duration(elapsed)} of {util.fmt_duration(seconds)}"
        if t is not None:
            msg += f" · {t:.0f} °C"
        if f is not None:
            msg += f" · {f:.0f} MHz"
        ctx.progress(min(1.0, elapsed / seconds), msg)

    cmd = ["stress-ng", "--cpu", "0", "--verify", "--timeout", f"{seconds}s", "--metrics-brief"]
    ctx.log("Running: " + " ".join(cmd))
    res = util.run_cancellable(ctx, cmd, timeout=seconds + 60, on_tick=tick, tick=2.0)
    output = (res.stdout or "") + "\n" + (res.stderr or "")
    for line in output.strip().splitlines()[-8:]:
        ctx.log(line)

    temps = [s[1] for s in samples if s[1] is not None]
    late = [s[2] for s in samples if s[2] is not None and s[0] >= seconds * 0.6]
    hot_fan_zero = any(s[1] is not None and s[1] >= 80 and s[3] == 0 for s in samples)
    return evaluate(res.returncode, output, max(temps) if temps else None,
                    sum(late) / len(late) if late else None, max_freq,
                    _throttle_count() - throttle_start, hot_fan_zero, seconds)
