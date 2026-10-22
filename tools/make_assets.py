#!/usr/bin/env python3
"""Render the boot-menu and boot-splash artwork from the mascot drawing in src/troubleshoot/art.py.

Run this after changing the art; the PNGs (and GRUB .pf2 fonts) it writes are committed, so
building the ISO doesn't need Pillow or the fonts.

    python3 tools/make_assets.py

Needs: Pillow, fonts-comfortaa, fonts-dejavu-core, grub-common (for grub-mkfont).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from troubleshoot import art  # noqa: E402

BOOT = os.path.join(ROOT, "live", "config", "bootmenu")
SPLASH = os.path.join(ROOT, "live", "config", "includes.chroot", "usr", "share", "plymouth", "themes", "chip")
TITLE_FONT = "/usr/share/fonts/truetype/comfortaa/Comfortaa-Bold.ttf"
BODY_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SS = 4  # supersampling factor for smooth edges

BG_TOP, BG_BOTTOM = (15, 23, 42), (30, 27, 75)
MUTED = (148, 163, 184)
ACCENT = (96, 165, 250)


def hexrgb(c: str) -> tuple[int, int, int]:
    return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)


def draw_chip(d: ImageDraw.ImageDraw, x: float, y: float, size: float, expression="happy") -> None:
    """Draw the mascot (already in supersampled coordinates)."""
    sc = lambda pts: [(x + px * size, y + py * size) for px, py in pts]  # noqa: E731
    for shape in art.chip(expression):
        if shape[0] == "poly":
            _, pts, fill, outline, w = shape
            d.polygon(sc(pts), fill=hexrgb(fill), outline=hexrgb(outline) if outline else None,
                      width=max(1, int(w * size)) if outline else 0)
        elif shape[0] == "line":
            _, pts, color, w = shape
            width = max(1, int(w * size))
            p = sc(pts)
            d.line(p, fill=hexrgb(color), width=width, joint="curve")
            for px, py in (p[0], p[-1]):  # round caps
                d.ellipse((px - width / 2, py - width / 2, px + width / 2, py + width / 2), fill=hexrgb(color))
        else:
            _, (cx, cy, rx, ry), fill, outline, w = shape
            box = (x + (cx - rx) * size, y + (cy - ry) * size, x + (cx + rx) * size, y + (cy + ry) * size)
            d.ellipse(box, fill=hexrgb(fill), outline=hexrgb(outline) if outline else None,
                      width=max(1, int(w * size)) if outline else 0)


def gradient(w: int, h: int) -> Image.Image:
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for yy in range(h):
        t = yy / max(1, h - 1)
        d.line([(0, yy), (w, yy)], fill=tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)))
    return img


def pulse(d: ImageDraw.ImageDraw, x0, y0, w, h, color, width):
    pts = [(x0 + x * w, y0 + y * h) for x, y in art.pulse_line(0.1, 160)]
    d.line(pts, fill=color, width=width, joint="curve")


def font(path, px):
    return ImageFont.truetype(path, px)


def background(w: int, h: int, layout: dict) -> Image.Image:
    """Boot-menu background: Chip on the left, title and tagline above the menu area."""
    big = gradient(w * SS, h * SS)
    d = ImageDraw.Draw(big)
    pulse(d, 0, layout["pulse_y"] * SS, w * SS, layout["pulse_h"] * SS, (37, 99, 235), 2 * SS)
    draw_chip(d, layout["chip_x"] * SS, layout["chip_y"] * SS, layout["chip"] * SS)
    d.text((layout["text_x"] * SS, layout["title_y"] * SS), "Hardware Troubleshooter",
           font=font(TITLE_FONT, layout["title"] * SS), fill=(241, 245, 249))
    d.text((layout["text_x"] * SS, layout["tag_y"] * SS), layout["tagline"],
           font=font(BODY_FONT, layout["tag"] * SS), fill=MUTED)
    return big.resize((w, h), Image.LANCZOS)


def nine_slice(path_prefix: str, color, radius: int, size: int = 48) -> None:
    """GRUB's highlight box is drawn from 9 pieces: corners, edges and centre."""
    big = Image.new("RGBA", (size * SS, size * SS), (0, 0, 0, 0))
    ImageDraw.Draw(big).rounded_rectangle((0, 0, size * SS - 1, size * SS - 1), radius * SS, fill=color)
    img = big.resize((size, size), Image.LANCZOS)
    r = radius
    boxes = {"nw": (0, 0, r, r), "n": (r, 0, size - r, r), "ne": (size - r, 0, size, r),
             "w": (0, r, r, size - r), "c": (r, r, size - r, size - r), "e": (size - r, r, size, size - r),
             "sw": (0, size - r, r, size), "s": (r, size - r, size - r, size), "se": (size - r, size - r, size, size)}
    for name, box in boxes.items():
        img.crop(box).save(f"{path_prefix}_{name}.png")


