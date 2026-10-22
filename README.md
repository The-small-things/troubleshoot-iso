# Hardware Troubleshooter ISO

A bootable Linux USB stick that checks a computer's hardware and explains the results in plain
language, guided by **Chip**, a friendly robot made of a computer chip. Boot it, pick how thorough the test should be, answer a few on-screen prompts, and get
a report with **what was found, what it means, and what to do next**.

It runs entirely from the USB stick and **never writes to the computer's disks**. Drives are only
read, never mounted.

## What it tests

| Test | How | Interactive? |
|---|---|---|
| System information | DMI, CPU, RAM, disks, GPU inventory | – |
| Graphics driver | Detects software-rendering fallback (`glxinfo`) | – |
| Screen | Full-screen colours, gradients, edge frame, backlight dim/bright | ✔ |
| Keyboard | On-screen keyboard; every physical key lights up (layout-independent) | ✔ |
| Touchpad / mouse | Reach targets, left/right click, scroll, drag, "does it jump?" | ✔ |
| Webcam | Live preview (darkness/privacy-shutter hint), multiple cameras incl. IR | ✔ |
| Speakers & microphone | Left/right test tones, record and play back | ✔ |
| Battery & charging | Wear (capacity vs. design), cycles, charger detection, power draw | – |
| Network adapters | Ethernet/Wi-Fi detection, drivers, missing firmware, Wi-Fi scan | – |
| Bluetooth | Adapter detection, radio switches, power-on, scan for nearby devices | – |
| Storage drives | SMART health and attributes (SATA and NVMe), drive self-test, read speed | – |
| Memory (RAM) | `memtester` patterns, ECC (EDAC) error counters | – |
| Processor stress & cooling | `stress-ng --verify` on all cores while watching temperature, clock throttling and fans | – |
| Hardware error log | Kernel log scan for machine checks, disk I/O errors, GPU hangs, USB/PCIe errors | – |

The hands-on tests come first, so after a few minutes you can leave the computer while the long
automatic tests run.

### Games while you wait (Chip's Arcade)

During the automatic tests you can play a game on the progress screen while the progress bar
stays visible. The arcade is also on the welcome screen. If the tests finish mid-game, a banner
offers the results instead of interrupting you.

| Game | Style |
|---|---|
| **Maze Runner 3D** | First-person ray-cast maze. Find the exit, collect chips; each win makes the maze bigger |
| **Turbo Road** | Pseudo-3D arcade racer with curves, hills, traffic and lap times |
| **Star Pilot 3D** | Real 3D: flat-shaded rotating asteroids, perspective, lighting; dodge rocks, catch crystals |
| Snake, 2048, Minesweeper | The classics |

The 3D games are software-rendered on a Tk canvas, so they run in a VM or on hardware without a
working graphics driver. The stress tests run at low CPU priority so the games stay smooth.

### Music and sound effects

All the music and effects are synthesised in code (`src/troubleshoot/sound.py`), so there are no
audio files to license. The build pre-renders them to WAV files:

- **Music:** a calm lo-fi loop for the menus and while the automatic tests run, and an upbeat
  chiptune loop in Chip's games.
- **Effects:** button clicks, game sounds (eating, merging, pickups, crashes, laps, wins, losses)
  and a results jingle that matches the verdict.
- **Silence where it matters:** music and effects are off during the hands-on tests, so they can't
  interfere with the speaker, microphone or keyboard checks. Music pauses while an open-source app
  is running, because those games have their own soundtracks.
- **Mute:** a **♪ Sound on/off** toggle sits in the top-right corner.

### Open-source games and apps

**Games & apps** (on the welcome screen, or press **G**) also has real open-source software.
These apps open in their own window; close it to return to the troubleshooter.

| | |
|---|---|
| Data rescue & recovery | PhotoRec (recover deleted files), TestDisk (lost partitions, boot repair), ddrescue (copy a failing drive, with a step-by-step guide), GParted (partitions; changes your drives) |
| Repair & maintenance | Windows password reset (chntpw), Boot repair (efibootmgr, os-prober), Clonezilla (back up, restore or clone drives), Securely erase a drive (nwipe). The guided tools open a terminal with step-by-step instructions |
| Games | SuperTuxKart, Extreme Tux Racer, Neverball, Frozen Bubble |
| Internet | Firefox, plus a built-in **Wi-Fi & internet** screen to get online (Ethernet connects by itself) |
| Drawing & painting | Tux Paint, Drawing |
| Tools | Files (e.g. copy photos off an old drive), Text Editor, Calculator, Terminal, GNOME Disks, GSmartControl, glmark2 (graphics benchmark) |

The list is in `live/config/includes.chroot/usr/share/troubleshoot/apps.list`. At build time
each package is installed if Debian has it and skipped otherwise. At runtime the app shows only
what's installed. CI fails the build if the ISO grows past 2 GiB, GitHub's limit for release
files, and the build log lists the largest packages. (SuperTux is left out for that reason; the ISO
is about 1.9 GB.)

### Boot menu and splash

The boot menu (GRUB on UEFI, isolinux on BIOS) shows Chip and plain-language entries: *Start
the hardware check-up*, *Load into RAM*, *Safe mode*, *Deep memory test*, *Check this USB stick
for errors*, *BIOS/UEFI settings*, *Restart* and *Power off*.

**Load into RAM** copies the whole system (about 2 GB) into memory while it starts. Afterwards
the welcome screen says *Running from memory*, and you can unplug the USB stick and keep working.
That takes about 20–40 s longer to start on USB 3, and needs roughly 4 GB of RAM or more. With too
little RAM it runs from the stick as usual, and the welcome screen tells you to keep the stick
plugged in. The copy uses about 2 GB of RAM, so the in-session memory test checks less of it. It starts the check-up automatically after
10 seconds. While Linux loads, a Plymouth splash with Chip replaces the scrolling boot text.

