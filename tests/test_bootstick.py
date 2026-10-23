"""Saving the report onto the troubleshooter's own USB stick."""

import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from troubleshoot import bootstick, report, util  # noqa: E402

LSBLK = {"blockdevices": [
    {"name": "sdb", "fstype": "iso9660", "rm": True, "tran": "usb", "mountpoint": None, "label": "TROUBLESHOOT",
     "type": "disk", "pkname": None, "parttype": None, "children": [
         {"name": "sdb1", "fstype": "iso9660", "rm": True, "tran": None, "mountpoint": "/run/live/medium",
          "label": "TROUBLESHOOT", "type": "part", "pkname": "sdb", "parttype": "0x0"},
         {"name": "sdb2", "fstype": "vfat", "rm": True, "tran": None, "mountpoint": None, "label": "ESP",
          "type": "part", "pkname": "sdb", "parttype": "0xef"},
         {"name": "sdb3", "fstype": "vfat", "rm": True, "tran": None, "mountpoint": None, "label": "REPORTS",
          "type": "part", "pkname": "sdb", "parttype": "0xc"}]},
    {"name": "sdc", "fstype": None, "rm": True, "tran": "usb", "mountpoint": None, "label": None, "type": "disk",
     "pkname": None, "parttype": None, "children": [
         {"name": "sdc1", "fstype": "exfat", "rm": True, "tran": None, "mountpoint": None, "label": "MYSTICK",
          "type": "part", "pkname": "sdc", "parttype": "0x7"}]},
    {"name": "nvme0n1", "fstype": None, "rm": False, "tran": "nvme", "mountpoint": None, "label": None,
     "type": "disk", "pkname": None, "parttype": None, "children": [
         {"name": "nvme0n1p1", "fstype": "vfat", "rm": False, "tran": None, "mountpoint": None, "label": None,
          "type": "part", "pkname": "nvme0n1", "parttype": "c12a7328-f81f-11d2-ba4b-00a0c93ec93b"},
         {"name": "nvme0n1p2", "fstype": "ntfs", "rm": False, "tran": None, "mountpoint": None, "label": None,
          "type": "part", "pkname": "nvme0n1", "parttype": "ebd0a0a2-b9e5-4433-87c0-68b6b72699c7"}]},
]}


class BootStickTests(unittest.TestCase):
    def test_medium_source(self):
        self.assertEqual(bootstick.medium_source("/dev/sdb1 /run/live/medium iso9660 ro 0 0\n"),
                         ("/dev/sdb1", "iso9660"))
        self.assertIsNone(bootstick.medium_source("tmpfs /run/live/medium tmpfs rw 0 0\n"))
        self.assertIsNone(bootstick.medium_source("/dev/sda1 / ext4 rw 0 0\n"))

    def test_iso_sectors(self):
        pvd = bytearray(2048)
        pvd[0:6] = b"\x01CD001"
        struct.pack_into("<I", pvd, 80, 903096)    # blocks
        struct.pack_into("<H", pvd, 128, 2048)     # block size
        self.assertEqual(bootstick.iso_sectors(bytes(pvd)), 903096 * 4)
        self.assertEqual(bootstick.iso_sectors(bytes(2048)), 0)

    def test_new_partition_start_is_aligned_after_the_image(self):
        # The real 1.3.0 image ends at sector 3612384; on a 4 GB stick the partition starts at the next MiB.
        self.assertEqual(bootstick.new_partition_start(3612384, 8388608), 3612672)
        self.assertEqual(bootstick.new_partition_start(4096, 8388608), 4096)
        with self.assertRaises(bootstick.BootStickError):  # stick barely bigger than the image
            bootstick.new_partition_start(3612384, 3612384 + 2048 * 10)

    def test_parent_disk(self):
        with tempfile.TemporaryDirectory() as d:
            old = util.SYS
            util.SYS = d
            try:
                part = os.path.join(d, "devices", "pci0", "sdb", "sdb1")
                os.makedirs(part)
                with open(os.path.join(part, "partition"), "w") as f:
                    f.write("1")
                os.makedirs(os.path.join(d, "devices", "pci0", "sdb"), exist_ok=True)
                os.makedirs(os.path.join(d, "class", "block"))
                os.symlink(part, os.path.join(d, "class", "block", "sdb1"))
                os.symlink(os.path.dirname(part), os.path.join(d, "class", "block", "sdb"))
                self.assertEqual(bootstick.parent_disk("sdb1"), "sdb")
                self.assertEqual(bootstick.parent_disk("sdb"), "sdb")
            finally:
                util.SYS = old


class UsbTargetTests(unittest.TestCase):
    def setUp(self):
        self.old_run = util.run
        util.run = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, json.dumps(LSBLK), "")

    def tearDown(self):
        util.run = self.old_run

    def test_boot_stick_only_offers_its_reports_drive(self):
        names = [d["name"] for d in report._usb_targets("sdb")]
        self.assertEqual(names, ["sdb3", "sdc1"])  # not the image, not its EFI partition, not the internal disk

    def test_efi_partitions_are_never_targets(self):
        self.assertNotIn("sdb2", [d["name"] for d in report._usb_targets(None)])


class SaveFlowTests(unittest.TestCase):
    def setUp(self):
        self.saved = {}
        self.patches = {(report, "save_to_usb"): lambda files: [],
                        (report, "save_home"): lambda files: ["/root/report.txt"],
                        (bootstick, "find"): lambda: {"disk": "sdb", "medium": "sdb", "fstype": "iso9660",
                                                      "mounted": True, "ventoy": False},
                        (bootstick, "needs_partition"): lambda stick: True,
                        (bootstick, "save"): lambda files: ["this USB stick (new REPORTS drive): r.txt"]}
        for (mod, name), fn in self.patches.items():
            self.saved[(mod, name)] = getattr(mod, name)
            setattr(mod, name, fn)

    def tearDown(self):
        for (mod, name), fn in self.saved.items():
            setattr(mod, name, fn)

    def test_asks_before_adding_a_partition(self):
        asked = []
        paths, problem = report.save([], "Quick", lambda q: asked.append(q) or True)
        self.assertEqual(len(asked), 1)
        self.assertIn("REPORTS", asked[0])
        self.assertEqual(paths, ["this USB stick (new REPORTS drive): r.txt"])
        self.assertIsNone(problem)

    def test_declining_keeps_it_in_memory_and_says_so(self):
        paths, problem = report.save([], "Quick", lambda q: False)
        self.assertEqual(paths, ["/root/report.txt"])
        self.assertIn("Not saved to a USB drive", problem)

    def test_errors_fall_back_with_the_reason(self):
        def fail(files):
            raise bootstick.BootStickError("no room")
        bootstick.save = fail
        paths, problem = report.save([], "Quick", lambda q: True)
        self.assertEqual(paths, ["/root/report.txt"])
        self.assertIn("no room", problem)

    def test_other_usb_drive_wins_without_asking(self):
        report.save_to_usb = lambda files: ["MYSTICK: r.txt"]
        paths, problem = report.save([], "Quick", lambda q: self.fail("shouldn't ask"))
        self.assertEqual(paths, ["MYSTICK: r.txt"])


if __name__ == "__main__":
    unittest.main()
