"""Turn the user's answers in the hands-on tests into results with explanations.

Shared by the graphical and text interfaces so the advice is identical in both.
"""

from __future__ import annotations

from .model import Result, Status

SCREEN_PROBLEMS = {
    "dead_pixels": ("Dead or stuck pixels (dots that stay one colour)",
                    "Single pixels that stay black, white or one colour are a defect of the panel itself. "
                    "One or two are often within the manufacturer's tolerance; a cluster usually isn't.",
                    ["Check the warranty's \"dead pixel policy\" – many replace panels with several dead pixels.",
                     "A stuck (coloured) pixel can sometimes be revived by \"pixel fixer\" videos that flash "
                     "colours rapidly; dead (black) pixels can't."]),
    "lines": ("Lines or bands across the screen",
              "Vertical or horizontal lines usually come from a damaged display cable, a loose connector, "
              "or a failing panel. If the lines change when you open/close a laptop lid, it's the cable.",
              ["Gently flex the lid (laptop) or wiggle the cable (desktop monitor): if the lines change, "
               "reseat or replace the display cable.",
               "Connect an external monitor: if it's clean there, the panel or its cable is at fault; if "
               "the lines show there too, it's the graphics chip."]),
    "backlight": ("Uneven brightness, dark corners or light bleeding at the edges",
                  "Some backlight bleed is normal on LCD screens, especially on black. Large dark patches "
                  "or a dim area that's getting worse point at a failing backlight.",
                  ["Mild bleed on a black screen is cosmetic and can be ignored.",
                   "Dark patches or a flickering backlight usually need a panel replacement."]),
    "flicker": ("Flickering or the screen going black",
                "Flicker is caused by a failing backlight, a loose display cable, or a graphics driver problem.",
                ["If flicker changes as you move the lid, the display cable is the likely culprit.",
                 "Test with an external monitor to separate the screen from the graphics chip."]),
    "colors": ("Wrong colours, tint or colour blotches",
               "A tint that is the same everywhere can be a colour setting; blotches or a colour that's "
               "missing entirely point at the panel or cable.",
               ["Compare with an external monitor.",
                "Check for pressure marks (blotches) from something pressing on the lid."]),
    "brightness": ("Brightness control didn't change the screen",
                   "If the screen brightness didn't change when we adjusted it, the backlight control may "
                   "not be supported by this test system, or the backlight circuit may be faulty.",
                   ["Check whether the brightness keys work in your normal OS.",
                    "If brightness is stuck there too, the backlight driver/circuit needs repair."]),
}


def screen_result(problems: list[str], brightness_tested: bool) -> Result:
    if not problems:
        return Result("screen", "Screen", Status.PASS, "No problems seen on the screen.",
                      ["Solid colours, gradient and edges looked fine to you."] +
                      (["Brightness control works."] if brightness_tested else []),
                      explanation="You checked full-screen colours for dead pixels, lines and uneven "
                                  "backlight, and saw nothing wrong.")
    details = [SCREEN_PROBLEMS[p][0] for p in problems]
    expl = " ".join(SCREEN_PROBLEMS[p][1] for p in problems)
    steps: list[str] = []
    for p in problems:
        steps += SCREEN_PROBLEMS[p][2]
    status = Status.WARN if set(problems) <= {"backlight", "brightness"} else Status.FAIL
    return Result("screen", "Screen", status, "You reported: " + "; ".join(d.lower() for d in details) + ".",
                  details, expl, steps)


def screen_skipped(reason: str) -> Result:
    return Result("screen", "Screen", Status.SKIP, reason)


def keyboard_result(pressed: set[str], all_keys: list[str], user_ok: bool, untested_ok: bool = False) -> Result:
    missing = [k for k in all_keys if k not in pressed]
    details = [f"{len(pressed & set(all_keys))} of {len(all_keys)} keys registered."]
    if missing:
        details.append("Not pressed / not detected: " + " ".join(missing))
    if user_ok:
        status = Status.PASS if not missing else Status.INFO
        summary = "All keys work." if not missing else \
            f"The keys you tried work ({len(missing)} weren't tested)."
        return Result("keyboard", "Keyboard", status, summary, details,
                      explanation="Every key you pressed was detected by the computer.")
    return Result(
        "keyboard", "Keyboard", Status.FAIL,
        "Some keys don't work" + (f": {' '.join(missing[:15])}" if missing else "."), details,
        explanation="Keys that don't register are usually caused by spilled liquid, dirt under the key, "
                    "or a damaged keyboard ribbon cable. If a whole row or group of keys fails together, "
                    "it's almost always the cable or the keyboard's circuit rather than individual keys.",
        next_steps=[
            "Clean under the affected keys with compressed air.",
            "Plug in a USB keyboard: if it works, the laptop's built-in keyboard (or its cable) is at fault.",
            "On most laptops the keyboard is a replaceable part; on some it's part of the top case.",
        ])


