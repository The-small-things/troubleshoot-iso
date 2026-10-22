#!/usr/bin/env python3
"""Shrink SuperTuxKart's data to keep the ISO under GitHub's 2 GiB release-file limit.

- Textures larger than 512 px are scaled down to 512 px, which is about what the game itself
  does at load time when "high-definition textures" is off. That saves ~280 MB of the
  ~700 MB of data.
- Smaller PNGs are recompressed losslessly.
- Translations (the live system runs in English) and the bundled ghost-race replays are removed.

Run inside the ISO's chroot by hooks/live/0060-shrink-supertuxkart.hook.chroot (needs Pillow).
"""

import glob
import io
import os
import shutil
import sys
from multiprocessing import Pool

from PIL import Image

CAP = 512


def shrink(path: str) -> int:
    """Rewrite one image in place if that makes it smaller. Returns bytes saved."""
    before = os.path.getsize(path)
    try:
        with Image.open(path) as im:
            im.load()
            fmt = "PNG" if path.lower().endswith(".png") else "JPEG"
            w, h = im.size
            if max(w, h) > CAP:
                s = CAP / max(w, h)
                im = im.resize((max(1, round(w * s)), max(1, round(h * s))), Image.LANCZOS)
            buf = io.BytesIO()
            if fmt == "PNG":
                im.save(buf, "PNG", optimize=True)
            else:
                im.convert("RGB").save(buf, "JPEG", quality=90, optimize=True)
    except Exception as e:  # leave anything unusual untouched
        print(f"  skipped {path}: {e}", file=sys.stderr)
        return 0
    if buf.tell() >= before:
        return 0
    with open(path, "wb") as f:
        f.write(buf.getvalue())
    return before - buf.tell()


def dir_size(d: str) -> int:
    return sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(d) for f in fs)


def main(data: str) -> None:
    before = dir_size(data)
    for sub in ("po", "replay"):
        p = os.path.join(data, sub)
        if os.path.isdir(p):
            shutil.rmtree(p)
            os.makedirs(p)  # keep the (now empty) directory the game looks in
    images = [f for ext in ("png", "jpg", "jpeg") for f in glob.glob(f"{data}/**/*.{ext}", recursive=True)]
    try:
        with Pool(os.cpu_count() or 2) as pool:
            pool.map(shrink, images, chunksize=8)
    except OSError as e:  # e.g. no /dev/shm inside the build chroot: do it in one process
        print(f"  parallel processing unavailable ({e}); continuing in one process")
        for path in images:
            shrink(path)
    after = dir_size(data)
    print(f"SuperTuxKart data: {before / 1048576:.0f} MB -> {after / 1048576:.0f} MB "
          f"({len(images)} images processed)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/usr/share/games/supertuxkart/data")
