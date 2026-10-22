"""Core data types shared by every test, the runner and the report."""

from __future__ import annotations

import enum
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional


class Status(enum.Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"
    INFO = "info"

    @property
    def label(self) -> str:
        return {
            Status.PASS: "Passed",
            Status.WARN: "Needs attention",
            Status.FAIL: "Failed",
            Status.SKIP: "Skipped",
            Status.INFO: "Info",
        }[self]

    @property
    def rank(self) -> int:
        """Higher is worse; used to sort the report and pick the overall verdict."""
        return {Status.FAIL: 4, Status.WARN: 3, Status.SKIP: 1, Status.INFO: 0, Status.PASS: 0}[self]


@dataclass
class Result:
    test_id: str
    name: str
    status: Status
    summary: str
    details: list[str] = field(default_factory=list)
    explanation: str = ""
    next_steps: list[str] = field(default_factory=list)
    duration: float = 0.0

    def to_dict(self) -> dict:
        return {
            "test_id": self.test_id,
            "name": self.name,
            "status": self.status.value,
            "summary": self.summary,
            "details": self.details,
            "explanation": self.explanation,
            "next_steps": self.next_steps,
            "duration": round(self.duration, 1),
        }


class Cancelled(Exception):
    """Raised inside a test when the user pressed "Skip this test"."""


@dataclass
class Context:
    """Everything a test needs from the outside world.

    ``params`` holds the per-profile knobs for this test (durations, sizes...).
    ``progress`` takes a fraction 0..1 (or None for "unknown") and a short message.
    """

    params: dict
    cancel: threading.Event = field(default_factory=threading.Event)
    progress: Callable[[Optional[float], str], None] = lambda frac, msg: None
    log: Callable[[str], None] = lambda line: None
    time_scale: float = 1.0  # <1 shortens timed tests (developer --fast mode)

    def check_cancel(self) -> None:
        if self.cancel.is_set():
            raise Cancelled()

    def sleep(self, seconds: float) -> None:
        """Interruptible sleep."""
        if self.cancel.wait(seconds):
            raise Cancelled()

    def scaled(self, seconds: float) -> float:
        return max(1.0, seconds * self.time_scale)


@dataclass
class TestSpec:
    test_id: str
    name: str
    description: str
    interactive: bool
    run: Optional[Callable[[Context], Result]] = None  # None for GUI-driven interactive tests


def timed(fn: Callable[[Context], Result]) -> Callable[[Context], Result]:
    def wrapper(ctx: Context) -> Result:
        start = time.monotonic()
        res = fn(ctx)
        res.duration = time.monotonic() - start
        return res

    wrapper.__name__ = fn.__name__
    return wrapper
