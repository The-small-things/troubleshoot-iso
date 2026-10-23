"""Saving files onto the USB stick the troubleshooter booted from.

How depends on how the stick was made:

* Written as an image (Etcher, dd, Rufus "DD mode"): the stick holds a read-only copy of the ISO
  and the rest of it is unused. We add a FAT32 partition labelled REPORTS in that free space
  (once), the way Debian documents adding a persistence partition to a live stick. The ISO part
  isn't touched, so the stick still boots, and the REPORTS drive opens on Windows, macOS and Linux.
* Files copied to a FAT/exFAT/NTFS stick (Rufus "ISO mode"): we write into a reports folder.
* Ventoy: the ISO is a file on Ventoy's exFAT partition; we write there if it can be mounted.
"""

from __future__ import annotations

import json
import os
import struct
import tempfile
import time

from . import util

LABEL = "REPORTS"
ISO_LABEL = "TROUBLESHOOT"  # --iso-volume in live/auto/config
MEDIUM_MOUNTS = ("/run/live/medium", "/lib/live/mount/medium")
WRITABLE_FS = ("vfat", "exfat", "ntfs", "ntfs3")
ALIGN = 2048                  # sectors (1 MiB), like every partitioning tool
MIN_FREE = 64 * 1024 * 1024   # bytes; smaller than this isn't worth a FAT32 partition


VENTOY = ("This stick was made with Ventoy, which keeps its drive locked while the troubleshooter runs. "
          "Use another USB drive.")


class BootStickError(Exception):
    """A plain-language reason why the report can't be saved on the boot stick."""


def medium_source(mounts: str | None = None) -> tuple[str, str] | None:
    """(device, fstype) of the mounted boot medium, or None when it isn't a block device
    (e.g. the system was copied into RAM and the medium is a tmpfs)."""
    if mounts is None:
        mounts = util.read(os.path.join(util.PROC, "mounts")) or ""
    for line in mounts.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[1] in MEDIUM_MOUNTS:
            if parts[0].startswith("/dev/"):
                return parts[0], parts[2]
            return None
    return None


def _block(name: str, *rest: str) -> str:
    return util.sys_path("class", "block", name, *rest)


def parent_disk(name: str) -> str:
    """'sdb' for 'sdb1' (and 'nvme0n1' for 'nvme0n1p1'); a whole disk is its own parent."""
    if os.path.exists(_block(name, "partition")):
        return os.path.basename(os.path.dirname(os.path.realpath(_block(name))))
    return name


def _lsblk(*devices: str) -> list[dict]:
    res = util.run(["lsblk", "-J", "-b", "-o", "NAME,FSTYPE,LABEL,PARTTYPE,TYPE,MOUNTPOINT,SIZE", *devices])
    if res.returncode != 0:
        return []
    try:
        tree = json.loads(res.stdout).get("blockdevices", [])
    except ValueError:
        return []
    out: list[dict] = []

    def walk(devs):
        for d in devs:
            out.append(d)
            walk(d.get("children", []))
    walk(tree)
    return out


def find() -> dict | None:
    """The boot stick: {disk, medium, fstype, mounted, ventoy}. None if it can't be found
    (e.g. it was unplugged after "Load into RAM")."""
    src = medium_source()
    if src:
        dev, fstype = src
        name = os.path.basename(os.path.realpath(dev))
        ventoy = False
        slaves = util.sys_path("class", "block", name, "slaves")
        if os.path.isdir(slaves) and os.listdir(slaves):  # device-mapper, i.e. Ventoy
            name = sorted(os.listdir(slaves))[0]
            ventoy = True
            fstype = next((d.get("fstype") for d in _lsblk(f"/dev/{name}") if d["name"] == name), None) or ""
        if name.startswith("loop"):
            return None  # booted from an ISO file on some other drive; not ours to change
        return {"disk": parent_disk(name), "medium": name, "fstype": fstype, "mounted": not ventoy,
                "ventoy": ventoy}
    # Not mounted (copied into RAM): look for a plugged-in stick that carries our image.
    for d in _lsblk():
        if (d.get("label") or "").upper() in (ISO_LABEL, ISO_LABEL[:11]) and d.get("type") in ("disk", "part"):
            return {"disk": parent_disk(d["name"]), "medium": d["name"], "fstype": d.get("fstype") or "",
                    "mounted": False, "ventoy": False}
    return None


def reports_partition(disk: str) -> str | None:
    for d in _lsblk(f"/dev/{disk}"):
        if d.get("type") == "part" and d.get("label") == LABEL and d.get("fstype") == "vfat":
            return d["name"]
    return None


def needs_partition(stick: dict) -> bool:
    """True if saving will first have to create the REPORTS partition (worth asking about)."""
    return stick["fstype"] == "iso9660" and reports_partition(stick["disk"]) is None


def iso_sectors(header: bytes) -> int:
    """Size of an ISO 9660 filesystem in 512-byte sectors, from the bytes at offset 32768
    (the primary volume descriptor); 0 if it isn't one."""
    if len(header) < 88 or header[1:6] != b"CD001":
        return 0
    blocks = struct.unpack_from("<I", header, 80)[0]
    block_size = struct.unpack_from("<H", header, 128)[0] if len(header) >= 130 else 2048
    return blocks * (block_size or 2048) // 512


