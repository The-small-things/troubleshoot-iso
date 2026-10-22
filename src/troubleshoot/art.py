"""Chip, the troubleshooter's mascot, as resolution-independent shapes.

The art is a list of primitives in a unit square (0..1), so the same drawing is used by the
Tk interface (``gui/mascot.py``) and by ``tools/make_assets.py``, which renders the boot-menu
and boot-splash PNGs. Only three primitive kinds exist so any renderer stays trivial:

    ("poly", points, fill, outline, width)
    ("line", points, color, width)          # polyline with round ends
    ("oval", (cx, cy, rx, ry), fill, outline, width)
"""

from __future__ import annotations

import math

BODY = "#3b82f6"
BODY_DARK = "#1e40af"
SCREEN = "#0f172a"
GLOW = "#67e8f9"
PIN = "#94a3b8"
ANTENNA = "#fbbf24"
CHEEK = "#f472b6"
HEART = "#ef4444"

EXPRESSIONS = ("happy", "blink", "thinking", "worried", "excited", "sleepy")


def rounded_rect(x0, y0, x1, y1, r, steps=6):
    pts = []
    for cx, cy, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for i in range(steps + 1):
            a = math.radians(a0 + 90 * i / steps)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def arc(cx, cy, rx, ry, a0, a1, steps=12):
    return [(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / steps)),
             cy + ry * math.sin(math.radians(a0 + (a1 - a0) * i / steps))) for i in range(steps + 1)]


def heart(cx, cy, s, steps=28):
    pts = []
    for i in range(steps):
        t = 2 * math.pi * i / steps
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((cx + x * s / 17, cy - y * s / 17))
    return pts


def chip(expression: str = "happy", antenna_glow: float = 1.0) -> list[tuple]:
    """The mascot's shapes for one expression. ``antenna_glow`` 0..1 animates the antenna ball."""
    shapes: list[tuple] = []
    # Antenna.
    shapes.append(("line", [(0.5, 0.13), (0.5, 0.05)], BODY_DARK, 0.022))
    g = 0.03 + 0.015 * antenna_glow
    shapes.append(("oval", (0.5, 0.04, g, g), ANTENNA, BODY_DARK, 0.008))
    # Chip pins on both sides.
    for y in (0.36, 0.5, 0.64):
        shapes.append(("poly", rounded_rect(0.04, y - 0.035, 0.16, y + 0.035, 0.015, 2), PIN, BODY_DARK, 0.008))
        shapes.append(("poly", rounded_rect(0.84, y - 0.035, 0.96, y + 0.035, 0.015, 2), PIN, BODY_DARK, 0.008))
    # Body and face screen.
    shapes.append(("poly", rounded_rect(0.12, 0.13, 0.88, 0.89, 0.15), BODY, BODY_DARK, 0.018))
    shapes.append(("poly", rounded_rect(0.2, 0.24, 0.8, 0.66, 0.09), SCREEN, BODY_DARK, 0.01))
    # Eyes.
    ex = {"thinking": 0.03}.get(expression, 0.0)
    ey = {"thinking": -0.03, "sleepy": 0.02}.get(expression, 0.0)
    for x in (0.38, 0.62):
        cx, cy = x + ex, 0.42 + ey
        if expression in ("happy", "excited"):
            shapes.append(("line", arc(cx, cy + 0.025, 0.06, 0.055, 200, 340), GLOW, 0.028))
        elif expression in ("blink", "sleepy"):
            shapes.append(("line", [(cx - 0.055, cy), (cx + 0.055, cy)], GLOW, 0.026))
        else:
            shapes.append(("oval", (cx, cy, 0.062, 0.07), GLOW, None, 0))
            shapes.append(("oval", (cx + 0.015, cy - 0.02, 0.02, 0.02), "white", None, 0))
    if expression == "worried":
        shapes.append(("line", [(0.31, 0.345), (0.43, 0.31)], GLOW, 0.02))
        shapes.append(("line", [(0.69, 0.345), (0.57, 0.31)], GLOW, 0.02))
    # Mouth.
    if expression == "worried":
        shapes.append(("line", arc(0.5, 0.6, 0.07, 0.035, 200, 340), GLOW, 0.022))
    elif expression == "excited":
        shapes.append(("poly", arc(0.5, 0.53, 0.09, 0.07, 0, 180), GLOW, None, 0))
    elif expression == "thinking":
        shapes.append(("line", [(0.45, 0.56), (0.56, 0.545)], GLOW, 0.022))
    elif expression == "sleepy":
        shapes.append(("oval", (0.5, 0.56, 0.025, 0.02), GLOW, None, 0))
    else:
        shapes.append(("line", arc(0.5, 0.52, 0.08, 0.055, 20, 160), GLOW, 0.022))
    # Cheeks and the heart badge ("health check").
    if expression in ("happy", "excited", "blink"):
        shapes.append(("oval", (0.29, 0.56, 0.035, 0.022), CHEEK, None, 0))
        shapes.append(("oval", (0.71, 0.56, 0.035, 0.022), CHEEK, None, 0))
    shapes.append(("poly", heart(0.5, 0.775, 0.065), HEART, BODY_DARK, 0.008))
    return shapes


def pulse_line(phase: float = 0.0, points: int = 60) -> list[tuple[float, float]]:
    """A heartbeat (ECG) trace across the unit width; ``phase`` 0..1 scrolls it."""
    pts = []
    for i in range(points + 1):
        x = i / points
        t = (x + phase) % 1.0
        if 0.40 < t < 0.44:
            y = 0.5 + (t - 0.40) / 0.04 * 0.25
        elif 0.44 <= t < 0.48:
            y = 0.75 - (t - 0.44) / 0.04 * 0.75
        elif 0.48 <= t < 0.53:
            y = (t - 0.48) / 0.05 * 0.65
        elif 0.53 <= t < 0.56:
            y = 0.65 - (t - 0.53) / 0.03 * 0.15
        else:
            y = 0.5
        pts.append((x, y))
    return pts
