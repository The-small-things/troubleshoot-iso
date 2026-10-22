"""Game and app cards: Chip's built-in games plus the open-source apps installed on the ISO."""

from __future__ import annotations

import tkinter as tk

from .. import apps
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
CATEGORY_COLORS = {"games": "#a855f7", "internet": "#3b82f6", "creative": "#ec4899", "tools": "#14b8a6"}

_icon_cache: dict[str, tk.PhotoImage] = {}


def app_icon(master, app: apps.App, size: int) -> tk.PhotoImage | None:
    path = apps.icon_path(app)
    if not path:
        return None
    key = f"{path}@{size}"
    if key not in _icon_cache:
        try:
            img = tk.PhotoImage(master=master, file=path)
        except tk.TclError:
            return None
        factor = max(1, round(img.height() / size))
        _icon_cache[key] = img.subsample(factor) if factor > 1 else img
    return _icon_cache[key]


def card(parent, title, blurb, command, icon_text="", color=T.ACCENT, image=None, wrap=None):
    c = T.Card(parent, command=command)
    head = tk.Frame(c.body, bg=T.PANEL)
    head.pack(fill="x")
    if image is not None:
        tk.Label(head, image=image, bg=T.PANEL).pack(side="left")
    else:
        badge = tk.Canvas(head, width=T.px(2.2), height=T.px(2.2), bg=T.PANEL, highlightthickness=0)
        T.rounded(badge, 0, 0, T.px(2.2), T.px(2.2), T.px(0.6), fill=color, outline="")
        badge.create_text(T.px(1.1), T.px(1.1), text=icon_text, fill="white", font=T.FONTS["bold"])
        badge.pack(side="left")
    T.label(head, title, "bold", bg=T.PANEL).pack(side="left", padx=(T.px(0.5), 0))
    T.label(c.body, blurb, "small", T.MUTED, bg=T.PANEL, wrap=wrap or T.px(14)).pack(anchor="w")
    return c


def grid(parent, cards_spec, columns):
    frame = tk.Frame(parent, bg=parent["bg"])
    for i, spec in enumerate(cards_spec):
        card(frame, **spec).grid(row=i // columns, column=i % columns, sticky="nsew", padx=T.px(0.3),
                                 pady=T.px(0.3))
    for c in range(columns):
        frame.columnconfigure(c, weight=1, uniform="cards")
    return frame


def builtin_specs(on_pick):
    return [dict(title=cls.title, blurb=blurb, command=lambda c=cls: on_pick(c), icon_text=icon, color=color)
            for cls, icon, color, blurb in ARCADE]


def app_specs(master, category, on_launch, size):
    out = []
    for a in apps.installed(category):
        out.append(dict(title=a.name, blurb=a.blurb, command=lambda a=a: on_launch(a),
                        icon_text=a.name[:1], color=CATEGORY_COLORS[a.category], image=app_icon(master, a, size)))
    return out


class GamePicker(tk.Frame):
    """Chip's games, plus the installed open-source games (which open in their own window)."""

    def __init__(self, parent, on_pick, on_launch=None, columns: int = 3):
        super().__init__(parent, bg=parent["bg"])
        grid(self, builtin_specs(on_pick), columns).pack(fill="x")
        if on_launch is not None:
            specs = app_specs(self, "games", on_launch, T.px(2.2))
            if specs:
                T.label(self, "Open-source games (open in their own window – close it to come back):",
                        "small", T.MUTED).pack(anchor="w", pady=(T.px(0.6), T.px(0.2)))
                grid(self, specs, columns).pack(fill="x")
