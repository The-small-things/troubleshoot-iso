"""2.5D / 3D games, software-rendered on a Tk canvas (no GPU or extra libraries needed).

* Maze Runner – first-person maze, ray-casting like the classic 1992 shooters.
* Turbo Road  – pseudo-3D arcade racer with curves, hills and traffic.
* Star Pilot  – real 3D: flat-shaded, rotating meshes with perspective, culling and lighting.

Canvas items are created once and reused every frame ("pooled"), which keeps the frame rate
playable even while the stress tests are running.
"""

from __future__ import annotations

import math
import random
import time

from ..sound import sfx
from . import theme as T
from .games import Game


def shade(color: str, f: float) -> str:
    """Scale a #rrggbb colour's brightness by f (0..1+)."""
    r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
    return f"#{min(255, int(r * f)):02x}{min(255, int(g * f)):02x}{min(255, int(b * f)):02x}"


def mix(a: str, b: str, t: float) -> str:
    """Blend colour a towards b by t (0..1)."""
    t = max(0.0, min(1.0, t))
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{int(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


class Game3D(Game):
    """Real-time game: tracks held keys and runs a frame loop while visible."""

    FPS = 30

    def __init__(self, master):
        self.held: set[str] = set()
        self._release_jobs: dict[str, str] = {}
        self.loop_job = None
        self.state = "ready"
        super().__init__(master)
        self.canvas.bind("<KeyRelease>", self.on_release)
        self.last = time.monotonic()
        self.loop_job = self.after(100, self.loop)

    @staticmethod
    def norm(e) -> str:
        k = e.keysym
        return {"w": "Up", "s": "Down", "a": "Left", "d": "Right"}.get(k.lower(), k)

    def on_key(self, e):
        k = self.norm(e)
        job = self._release_jobs.pop(k, None)
        if job:  # X key auto-repeat sends release+press pairs: ignore the fake release
            self.after_cancel(job)
        self.held.add(k)
        if k == "space":
            self.on_space()
        elif k.lower() == "p" and self.state in ("running", "paused"):
            self.state = "paused" if self.state == "running" else "running"
        return "break"

    def on_release(self, e):
        k = self.norm(e)
        self._release_jobs[k] = self.after(40, lambda: (self.held.discard(k), self._release_jobs.pop(k, None)))
        return "break"

    def on_space(self):
        if self.state in ("ready", "over", "won"):
            self.new_game()
            self.state = "running"
            sfx("start")

    def loop(self):
        now = time.monotonic()
        dt = min(0.1, now - self.last)
        self.last = now
        if self.winfo_ismapped() and self.canvas.winfo_width() > 10:
            if self.state == "running":
                self.update_game(dt)
            self.render()
        self.loop_job = self.after(int(1000 / self.FPS), self.loop)

    def overlay(self, text):
        self.canvas.delete("overlay")
        if text:
            c = self.canvas
            w, h = c.winfo_width(), c.winfo_height()
            t = c.create_text(w / 2, h / 2, text=text, fill="white", font=T.FONTS["h2"], justify="center",
                              tags="overlay")
            x0, y0, x1, y1 = c.bbox(t)
            p = T.px(0.8)
            r = c.create_rectangle(x0 - p, y0 - p, x1 + p, y1 + p, fill=T.PANEL, outline=T.ACCENT, width=2,
                                   tags="overlay")
            c.tag_raise(t, r)

    def draw(self):
        self.canvas.delete("all")
        self.build_scene()
        self.render()

    def destroy(self):
        if self.loop_job:
            self.after_cancel(self.loop_job)
        for j in self._release_jobs.values():
            self.after_cancel(j)
        super().destroy()

    # Subclasses implement these.
    def new_game(self): ...
    def build_scene(self): ...
    def update_game(self, dt): ...
    def render(self): ...


# ======================================================================================
# Maze Runner – ray casting
# ======================================================================================

def make_maze(cw: int, ch: int, rng: random.Random) -> list[list[int]]:
    """A perfect maze as a grid of 1 (wall) / 0 (floor), size (2*ch+1) x (2*cw+1)."""
    grid = [[1] * (2 * cw + 1) for _ in range(2 * ch + 1)]
    stack = [(0, 0)]
    seen = {(0, 0)}
    grid[1][1] = 0
    while stack:
        x, y = stack[-1]
        options = [(x + dx, y + dy, dx, dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                   if 0 <= x + dx < cw and 0 <= y + dy < ch and (x + dx, y + dy) not in seen]
        if not options:
            stack.pop()
            continue
        nx, ny, dx, dy = rng.choice(options)
        grid[2 * y + 1 + dy][2 * x + 1 + dx] = 0
        grid[2 * ny + 1][2 * nx + 1] = 0
        seen.add((nx, ny))
        stack.append((nx, ny))
    return grid


def cast(grid, px: float, py: float, angle: float, max_dist: float = 40.0) -> tuple[float, int, int, float]:
    """DDA ray cast. Returns (perpendicular distance, side 0/1, cell value hit, hit position 0..1 along the wall)."""
    dx, dy = math.cos(angle), math.sin(angle)
    mx, my = int(px), int(py)
    ddx = abs(1 / dx) if dx else 1e30
    ddy = abs(1 / dy) if dy else 1e30
    stepx, sdx = (-1, (px - mx) * ddx) if dx < 0 else (1, (mx + 1 - px) * ddx)
    stepy, sdy = (-1, (py - my) * ddy) if dy < 0 else (1, (my + 1 - py) * ddy)
    side = 0
    h, w = len(grid), len(grid[0])
    while True:
        if sdx < sdy:
            sdx += ddx
            mx += stepx
            side = 0
        else:
            sdy += ddy
            my += stepy
            side = 1
        if not (0 <= mx < w and 0 <= my < h):
            return max_dist, side, 1, 0.5
        cell = grid[my][mx]
        if cell:
            dist = max(0.0001, (sdx - ddx) if side == 0 else (sdy - ddy))
            along = (py + dist * dy) if side == 0 else (px + dist * dx)
            return dist, side, cell, along - math.floor(along)


class MazeRunner(Game3D):
    title = "Maze Runner 3D"
    help = "Arrows / WASD to walk and turn · find the green exit · grab the gold chips · M map · P pause"
    COLUMNS = 140
    FOV = math.radians(66)
    WALL = "#6366f1"
    EXIT = 2

    def __init__(self, master):
        self.maze_n = 6
        self.best_time: float | None = None
        self.show_map = True
        super().__init__(master)
        self.new_game()

    def new_game(self):
        rng = random.Random()
        self.grid = make_maze(self.maze_n, self.maze_n, rng)
        n = len(self.grid)
        self.grid[n - 2][n - 1] = self.EXIT  # exit door in the outer wall
        self.px, self.py = 1.5, 1.5
        self.angle = 0.0 if self.grid[1][2] == 0 else math.pi / 2  # face the open corridor
        floors = [(x + 0.5, y + 0.5) for y in range(n) for x in range(n)
                  if not self.grid[y][x] and (x, y) != (1, 1)]
        self.chips = rng.sample(floors, min(5, len(floors)))
        self.got = 0
        self.start = time.monotonic()
        self.elapsed = 0.0
        if self.canvas.winfo_width() > 10:
            self.draw()

    def build_scene(self):
        c = self.canvas
        w, h = c.winfo_width(), c.winfo_height()
        bands = 12
        for i in range(bands):  # ceiling and floor gradients
            y0, y1 = h / 2 * i / bands, h / 2 * (i + 1) / bands
            c.create_rectangle(0, y0, w, y1 + 1, fill=mix("#020617", "#1e1b4b", i / bands), outline="")
            c.create_rectangle(0, h - y1, w, h - y0 + 1, fill=mix("#3f3f46", "#0b0b0f", i / bands), outline="")
        self.cols = [c.create_rectangle(0, 0, 0, 0, outline="") for _ in range(self.COLUMNS)]
        self.sprites = [c.create_oval(0, 0, 0, 0, fill="#facc15", outline="#a16207", width=2) for _ in range(5)]
        self.map_items = []
        self.hud = c.create_text(T.px(0.6), T.px(0.5), anchor="nw", fill="white", font=T.FONTS["bold"])
        self.zbuf = [1.0] * self.COLUMNS
        self.build_map()

    def build_map(self):
        c = self.canvas
        for it in self.map_items:
            c.delete(it)
        self.map_items = []
        if not self.show_map:
            self.map_player = None
            return
        n = len(self.grid)
        cell = max(3, min(c.winfo_width(), c.winfo_height()) // 4 // n)
        ox = c.winfo_width() - cell * n - T.px(0.6)
        oy = T.px(0.6)
        self.map_geom = (ox, oy, cell)
        self.map_items.append(c.create_rectangle(ox - 3, oy - 3, ox + n * cell + 3, oy + n * cell + 3,
                                                 fill="#000000", outline=T.PANEL_HI))
        for y in range(n):
            for x in range(n):
                v = self.grid[y][x]
                if v:
                    self.map_items.append(c.create_rectangle(
                        ox + x * cell, oy + y * cell, ox + (x + 1) * cell, oy + (y + 1) * cell,
                        fill=T.GOOD if v == self.EXIT else "#475569", outline=""))
        self.map_player = c.create_line(0, 0, 0, 0, fill=T.BAD, width=3, arrow="last", arrowshape=(6, 7, 3))
        self.map_items.append(self.map_player)

    def on_key(self, e):
        if e.keysym.lower() == "m":
            self.show_map = not self.show_map
            self.build_map()
            return "break"
        return super().on_key(e)

    def free(self, x, y):
        v = self.grid[int(y)][int(x)]
        return v == 0 or v == self.EXIT

    def update_game(self, dt):
        turn = 2.6 * dt
        if "Left" in self.held:
            self.angle -= turn
        if "Right" in self.held:
            self.angle += turn
        move = (("Up" in self.held) - ("Down" in self.held)) * 2.4 * dt
        if move:
            nx = self.px + math.cos(self.angle) * move
            ny = self.py + math.sin(self.angle) * move
            r = 0.2 if move > 0 else -0.2
            if self.free(nx + math.cos(self.angle) * r, self.py):
                self.px = nx
            if self.free(self.px, ny + math.sin(self.angle) * r):
                self.py = ny
        for chip in list(self.chips):
            if (chip[0] - self.px) ** 2 + (chip[1] - self.py) ** 2 < 0.16:
                self.chips.remove(chip)
                self.got += 1
                sfx("pickup")
        self.elapsed = time.monotonic() - self.start
        if self.grid[int(self.py)][int(self.px)] == self.EXIT:
            self.state = "won"
            sfx("win")
            score = self.elapsed - 5 * self.got
            self.best_time = score if self.best_time is None else min(self.best_time, score)
            self.maze_n = min(12, self.maze_n + 1)

    def render(self):
        c = self.canvas
        if not hasattr(self, "cols"):
            return
        w, h = c.winfo_width(), c.winfo_height()
        colw = w / self.COLUMNS
        for i, item in enumerate(self.cols):
            a = self.angle + (i / self.COLUMNS - 0.5) * self.FOV
            dist, side, cell, along = cast(self.grid, self.px, self.py, a)
            dist *= math.cos(a - self.angle)  # remove fish-eye
            self.zbuf[i] = dist
            wh = min(h * 3, h * 0.55 / dist)
            base = T.GOOD if cell == self.EXIT else self.WALL
            edge = 0.55 if along < 0.035 or along > 0.965 else 1.0  # darker seams where wall blocks meet
            col = mix(shade(base, (0.75 if side else 1.0) * edge), "#05050a", dist / 14)
            c.coords(item, i * colw, h / 2 - wh / 2, (i + 1) * colw + 1, h / 2 + wh / 2)
            c.itemconfigure(item, fill=col)
        # Gold chips as billboards, hidden behind walls via the column depth buffer.
        for k, item in enumerate(self.sprites):
            if k >= len(self.chips):
                c.coords(item, -10, -10, -10, -10)
                continue
            sx, sy = self.chips[k]
            dx, dy = sx - self.px, sy - self.py
            ang = (math.atan2(dy, dx) - self.angle + math.pi) % (2 * math.pi) - math.pi
            dist = math.hypot(dx, dy) * math.cos(ang)
            col = int((ang / self.FOV + 0.5) * self.COLUMNS)
            if dist < 0.2 or not 0 <= col < self.COLUMNS or self.zbuf[col] < dist:
                c.coords(item, -10, -10, -10, -10)
                continue
            size = h / dist * 0.16
            bob = math.sin(time.monotonic() * 4 + k) * size * 0.1
            x = (col + 0.5) * colw
            y = h / 2 + h / dist * 0.12 + bob
            c.coords(item, x - size / 2, y - size / 2, x + size / 2, y + size / 2)
        for item in self.sprites:
            c.tag_raise(item)
        if self.show_map and self.map_items:
            ox, oy, cell = self.map_geom
            x, y = ox + self.px * cell, oy + self.py * cell
            c.coords(self.map_player, x, y, x + math.cos(self.angle) * cell * 1.6, y + math.sin(self.angle) * cell * 1.6)
            for it in self.map_items:
                c.tag_raise(it)
        c.itemconfigure(self.hud, text=f"Time {self.elapsed:5.1f}s   Chips {self.got}/5" +
                        (f"   Best {self.best_time:.1f}" if self.best_time is not None else ""))
        c.tag_raise(self.hud)
        self.score_lbl.configure(text=f"Maze size {self.maze_n}×{self.maze_n}")
        self.overlay({"ready": "Find the green exit!\nPress Space to start",
                      "paused": "Paused – P to continue",
                      "won": f"You escaped in {self.elapsed:.1f}s with {self.got} chips!\n"
                             "Space for a bigger maze"}.get(self.state, ""))


# ======================================================================================
# Turbo Road – pseudo-3D racer
# ======================================================================================

SEG_LEN = 200
ROAD_W = 2000
CAM_H = 1000
DRAW_DIST = 70


class TurboRoad(Game3D):
    title = "Turbo Road"
    help = "Up = accelerate · Down = brake · Left/Right = steer · overtake the traffic · P pause"
    MAX_SPEED = SEG_LEN * 60  # units per second

    def __init__(self, master):
        self.best_lap: float | None = None
        super().__init__(master)
        self.build_track()
        self.new_game()

    def build_track(self):
        segs = []

        def add(n, curve, hill):
            start_y = segs[-1]["y"] if segs else 0.0
            for i in range(n):
                t = i / n
                ease = (1 - math.cos(t * math.pi)) / 2
                segs.append({"curve": curve * math.sin(t * math.pi), "y": start_y + hill * ease * SEG_LEN * 20})

        for curve, hill, n in ((0, 0, 40), (2.5, 0.5, 60), (0, -0.5, 40), (-3, 0, 70), (0, 1, 50),
                               (3.5, -1, 60), (0, 0, 30), (-2, 0.4, 60), (2, -0.4, 50), (0, 0, 40)):
            add(n, curve, hill)
        # Ease the last segments back to the start height so the loop is seamless.
        end_y = segs[-1]["y"]
        for i in range(60):
            segs.append({"curve": 0.0, "y": end_y * (1 - (i + 1) / 60)})
        rng = random.Random(7)
        for i, s in enumerate(segs):
            s["sprite"] = None
            if i % 8 == 0 and i > 10:
                s["sprite"] = (rng.choice((-1.6, 1.6, -2.2, 2.2)), rng.choice(("tree", "tree", "post")))
        self.segs = segs
        self.track_len = len(segs) * SEG_LEN

    def new_game(self):
        self.pos = 0.0
        self.x = 0.0  # -1..1 across the road
        self.speed = 0.0
        self.lap_start = time.monotonic()
        self.lap = 1
        self.lap_time = 0.0
        self.passed = 0
        self.cars = [{"z": (i + 1) * self.track_len / 9, "x": random.choice((-0.5, 0.0, 0.5)),
                      "speed": self.MAX_SPEED * random.uniform(0.3, 0.55),
                      "color": random.choice(("#ef4444", "#f59e0b", "#a855f7", "#10b981", "#e5e7eb"))}
                     for i in range(8)]
        self.bg_offset = 0.0

    def build_scene(self):
        c = self.canvas
        w, h = c.winfo_width(), c.winfo_height()
        for i in range(10):
            c.create_rectangle(0, h * 0.55 * i / 10, w, h * 0.55 * (i + 1) / 10 + 1,
                               fill=mix("#1e3a8a", "#f97316", i / 9), outline="", tags="sky")
        self.sun = c.create_oval(0, 0, 0, 0, fill="#fde047", outline="")
        self.mountains = [c.create_polygon(0, 0, 0, 0, 0, 0, fill=col, outline="")
                          for col in ("#4c1d95", "#312e81")]
        # One pooled set of polygons per visible segment, created far-to-near so z-order is right.
        self.pool = []
        for _ in range(DRAW_DIST):
            self.pool.append([c.create_polygon(0, 0, 0, 0, 0, 0, 0, 0, outline="") for _ in range(5)])
        self.sprite_items = [c.create_polygon(0, 0, 0, 0, 0, 0, outline="") for _ in range(40)]
        self.car_items = [[c.create_polygon(0, 0, 0, 0, 0, 0, 0, 0, outline="") for _ in range(5)]
                          for _ in range(len(self.cars))]
        self.player = [c.create_polygon(0, 0, 0, 0, 0, 0, 0, 0, outline="") for _ in range(5)]
        self.hud = c.create_text(T.px(0.6), T.px(0.5), anchor="nw", fill="white", font=T.FONTS["bold"])
        self.speedo = c.create_text(w - T.px(0.6), h - T.px(0.5), anchor="se", fill="white", font=T.FONTS["h1"])

    def update_game(self, dt):
        accel = self.MAX_SPEED / 4
        if "Up" in self.held:
            self.speed += accel * dt
        elif "Down" in self.held:
            self.speed -= accel * 2.2 * dt
        else:
            self.speed -= accel * 0.4 * dt
        steer = (("Right" in self.held) - ("Left" in self.held)) * 2.2 * dt * (self.speed / self.MAX_SPEED + 0.2)
        seg = self.segs[int(self.pos / SEG_LEN) % len(self.segs)]
        self.x += steer - seg["curve"] * 0.3 * dt * (self.speed / self.MAX_SPEED) ** 2
        if abs(self.x) > 1.0:  # off-road: grass slows you down
            self.speed = min(self.speed, self.MAX_SPEED * 0.35)
        self.x = max(-2.2, min(2.2, self.x))
        self.speed = max(0.0, min(self.MAX_SPEED, self.speed))
        self.bg_offset += seg["curve"] * self.speed / self.MAX_SPEED * dt * 0.05
        old = self.pos
        self.pos += self.speed * dt
        for car in self.cars:
            before = (car["z"] - old) % self.track_len
            car["z"] = (car["z"] + car["speed"] * dt) % self.track_len
            rel = (car["z"] - self.pos) % self.track_len
            if rel > self.track_len / 2 and before < self.track_len / 2:
                self.passed += 1  # we overtook it
                sfx("coin")
            if rel < SEG_LEN * 1.2 and abs(car["x"] - self.x) < 0.35 and self.speed > car["speed"]:
                self.speed = car["speed"] * 0.6  # bump!
                sfx("bump")
                self.pos = car["z"] - SEG_LEN * 1.3
        if self.pos >= self.track_len:
            self.pos -= self.track_len
            lap = time.monotonic() - self.lap_start
            self.best_lap = lap if self.best_lap is None else min(self.best_lap, lap)
            self.lap_start = time.monotonic()
            self.lap += 1
            sfx("lap")
        self.lap_time = time.monotonic() - self.lap_start

    def project(self, wx, wy, wz, camx, camy, camz, w, h):
        z = wz - camz
        if z <= 1:
            return None
        scale = 0.84 / z  # camera depth ≈ 1/tan(fov/2) for ~100° FOV
        return (w / 2 + scale * (wx - camx) * w / 2, h / 2 - scale * (wy - camy) * h / 2, scale * ROAD_W * w / 2)

    def render(self):
        c = self.canvas
        if not hasattr(self, "pool"):
            return
        w, h = c.winfo_width(), c.winfo_height()
        n = len(self.segs)
        base = int(self.pos / SEG_LEN)
        frac = (self.pos % SEG_LEN) / SEG_LEN
        base_y = self.segs[base % n]["y"] + (self.segs[(base + 1) % n]["y"] - self.segs[base % n]["y"]) * frac
        camy = base_y + CAM_H
        # Sun and parallax mountains move with the curves.
        sx = (w * 0.7 - self.bg_offset * w) % (w * 1.4) - w * 0.2
        c.coords(self.sun, sx - h * 0.08, h * 0.25, sx + h * 0.08, h * 0.41)
        for k, item in enumerate(self.mountains):
            pts = []
            off = self.bg_offset * w * (0.5 + 0.5 * k)
            for i in range(0, 13):
                x = i * w / 12
                y = h * 0.5 - (math.sin((x + off) / w * 6.3 * (k + 1)) * 0.5 + 0.6) * h * (0.10 - 0.03 * k)
                pts += [x, y]
            pts += [w, h * 0.56, 0, h * 0.56]
            c.coords(item, *pts)
        # Road segments, near to far, with curve accumulation; then paint far to near.
        x, dx = 0.0, -self.segs[base % n]["curve"] * frac
        proj = []
        clip = h
        for i in range(DRAW_DIST):
            s = self.segs[(base + i) % n]
            s2 = self.segs[(base + i + 1) % n]
            camx = self.x * ROAD_W
            p1 = self.project(-x, s["y"], i * SEG_LEN, camx, camy, frac * SEG_LEN, w, h)
            x += dx
            dx += s["curve"]
            p2 = self.project(-x, s2["y"], (i + 1) * SEG_LEN, camx, camy, frac * SEG_LEN, w, h)
            visible = p1 and p2 and p2[1] < clip and p2[1] < p1[1] + 0.5
            proj.append((p1, p2, visible, (base + i) % n, x))
            if visible:
                clip = p2[1]
        sprite_i = 0
        for i in range(DRAW_DIST - 1, -1, -1):
            items = self.pool[DRAW_DIST - 1 - i]
            p1, p2, visible, idx, _ = proj[i]
            if not visible:
                for it in items:
                    c.coords(it, 0, 0, 0, 0, 0, 0, 0, 0)
                continue
            (x1, y1, w1), (x2, y2, w2) = p1, p2
            light = (idx // 3) % 2 == 0
            fog = i / DRAW_DIST
            grass = mix("#16a34a" if light else "#15803d", "#7c2d12", fog * 0.6)
            rumble = mix("#f8fafc" if light else "#dc2626", "#7c2d12", fog * 0.6)
            road = mix("#52525b" if light else "#4b5563", "#7c2d12", fog * 0.6)
            r1, r2 = w1 * 1.12, w2 * 1.12
            quads = [((0, y1, w, y1, w, y2, 0, y2), grass),
                     ((x1 - r1, y1, x1 + r1, y1, x2 + r2, y2, x2 - r2, y2), rumble),
                     ((x1 - w1, y1, x1 + w1, y1, x2 + w2, y2, x2 - w2, y2), road)]
            if light:
                lw1, lw2 = w1 * 0.03, w2 * 0.03
                for lane in (-1 / 3, 1 / 3):
                    quads.append(((x1 + w1 * lane * 2 - lw1, y1, x1 + w1 * lane * 2 + lw1, y1,
                                   x2 + w2 * lane * 2 + lw2, y2, x2 + w2 * lane * 2 - lw2, y2), "#f1f5f9"))
            for k, it in enumerate(items):
                if k < len(quads):
                    c.coords(it, *quads[k][0])
                    c.itemconfigure(it, fill=quads[k][1])
                else:
                    c.coords(it, 0, 0, 0, 0, 0, 0, 0, 0)
            # Roadside scenery for this segment.
            spr = self.segs[idx]["sprite"]
            if spr and sprite_i < len(self.sprite_items) and i > 1:
                offset, kind = spr
                sx2 = x1 + w1 * offset
                sz = w1 * (0.9 if kind == "tree" else 0.35)
                it = self.sprite_items[sprite_i]
                sprite_i += 1
                if kind == "tree":
                    c.coords(it, sx2, y1 - sz * 1.6, sx2 - sz * 0.45, y1, sx2 + sz * 0.45, y1)
                    c.itemconfigure(it, fill=mix("#065f46", "#7c2d12", fog * 0.5))
                else:
                    c.coords(it, sx2 - sz * 0.08, y1 - sz, sx2 + sz * 0.08, y1 - sz, sx2 + sz * 0.08, y1)
                    c.itemconfigure(it, fill=mix("#e2e8f0", "#7c2d12", fog * 0.5))
                c.tag_raise(it)
        for it in self.sprite_items[sprite_i:]:
            c.coords(it, 0, 0, 0, 0, 0, 0)
        # Traffic.
        for car, items in zip(self.cars, self.car_items):
            rel = (car["z"] - self.pos) % self.track_len
            seg_i = int(rel / SEG_LEN)
            if seg_i >= DRAW_DIST - 2 or rel < SEG_LEN * 0.5 or not proj[seg_i][2]:
                for it in items:
                    c.coords(it, 0, 0, 0, 0, 0, 0, 0, 0)
                continue
            p1 = proj[seg_i][0]
            cx = p1[0] + p1[2] * car["x"]
            cw = p1[2] * 0.42
            cy = p1[1]
            self.draw_car(items, cx, cy, cw, car["color"])
        # Player car.
        pw = w * 0.16
        tilt = ((("Right" in self.held) - ("Left" in self.held)) * pw * 0.06) if self.state == "running" else 0
        self.draw_car(self.player, w / 2, h * 0.97, pw, "#3b82f6", tilt)
        kmh = int(self.speed / self.MAX_SPEED * 240)
        c.itemconfigure(self.speedo, text=f"{kmh} km/h")
        c.itemconfigure(self.hud, text=f"Lap {self.lap}   {self.lap_time:5.1f}s   Overtaken {self.passed}" +
                        (f"   Best lap {self.best_lap:.1f}s" if self.best_lap else ""))
        c.tag_raise(self.speedo)
        c.tag_raise(self.hud)
        self.score_lbl.configure(text=f"Overtaken {self.passed}")
        self.overlay({"ready": "Turbo Road\nPress Space to start your engine",
                      "paused": "Paused – P to continue"}.get(self.state, ""))

    def draw_car(self, items, cx, by, cw, color, tilt=0.0):
        """A car seen from behind: two wheels, body, rear window and tail lights."""
        c = self.canvas
        hgt = cw * 0.5
        wheel_l, wheel_r, body, window, lights = items

        def quad(it, x0, y0, x1, y1, fill, lean=0.0):
            c.coords(it, x0, y1 + lean, x1, y1 - lean, x1 - (x1 - x0) * 0.04, y0 - lean, x0 + (x1 - x0) * 0.04, y0 + lean)
            c.itemconfigure(it, fill=fill)

        quad(wheel_l, cx - cw * 0.48, by - hgt * 0.3, cx - cw * 0.3, by, "#111827", tilt * 0.3)
        quad(wheel_r, cx + cw * 0.3, by - hgt * 0.3, cx + cw * 0.48, by, "#111827", tilt * 0.3)
        c.coords(body, cx - cw / 2, by - hgt * 0.18 + tilt, cx + cw / 2, by - hgt * 0.18 - tilt,
                 cx + cw * 0.44, by - hgt * 0.62 - tilt, cx - cw * 0.44, by - hgt * 0.62 + tilt)
        c.itemconfigure(body, fill=color)
        c.coords(window, cx - cw * 0.33, by - hgt * 0.62 + tilt * 0.8, cx + cw * 0.33, by - hgt * 0.62 - tilt * 0.8,
                 cx + cw * 0.24, by - hgt + tilt * 0.6, cx - cw * 0.24, by - hgt - tilt * 0.6)
        c.itemconfigure(window, fill=mix(shade(color, 0.45), "#93c5fd", 0.35))
        quad(lights, cx - cw * 0.42, by - hgt * 0.48, cx + cw * 0.42, by - hgt * 0.36, "#f87171", tilt)
        for it in items:
            c.tag_raise(it)


# ======================================================================================
# Star Pilot – flat-shaded 3D
# ======================================================================================

def icosahedron():
    t = (1 + 5 ** 0.5) / 2
    v = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
         (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    f = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2),
         (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5),
         (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    n = math.sqrt(1 + t * t)
    return [(x / n, y / n, z / n) for x, y, z in v], f


def octahedron():
    v = [(1, 0, 0), (-1, 0, 0), (0, 1.4, 0), (0, -1.4, 0), (0, 0, 1), (0, 0, -1)]
    f = [(2, 4, 0), (2, 0, 5), (2, 5, 1), (2, 1, 4), (3, 0, 4), (3, 5, 0), (3, 1, 5), (3, 4, 1)]
    return v, f


def rotate(v, ax, ay):
    x, y, z = v
    cy, sy = math.cos(ay), math.sin(ay)
    x, z = x * cy + z * sy, -x * sy + z * cy
    cx, sx = math.cos(ax), math.sin(ax)
    y, z = y * cx - z * sx, y * sx + z * cx
    return x, y, z


def face_normal(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1
    return nx / ln, ny / ln, nz / ln


class StarPilot(Game3D):
    title = "Star Pilot 3D"
    help = "Arrows / WASD to fly · dodge the asteroids · catch the green crystals · P pause"
    FAR = 60.0
    LIGHT = (-0.4, -0.6, -0.7)

    def __init__(self, master):
        self.best_score = 0
        lx, ly, lz = self.LIGHT
        ln = math.sqrt(lx * lx + ly * ly + lz * lz)
        self.light = (lx / ln, ly / ln, lz / ln)
        rv, rf = icosahedron()
        self.rock_faces = rf
        self.rock_verts = rv
        self.gem = octahedron()
        super().__init__(master)
        self.new_game()

    def new_game(self):
        self.sx, self.sy = 0.0, 0.0  # ship position
        self.speed = 14.0
        self.score = 0.0
        self.shield = 100.0
        self.objects = []
        self.spawn_t = 0.0
        self.flash = 0.0
        self.stars = [[random.uniform(-30, 30), random.uniform(-20, 20), random.uniform(1, self.FAR)]
                      for _ in range(70)]

    def spawn(self):
        gem = random.random() < 0.2
        jitter = [(x * random.uniform(0.8, 1.2), y * random.uniform(0.8, 1.2), z * random.uniform(0.8, 1.2))
                  for x, y, z in self.rock_verts]
        self.objects.append({
            "x": self.sx + random.uniform(-7, 7), "y": self.sy + random.uniform(-4.5, 4.5), "z": self.FAR,
            "r": 0.7 if gem else random.uniform(0.8, 1.8), "gem": gem,
            "verts": self.gem[0] if gem else jitter, "faces": self.gem[1] if gem else self.rock_faces,
            "ax": random.uniform(0, 6), "ay": random.uniform(0, 6),
            "spin": (random.uniform(-2, 2), random.uniform(-2, 2)),
            "color": "#22c55e" if gem else random.choice(("#a8a29e", "#78716c", "#b45309", "#94a3b8")),
        })

    def build_scene(self):
        c = self.canvas
        w, h = c.winfo_width(), c.winfo_height()
        c.create_rectangle(0, 0, w, h, fill="#020617", outline="")
        self.star_items = [c.create_line(0, 0, 0, 0, fill="white") for _ in range(70)]
        self.hud = c.create_text(T.px(0.6), T.px(0.5), anchor="nw", fill="white", font=T.FONTS["bold"])
        self.shield_bg = c.create_rectangle(0, 0, 0, 0, fill=T.PANEL, outline=T.PANEL_HI)
        self.shield_bar = c.create_rectangle(0, 0, 0, 0, fill=T.ACCENT, outline="")
        self.ship = [c.create_polygon(0, 0, 0, 0, 0, 0, outline="") for _ in range(4)]
        self.flash_item = c.create_rectangle(0, 0, 0, 0, outline="", fill="")

    def update_game(self, dt):
        mx = ("Right" in self.held) - ("Left" in self.held)
        my = ("Down" in self.held) - ("Up" in self.held)
        self.sx = max(-8, min(8, self.sx + mx * 9 * dt))
        self.sy = max(-5, min(5, self.sy + my * 7 * dt))
        self.speed = min(40, self.speed + dt * 0.6)
        self.score += dt * self.speed / 4
        self.spawn_t -= dt
        if self.spawn_t <= 0:
            self.spawn()
            self.spawn_t = max(0.18, 0.8 - self.speed / 80)
        for st in self.stars:
            st[2] -= self.speed * dt * 1.5
            if st[2] < 1:
                st[:] = [random.uniform(-30, 30), random.uniform(-20, 20), self.FAR]
        keep = []
        for o in self.objects:
            o["z"] -= self.speed * dt
            o["ax"] += o["spin"][0] * dt
            o["ay"] += o["spin"][1] * dt
            if o["z"] < 1.2 and not o.get("hit"):
                if abs(o["x"] - self.sx) < o["r"] + 0.6 and abs(o["y"] - self.sy) < o["r"] + 0.4:
                    o["hit"] = True
                    if o["gem"]:
                        self.score += 50
                        sfx("pickup")
                        self.shield = min(100, self.shield + 10)
                    else:
                        self.shield -= 25 * o["r"]
                        self.flash = 0.3
                        if self.shield <= 0:
                            self.shield = 0
                            self.state = "over"
                            sfx("explode")
                        else:
                            sfx("bump")
                            self.best_score = max(self.best_score, int(self.score))
                    continue
            if o["z"] > 0.5:
                keep.append(o)
        self.objects = keep
        self.flash = max(0.0, self.flash - dt)

    def render(self):
        c = self.canvas
        if not hasattr(self, "star_items"):
            return
        w, h = c.winfo_width(), c.winfo_height()
        f = min(w, h) * 0.9
        cx, cy = w / 2, h / 2

        def proj(x, y, z):
            return cx + (x - self.sx * 0.6) * f / z, cy + (y - self.sy * 0.6) * f / z

        for it, (x, y, z) in zip(self.star_items, self.stars):
            x1, y1 = proj(x, y, z)
            x2, y2 = proj(x, y, z + 0.6 + self.speed * 0.05)
            b = int(min(255, 80 + 175 * (1 - z / self.FAR)))
            c.coords(it, x1, y1, x2, y2)
            c.itemconfigure(it, fill=f"#{b:02x}{b:02x}{b:02x}")
        c.delete("mesh")
        faces = []
        for o in self.objects:
            pts = [rotate(v, o["ax"], o["ay"]) for v in o["verts"]]
            pts = [(o["x"] + x * o["r"], o["y"] + y * o["r"], o["z"] + z * o["r"]) for x, y, z in pts]
            for a, b, cc in o["faces"]:
                pa, pb, pc = pts[a], pts[b], pts[cc]
                if min(pa[2], pb[2], pc[2]) < 0.6:
                    continue
                n = face_normal(pa, pb, pc)
                # Back-face culling: skip faces pointing away from the camera.
                if n[0] * pa[0] + n[1] * pa[1] + n[2] * pa[2] >= 0:
                    continue
                lum = max(0.0, n[0] * self.light[0] + n[1] * self.light[1] + n[2] * self.light[2])
                fog = (pa[2] + pb[2] + pc[2]) / 3 / self.FAR
                col = mix(shade(o["color"], 0.35 + 0.9 * lum), "#020617", fog * 0.85)
                faces.append(((pa[2] + pb[2] + pc[2]) / 3, [v for p in (pa, pb, pc) for v in proj(*p)], col))
        faces.sort(key=lambda t: -t[0])  # painter's algorithm: far faces first
        for _, pts, col in faces:
            c.create_polygon(pts, fill=col, outline=col, tags="mesh")
        # Ship.
        bx, by = cx + self.sx * 4, h * 0.82 + self.sy * 3
        s = min(w, h) * 0.07
        bank = (("Right" in self.held) - ("Left" in self.held)) * s * 0.25 if self.state == "running" else 0
        shapes = [((bx, by - s * 0.6, bx - s, by + s * 0.3 + bank, bx + s, by + s * 0.3 - bank), "#cbd5e1"),
                  ((bx, by - s * 0.6, bx - s * 0.25, by + s * 0.2, bx + s * 0.25, by + s * 0.2), "#3b82f6"),
                  ((bx - s * 0.2, by + s * 0.25, bx + s * 0.2, by + s * 0.25, bx, by + s * 0.7), "#f97316"),
                  ((bx, by - s * 0.35, bx - s * 0.1, by - s * 0.05, bx + s * 0.1, by - s * 0.05), "#67e8f9")]
        for it, (pts, col) in zip(self.ship, shapes):
            c.coords(it, *pts)
            c.itemconfigure(it, fill=col)
            c.tag_raise(it)
        bw = w * 0.25
        c.coords(self.shield_bg, w - bw - T.px(0.6), T.px(0.6), w - T.px(0.6), T.px(1.4))
        c.coords(self.shield_bar, w - bw - T.px(0.6), T.px(0.6), w - bw - T.px(0.6) + bw * self.shield / 100,
                 T.px(1.4))
        c.itemconfigure(self.shield_bar, fill=T.ACCENT if self.shield > 30 else T.BAD)
        c.coords(self.flash_item, 0, 0, w, h)
        c.itemconfigure(self.flash_item, fill="#ef4444" if self.flash > 0 else "",
                        stipple="gray25" if self.flash > 0 else "")
        for it in (self.shield_bg, self.shield_bar, self.hud, self.flash_item):
            c.tag_raise(it)
        c.itemconfigure(self.hud, text=f"Score {int(self.score)}   Speed {int(self.speed * 10)}   Shield")
        self.score_lbl.configure(text=f"Best {self.best_score}")
        self.overlay({"ready": "Star Pilot\nDodge the rocks, catch the green crystals\nPress Space to launch",
                      "paused": "Paused – P to continue",
                      "over": f"Ship destroyed! Score {int(self.score)}\nSpace to fly again"}.get(self.state, ""))


GAMES_3D = [("Maze Runner 3D", MazeRunner), ("Turbo Road", TurboRoad), ("Star Pilot 3D", StarPilot)]
