"""The arcade: a grid of game cards shared by the test-progress screen and the welcome screen."""

from __future__ import annotations

import tkinter as tk

from . import theme as T
from .games import Game2048, Minesweeper, Snake
from .games3d import MazeRunner, StarPilot, TurboRoad

# (class, icon, colour, blurb)
ARCADE = [
    (MazeRunner, "◰", "#6366f1", "First-person 3D maze. Find the exit, grab the chips."),
    (TurboRoad, "➤", "#f97316", "Retro 3D racer. Overtake the traffic, beat your lap."),
    (StarPilot, "✦", "#22d3ee", "3D space flight. Dodge asteroids, catch crystals."),
    (Snake, "∿", "#22c55e", "The classic. Eat, grow, don't bite yourself."),
    (Game2048, "▣", "#eab308", "Slide and merge the tiles to reach 2048."),
    (Minesweeper, "✹", "#ef4444", "Clear the field without hitting a mine."),
]


class GamePicker(tk.Frame):
    def __init__(self, parent, on_pick, columns: int = 3):
        super().__init__(parent, bg=parent["bg"])
        for i, (cls, icon, color, blurb) in enumerate(ARCADE):
            card = T.Card(self, command=lambda c=cls: on_pick(c))
            card.grid(row=i // columns, column=i % columns, sticky="nsew", padx=T.px(0.3), pady=T.px(0.3))
            head = tk.Frame(card.body, bg=T.PANEL)
            head.pack(fill="x")
            tk.Label(head, text=icon, font=T.FONTS["icon"], fg=color, bg=T.PANEL).pack(side="left")
            T.label(head, cls.title, "bold", bg=T.PANEL).pack(side="left", padx=(T.px(0.5), 0))
            T.label(card.body, blurb, "small", T.MUTED, bg=T.PANEL, wrap=T.px(14)).pack(anchor="w")
        for c in range(columns):
            self.columnconfigure(c, weight=1, uniform="games")
