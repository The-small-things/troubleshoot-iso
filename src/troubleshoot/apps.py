"""Open-source apps and games bundled on the ISO: what's installed, their icons, launching them.

The ISO build installs each package in live/config/includes.chroot/usr/share/troubleshoot/apps.list
if Debian has it, so everything here is looked up at runtime and missing apps are simply hidden.
"""

from __future__ import annotations

import configparser
import glob
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass

from . import util

# Debian puts games in /usr/games, which isn't on root's default PATH.
SEARCH_PATH = os.pathsep.join([os.environ.get("PATH", "/usr/bin:/bin"), "/usr/games", "/usr/local/games"])


def which(command: str) -> str | None:
    return shutil.which(command, path=SEARCH_PATH)


@dataclass
class App:
    command: str          # executable name, looked up on $PATH
    name: str
    blurb: str
    category: str         # games | internet | creative | tools
    args: tuple = ()
    heavy: bool = False   # needs real 3D graphics; slow while the CPU stress test runs
    terminal: bool = False  # text-mode tool: open it in a terminal window
    guide: str | None = None  # text shown in the terminal first (for tools that need instructions)
    unless: str | None = None  # hide this entry when that command is installed (a nicer alternative)

    @property
    def installed(self) -> bool:
        return which(self.command) is not None and not (self.unless and which(self.unless))


CATALOG = [
    App("qphotorec", "PhotoRec", "Recover deleted photos, documents and other files – even from a formatted "
        "drive or memory card. Saves them to another drive.", "rescue"),
    App("photorec", "PhotoRec", "Recover deleted photos, documents and other files – even from a formatted "
        "drive or memory card. Text-mode, opens in a terminal.", "rescue", terminal=True, unless="qphotorec"),
    App("testdisk", "TestDisk", "Recover lost partitions and make a drive bootable again. Text-mode, opens in a "
        "terminal.", "rescue", terminal=True),
    App("ddrescue", "Rescue a failing drive", "Copy a dying drive to a healthy one, skipping bad areas. Opens a "
        "terminal with step-by-step instructions.", "rescue", terminal=True,
        guide="/usr/share/troubleshoot/guides/ddrescue.txt"),
    App("gparted", "GParted", "View, resize and repair partitions. Careful: changes made here DO change your "
        "drives.", "rescue"),
    App("chntpw", "Reset Windows password", "Clear a forgotten password on a local Windows account. Opens a "
        "terminal with step-by-step instructions.", "repair", terminal=True,
        guide="/usr/share/troubleshoot/guides/windows-password.txt"),
    App("efibootmgr", "Boot repair", "Fix \"no bootable device\" and a wrong boot order. Opens a terminal with "
        "step-by-step instructions.", "repair", terminal=True, guide="/usr/share/troubleshoot/guides/boot-repair.txt"),
    App("clonezilla", "Clonezilla", "Back up a whole drive to an image, restore it, or clone one drive to another. "
        "Opens in a terminal.", "repair", terminal=True),
    App("nwipe", "Securely erase a drive", "Wipe a drive before selling or giving it away. DESTROYS ALL DATA. "
        "Opens a terminal with instructions.", "repair", terminal=True, guide="/usr/share/troubleshoot/guides/nwipe.txt"),
    App("supertuxkart", "SuperTuxKart", "3D kart racing with Tux and friends. Items, tracks, battle mode.",
        "games", heavy=True),
    App("supertux2", "SuperTux", "Classic side-scrolling platformer starring Tux.", "games"),
    App("etr", "Extreme Tux Racer", "Slide down snowy 3D mountains as fast as you can.", "games", heavy=True),
    App("neverball", "Neverball", "Tilt the floor to roll the ball to the goal. 3D puzzle-action.", "games",
        heavy=True),
    App("frozen-bubble", "Frozen Bubble", "Pop coloured bubbles before they reach the bottom.", "games"),
    App("firefox-esr", "Firefox", "Web browser – look up drivers, manuals and the next steps from your report.",
        "internet"),
    App("tuxpaint", "Tux Paint", "Fun, easy drawing app with stamps and magic tools.", "creative"),
    App("drawing", "Drawing", "Simple paint app for sketches and editing pictures.", "creative"),
    App("pcmanfm", "Files", "Browse files – e.g. copy photos off an old drive to a USB stick.", "tools"),
    App("mousepad", "Text Editor", "Simple text editor.", "tools"),
    App("galculator", "Calculator", "A calculator.", "tools"),
    App("lxterminal", "Terminal", "Command line, for experts.", "tools"),
    App("gnome-disks", "Disks", "See and benchmark drives and partitions.", "tools"),
    App("gsmartcontrol", "GSmartControl", "Detailed drive health (SMART) viewer.", "tools"),
    App("glmark2", "glmark2", "Graphics benchmark: stress-tests the graphics chip with 3D scenes.", "tools",
        heavy=True),
]

CATEGORIES = [("rescue", "Data rescue & recovery"), ("repair", "Repair & maintenance"), ("games", "Games"),
              ("internet", "Internet"),
              ("creative", "Drawing & painting"), ("tools", "Tools")]


