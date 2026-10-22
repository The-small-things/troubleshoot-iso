"""Tests for the synthesised music/effects and the background player's behaviour."""

import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from troubleshoot import sound  # noqa: E402


class SynthTests(unittest.TestCase):
    def test_effects_are_short_and_audible(self):
        for name, fn in sound.SFX.items():
            buf = fn()
            self.assertLess(len(buf) / sound.RATE, 2.0, name)
            self.assertGreater(max(abs(x) for x in buf), 0.05, name)

    def test_music_loops_are_whole_bars_and_seamless(self):
        for name, (fn, _) in sound.MUSIC.items():
            buf = fn()
            self.assertGreater(len(buf) / sound.RATE, 10, name)
            # The end flows into the start: the jump across the seam is no bigger than
            # the largest jumps inside the loop.
            steps = sorted(abs(buf[i + 1] - buf[i]) for i in range(0, len(buf) - 1, 5))
            self.assertLessEqual(abs(buf[0] - buf[-1]), steps[int(len(steps) * 0.999)], name)

    def test_render_all_writes_every_file(self):
        with tempfile.TemporaryDirectory() as d:
            sound.render_all(d)
            names = set(os.listdir(d))
            for n in sound.SFX:
                self.assertIn(f"{n}.wav", names)
            for n in sound.MUSIC:
                self.assertIn(f"music-{n}.wav", names)


class PlayerTests(unittest.TestCase):
    """Drive the player with a fake 'audio player' that records what it was asked to play."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = os.path.join(self.tmp.name, "played.log")
        for n in list(sound.SFX) + [f"music-{m}" for m in sound.MUSIC]:
            open(os.path.join(self.tmp.name, f"{n}.wav"), "w").close()
        with open(os.path.join(self.tmp.name, "VERSION"), "w") as f:
            f.write(sound.VERSION)
        self.old_dir, self.old_cmd = sound.SYSTEM_DIR, sound.Player._player_cmd
        sound.SYSTEM_DIR = self.tmp.name
        fake = ["sh", "-c", f'echo "$1" >> {self.log}; sleep 8', "fake-player"]
        sound.Player._player_cmd = staticmethod(lambda: fake)
        self.p = sound.Player()
        self.wait(lambda: self.p.dir is not None)

    def tearDown(self):
        self.p.music(None)
        time.sleep(0.4)
        sound.SYSTEM_DIR, sound.Player._player_cmd = self.old_dir, self.old_cmd
        self.tmp.cleanup()

    def wait(self, cond, timeout=3.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if cond():
                return True
            time.sleep(0.05)
        return False

    def played(self):
        try:
            with open(self.log) as f:
                return [os.path.basename(line.strip()) for line in f]
        except OSError:
            return []

    def test_music_switches_and_stops(self):
        self.p.music("chill")
        self.assertTrue(self.wait(lambda: self.played()[-1:] == ["music-chill.wav"]))
        first = self.p._proc
        self.p.music("arcade")
        self.assertTrue(self.wait(lambda: self.played()[-1:] == ["music-arcade.wav"]))
        self.assertIsNotNone(first.poll())  # the old track was stopped
        self.p.set_enabled(False)
        self.assertTrue(self.wait(lambda: self.p._proc is None))

    def test_pause_while_external_app_runs(self):
        import subprocess
        self.p.music("chill")
        self.assertTrue(self.wait(lambda: self.p._proc is not None))
        app = subprocess.Popen(["sleep", "0.5"])
        self.p.watch(app)
        self.assertTrue(self.wait(lambda: self.p._proc is None))
        self.assertTrue(self.wait(lambda: self.p._proc is not None, timeout=4))  # resumed after exit

    def test_gives_up_without_a_sound_device(self):
        self.p.music(None)
        self.wait(lambda: self.p._proc is None)
        self.p.cmd = ["false"]  # a player that fails instantly, like aplay without a sound card
        self.p.music("chill")
        self.assertTrue(self.wait(lambda: self.p.cmd is None, timeout=5))

    def test_effects_respect_mute_quiet_and_rate_limit(self):
        self.p.min_gap = 60  # don't depend on how fast the machine starts processes
        self.p.sfx("coin")
        self.p.sfx("coin")  # within 60 ms: dropped
        self.p.quiet = True
        self.p.sfx("win")
        self.p.quiet = False
        self.p.set_enabled(False)
        self.p.sfx("lose")
        self.assertTrue(self.wait(lambda: len(self.played()) >= 1))
        time.sleep(0.3)
        self.assertEqual(self.played(), ["coin.wav"])


if __name__ == "__main__":
    unittest.main()