POINTER_STEPS = {
    "move": "Moving the pointer to every area of the screen",
    "left": "Left click",
    "right": "Right click",
    "scroll": "Scrolling",
    "drag": "Click-and-drag",
}


def pointer_result(done: set[str], device: str, failed: bool, jumpy: bool = False) -> Result:
    missing = [s for s in POINTER_STEPS if s not in done]
    details = [f"Device: {device or 'unknown'}"]
    details += [f"✔ {POINTER_STEPS[s]}" for s in POINTER_STEPS if s in done]
    details += [f"✘ {POINTER_STEPS[s]}" for s in missing]
    if jumpy:
        details.append("You reported the pointer jumping or moving on its own.")
    if not failed and not missing and not jumpy:
        return Result("pointer", "Touchpad / mouse", Status.PASS,
                      "Pointer movement, clicks, scrolling and dragging all work.", details,
                      explanation="You reached every target and every button and gesture registered.")
    steps = []
    expl = []
    if jumpy:
        expl.append("A pointer that jumps or moves by itself is often caused by a dirty or damp touchpad, "
                    "a charger with poor grounding, or – importantly – a swollen battery pressing on the "
                    "touchpad from underneath.")
        steps += ["Check whether the touchpad or the bottom case is bulging. If it is, stop using the "
                  "laptop and replace the battery (fire risk).",
                  "Clean the touchpad and test again with the charger unplugged."]
    if missing:
        expl.append("Some pointer actions didn't register. If clicks fail but movement works, the click "
                    "mechanism is worn or obstructed; if nothing works, the touchpad's cable may be loose "
                    "or it may be disabled with a key (often Fn + F-key).")
        steps += ["Check for a touchpad on/off key or setting in the BIOS.",
                  "Try a USB mouse to confirm the rest of the computer is fine.",
                  "A dead touchpad on a laptop usually needs its ribbon cable reseated or the touchpad replaced."]
    if missing:
        summary = "Didn't work: " + ", ".join(POINTER_STEPS[s].lower() for s in missing) + "."
        if jumpy:
            summary += " The pointer also jumps on its own."
    elif jumpy:
        summary = "The pointer jumps or moves on its own."
    else:
        summary = "You reported a problem with the touchpad or mouse."
    return Result("pointer", "Touchpad / mouse", Status.FAIL, summary, details,
                  " ".join(expl) or "You reported that the touchpad or mouse doesn't work properly.",
                  steps or ["Try a USB mouse to confirm the rest of the computer is fine."])


def audio_result(left: bool | None, right: bool | None, mic: bool | None, mic_level: float | None,
                 device: str) -> Result:
    details = [f"Output device: {device or 'default'}"]
    for name, val in (("Left speaker", left), ("Right speaker", right), ("Microphone", mic)):
        details.append(f"{name}: " + {True: "works", False: "NOT working", None: "not tested"}[val])
    if mic_level is not None:
        details.append(f"Microphone peak level: {mic_level:.0%}")
    problems = []
    expl = []
    steps = []
    if left is False or right is False:
        both = left is False and right is False
        problems.append("no sound from " + ("either speaker" if both else
                                             ("the left speaker" if left is False else "the right speaker")))
        if both:
            expl.append("No sound at all can be a driver problem with very new sound chips, a muted/"
                        "disabled output, or failed speakers / speaker cable.")
            steps += ["Plug in headphones: if they work, the speakers or their cable are faulty.",
                      "Check sound in your normal OS – if it works there, it's a driver limitation of this test system."]
        else:
            expl.append("Sound works but one side is silent, which points at one speaker or its "
                        "connector being faulty or disconnected.")
            steps += ["Have the speaker connection checked or the speaker replaced."]
    if mic is False:
        problems.append("the microphone didn't pick up sound")
        expl.append("The microphone recorded silence. It may be disabled by a privacy switch/key, "
                    "covered, or its cable may be disconnected (common after screen repairs on laptops, "
                    "since the mic sits next to the webcam).")
        steps += ["Check for a microphone mute key or privacy switch.", "Try a headset microphone."]
    if not problems:
        tested = [v for v in (left, right, mic) if v is not None]
        if not tested:
            return Result("audio", "Speakers & microphone", Status.SKIP, "Audio test was skipped.", details)
        return Result("audio", "Speakers & microphone", Status.PASS, "Speakers and microphone work.", details,
                      explanation="You heard the test tones on each side and the microphone picked up sound.")
    return Result("audio", "Speakers & microphone", Status.FAIL,
                  "Problem: " + "; ".join(problems) + ".", details, " ".join(expl), steps)
