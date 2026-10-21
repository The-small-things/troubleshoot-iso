"""Scan the kernel log for hardware errors seen since boot (and during the stress tests)."""

from __future__ import annotations

import re

from .. import util
from ..model import Context, Result, Status, timed

NAME = "Hardware error log"

# (category, severity, pattern). Order matters only for display.
PATTERNS = [
    ("cpu", Status.FAIL, r"\[Hardware Error\]|Machine check events logged|mce: .*(error|CPU \d+ BANK)"),
    ("memory", Status.FAIL, r"EDAC .*(UE|uncorrect)|Memory failure:"),
    ("pcie_fatal", Status.FAIL, r"AER: .*Uncorrect(ed|able) \(Fatal\)"),
    ("disk", Status.WARN, r"I/O error, dev (?!sr|loop)|critical medium error|Buffer I/O error on dev (?!sr|loop)"
                          r"|ata\d+(\.\d+)?: failed command|nvme\d+.*(timeout|I/O \d+ QID|controller is down)"),
    ("link", Status.WARN, r"ata\d+: (hard resetting link|SATA link down|COMRESET failed)"),
    ("thermal", Status.WARN, r"temperature above threshold|critical temperature|thermal.*shutdown"),
    ("gpu", Status.WARN, r"GPU HANG|GPU hang|ring \S+ timeout|amdgpu.*(page fault|GPU reset)|NVRM: Xid"),
    ("usb", Status.WARN, r"over-current|device descriptor read/\d+, error|unable to enumerate USB device"),
    ("pcie", Status.WARN, r"AER: .*Corrected error"),
]

ADVICE = {
    "cpu": ("The processor reported internal hardware errors (machine checks). These come from the CPU, "
            "its cache, the memory controller or the motherboard.",
            ["Reset any overclocking/undervolting in the BIOS to defaults.",
             "Run the Full test and memtest86+ to narrow down whether RAM or the CPU is at fault.",
             "Persistent machine-check errors on default settings need a repair shop or warranty claim."]),
    "memory": ("The memory controller reported uncorrectable memory errors.",
               ["Replace or reseat the RAM; test sticks one at a time."]),
    "pcie_fatal": ("A device on the PCIe bus (graphics card, SSD, Wi-Fi card...) had a fatal communication error.",
                   ["Reseat expansion cards and M.2 drives.", "Update the BIOS."]),
    "disk": ("A drive returned read/write errors or stopped responding.",
             ["Back up your data.", "See the Storage result for which drive is affected."]),
    "link": ("A SATA drive's connection kept dropping and resetting.",
             ["Replace the SATA cable or try another port (desktops); reseat the drive (laptops)."]),
    "thermal": ("The system hit a temperature limit and had to slow down or protect itself.",
                ["Clean the fans and vents, and see the Processor stress & cooling result."]),
    "gpu": ("The graphics chip hung or crashed and had to be reset.",
            ["Update the graphics driver and BIOS in your normal OS.",
             "If you see artifacts or crashes there too, the GPU (or its cooling) may be failing."]),
    "usb": ("A USB device or port misbehaved (failed to connect, or drew too much power).",
            ["Unplug USB devices one by one to find the culprit; avoid using a port that reports over-current."]),
    "pcie": ("Some corrected PCIe bus errors were logged. These were fixed automatically and are often "
             "harmless noise from a specific device or BIOS.",
             ["Only worry about these if you also have crashes; a BIOS update often silences them."]),
}

LABELS = {
    "cpu": "processor machine-check errors", "memory": "memory errors", "pcie_fatal": "fatal PCIe errors",
    "disk": "disk I/O errors", "link": "SATA link resets", "thermal": "overheating events",
    "gpu": "graphics crashes", "usb": "USB errors", "pcie": "corrected PCIe errors",
}


def scan(log: str) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    for line in log.splitlines():
        for cat, _sev, pat in PATTERNS:
            if re.search(pat, line):
                hits.setdefault(cat, []).append(line.strip())
                break
    return hits


def evaluate(log: str) -> Result:
    hits = scan(log)
    if not hits:
        return Result("kernel_log", NAME, Status.PASS, "No hardware errors were logged.",
                      explanation="Linux keeps a log of problems reported by the hardware (disks, "
                                  "processor, memory, USB, graphics). Nothing worrying was recorded "
                                  "since this test system started, including during the stress tests.")
    sev = {cat: s for cat, s, _ in PATTERNS}
    cats = sorted(hits, key=lambda c: -sev[c].rank)
    worst = sev[cats[0]]
    details = []
    for c in cats:
        details.append(f"{LABELS[c]}: {len(hits[c])} message(s), e.g.:")
        details += ["    " + l[:200] for l in hits[c][:3]]
    steps: list[str] = []
    for c in cats:
        steps += [s for s in ADVICE[c][1] if s not in steps]
    summary = "Logged: " + ", ".join(LABELS[c] for c in cats) + "."
    return Result("kernel_log", NAME, worst, summary, details,
                  " ".join(ADVICE[c][0] for c in cats), steps)


@timed
def run(ctx: Context) -> Result:
    res = util.run(["dmesg", "--notime"])
    if res.returncode != 0:
        return Result("kernel_log", NAME, Status.SKIP, "Could not read the kernel log (needs root).")
    return evaluate(res.stdout)
