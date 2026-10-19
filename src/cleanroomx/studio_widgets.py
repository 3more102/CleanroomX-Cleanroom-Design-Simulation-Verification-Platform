"""Native vector details shared by the desktop Studio presentation."""

from __future__ import annotations

import math
from tkinter import font as tkfont


def blend(color: str, background: str, amount: float) -> str:
    return "#" + "".join(
        f"{round(int(color[i:i + 2], 16) * amount + int(background[i:i + 2], 16) * (1 - amount)):02x}"
        for i in (1, 3, 5)
    )


def rounded_rect(canvas, bounds, radius=10, **options):
    x0, y0, x1, y1 = bounds
    r = min(radius, (x1 - x0) / 2, (y1 - y0) / 2)
    return canvas.create_polygon(
        x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r,
        x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
        x0, y1, x0, y1 - r, x0, y0 + r, x0, y0,
        smooth=True, splinesteps=16, **options,
    )


def fit_text(canvas, value, width, font):
    value = str(value)
    measure = tkfont.Font(root=canvas, font=font).measure
    if measure(value) <= width:
        return value
    while value and measure(value + "…") > width:
        value = value[:-1]
    return value + "…"


def draw_icon(canvas, kind, x, y, size, color, tags=()):
    """Draw small geometric icons without font or bitmap dependencies."""
    s = size / 2
    line = lambda *points, **kw: canvas.create_line(
        *points, fill=color, width=1.5, tags=tags, **kw
    )
    if kind == "rooms":
        for dx in (-s, 1):
            for dy in (-s, 1):
                canvas.create_rectangle(x + dx, y + dy, x + dx + s - 2, y + dy + s - 2,
                                        fill="", outline=color, width=1.5, tags=tags)
    elif kind in {"area", "volume"}:
        line(x - s, y - s / 3, x, y - s, x + s, y - s / 3,
             x, y + s / 3, x - s, y - s / 3)
        if kind == "volume":
            line(x - s, y - s / 3, x - s, y + s / 2, x, y + s,
                 x + s, y + s / 2, x + s, y - s / 3)
            line(x, y + s / 3, x, y + s)
        else:
            line(x - s, y + s / 2, x, y + s, x + s, y + s / 2)
    elif kind in {"supply", "return_exhaust"}:
        direction = 1 if kind == "supply" else -1
        line(x, y - direction * s, x, y + direction * s / 2, arrow="last")
        line(x - s, y + direction * s, x + s, y + direction * s)
    elif kind == "ffu":
        canvas.create_oval(x - s, y - s, x + s, y + s, outline=color, tags=tags)
        for angle in (0, 120, 240):
            a = math.radians(angle)
            line(x, y, x + .7 * s * math.cos(a), y + .7 * s * math.sin(a))
    else:
        canvas.create_rectangle(x - s * .55, y - s * .55, x + s * .55, y + s * .55,
                                outline=color, width=1.5, tags=tags)
        for direction in (-1, 1):
            line(x + direction * s * .55, y, x + direction * s, y)
            line(x, y + direction * s * .55, x, y + direction * s)


def draw_metrics(workspace):
    canvas, p = workspace._studio_metrics_canvas, workspace._theme_palette
    canvas.delete("all")
    canvas.configure(background=p["background"])
    width = max(320, canvas.winfo_width())
    gap, margin = 10, 8
    card_width = (width - margin * 2 - gap * 3) / 4
    for index, (key, title, color) in enumerate((
        ("rooms", "ROOMS", p["accent"]),
        ("area", "FLOOR AREA · m²", "#85adff"),
        ("volume", "GEOMETRIC VOLUME · m³", "#b6a1f2"),
        ("devices", "PLACED DEVICES", "#efc381"),
    )):
        x = margin + index * (card_width + gap)
        tags = (f"studio-metric:{key}",)
        rounded_rect(canvas, (x + 1, 8, x + card_width + 1, 83),
                     fill=blend(p["canvas_3d"], p["background"], .5), outline="", tags=tags)
        rounded_rect(canvas, (x, 5, x + card_width, 80),
                     fill=p["panel"], outline=p["border"], tags=tags)
        value = workspace._studio_card_vars[key].get()
        value_font = ("TkDefaultFont", 21 if len(value) < 9 else 15, "bold")
        canvas.create_text(x + 16, 33, text=value, anchor="w", fill=p["text"],
                           font=value_font, tags=tags + (f"studio-metric-value:{key}",))
        canvas.create_text(x + 16, 62, text=title, anchor="w", fill=p["muted"],
                           font=("TkDefaultFont", 7, "bold"), tags=tags)
        if card_width >= 210:
            cx, cy = x + card_width - 33, 35
            rounded_rect(canvas, (cx - 18, cy - 18, cx + 18, cy + 18), radius=10,
                         fill=blend(color, p["panel"], .12), outline="", tags=tags)
            draw_icon(canvas, key, cx, cy, 18, color, tags)
