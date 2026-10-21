"""Text-mode fallback for when the graphical interface can't start."""

from __future__ import annotations

import os
import shutil
import string
import subprocess
import sys
import tempfile
import threading

from . import catalog, report, util
from .audio import Audio, make_tone, peak_level
from .checks import sysinfo
from .interactive import audio_result, keyboard_result, screen_result
from .model import Context, Result, Status
from .runner import run_one

ANSI = {Status.PASS: "\033[32m", Status.WARN: "\033[33m", Status.FAIL: "\033[31m",
        Status.SKIP: "\033[90m", Status.INFO: "\033[36m"}
RESET = "\033[0m"
BOLD = "\033[1m"


def ask(prompt: str, choices: str = "yn") -> str:
    while True:
        try:
            ans = input(f"{prompt} [{'/'.join(choices)}] ").strip().lower()
        except EOFError:
            return choices[-1]
        if ans and ans[0] in choices:
            return ans[0]


def screen_test() -> Result:
    print("\nScreen test: the screen will fill with colours. Press Enter to go to the next one.")
    input("Press Enter to start...")
    for code, name in ((40, "black"), (47, "white"), (41, "red"), (42, "green"), (44, "blue")):
        rows = shutil.get_terminal_size().lines
        sys.stdout.write(f"\033[{code}m\033[2J\033[H" + "\n" * (rows - 1))
        sys.stdout.flush()
        input()
    sys.stdout.write(RESET + "\033[2J\033[H")
    print("Note: text mode can only show a few colours; the graphical test is more thorough.")
    problems = []
    for key, q in (("dead_pixels", "Did you see dots that stayed black/white/coloured?"),
                   ("lines", "Did you see lines or stripes?"),
                   ("backlight", "Was the brightness uneven / were there dark patches?"),
                   ("flicker", "Did the screen flicker?")):
        if ask(q) == "y":
            problems.append(key)
    return screen_result(problems, False)


def keyboard_test() -> Result:
    keys = list(string.ascii_lowercase + string.digits + "`-=[]\;',./")
    print("\nKeyboard test: type every letter, number and symbol key once (in any order),")
    print("then press Enter. Shift, Ctrl, Alt and function keys can't be checked in text mode.")
    typed = input("> ").lower()
    pressed = {c for c in typed}
    missing = [k for k in keys if k not in pressed]
    if missing:
        print("Not detected: " + " ".join(missing))
        ok = ask("Did those keys fail to work (y), or did you just skip them (n)?") == "n"
    else:
        ok = True
    return keyboard_result(pressed & set(keys), keys, ok)


def audio_test() -> Result:
    a = Audio()
    if not a.available:
        return Result("audio", "Speakers & microphone", Status.WARN, "No sound device was detected.")
    a.prepare()
    tmp = tempfile.mkdtemp()
    answers: dict[str, bool | None] = {"left": None, "right": None, "mic": None}
    for side in ("left", "right"):
        path = os.path.join(tmp, f"{side}.wav")
        make_tone(path, side)
        while True:
            print(f"Playing beeps on the {side.upper()} speaker...")
            a.play(path)
            ans = ask(f"Heard it from the {side} side? (p = play again)", "ynp")
            if ans != "p":
                answers[side] = ans == "y"
                break
    level = None
    if a.inp and ask("Test the microphone?") == "y":
        path = os.path.join(tmp, "mic.wav")
        input("Press Enter, then talk for 4 seconds...")
        a.record(path, 4)
        level = peak_level(path)
        print("Playing it back...")
        a.play(path)
        answers["mic"] = ask("Did you hear your recording?") == "y"
    return audio_result(answers["left"], answers["right"], answers["mic"], level, a.description)


TEXT_INTERACTIVE = {"screen": screen_test, "keyboard": keyboard_test, "audio": audio_test}


def run_auto(spec, params, fast: bool) -> Result:
    state = {"frac": None, "msg": ""}

    def progress(frac, msg):
        state["frac"], state["msg"] = frac, msg
        pct = f"{frac * 100:3.0f}%" if frac is not None else " ...."
        sys.stdout.write(f"\r  {pct}  {msg[:70]:<70}")
        sys.stdout.flush()

    ctx = Context(params=params, progress=progress, time_scale=0.05 if fast else 1.0)
    print(f"\n{BOLD}{spec.name}{RESET} – {spec.description}")
    print("  (press Ctrl+C to skip this test)")
    result: list[Result] = []
    t = threading.Thread(target=lambda: result.append(run_one(spec, ctx)), daemon=True)
    t.start()
    try:
        while t.is_alive():
            t.join(0.5)
    except KeyboardInterrupt:
        ctx.cancel.set()
        t.join()
    r = result[0]
    print(f"\r  {ANSI[r.status]}{r.status.label}{RESET}: {r.summary:<70}")
    return r


def main(fast: bool = False, profile_key: str | None = None) -> None:
    info = sysinfo.collect()
    print(f"\n{BOLD}HARDWARE TROUBLESHOOTER (text mode){RESET}")
    print(f"{info['vendor']} {info['product']} · {info['cpu']} · {info['ram_total']} RAM\n")
    profiles = list(catalog.PROFILES.values())
    if profile_key is None:
        for n, p in enumerate(profiles, 1):
            print(f"  {n}) {p.title:<22} {p.duration}\n     {p.description}\n")
        choice = ask("Choose a test", "1234")
        prof = profiles[int(choice) - 1]
    else:
        prof = catalog.PROFILES[profile_key]
    only = None
    if prof.key == "custom":
        ids = [t for t in catalog.ORDER if t != "sysinfo"]
        for n, tid in enumerate(ids, 1):
            print(f"  {n:2}) {catalog.TESTS[tid].name}")
        picks = input("Enter the numbers to run, separated by spaces: ").split()
        only = {ids[int(p) - 1] for p in picks if p.isdigit() and 0 < int(p) <= len(ids)}

    results: list[Result] = []
    for spec, params in catalog.plan(prof, only):
        if spec.interactive:
            fn = TEXT_INTERACTIVE.get(spec.test_id)
            if fn is None:
                results.append(Result(spec.test_id, spec.name, Status.SKIP,
                                      "Needs the graphical interface (not available in text mode)."))
                continue
            try:
                results.append(fn())
            except KeyboardInterrupt:
                results.append(Result(spec.test_id, spec.name, Status.SKIP, "Skipped by you."))
        else:
            results.append(run_auto(spec, params, fast))

    text = report.to_text(results, prof.title)
    if util.have("less") and sys.stdout.isatty():
        subprocess.run(["less", "-R"], input=text, text=True)
    else:
        print(text)
    if ask("Save the report to a USB drive?") == "y":
        for p in report.save(results, prof.title):
            print("Saved:", p)
