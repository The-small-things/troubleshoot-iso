"""Chip's face animation: blinks and expression changes."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from troubleshoot import art  # noqa: E402


def eyes(shapes):
    return [s for s in shapes if s[0] in ("line", "oval") and s[2] == art.GLOW][:2]


class ArtTests(unittest.TestCase):
    def test_every_face_shuts_its_eyes_the_same_way(self):
        # A face change happens while the eyes are shut, so shut eyes must look alike.
        for e in art.EXPRESSIONS:
            shut = eyes(art.chip(e, blink=1.0, parts=("face",)))
            self.assertTrue(all(s[0] == "line" and len(s[1]) == 2 for s in shut), e)

    def test_blinking_keeps_the_mouth(self):
        for e in art.OPEN_EYES:
            open_ = art.chip(e, parts=("face",))
            shut = art.chip(e, blink=1.0, parts=("face",))
            self.assertEqual(open_[-1], shut[-1], e)  # the mouth is drawn last

    def test_parts_split_the_drawing(self):
        whole = art.chip("happy")
        layers = sum((art.chip("happy", parts=(p,)) for p in art.PARTS), [])
        self.assertEqual(sorted(map(repr, whole)), sorted(map(repr, layers)))


class MascotTests(unittest.TestCase):
    def setUp(self):
        try:
            import tkinter as tk
            self.root = tk.Tk()
        except Exception as e:  # no tkinter or no display
            self.skipTest(f"Tk not available: {e}")
        self.root.withdraw()
        from troubleshoot.gui.mascot import Mascot
        self.chip = Mascot(self.root, 80, "thinking", bg="black")
        self.chip.after_cancel(self.chip.job)
        self.chip.job = None

    def tearDown(self):
        if hasattr(self, "root"):
            self.root.destroy()

    def step(self):
        self.chip.animate()
        self.chip.after_cancel(self.chip.job)
        self.chip.job = None

    def test_new_face_appears_while_the_eyes_are_shut(self):
        self.chip.set("excited")
        seen = []
        for _ in range(12):
            self.step()
            seen.append((self.chip.expression, self.chip.last_face[1]))
        switch = next(i for i, (e, _) in enumerate(seen) if e == "excited")
        self.assertGreaterEqual(seen[switch][1], 0.85)  # first frame of the new face: eyes still shut
        self.assertTrue(all(e == "thinking" for e, _ in seen[:switch]))
        self.assertEqual(seen[-1], ("excited", 0.0))

    def test_setting_the_same_face_does_nothing(self):
        self.chip.set("thinking")
        self.assertIsNone(self.chip.pending)
        self.assertEqual(self.chip.blink_frames, [])


if __name__ == "__main__":
    unittest.main()
