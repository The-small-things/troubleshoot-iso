# Hardware Troubleshooter ISO

A bootable Linux USB stick that checks a computer's hardware and explains the results in plain
language. Boot it, pick how thorough the test should be, answer a few on-screen prompts, and get
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

### Games while you wait

During the automatic tests you can play **Snake**, **2048** or **Minesweeper** from the progress
screen, with the progress bar staying visible. If the tests finish mid-game, a banner offers the
results instead of interrupting you.

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

Every push builds the ISO with GitHub Actions (**Actions → Build ISO → Artifacts**). Publishing
a GitHub Release builds it again and attaches the ISO to that release, for example:

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
  gui/                     full-screen Tk interface (screen/keyboard/pointer/webcam/audio pages, games)
  text_ui.py               text-mode fallback
  report.py                verdict, text/HTML report, saving to USB
  catalog.py               test list and the Quick/Standard/Full/Custom profiles
live/                      Debian live-build configuration (packages, autologin, X session)
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
