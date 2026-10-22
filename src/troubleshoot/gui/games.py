"""Small games to play while the automatic tests run: Snake, 2048 and Minesweeper.

Each game is a Frame that fits whatever space it gets, takes keyboard focus when clicked, and
stops its timers when destroyed.
"""

from __future__ import annotations

import random
import tkinter as tk

from ..sound import sfx
from . import theme as T

ARROWS = {"Up": (0, -1), "Down": (0, 1), "Left": (-1, 0), "Right": (1, 0),
          "w": (0, -1), "s": (0, 1), "a": (-1, 0), "d": (1, 0)}


class Game(tk.Frame):
    title = ""
    help = ""

    def __init__(self, master):
        super().__init__(master, bg=T.BG)
        top = tk.Frame(self, bg=T.BG)
        top.pack(fill="x")
        T.label(top, self.title, "h2").pack(side="left")
        self.score_lbl = T.label(top, "", "bold", T.ACCENT_HI)
        self.score_lbl.pack(side="right")
        T.label(self, self.help, "small", T.MUTED).pack(anchor="w")
        self.canvas = tk.Canvas(self, bg="#0b1220", highlightthickness=0, takefocus=1)
        self.canvas.pack(fill="both", expand=True, pady=(T.px(0.4), 0))
        self.canvas.bind("<Configure>", lambda e: self.draw())
        self.canvas.bind("<Button-1>", lambda e: self.canvas.focus_set(), add="+")
        self.canvas.bind("<KeyPress>", self.on_key)
        self.after(50, self.canvas.focus_set)
        self.best = 0

    def on_key(self, e):
        return "break"

    def draw(self):
        pass

    def set_score(self, score):
        self.best = max(self.best, score)
        self.score_lbl.configure(text=f"Score {score}   Best {self.best}")

    def message(self, text):
        c = self.canvas
        w, h = c.winfo_width(), c.winfo_height()
        t = c.create_text(w / 2, h / 2, text=text, fill="white", font=T.FONTS["h2"], justify="center")
        x0, y0, x1, y1 = c.bbox(t)
        p = T.px(0.8)
        r = c.create_rectangle(x0 - p, y0 - p, x1 + p, y1 + p, fill=T.PANEL, outline=T.ACCENT)
        c.tag_raise(t, r)


