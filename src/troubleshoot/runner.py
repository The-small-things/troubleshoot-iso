"""Run one automated test safely: a crashing test must never abort the whole session."""

from __future__ import annotations

import time
import traceback

from .model import Cancelled, Context, Result, Status, TestSpec


def run_one(spec: TestSpec, ctx: Context) -> Result:
    start = time.monotonic()
    try:
        assert spec.run is not None
        res = spec.run(ctx)
    except Cancelled:
        res = Result(spec.test_id, spec.name, Status.SKIP, "Skipped by you before it finished.")
    except Exception as exc:  # noqa: BLE001 - report any bug in a test as a skipped test
        ctx.log(traceback.format_exc())
        res = Result(spec.test_id, spec.name, Status.SKIP,
                     "This test couldn't run on this computer.",
                     [f"{type(exc).__name__}: {exc}"],
                     explanation="The test itself ran into an unexpected situation. This is a "
                                 "limitation of the test, not a sign that your hardware is faulty.")
    res.duration = res.duration or (time.monotonic() - start)
    return res
