"""Unit tests for the parts of the troubleshooter that interpret hardware data.

Run with:  python3 -m unittest discover -s tests
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from troubleshoot import apps, catalog, interactive, report, util  # noqa: E402
from troubleshoot.checks import battery, bluetooth, cpu, kernel_log, memory, storage  # noqa: E402
from troubleshoot.model import Result, Status  # noqa: E402

STRESS_OK = """stress-ng: info:  [875] dispatching hogs: 2 cpu
stress-ng: info:  [875] skipped: 0
stress-ng: info:  [875] passed: 2: cpu (2)
stress-ng: info:  [875] failed: 0
stress-ng: info:  [875] metrics untrustworthy: 0
stress-ng: info:  [875] successful run completed in 3.09 secs
"""
STRESS_FAIL = STRESS_OK.replace("failed: 0", "failed: 1: cpu (1)") + \
    "stress-ng: fail:  [880] cpu: matrixprod: verification error detected\n"


class CpuTests(unittest.TestCase):
    def test_clean_run_passes(self):
        self.assertEqual(cpu.stress_failures(STRESS_OK), [])
        r = cpu.evaluate(0, STRESS_OK, 72.0, 3000, 3500, 0, False, 60)
        self.assertIs(r.status, Status.PASS)

    def test_verification_error_fails(self):
        self.assertEqual(len(cpu.stress_failures(STRESS_FAIL)), 2)
        self.assertIs(cpu.evaluate(2, STRESS_FAIL, 70.0, None, None, 0, False, 60).status, Status.FAIL)

    def test_overheating_and_throttling_warns(self):
        r = cpu.evaluate(0, STRESS_OK, 99.0, 1200, 3500, 40, False, 60)
        self.assertIs(r.status, Status.WARN)
        self.assertIn("99", r.summary)
        self.assertIn("34%", r.summary)

    def test_fan_not_spinning_warns(self):
        self.assertIs(cpu.evaluate(0, STRESS_OK, 85.0, 3000, 3500, 0, True, 60).status, Status.WARN)


class MemoryTests(unittest.TestCase):
    def test_clean_removes_backspace_progress(self):
        self.assertEqual(memory.clean("  Stuck Address       : setting  1\b\b\b\b\b\b\b\b\b\bok\n"),
                         "  Stuck Address       : ok\n")
        self.assertEqual(memory.clean("a\n\b\bb"), "a\nb")

    def test_failure_detected(self):
        out = "  Random Value        : FAILURE: 0x1234 != 0x1236 at offset 0x00001000.\n"
        r = memory.evaluate(4, out, 1024, 1, None)
        self.assertIs(r.status, Status.FAIL)
        self.assertTrue(any("FAILURE" in d for d in r.details))

    def test_pass_and_ecc(self):
        out = "  Stuck Address       : ok\n  Random Value        : ok\n"
        self.assertIs(memory.evaluate(0, out, 1024, 1, None).status, Status.PASS)
        self.assertIs(memory.evaluate(0, out, 1024, 1, (3, 0)).status, Status.WARN)
        self.assertIs(memory.evaluate(0, out, 1024, 1, (0, 1)).status, Status.FAIL)

    def test_size(self):
        self.assertEqual(memory.test_size_mb(8 * 1024 * 1024, 0.5, 2048), 2048)
        self.assertEqual(memory.test_size_mb(1024 * 1024, 0.5, None), 512 - memory.HEADROOM_MB)
        self.assertEqual(memory.test_size_mb(100 * 1024, 0.5, None), 0)


def ata(attrs, passed=True, hours=1000):
    return {"smart_status": {"passed": passed}, "power_on_time": {"hours": hours},
            "ata_smart_attributes": {"table": [{"id": i, "value": norm, "raw": {"value": raw}}
                                               for i, raw, norm in attrs]}}


class StorageTests(unittest.TestCase):
    def ids(self, smart, rc=0):
        return [p for p, _ in storage.analyze_smart(smart, rc)[0]]

    def test_healthy_ata(self):
        self.assertEqual(self.ids(ata([(5, 0, 100), (197, 0, 100), (199, 0, 200)])), [])

    def test_pending_sectors_are_bad(self):
        self.assertIn("bad_sectors", self.ids(ata([(197, 8, 100)])))

    def test_few_reallocated_is_warning_many_is_bad(self):
        self.assertEqual(self.ids(ata([(5, 4, 100)])), ["remapped"])
        self.assertEqual(self.ids(ata([(5, 500, 90)])), ["bad_sectors"])

    def test_crc_points_at_cable(self):
        self.assertEqual(self.ids(ata([(199, 12, 200)])), ["crc"])

    def test_smart_failed(self):
        self.assertIn("smart_failed", self.ids(ata([], passed=False)))

    def test_nvme(self):
        healthy = {"smart_status": {"passed": True}, "nvme_smart_health_information_log": {
            "critical_warning": 0, "available_spare": 100, "available_spare_threshold": 10,
            "percentage_used": 3, "media_errors": 0}}
        self.assertEqual(self.ids(healthy), [])
        worn = {"nvme_smart_health_information_log": {**healthy["nvme_smart_health_information_log"],
                                                      "percentage_used": 97}}
        self.assertEqual(self.ids(worn), ["worn"])
        bad = {"nvme_smart_health_information_log": {**healthy["nvme_smart_health_information_log"],
                                                     "critical_warning": 1, "media_errors": 2}}
        self.assertEqual(sorted(self.ids(bad)), ["bad_sectors", "nvme_critical"])

    def test_has_smart(self):
        self.assertFalse(storage.has_smart({"json_format_version": [1, 0], "device": {}}))
        self.assertTrue(storage.has_smart(ata([])))

    def test_every_problem_has_advice_and_severity(self):
        self.assertEqual(set(storage.ADVICE), set(storage.SEVERITY))


class BatteryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = util.SYS
        util.SYS = self.tmp.name

    def tearDown(self):
        util.SYS = self.old
        self.tmp.cleanup()

    def make(self, name, **files):
        d = os.path.join(self.tmp.name, "class", "power_supply", name)
        os.makedirs(d)
        for k, v in files.items():
            with open(os.path.join(d, k), "w") as f:
                f.write(str(v))

    def test_worn_battery_with_energy_values(self):
        self.make("BAT0", type="Battery", status="Discharging", capacity=80, energy_full=25_000_000,
                  energy_full_design=50_000_000, energy_now=20_000_000, power_now=10_000_000, cycle_count=900)
        self.make("AC", type="Mains", online=0)
        r = battery.run(None)
        self.assertIs(r.status, Status.FAIL)
        self.assertIn("50%", r.summary)
        self.assertTrue(any("runtime" in d for d in r.details))

    def test_healthy_battery_with_charge_values(self):
        self.make("BAT1", type="Battery", status="Charging", capacity=50, charge_full=4_500_000,
                  charge_full_design=5_000_000, charge_now=2_000_000, voltage_min_design=11_400_000)
        self.make("ADP1", type="Mains", online=1)
        r = battery.run(None)
        self.assertIs(r.status, Status.PASS)
        self.assertIn("90%", r.summary)

    def test_charger_connected_but_draining(self):
        self.make("BAT0", type="Battery", status="Discharging", capacity=40, energy_full=45_000_000,
                  energy_full_design=50_000_000)
        self.make("AC", type="Mains", online=1)
        r = battery.run(None)
        self.assertIs(r.status, Status.WARN)
        self.assertIn("charger", r.summary.lower())

    def test_no_battery(self):
        self.assertIs(battery.run(None).status, Status.SKIP)

    def test_peripheral_batteries_ignored(self):
        self.make("hidpp_battery_0", type="Battery", scope="Device", capacity=50)
        self.assertIs(battery.run(None).status, Status.SKIP)


class KernelLogTests(unittest.TestCase):
    def test_clean_log(self):
        self.assertIs(kernel_log.evaluate("usb 1-1: new high-speed USB device\n").status, Status.PASS)

    def test_mce_is_failure(self):
        r = kernel_log.evaluate("mce: [Hardware Error]: Machine check events logged\n"
                                "blk_update_request: I/O error, dev sda, sector 1234\n")
        self.assertIs(r.status, Status.FAIL)
        self.assertIn("machine-check", r.summary)
        self.assertIn("disk", r.summary)

    def test_cdrom_and_loop_errors_ignored(self):
        self.assertIs(kernel_log.evaluate("I/O error, dev sr0, sector 0\nBuffer I/O error on dev loop0\n").status,
                      Status.PASS)

    def test_every_category_has_advice(self):
        cats = {c for c, _, _ in kernel_log.PATTERNS}
        self.assertEqual(cats, set(kernel_log.ADVICE))
        self.assertEqual(cats, set(kernel_log.LABELS))


class InteractiveTests(unittest.TestCase):
    def test_screen(self):
        self.assertIs(interactive.screen_result([], False).status, Status.PASS)
        self.assertIs(interactive.screen_result(["backlight"], False).status, Status.WARN)
        self.assertIs(interactive.screen_result(["lines", "backlight"], False).status, Status.FAIL)

    def test_keyboard(self):
        keys = ["A", "B", "C"]
        self.assertIs(interactive.keyboard_result({"A", "B", "C"}, keys, True).status, Status.PASS)
        self.assertIs(interactive.keyboard_result({"A"}, keys, True).status, Status.INFO)
        r = interactive.keyboard_result({"A"}, keys, False)
        self.assertIs(r.status, Status.FAIL)
        self.assertIn("B C", r.summary)

    def test_pointer(self):
        allsteps = set(interactive.POINTER_STEPS)
        self.assertIs(interactive.pointer_result(allsteps, "Touchpad", False).status, Status.PASS)
        r = interactive.pointer_result(allsteps - {"right"}, "Touchpad", False)
        self.assertIs(r.status, Status.FAIL)
        self.assertIn("right click", r.summary)
        r = interactive.pointer_result(allsteps, "Touchpad", False, jumpy=True)
        self.assertIn("swollen battery", r.explanation)

    def test_audio(self):
        self.assertIs(interactive.audio_result(True, True, True, 0.4, "x").status, Status.PASS)
        self.assertIs(interactive.audio_result(True, False, None, None, "x").status, Status.FAIL)
        self.assertIs(interactive.audio_result(None, None, None, None, "x").status, Status.SKIP)


class BluetoothTests(unittest.TestCase):
    AD = [{"name": "hci0", "driver": "btusb"}]

    def test_parse_scan(self):
        out = ("[NEW] Device 4C:87:5D:11:22:33 Phone\n[CHG] Device 4C:87:5D:11:22:33 RSSI: -60\n"
               "[NEW] Device AA:BB:CC:DD:EE:FF Headphones\n[CHG] Controller 00:11:22:33:44:55 Discovering: yes\n")
        self.assertEqual(len(bluetooth.parse_scan(out)), 2)

    def test_outcomes(self):
        ev = bluetooth.evaluate
        self.assertIs(ev(self.AD, None, True, 3, [], True).status, Status.PASS)
        self.assertIs(ev(self.AD, None, True, 0, [], True).status, Status.INFO)
        self.assertIs(ev(self.AD, None, False, None, [], True).status, Status.FAIL)
        self.assertIs(ev(self.AD, "hard", None, None, [], True).status, Status.WARN)
        self.assertIs(ev([], None, None, None, [], True).status, Status.WARN)
        self.assertIs(ev([], None, None, None, [], False).status, Status.SKIP)
        self.assertIn("firmware", ev([], None, None, None, ["intel/ibt-0040.sfi"], True).summary)

    def test_firmware_filter(self):
        self.assertEqual(bluetooth.bt_firmware_missing(["iwlwifi-so-a0.ucode", "rtl_bt/rtl8852bu_fw.bin"]),
                         ["rtl_bt/rtl8852bu_fw.bin"])


class WebcamTests(unittest.TestCase):
    def test_outcomes(self):
        wr = interactive.webcam_result
        self.assertIs(wr(["Integrated Camera"], True, [], True, True).status, Status.PASS)
        self.assertIs(wr(["Integrated Camera"], False, ["black"], True, True).status, Status.FAIL)
        self.assertIs(wr(["Integrated Camera"], False, ["blurry"], True, True).status, Status.WARN)
        self.assertIs(wr(["Integrated Camera"], True, [], True, False).status, Status.FAIL)
        self.assertIs(wr([], None, [], True, None).status, Status.WARN)
        self.assertIs(wr([], None, [], False, None).status, Status.SKIP)
        self.assertIs(wr([], None, [], True, None, mipi=True).status, Status.SKIP)


class AppsTests(unittest.TestCase):
    def test_parse_wifi(self):
        out = ("*:Home\\:Net:80:WPA2\n"
               ":Cafe:40:\n"
               ":Cafe:65:\n"
               "::30:WPA2\n")
        nets = apps.parse_wifi(out)
        self.assertEqual([n["ssid"] for n in nets], ["Home:Net", "Cafe"])  # connected first, hidden dropped
        self.assertTrue(nets[0]["connected"] and nets[0]["secure"])
        self.assertEqual(nets[1]["signal"], 65)  # strongest of duplicate access points
        self.assertFalse(nets[1]["secure"])

    def test_catalog_is_consistent(self):
        cats = {k for k, _ in apps.CATEGORIES}
        self.assertTrue(all(a.category in cats for a in apps.CATALOG))
        self.assertEqual(len({a.command for a in apps.CATALOG}), len(apps.CATALOG))

    def test_photorec_fallback_only_without_the_gui(self):
        old = apps.which
        try:
            apps.which = lambda c: f"/usr/bin/{c}" if c in ("photorec", "qphotorec") else None
            self.assertEqual([a.command for a in apps.installed("rescue")], ["qphotorec"])
            apps.which = lambda c: f"/usr/bin/{c}" if c == "photorec" else None
            self.assertEqual([a.command for a in apps.installed("rescue")], ["photorec"])
        finally:
            apps.which = old


class ReportTests(unittest.TestCase):
    def results(self):
        return [Result("sysinfo", "System information", Status.INFO, "PC"),
                Result("cpu", "CPU", Status.PASS, "ok"),
                Result("audio", "Audio", Status.SKIP, "skipped"),
                Result("battery", "Battery", Status.WARN, "worn", ["detail <b>"], "expl", ["replace"])]

    def test_verdicts(self):
        self.assertIs(report.verdict(self.results())[0], Status.WARN)
        self.assertIs(report.verdict([Result("cpu", "CPU", Status.PASS, "ok")])[0], Status.PASS)
        fail = self.results() + [Result("storage", "Storage", Status.FAIL, "bad")]
        status, _, para = report.verdict(fail)
        self.assertIs(status, Status.FAIL)
        self.assertIn("Back up", para)

    def test_order_problems_first_skips_last(self):
        order = [r.test_id for r in report.sorted_results(self.results())]
        self.assertEqual(order, ["battery", "sysinfo", "cpu", "audio"])

    def test_text_and_html(self):
        text = report.to_text(self.results(), "Quick check")
        self.assertIn("NEEDS ATTENTION", text)
        html = report.to_html(self.results(), "Quick check")
        self.assertIn("&lt;b&gt;", html)  # escaped
        self.assertNotIn("detail <b>", html)


class CatalogTests(unittest.TestCase):
    def test_profiles_reference_known_tests(self):
        for p in catalog.PROFILES.values():
            self.assertTrue(set(p.params) <= set(catalog.TESTS), p.key)

    def test_interactive_tests_come_before_long_tests(self):
        plan = [s.test_id for s, _ in catalog.plan(catalog.PROFILES["full"])]
        last_interactive = max(i for i, t in enumerate(plan) if catalog.TESTS[t].interactive)
        self.assertLess(last_interactive, plan.index("memory"))
        self.assertEqual(plan[-1], "kernel_log")

    def test_custom_selection_keeps_sysinfo(self):
        plan = [s.test_id for s, _ in catalog.plan(catalog.PROFILES["custom"], {"cpu"})]
        self.assertEqual(plan, ["sysinfo", "cpu"])

    def test_automated_tests_have_runners(self):
        for t in catalog.TESTS.values():
            self.assertEqual(t.run is None, t.interactive, t.test_id)


if __name__ == "__main__":
    unittest.main()


class RamBootTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = (util.SYS, util.PROC)
        util.SYS = os.path.join(self.tmp.name, "sys")
        util.PROC = os.path.join(self.tmp.name, "proc")
        os.makedirs(util.PROC)

    def tearDown(self):
        util.SYS, util.PROC = self.old
        self.tmp.cleanup()

    def setup(self, cmdline, medium_fstype):
        with open(os.path.join(util.PROC, "cmdline"), "w") as f:
            f.write(cmdline)
        with open(os.path.join(util.PROC, "mounts"), "w") as f:
            f.write("proc /proc proc rw 0 0\n")
            if medium_fstype:
                f.write(f"/dev/sdb1 /run/live/medium {medium_fstype} ro,noatime 0 0\n")
            f.write("/dev/loop0 /run/live/rootfs/filesystem.squashfs squashfs ro 0 0\n")

    def test_normal_boot(self):
        self.setup("boot=live quiet", "iso9660")
        self.assertIsNone(util.ram_boot_status())

    def test_loaded_into_ram(self):
        self.setup("boot=live toram quiet", "tmpfs")
        self.assertEqual(util.ram_boot_status(), "ram")

    def test_requested_but_not_enough_memory(self):
        self.setup("boot=live toram", "iso9660")
        self.assertEqual(util.ram_boot_status(), "fallback")

    def test_medium_unmounted_after_copy(self):
        self.setup("boot=live toram=filesystem.squashfs", None)
        self.assertEqual(util.ram_boot_status(), "ram")


class TerminalAppTests(unittest.TestCase):
    def test_terminal_apps_open_in_a_terminal(self):
        app = apps.App("testdisk", "TestDisk", "", "rescue", terminal=True)
        old = apps.which
        apps.which = lambda c: {"lxterminal": "/usr/bin/lxterminal"}.get(c)
        try:
            cmd = apps.command_line(app, "/usr/bin/testdisk")
            self.assertEqual(cmd[0], "/usr/bin/lxterminal")
            self.assertIn("/usr/bin/testdisk", cmd[-1])
            guided = apps.App("ddrescue", "Rescue", "", "rescue", terminal=True, guide="/g/ddrescue.txt")
            self.assertIn("cat /g/ddrescue.txt", apps.command_line(guided, "/usr/bin/ddrescue")[-1])
            apps.which = lambda c: None
            self.assertIsNone(apps.command_line(app, "/usr/bin/testdisk"))
            self.assertEqual(apps.command_line(apps.App("x", "X", "", "tools"), "/usr/bin/x"), ["/usr/bin/x"])
        finally:
            apps.which = old