### Test profiles

| Profile | Time | Contents |
|---|---|---|
| **Quick check** | ~5 min | Screen, keyboard, touchpad, webcam, battery, Wi-Fi, Bluetooth, SMART health, 512 MB RAM, 1 min CPU stress |
| **Standard** | ~20–40 min | Everything + audio, drive self-test, 1 GB read test, half the RAM (≤4 GB), 5 min stress |
| **Full / overnight** | 1–3 h+ | 85% of RAM × 2 passes, 20 min stress, drive self-test, 4 GB read test |
| **Custom** | – | Choose individual tests |

The boot menu also has **memtest86+**, which tests 100% of RAM without an OS running. Use it when
the RAM test passes but you still suspect the memory.

### Results

The results screen shows an overall verdict (*No problems found*, *Some things need attention*,
or *Problems found*). Each test has an explanation and concrete next steps. For example: *"The
drive has 8 sectors waiting to be remapped… Back up your files now; plan to replace the drive"*,
or *"Interface CRC errors… almost always the cable, not the drive"*. If everything passes, it
says so, and suggests the problem is likely software.

**Save report to USB drive** writes an HTML and a text report to any FAT/exFAT/NTFS/ext USB
stick that's plugged in. If you boot with [Ventoy](https://www.ventoy.net), that includes the
boot stick itself.

## Getting the ISO

Every push builds the ISO with GitHub Actions (**Actions → Build ISO → Artifacts**). To publish
a release, either run **Actions → Build ISO → Run workflow** with a release tag (e.g. `v1.2.0`),
or publish a GitHub Release yourself. Either way the ISO is built, boot-tested, and attached to the
release only if it boots. For example:

```sh
gh release create v1.0.0 --repo The-small-things/troubleshoot-iso --target main \
  --title "Hardware Troubleshooter 1.0.0" --generate-notes
```

To build it yourself (about 10–20 minutes, needs ~6 GB free):

```sh
sudo apt-get install live-build     # on Debian 13 (trixie)
sudo ./build.sh
# or, on any Linux machine with Docker:
./build.sh --docker
```

The image is written to `dist/troubleshoot-<version>-amd64.iso`.

## Using it

1. Write the ISO to a USB stick with [balenaEtcher](https://etcher.balena.io), Rufus (DD mode),
   Ventoy, or `sudo dd if=troubleshoot-*.iso of=/dev/sdX bs=4M status=progress`.
2. Boot from the stick (usually F12, F11, F9, Esc or Option on Macs). If the stick
   isn't accepted, disable Secure Boot in the BIOS/UEFI settings.
3. Pick from the boot menu:
   - **Live system** – the normal graphical troubleshooter.
   - **Live system (fail-safe mode)** – text-mode troubleshooter with basic graphics. Use this if
     the screen stays black.
   - **Memory test (memtest86+)** – standalone full RAM test.
4. Choose a profile with the mouse or keys **1–4**.

If the graphical interface can't start, the troubleshooter falls back to text mode on its own.
**Exit to command line** gives you a root shell; run `troubleshoot-session` to start again.

## Project layout

```
src/troubleshoot/          the Python app (stdlib + Tkinter only)
  checks/                  automated tests: each returns a Result with explanation + next steps
  interactive.py           turns answers from hands-on tests into results (shared by GUI/text UI)
  art.py                   Chip the mascot as shapes (shared by the GUI and the boot artwork)
  gui/                     full-screen Tk interface: test pages, mascot, arcade (games.py, games3d.py)
  text_ui.py               text-mode fallback
  report.py                verdict, text/HTML report, saving to USB
  catalog.py               test list and the Quick/Standard/Full/Custom profiles
live/                      Debian live-build configuration (packages, autologin, X session)
  config/bootmenu/         branded GRUB/isolinux menus, installed by hooks/live/0500-boot-menu.hook.binary
tools/make_assets.py       renders the boot-menu/splash artwork from the Chip drawing in src/troubleshoot/art.py
tests/                     unit tests for all the result-interpretation logic
build.sh                   builds the ISO
```

### Developing without building an ISO

The app runs on any Linux machine with Python 3.11+ and Tkinter. Most tests need root and the
tools from `live/config/package-lists/`.

```sh
cd src
python3 -m troubleshoot --windowed --fast     # GUI in a window; timed tests cut to ~5%
python3 -m troubleshoot --text --fast         # text mode
sudo python3 -m troubleshoot --run storage    # one automated test, JSON result
python3 -m unittest discover -s ../tests      # unit tests
```

To add a test, write `checks/<name>.py` with a `run(ctx) -> Result` function, register it in
`catalog.py` (`TESTS`, `ORDER`, and the profiles' `params`), and add unit tests for its
interpretation logic.

## Limitations

- **Detection, not repair.** A pass doesn't guarantee a fault-free machine. Some faults only
  appear with specific software, temperatures or timing.
- **x86-64 PCs only** (no Apple Silicon/ARM). Intel Macs boot, but often lack Wi-Fi and
  sound drivers.
- Card readers and USB-port-by-port tests aren't included yet.
- Newer laptops with Intel IPU6/MIPI cameras need drivers Debian doesn't ship, so their webcam
  is reported as "can't be tested here", not as faulty.
- Very new hardware may need drivers/firmware newer than Debian 13 ships. The app reports this as
  "not detected / not tested", not as a hardware failure.