def icon(name: str, out_dir: str, px: int = 32) -> None:
    S = px * SS
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    white = (241, 245, 249)
    lw = int(S * 0.09)
    if name == "chip":
        draw_chip(d, 0, 0, S)
    elif name == "safe":  # a text terminal
        d.rounded_rectangle((S * 0.06, S * 0.14, S * 0.94, S * 0.86), S * 0.12, outline=white, width=lw)
        d.text((S * 0.2, S * 0.24), ">_", font=font(BOLD_FONT, int(S * 0.42)), fill=white)
    elif name == "memory":  # a RAM stick
        d.rounded_rectangle((S * 0.04, S * 0.28, S * 0.96, S * 0.66), S * 0.06, outline=white, width=lw)
        for i in range(4):
            x = S * (0.16 + i * 0.2)
            d.rectangle((x, S * 0.38, x + S * 0.1, S * 0.56), fill=white)
        for i in range(7):
            x = S * (0.1 + i * 0.12)
            d.rectangle((x, S * 0.7, x + S * 0.05, S * 0.8), fill=white)
    elif name == "verify":
        d.line([(S * 0.18, S * 0.52), (S * 0.42, S * 0.76), (S * 0.84, S * 0.26)], fill=white, width=lw * 2,
               joint="curve")
    elif name == "firmware":  # gear
        cx = cy = S / 2
        import math
        pts = []
        for i in range(16):
            a = math.pi * 2 * i / 16
            rr = S * (0.46 if i % 2 == 0 else 0.34)
            pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
        d.polygon(pts, fill=white)
        d.ellipse((cx - S * 0.14, cy - S * 0.14, cx + S * 0.14, cy + S * 0.14), fill=(0, 0, 0, 0))
    elif name in ("restart", "poweroff"):
        d.arc((S * 0.14, S * 0.14, S * 0.86, S * 0.86), -60 if name == "poweroff" else -20,
              240 if name == "poweroff" else 290, fill=white, width=lw)
        if name == "poweroff":
            d.line([(S / 2, S * 0.06), (S / 2, S * 0.46)], fill=white, width=lw)
        else:
            d.polygon([(S * 0.66, S * 0.04), (S * 0.9, S * 0.3), (S * 0.58, S * 0.34)], fill=white)
    img.resize((px, px), Image.LANCZOS).save(os.path.join(out_dir, f"{name}.png"))


def grub_fonts(out_dir: str) -> None:
    if not shutil.which("grub-mkfont"):
        sys.exit("grub-mkfont not found: apt-get install grub-common")
    for src, size, name in ((TITLE_FONT, 22, "comfortaa_22"), (BODY_FONT, 16, "dejavu_16"),
                            (BOLD_FONT, 16, "dejavu_bold_16")):
        # ASCII plus a few symbols used in the menu keeps the fonts small.
        subprocess.run(["grub-mkfont", "-s", str(size), "-r", "0x20-0x7E,0x2013-0x2014,0x2190-0x2193,0x2022-0x2022",
                        "-o", os.path.join(out_dir, f"{name}.pf2"), src], check=True)


def main() -> None:
    grub_dir = os.path.join(BOOT, "grub", "chip-theme")
    icons_dir = os.path.join(grub_dir, "icons")
    iso_dir = os.path.join(BOOT, "isolinux")
    for d in (grub_dir, icons_dir, iso_dir, SPLASH):
        os.makedirs(d, exist_ok=True)

    background(1024, 768, dict(chip_x=40, chip_y=230, chip=330, text_x=420, title_y=120, title=40,
                               tag_y=186, tag=19, pulse_y=664, pulse_h=40,
                               tagline="Hi, I'm Chip! Choose what you'd like to do:")
               ).save(os.path.join(grub_dir, "background.png"))
    # isolinux (BIOS) menu: 640x480, menu text grid of 8x16 px cells.
    background(640, 480, dict(chip_x=14, chip_y=150, chip=220, text_x=264, title_y=64, title=27,
                              tag_y=106, tag=13, pulse_y=430, pulse_h=26,
                              tagline="Hi, I'm Chip! Choose what you'd like to do:")
               ).convert("RGB").save(os.path.join(iso_dir, "splash.png"))
    nine_slice(os.path.join(grub_dir, "select"), (59, 130, 246, 255), 6, 24)
    nine_slice(os.path.join(grub_dir, "menu"), (30, 41, 59, 200), 16)
    for name in ("chip", "safe", "memory", "verify", "firmware", "restart", "poweroff"):
        icon(name, icons_dir)
    grub_fonts(grub_dir)

    # Plymouth boot splash: Chip with the title underneath, on a transparent background.
    W, H = 520, 380
    big = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    draw_chip(d, (W / 2 - 120) * SS, 0, 240 * SS)
    f = font(TITLE_FONT, 34 * SS)
    text = "Hardware Troubleshooter"
    tw = d.textlength(text, font=f)
    d.text(((W * SS - tw) / 2, 268 * SS), text, font=f, fill=(241, 245, 249))
    f2 = font(BODY_FONT, 17 * SS)
    sub = "Chip is waking up…"
    sw = d.textlength(sub, font=f2)
    d.text(((W * SS - sw) / 2, 326 * SS), sub, font=f2, fill=MUTED)
    big.resize((W, H), Image.LANCZOS).save(os.path.join(SPLASH, "watermark.png"))
    print("Assets written to", BOOT, "and", SPLASH)


if __name__ == "__main__":
    main()
