"""Tests for the game logic that doesn't need a display."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    from troubleshoot.gui.games import neighbours, slide_row
except ImportError:  # tkinter not installed
    slide_row = None


@unittest.skipIf(slide_row is None, "tkinter not available")
class GameLogicTests(unittest.TestCase):
    def test_2048_slide(self):
        self.assertEqual(slide_row([2, 2, 0, 0]), ([4, 0, 0, 0], 4))
        self.assertEqual(slide_row([2, 2, 2, 2]), ([4, 4, 0, 0], 8))
        self.assertEqual(slide_row([0, 4, 4, 8]), ([8, 8, 0, 0], 8))  # merged tile doesn't merge again
        self.assertEqual(slide_row([2, 4, 8, 16]), ([2, 4, 8, 16], 0))

    def test_minesweeper_neighbours(self):
        self.assertEqual(len(list(neighbours(0, 0, 5, 5))), 3)
        self.assertEqual(len(list(neighbours(2, 2, 5, 5))), 8)


if __name__ == "__main__":
    unittest.main()