class Snake(Game):
    title = "Snake"
    help = "Arrow keys or WASD to steer · Space to start / pause"
    COLS, ROWS = 28, 18

    def __init__(self, master):
        super().__init__(master)
        self.job = None
        self.reset()

    def reset(self):
        cx, cy = self.COLS // 2, self.ROWS // 2
        self.body = [(cx - i, cy) for i in range(4)]
        self.dir = self.next_dir = (1, 0)
        self.state = "ready"
        self.score = 0
        self.place_food()
        self.set_score(0)
        self.draw()

    def place_food(self):
        free = [(x, y) for x in range(self.COLS) for y in range(self.ROWS) if (x, y) not in self.body]
        self.food = random.choice(free)

    def on_key(self, e):
        key = e.keysym if e.keysym in ARROWS else e.keysym.lower()
        if key in ARROWS:
            d = ARROWS[key]
            if (d[0] + self.dir[0], d[1] + self.dir[1]) != (0, 0):
                self.next_dir = d
            if self.state == "ready":
                self.start()
        elif e.keysym == "space":
            if self.state in ("ready", "over"):
                if self.state == "over":
                    self.reset()
                self.start()
            elif self.state == "running":
                self.state = "paused"
                self.draw()
            elif self.state == "paused":
                self.start()
        return "break"

    def start(self):
        if self.state != "paused":
            sfx("start")
        self.state = "running"
        if self.job is None:
            self.tick()

    def tick(self):
        self.job = None
        if self.state != "running":
            return
        self.dir = self.next_dir
        hx, hy = self.body[0]
        head = (hx + self.dir[0], hy + self.dir[1])
        if not (0 <= head[0] < self.COLS and 0 <= head[1] < self.ROWS) or head in self.body[:-1]:
            self.state = "over"
            sfx("lose")
            self.draw()
            return
        self.body.insert(0, head)
        if head == self.food:
            sfx("coin")
            self.score += 1
            self.set_score(self.score)
            self.place_food()
        else:
            self.body.pop()
        self.draw()
        self.job = self.after(max(60, 150 - self.score * 3), self.tick)

    def draw(self):
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        cell = max(4, min(w // self.COLS, h // self.ROWS))
        ox, oy = (w - cell * self.COLS) / 2, (h - cell * self.ROWS) / 2
        c.create_rectangle(ox, oy, ox + cell * self.COLS, oy + cell * self.ROWS, outline=T.PANEL_HI, width=2)
        fx, fy = self.food
        c.create_oval(ox + fx * cell + 2, oy + fy * cell + 2, ox + (fx + 1) * cell - 2, oy + (fy + 1) * cell - 2,
                      fill=T.BAD, outline="")
        for i, (x, y) in enumerate(self.body):
            c.create_rectangle(ox + x * cell + 1, oy + y * cell + 1, ox + (x + 1) * cell - 1, oy + (y + 1) * cell - 1,
                               fill=T.GOOD if i else "#86efac", outline="")
        if self.state == "ready":
            self.message("Press an arrow key or Space to start")
        elif self.state == "paused":
            self.message("Paused – Space to continue")
        elif self.state == "over":
            self.message(f"Game over – score {self.score}\nSpace to play again")

    def destroy(self):
        if self.job:
            self.after_cancel(self.job)
        super().destroy()


TILE_COLORS = {0: "#1e293b", 2: "#e2e8f0", 4: "#cbd5e1", 8: "#fdba74", 16: "#fb923c", 32: "#f97316",
               64: "#ea580c", 128: "#fde047", 256: "#facc15", 512: "#eab308", 1024: "#a3e635", 2048: "#22c55e"}


def slide_row(row: list[int]) -> tuple[list[int], int]:
    """Slide one 2048 row to the left, merging equal neighbours once. Returns (row, points)."""
    tiles = [v for v in row if v]
    out, points, i = [], 0, 0
    while i < len(tiles):
        if i + 1 < len(tiles) and tiles[i] == tiles[i + 1]:
            out.append(tiles[i] * 2)
            points += tiles[i] * 2
            i += 2
        else:
            out.append(tiles[i])
            i += 1
    return out + [0] * (len(row) - len(out)), points


class Game2048(Game):
    title = "2048"
    help = "Arrow keys or WASD to slide the tiles · equal tiles merge · N for a new game"
    N = 4

    def __init__(self, master):
        super().__init__(master)
        self.reset()

    def reset(self):
        self.grid = [[0] * self.N for _ in range(self.N)]
        self.score = 0
        self.won = False
        self.spawn()
        self.spawn()
        self.set_score(0)
        self.draw()

    def spawn(self):
        empty = [(r, c) for r in range(self.N) for c in range(self.N) if not self.grid[r][c]]
        if empty:
            r, c = random.choice(empty)
            self.grid[r][c] = 4 if random.random() < 0.1 else 2

    def move(self, dx, dy):
        g = self.grid
        n = self.N
        # Turn every move into "slide left" on transformed rows.
        if dx == -1:
            rows = [g[r][:] for r in range(n)]
        elif dx == 1:
            rows = [g[r][::-1] for r in range(n)]
        elif dy == -1:
            rows = [[g[r][c] for r in range(n)] for c in range(n)]
        else:
            rows = [[g[r][c] for r in range(n - 1, -1, -1)] for c in range(n)]
        moved, gained = [], 0
        for row in rows:
            new, pts = slide_row(row)
            moved.append(new)
            gained += pts
        new = [[0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                v = moved[i][j]
                if dx == -1:
                    new[i][j] = v
                elif dx == 1:
                    new[i][n - 1 - j] = v
                elif dy == -1:
                    new[j][i] = v
                else:
                    new[n - 1 - j][i] = v
        if new != g:
            had_2048 = any(2048 in row for row in g)
            self.grid = new
            self.score += gained
            self.set_score(self.score)
            self.spawn()
            if not had_2048 and any(2048 in row for row in new):
                sfx("win")
            elif not self.can_move():
                sfx("lose")
            elif gained:
                sfx("merge")
            else:
                sfx("tick")
        self.draw()

    def can_move(self):
        g = self.grid
        for r in range(self.N):
            for c in range(self.N):
                if not g[r][c]:
                    return True
                if c + 1 < self.N and g[r][c] == g[r][c + 1]:
                    return True
                if r + 1 < self.N and g[r][c] == g[r + 1][c]:
                    return True
        return False

    def on_key(self, e):
        key = e.keysym if e.keysym in ARROWS else e.keysym.lower()
        if key in ARROWS and self.can_move():
            self.move(*ARROWS[key])
        elif key == "n":
            self.reset()
        return "break"

    def draw(self):
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        size = min(w, h) * 0.95
        cell = size / self.N
        ox, oy = (w - size) / 2, (h - size) / 2
        for r in range(self.N):
            for col in range(self.N):
                v = self.grid[r][col]
                x, y = ox + col * cell, oy + r * cell
                c.create_rectangle(x + 4, y + 4, x + cell - 4, y + cell - 4, fill=TILE_COLORS.get(v, "#16a34a"),
                                   outline="")
                if v:
                    fs = -int(cell * (0.4 if v < 100 else 0.32 if v < 1000 else 0.25))
                    c.create_text(x + cell / 2, y + cell / 2, text=str(v), fill="#0f172a" if v < 8 else "white",
                                  font=(T.FONTS["bold"].actual("family"), fs, "bold"))
        if any(2048 in row for row in self.grid) and not self.won:
            self.won = True
            self.message("You made 2048! Keep going…")
        elif not self.can_move():
            self.message(f"No more moves – score {self.score}\nPress N for a new game")


def neighbours(r: int, c: int, rows: int, cols: int):
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if (dr or dc) and 0 <= r + dr < rows and 0 <= c + dc < cols:
                yield r + dr, c + dc


class Minesweeper(Game):
    title = "Minesweeper"
    help = "Left-click to uncover · right-click to flag a mine · N for a new game"
    ROWS, COLS, MINES = 12, 18, 32
    NUM_COLORS = ["", "#60a5fa", "#4ade80", "#f87171", "#c084fc", "#fbbf24", "#22d3ee", "#f1f5f9", "#94a3b8"]

    def __init__(self, master):
        super().__init__(master)
        self.canvas.bind("<Button-1>", self.on_left, add="+")
        self.canvas.bind("<Button-3>", self.on_right)
        self.reset()

    def reset(self):
        self.mines: set[tuple[int, int]] = set()
        self.open: set[tuple[int, int]] = set()
        self.flags: set[tuple[int, int]] = set()
        self.state = "ready"
        self.set_score(0)
        self.draw()

    def lay_mines(self, safe):
        cells = [(r, c) for r in range(self.ROWS) for c in range(self.COLS)
                 if (r, c) != safe and (r, c) not in set(neighbours(*safe, self.ROWS, self.COLS))]
        self.mines = set(random.sample(cells, self.MINES))

    def count(self, r, c):
        return sum((n in self.mines) for n in neighbours(r, c, self.ROWS, self.COLS))

    def cell_at(self, e):
        col = int((e.x - self.ox) // self.cell)
        row = int((e.y - self.oy) // self.cell)
        if 0 <= row < self.ROWS and 0 <= col < self.COLS:
            return row, col
        return None

    def on_left(self, e):
        if self.state in ("won", "lost"):
            self.reset()
            return
        cell = self.cell_at(e)
        if not cell or cell in self.flags or cell in self.open:
            return
        if self.state == "ready":
            self.lay_mines(cell)
            self.state = "playing"
        if cell in self.mines:
            self.state = "lost"
            sfx("explode")
        else:
            self.flood(cell)
            if len(self.open) == self.ROWS * self.COLS - self.MINES:
                self.state = "won"
                sfx("win")
            else:
                sfx("tick")
        self.set_score(len(self.open))
        self.draw()

    def flood(self, start):
        stack = [start]
        while stack:
            cell = stack.pop()
            if cell in self.open or cell in self.flags:
                continue
            self.open.add(cell)
            if self.count(*cell) == 0:
                stack.extend(n for n in neighbours(*cell, self.ROWS, self.COLS) if n not in self.open)

    def on_right(self, e):
        cell = self.cell_at(e)
        if self.state == "playing" and cell and cell not in self.open:
            self.flags ^= {cell}
            sfx("flag")
            self.draw()

    def on_key(self, e):
        if e.keysym.lower() == "n":
            self.reset()
        return "break"

    def draw(self):
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        self.cell = cell = max(6, min(w / self.COLS, h / self.ROWS))
        self.ox, self.oy = (w - cell * self.COLS) / 2, (h - cell * self.ROWS) / 2
        font = (T.FONTS["bold"].actual("family"), -int(cell * 0.55), "bold")
        for r in range(self.ROWS):
            for col in range(self.COLS):
                x, y = self.ox + col * cell, self.oy + r * cell
                cell_rc = (r, col)
                shown = cell_rc in self.open or (self.state == "lost" and cell_rc in self.mines)
                fill = "#0f172a" if shown else T.PANEL_HI
                if self.state == "lost" and cell_rc in self.mines:
                    fill = "#7f1d1d"
                c.create_rectangle(x + 1, y + 1, x + cell - 1, y + cell - 1, fill=fill, outline="")
                if shown and cell_rc in self.mines:
                    c.create_oval(x + cell * 0.25, y + cell * 0.25, x + cell * 0.75, y + cell * 0.75, fill="black")
                elif shown:
                    n = self.count(r, col)
                    if n:
                        c.create_text(x + cell / 2, y + cell / 2, text=str(n), fill=self.NUM_COLORS[n], font=font)
                elif cell_rc in self.flags:
                    c.create_text(x + cell / 2, y + cell / 2, text="⚑", fill=T.WARN, font=font)
        left = self.MINES - len(self.flags)
        self.score_lbl.configure(text=f"Mines left {left}")
        if self.state == "won":
            self.message("You cleared the field!\nClick for a new game")
        elif self.state == "lost":
            self.message("Boom! Click for a new game")


GAMES = [("Snake", Snake), ("2048", Game2048), ("Minesweeper", Minesweeper)]