def installed(category: str | None = None) -> list[App]:
    return [a for a in CATALOG if a.installed and (category is None or a.category == category)]


def _desktop_entries() -> dict[str, dict]:
    """Map executable basename -> [Desktop Entry] section, from /usr/share/applications."""
    out: dict[str, dict] = {}
    for path in glob.glob("/usr/share/applications/*.desktop"):
        cp = configparser.ConfigParser(interpolation=None, strict=False)
        try:
            cp.read(path, encoding="utf-8")
            entry = dict(cp["Desktop Entry"])
        except (configparser.Error, KeyError, UnicodeDecodeError):
            continue
        try:
            exe = os.path.basename(shlex.split(entry.get("exec", ""))[0])
        except (ValueError, IndexError):
            continue
        out.setdefault(exe, entry)
    return out


_ENTRIES: dict[str, dict] | None = None


def icon_path(app: App) -> str | None:
    """A PNG icon for the app (Tk can't load SVG), preferring sizes near 64 px."""
    global _ENTRIES
    if _ENTRIES is None:
        _ENTRIES = _desktop_entries()
    name = _ENTRIES.get(app.command, {}).get("icon", app.command)
    if os.path.isabs(name):
        return name if name.endswith(".png") and os.path.exists(name) else None
    for size in ("64x64", "48x48", "128x128", "96x96", "256x256", "512x512", "32x32"):
        for theme in ("hicolor", "Adwaita"):
            p = f"/usr/share/icons/{theme}/{size}/apps/{name}.png"
            if os.path.exists(p):
                return p
    p = f"/usr/share/pixmaps/{name}.png"
    return p if os.path.exists(p) else None


def command_line(app: App, path: str) -> list[str] | None:
    """The command that starts ``app`` (installed at ``path``); None if it needs a missing terminal."""
    if not app.terminal:
        return [path, *app.args]
    if app.guide:  # show the instructions, then leave the user at a prompt with the tool available
        script = f"cat {shlex.quote(app.guide)}; echo; exec bash"
    else:  # run the tool, and don't let the window vanish the moment it exits
        script = f"{shlex.join([path, *app.args])}; echo; read -r -p 'Press Enter to close this window.' _"
    term = which("lxterminal")
    if term:
        return [term, f"--title={app.name}", f"--command=bash -c {shlex.quote(script)}"]
    term = which("xterm")
    if term:
        return [term, "-T", app.name, "-e", "bash", "-c", script]
    return None


def launch(app: App) -> str | None:
    """Start the app in the background. Returns an error message, or None on success.
    Background music pauses while the app runs (games have their own)."""
    from . import sound
    path = which(app.command)
    if not path:
        return f"{app.name} isn't installed on this system."
    env = dict(os.environ)
    env.setdefault("HOME", "/root")
    env["PATH"] = SEARCH_PATH
    cmd = command_line(app, path)
    if cmd is None:
        return f"{app.name} needs a terminal window, but no terminal app is installed."
    try:
        proc = subprocess.Popen(cmd, env=env, start_new_session=True, cwd=env["HOME"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        return f"Couldn't start {app.name}: {e}"
    if sound._player is not None:
        sound._player.watch(proc)
    return None


# --- Wi-Fi via NetworkManager ---------------------------------------------------------------

def online() -> bool:
    return util.run(["nmcli", "-t", "-f", "CONNECTIVITY", "general"], timeout=10).stdout.strip() == "full"


def wifi_networks() -> list[dict] | None:
    """Visible Wi-Fi networks, strongest first; None if NetworkManager isn't running."""
    res = util.run(["nmcli", "-t", "-e", "yes", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "dev", "wifi", "list",
                    "--rescan", "yes"], timeout=30)
    if res.returncode != 0:
        return None
    return parse_wifi(res.stdout)


def parse_wifi(output: str) -> list[dict]:
    nets: dict[str, dict] = {}
    for line in output.splitlines():
        parts = _split_escaped(line)
        if len(parts) != 4 or not parts[1]:
            continue
        inuse, ssid, signal, security = parts
        sig = int(signal) if signal.isdigit() else 0
        if ssid not in nets or nets[ssid]["signal"] < sig:
            nets[ssid] = {"ssid": ssid, "signal": sig, "secure": security not in ("", "--"),
                          "connected": inuse == "*"}
    return sorted(nets.values(), key=lambda n: (-n["connected"], -n["signal"]))


def _split_escaped(line: str) -> list[str]:
    """Split nmcli's terse output on ':' honouring '\\:' escapes."""
    parts, cur, esc = [], [], False
    for ch in line:
        if esc:
            cur.append(ch)
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == ":":
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


def wifi_connect(ssid: str, password: str | None) -> tuple[bool, str]:
    cmd = ["nmcli", "dev", "wifi", "connect", ssid]
    if password:
        cmd += ["password", password]
    res = util.run(cmd, timeout=60)
    msg = (res.stdout + res.stderr).strip().splitlines()
    return res.returncode == 0, (msg[-1] if msg else "")