def new_partition_start(used_end: int, disk_sectors: int) -> int:
    """Where a new partition can start after ``used_end`` (first sector not in use), 1 MiB aligned.
    Raises BootStickError if there isn't enough room after it."""
    start = -(-used_end // ALIGN) * ALIGN
    if (disk_sectors - start) * 512 < MIN_FREE:
        raise BootStickError("This USB stick has no free space after the troubleshooter (it's about the "
                             "same size as the image). Use another USB drive, or a bigger stick.")
    return start


def create_partition(disk: str) -> str:
    """Add a FAT32 partition labelled REPORTS in the free space after the image. Returns its name."""
    dev = f"/dev/{disk}"
    res = util.run(["sfdisk", "-J", dev])
    try:
        table = json.loads(res.stdout)["partitiontable"]
    except (ValueError, KeyError):
        raise BootStickError("Couldn't read this USB stick's partition table.")
    if table.get("label") != "dos":
        raise BootStickError("This USB stick isn't laid out the way the troubleshooter image is, so it's "
                             "left alone. Use another USB drive.")
    parts = table.get("partitions", [])
    if len(parts) >= 4:
        raise BootStickError("This USB stick has no room for another partition. Use another USB drive.")
    used_end = max((p["start"] + p["size"] for p in parts), default=0)
    try:
        with open(dev, "rb") as f:
            f.seek(32768)
            used_end = max(used_end, iso_sectors(f.read(2048)))
    except OSError:
        pass
    disk_sectors = util.read_int(_block(disk, "size")) or 0
    start = new_partition_start(used_end, disk_sectors)
    # --no-reread: the stick is in use (we're running from it), so let partx tell the kernel instead.
    res = util.run(["sfdisk", "--append", "--no-reread", "--no-tell-kernel", "--wipe", "never",
                    "--wipe-partitions", "never", dev], timeout=60, input=f"start={start}, type=c\n")
    if res.returncode != 0:
        raise BootStickError("Couldn't add a partition to the USB stick: " + (res.stderr or res.stdout).strip()[-200:])
    number = len(parts) + 1
    util.run(["partx", "--add", "--nr", str(number), dev])
    util.run(["udevadm", "settle"], timeout=30)
    name = None
    for _ in range(20):
        name = next((n for n in os.listdir(util.sys_path("class", "block", disk))
                     if util.read(_block(disk, n, "partition"), "").strip() == str(number)), None)
        if name and os.path.exists(f"/dev/{name}"):
            break
        time.sleep(0.25)
    else:
        raise BootStickError("The new partition didn't show up. Unplug the stick and plug it back in, then try again.")
    res = util.run(["mkfs.vfat", "-F", "32", "-n", LABEL, f"/dev/{name}"], timeout=300)
    if res.returncode != 0:
        raise BootStickError("Couldn't format the new partition: " + (res.stderr or res.stdout).strip()[-200:])
    util.run(["sync"], timeout=120)
    return name


def _write(mountpoint: str, files: dict[str, str], subdir: str = "") -> list[str]:
    folder = os.path.join(mountpoint, subdir) if subdir else mountpoint
    os.makedirs(folder, exist_ok=True)
    for name, content in files.items():
        with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
            f.write(content)
    return [os.path.join(subdir, n) if subdir else n for n in files]


def _write_partition(name: str, fstype: str, files: dict[str, str], subdir: str = "") -> list[str]:
    mnt = tempfile.mkdtemp(prefix="bootstick-")
    try:
        fstype = "ntfs3" if fstype == "ntfs" else fstype
        res = util.run(["mount", "-t", fstype, f"/dev/{name}", mnt])
        if res.returncode != 0:
            raise BootStickError((res.stderr or "mount failed").strip())
        try:
            return _write(mnt, files, subdir)
        finally:
            util.run(["sync"], timeout=120)
            util.run(["umount", mnt])
    finally:
        os.rmdir(mnt)


def save(files: dict[str, str]) -> list[str]:
    """Write ``files`` ({name: text}) onto the boot stick. Returns descriptions of what was written."""
    stick = find()
    if stick is None:
        raise BootStickError("Couldn't find the troubleshooter USB stick. If you unplugged it after loading "
                             "into memory, plug it back in and try again.")
    if util.read_int(_block(stick["disk"], "ro")) == 1:
        raise BootStickError("The troubleshooter's boot drive is read-only (a DVD, or a USB stick with its "
                             "write-protect switch on).")
    try:
        part = reports_partition(stick["disk"])
        if part:
            return [f"this USB stick (REPORTS drive): {n}" for n in _write_partition(part, "vfat", files)]
        if stick["fstype"] in WRITABLE_FS:
            if stick["mounted"]:  # Rufus ISO mode etc.: briefly make the medium writable
                mnt = next(m for m in MEDIUM_MOUNTS if os.path.ismount(m))
                if util.run(["mount", "-o", "remount,rw", mnt]).returncode != 0:
                    raise BootStickError("The USB stick couldn't be made writable.")
                try:
                    written = _write(mnt, files, "reports")
                finally:
                    util.run(["sync"], timeout=120)
                    util.run(["mount", "-o", "remount,ro", mnt])
            else:
                try:
                    written = _write_partition(stick["medium"], stick["fstype"], files, "reports")
                except BootStickError:
                    if stick["ventoy"]:
                        raise BootStickError(VENTOY)
                    raise
            return [f"this USB stick: {n}" for n in written]
        if stick["ventoy"]:
            raise BootStickError(VENTOY)
        if stick["fstype"] == "iso9660":
            part = create_partition(stick["disk"])
            return [f"this USB stick (new REPORTS drive): {n}" for n in _write_partition(part, "vfat", files)]
    except OSError as e:
        raise BootStickError(str(e))
    raise BootStickError("The troubleshooter's USB stick can't be written to.")
