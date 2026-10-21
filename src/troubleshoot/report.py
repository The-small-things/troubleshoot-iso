"""Overall verdict, plain-text/HTML report rendering, and saving to a USB drive."""

from __future__ import annotations

import datetime
import html
import json
import os
import tempfile

from . import util
from .model import Result, Status

GENERIC_HEALTHY_STEPS = [
    "The hardware looks healthy, so if you're having problems they are most likely software: install "
    "OS and driver updates, check for malware, and remove recently installed programs.",
    "If problems only happen occasionally, run the Full test – some faults only show after a long time "
    "under load.",
    "As a last resort, back up your files and reinstall / reset the operating system.",
]


def verdict(results: list[Result]) -> tuple[Status, str, str]:
    """(overall status, headline, one-paragraph explanation)."""
    fails = [r for r in results if r.status is Status.FAIL]
    warns = [r for r in results if r.status is Status.WARN]
    if fails:
        names = ", ".join(r.name for r in fails)
        para = (f"{len(fails)} test(s) found a hardware problem ({names}). Select each one for what it "
                "means and what to do.")
        if any(r.test_id == "storage" for r in fails):
            para += " Back up your files first – the drive problem puts your data at risk."
        return (Status.FAIL, "Problems found", para)
    if warns:
        names = ", ".join(r.name for r in warns)
        return (Status.WARN, "Mostly healthy – some things need attention",
                f"Nothing is broken, but {len(warns)} item(s) show wear or early warning signs ({names}).")
    return (Status.PASS, "No hardware problems found",
            "Every test that ran passed. " + GENERIC_HEALTHY_STEPS[0])


DISPLAY_ORDER = {Status.FAIL: 0, Status.WARN: 1, Status.INFO: 2, Status.PASS: 3, Status.SKIP: 4}


def sorted_results(results: list[Result]) -> list[Result]:
    """Problems first, then the system summary, passes, and finally skipped tests."""
    return sorted(results, key=lambda r: (DISPLAY_ORDER[r.status], results.index(r)))


def to_text(results: list[Result], profile: str, sysinfo: dict | None = None) -> str:
    status, head, para = verdict(results)
    when = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    out = [f"HARDWARE TROUBLESHOOTER REPORT – {profile} – {when}", "=" * 70, "",
           f"OVERALL: {head.upper()}", para, ""]
    for r in sorted_results(results):
        out.append(f"[{r.status.label.upper():^15}] {r.name}")
        out.append(f"    {r.summary}")
        for d in r.details:
            out.append(f"      · {d}")
        if r.explanation and r.status is not Status.INFO:
            out.append(f"    What this means: {r.explanation}")
        for s in r.next_steps:
            out.append(f"    → {s}")
        out.append("")
    if status is Status.PASS:
        out.append("NEXT STEPS")
        out += [f"  → {s}" for s in GENERIC_HEALTHY_STEPS]
    return "\n".join(out) + "\n"


COLORS = {Status.PASS: "#1a7f37", Status.WARN: "#b35900", Status.FAIL: "#c62828",
          Status.SKIP: "#6b7280", Status.INFO: "#2563eb"}


def to_html(results: list[Result], profile: str) -> str:
    status, head, para = verdict(results)
    e = html.escape
    when = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    parts = [f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hardware report {e(when)}</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:860px;margin:2rem auto;padding:0 1rem;color:#1f2328;background:#fff}}
.banner{{padding:1rem 1.25rem;border-radius:10px;color:#fff;background:{COLORS[status]}}}
.banner h1{{margin:0 0 .3rem;font-size:1.5rem}}
details{{border:1px solid #d0d7de;border-radius:8px;margin:.6rem 0;padding:.6rem 1rem}}
summary{{cursor:pointer;font-weight:600}}
.badge{{display:inline-block;min-width:8.5em;text-align:center;border-radius:99px;color:#fff;font-size:.8rem;padding:.1rem .6rem;margin-right:.6rem}}
.muted{{color:#57606a}} ul{{margin:.3rem 0}}
</style></head><body>
<p class="muted">Hardware Troubleshooter · {e(profile)} · {e(when)}</p>
<div class="banner"><h1>{e(head)}</h1><div>{e(para)}</div></div>"""]
    for r in sorted_results(results):
        open_attr = " open" if r.status in (Status.FAIL, Status.WARN) else ""
        parts.append(f"<details{open_attr}><summary><span class=badge style='background:{COLORS[r.status]}'>"
                     f"{e(r.status.label)}</span>{e(r.name)} – <span class=muted>{e(r.summary)}</span></summary>")
        if r.details:
            parts.append("<ul>" + "".join(f"<li>{e(d)}</li>" for d in r.details) + "</ul>")
        if r.explanation and r.status is not Status.INFO:
            parts.append(f"<p><b>What this means:</b> {e(r.explanation)}</p>")
        if r.next_steps:
            parts.append("<p><b>Next steps:</b></p><ol>" + "".join(f"<li>{e(s)}</li>" for s in r.next_steps) + "</ol>")
        parts.append("</details>")
    if status is Status.PASS:
        parts.append("<h2>Next steps</h2><ol>" + "".join(f"<li>{e(s)}</li>" for s in GENERIC_HEALTHY_STEPS) + "</ol>")
    parts.append("</body></html>")
    return "\n".join(parts)


def _usb_targets() -> list[dict]:
    res = util.run(["lsblk", "-J", "-o", "NAME,FSTYPE,RM,TRAN,MOUNTPOINT,LABEL,TYPE,PKNAME"])
    if res.returncode != 0:
        return []
    try:
        tree = json.loads(res.stdout).get("blockdevices", [])
    except ValueError:
        return []
    out = []

    def walk(devs, removable):
        for d in devs:
            rem = removable or d.get("tran") == "usb" or d.get("rm") in (True, 1, "1")
            if rem and d.get("fstype") in ("vfat", "exfat", "ntfs", "ext4", "ext3", "ext2") \
                    and d.get("type") == "part":
                out.append(d)
            walk(d.get("children", []), rem)
    walk(tree, False)
    return out


def save(results: list[Result], profile: str) -> list[str]:
    """Save the report to every writable USB partition (falls back to /root). Returns paths written."""
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    files = {f"hardware-report-{stamp}.html": to_html(results, profile),
             f"hardware-report-{stamp}.txt": to_text(results, profile)}
    written: list[str] = []
    for d in _usb_targets():
        dev = f"/dev/{d['name']}"
        mnt = d.get("mountpoint")
        temp_mount = None
        if not mnt:
            temp_mount = tempfile.mkdtemp(prefix="report-")
            fstype = "ntfs3" if d.get("fstype") == "ntfs" else d["fstype"]
            if util.run(["mount", "-t", fstype, dev, temp_mount]).returncode != 0:
                os.rmdir(temp_mount)
                continue
            mnt = temp_mount
        try:
            for name, content in files.items():
                path = os.path.join(mnt, name)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                written.append(f"{d.get('label') or d['name']}: {name}")
        except OSError:
            pass
        finally:
            util.run(["sync"])
            if temp_mount:
                util.run(["umount", temp_mount])
                os.rmdir(temp_mount)
    if not written:
        home = os.path.expanduser("~")
        for name, content in files.items():
            path = os.path.join(home, name)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            written.append(path)
    return written
