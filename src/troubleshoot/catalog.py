"""The list of tests and the test profiles (Quick / Standard / Full / Custom)."""

from __future__ import annotations

from dataclasses import dataclass

from .checks import battery, bluetooth, cpu, graphics, kernel_log, memory, network, storage, sysinfo
from .model import TestSpec

TESTS: dict[str, TestSpec] = {t.test_id: t for t in [
    TestSpec("sysinfo", "System information", "Model, processor, memory, disks.", False, sysinfo.run),
    TestSpec("graphics", "Graphics driver", "Checks the graphics chip has a working driver.", False, graphics.run),
    TestSpec("screen", "Screen", "Full-screen colours to spot dead pixels, lines and backlight problems.", True),
    TestSpec("keyboard", "Keyboard", "Press every key and watch it light up.", True),
    TestSpec("pointer", "Touchpad / mouse", "Move, click, scroll and drag to targets.", True),
    TestSpec("webcam", "Webcam", "Live camera picture to check it works and looks right.", True),
    TestSpec("audio", "Speakers & microphone", "Left/right test tones and a microphone recording.", True),
    TestSpec("battery", "Battery & charging", "Battery wear, charger and power draw.", False, battery.run),
    TestSpec("network", "Network adapters", "Ethernet/Wi-Fi detection and a Wi-Fi scan.", False, network.run),
    TestSpec("bluetooth", "Bluetooth", "Turns Bluetooth on and scans for nearby devices.", False,
             bluetooth.run),
    TestSpec("storage", "Storage drives", "Drive health (SMART), self-test and read speed. Read-only.",
             False, storage.run),
    TestSpec("memory", "Memory (RAM)", "Writes and verifies test patterns in RAM.", False, memory.run),
    TestSpec("cpu", "Processor stress & cooling", "Full load on all cores while watching temperature.",
             False, cpu.run),
    TestSpec("kernel_log", "Hardware error log", "Looks for hardware errors reported during testing.",
             False, kernel_log.run),
]}

# Interactive tests run first so the user can walk away during the long automated part.
ORDER = ["sysinfo", "graphics", "screen", "keyboard", "pointer", "webcam", "audio",
         "battery", "network", "bluetooth", "storage", "memory", "cpu", "kernel_log"]


@dataclass
class Profile:
    key: str
    title: str
    duration: str
    description: str
    params: dict  # test id -> parameters; tests not listed are not run


STANDARD_PARAMS = {
    "sysinfo": {}, "graphics": {}, "screen": {}, "keyboard": {}, "pointer": {}, "webcam": {}, "audio": {},
    "battery": {}, "network": {"scan": True}, "bluetooth": {"scan_seconds": 12},
    "storage": {"selftest": True, "read_mb": 1024},
    "memory": {"fraction": 0.5, "max_mb": 4096, "loops": 1},
    "cpu": {"seconds": 300},
    "kernel_log": {},
}

PROFILES: dict[str, Profile] = {p.key: p for p in [
    Profile("quick", "Quick check", "about 5 minutes",
            "Fast health check: screen, keyboard, touchpad, webcam, battery, Wi-Fi, Bluetooth, "
            "drive health, a short memory test and a 1-minute processor stress test.",
            {"sysinfo": {}, "graphics": {}, "screen": {}, "keyboard": {}, "pointer": {}, "webcam": {},
             "battery": {}, "network": {"scan": True}, "bluetooth": {"scan_seconds": 8},
             "storage": {"selftest": False, "read_mb": 0},
             "memory": {"fraction": 0.25, "max_mb": 512, "loops": 1},
             "cpu": {"seconds": 60}, "kernel_log": {}}),
    Profile("standard", "Standard test", "about 20–40 minutes",
            "Everything in Quick, plus speakers & microphone, a drive self-test and read test, half "
            "of the RAM, and a 5-minute stress test.", STANDARD_PARAMS),
    Profile("full", "Full / overnight test", "1–3 hours or more",
            "Thorough: tests almost all RAM twice, 20 minutes of full CPU load, drive self-test and "
            "a longer read test. Best for intermittent crashes and freezes.",
            {**STANDARD_PARAMS,
             "storage": {"selftest": True, "read_mb": 4096},
             "memory": {"fraction": 0.85, "max_mb": None, "loops": 2},
             "cpu": {"seconds": 1200}}),
    Profile("custom", "Custom", "you choose",
            "Pick exactly which tests to run (Standard-length settings).", STANDARD_PARAMS),
]}


def plan(profile: Profile, only: set[str] | None = None) -> list[tuple[TestSpec, dict]]:
    """Ordered (test, params) list for a profile; ``only`` restricts it (Custom)."""
    out = []
    for tid in ORDER:
        if tid not in profile.params:
            continue
        if only is not None and tid not in only and tid != "sysinfo":
            continue
        out.append((TESTS[tid], profile.params[tid]))
    return out
