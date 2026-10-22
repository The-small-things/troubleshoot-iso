"""Checks on the live system's configuration files."""

import os
import unittest
import xml.etree.ElementTree as ET

ROOT = os.path.join(os.path.dirname(__file__), "..")
OPENBOX_RC = os.path.join(ROOT, "live", "config", "includes.chroot", "etc", "troubleshoot", "openbox-rc.xml")
NS = {"ob": "http://openbox.org/3.4/rc"}


class OpenboxConfigTests(unittest.TestCase):
    def setUp(self):
        self.root = ET.parse(OPENBOX_RC).getroot()

    def test_no_unmodified_click_bindings_on_the_frame(self):
        # Openbox doesn't pass clicks bound in the "Frame" context (which covers the whole
        # window) on to the app. A plain Left/Right click there made every button in the
        # troubleshooter ignore the mouse (fixed in 1.1.1).
        for ctx in self.root.iterfind(".//ob:mouse/ob:context", NS):
            if ctx.get("name") not in ("Frame", "Root", "Desktop"):
                continue
            for bind in ctx.iterfind("ob:mousebind", NS):
                button = bind.get("button", "")
                self.assertIn("-", button, f"unmodified '{button}' click bound in {ctx.get('name')} context")

    def test_keyboard_test_keys_are_not_grabbed(self):
        # Only Alt+Tab may be bound, so the keyboard test sees every other key.
        keys = [k.get("key") for k in self.root.iterfind(".//ob:keyboard/ob:keybind", NS)]
        self.assertEqual(keys, ["A-Tab"])

    def test_troubleshooter_window_rule(self):
        apps = {a.get("class"): a for a in self.root.iterfind(".//ob:applications/ob:application", NS)}
        self.assertIn("Troubleshoot", apps)
        self.assertEqual(apps["Troubleshoot"].findtext("ob:fullscreen", namespaces=NS), "yes")


if __name__ == "__main__":
    unittest.main()
