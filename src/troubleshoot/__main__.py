"""Entry point: ``python3 -m troubleshoot [--text] [--fast] [--windowed]``."""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import catalog


def main() -> int:
    ap = argparse.ArgumentParser(prog="troubleshoot", description="Hardware troubleshooter")
    ap.add_argument("--text", action="store_true", help="use the text-mode interface")
    ap.add_argument("--profile", choices=list(catalog.PROFILES), help="text mode: skip the profile menu")
    ap.add_argument("--fast", action="store_true",
                    help="developer mode: shorten timed tests and never power off")
    ap.add_argument("--windowed", action="store_true", help="don't go full screen (development)")
    ap.add_argument("--run", metavar="TEST", help="run one automated test and print the result as JSON")
    args = ap.parse_args()

    if args.run:
        from .model import Context
        from .runner import run_one
        spec = catalog.TESTS[args.run]
        params = catalog.PROFILES[args.profile or "quick"].params.get(args.run, {})
        ctx = Context(params=params, time_scale=0.05 if args.fast else 1.0,
                      progress=lambda f, m: print(f"  [{'?' if f is None else f'{f:.0%}'}] {m}", file=sys.stderr),
                      log=lambda l: print("  " + l, file=sys.stderr))
        print(json.dumps(run_one(spec, ctx).to_dict(), indent=2, ensure_ascii=False))
        return 0

    if args.text or not os.environ.get("DISPLAY"):
        from . import text_ui
        text_ui.main(fast=args.fast, profile_key=args.profile)
        return 0
    try:
        from .gui import app
    except ImportError as e:  # tkinter missing
        print(f"Graphical interface unavailable ({e}); using text mode.", file=sys.stderr)
        from . import text_ui
        text_ui.main(fast=args.fast, profile_key=args.profile)
        return 0
    app.main(fast=args.fast, windowed=args.windowed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
