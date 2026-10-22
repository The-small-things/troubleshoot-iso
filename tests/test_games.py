"""Tests for the game logic that doesn't need a display."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    from troubleshoot.gui.games import neighbours, slide_row
    from troubleshoot.gui.games3d import cast, face_normal, icosahedron, make_maze, mix
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


@unittest.skipIf(slide_row is None, "tkinter not available")
class Game3DLogicTests(unittest.TestCase):
    def test_maze_is_fully_connected(self):
        import random
        grid = make_maze(7, 5, random.Random(1))
        floors = {(x, y) for y, row in enumerate(grid) for x, v in enumerate(row) if v == 0}
        seen, stack = set(), [(1, 1)]
        while stack:
            x, y = stack.pop()
            if (x, y) in seen or (x, y) not in floors:
                continue
            seen.add((x, y))
            stack += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
        self.assertEqual(seen, floors)

    def test_ray_cast_distance(self):
        grid = [[1, 1, 1, 1, 1],
                [1, 0, 0, 0, 1],
                [1, 1, 1, 1, 1]]
        dist, side, cell, along = cast(grid, 1.5, 1.5, 0.0)  # looking east
        self.assertAlmostEqual(dist, 2.5, places=6)
        self.assertEqual((side, cell), (0, 1))
        self.assertAlmostEqual(along, 0.5, places=6)

    def test_icosahedron_faces_point_outwards(self):
        verts, faces = icosahedron()
        self.assertEqual((len(verts), len(faces)), (12, 20))
        for a, b, c in faces:
            n = face_normal(verts[a], verts[b], verts[c])
            centre = [sum(v[i] for v in (verts[a], verts[b], verts[c])) / 3 for i in range(3)]
            self.assertGreater(sum(n[i] * centre[i] for i in range(3)), 0)

    def test_mix(self):
        self.assertEqual(mix("#000000", "#ffffff", 0.5), "#7f7f7f")
        self.assertEqual(mix("#123456", "#ffffff", 0), "#123456")


if __name__ == "__main__":
    unittest.main()
