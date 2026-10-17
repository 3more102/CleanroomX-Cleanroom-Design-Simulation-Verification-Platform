"""Presentation-only helpers for CleanroomX's Tk 3D spatial viewer.

The color key denotes geometric zones; it is not ISO classification, a
calculated pressure field, or a CFD result. No layout data is modified here.
"""
from __future__ import annotations

import math
from typing import Callable

ZONE_COLORS = (
    "#22b8a4",  # teal
    "#4d8cff",  # blue
    "#f97373",  # coral
    "#e5b65b",  # amber
    "#a68aff",  # violet
    "#45bd78",  # green
    "#db79ae",  # magenta
    "#6bc9e9",  # cyan
)

Point3D = Callable[[float, float, float], tuple[float, float]]


def axis_ticks(low: float, high: float, *, limit: int = 11) -> tuple[float, ...]:
    """Return finite, uniformly spaced, human-readable metric axis ticks."""
    if not (math.isfinite(low) and math.isfinite(high)) or high < low:
        raise ValueError("axis bounds must be finite and ordered")
    if limit < 2:
        raise ValueError("tick limit must be at least two")
    span = high - low
    if span < 1e-9:
        return (low,)
    desired_step = span / (limit - 1)
    exponent = math.floor(math.log10(desired_step))
    decade = 10 ** exponent
    step = next(
        (multiple * decade for multiple in (1.0, 2.0, 5.0, 10.0)
         if multiple * decade >= desired_step * (1.0 - 1e-12)),
        10.0 * decade,
    )
    first = math.ceil((low - step * 1e-9) / step)
    last = math.floor((high + step * 1e-9) / step)
    return tuple(round(index * step, 10) for index in range(first, last + 1))


def room_zone_colors(rooms: list[dict]) -> dict[str, str]:
    """Assign stable legend colors by sorted room ID, not unverified attributes."""
    ids = sorted({str(room["id"]) for room in rooms})
    return {room_id: ZONE_COLORS[index % len(ZONE_COLORS)]
            for index, room_id in enumerate(ids)}


def draw_3d_reference(
    canvas: object,
    project: Point3D,
    *,
    bounds: tuple[float, float, float, float],
    bottom_z: float,
    top_z: float,
    show_grid: bool,
) -> None:
    """Draw a calibrated X/Y/Z cage and ground grid behind the room geometry.

    Bounds and height are the real metric room extent plus viewport padding.
    The caller handles centering before passing the projection callback.
    """
    x0, y0, x1, y1 = bounds
    if not all(math.isfinite(n) for n in (*bounds, bottom_z, top_z)):
        raise ValueError("3D reference bounds must be finite")
    if x1 <= x0 or y1 <= y0 or top_z <= bottom_z:
        raise ValueError("3D reference extents must be positive")

    floor_color, cage_color, axis_color = "#344458", "#49607b", "#8fb2dd"
    draw_line = canvas.create_line
    draw_text = canvas.create_text

    if show_grid:
        for x in axis_ticks(x0, x1):
            draw_line(*project(x, y0, bottom_z), *project(x, y1, bottom_z),
                      fill=floor_color, width=1, tags=("grid3d",))
        for y in axis_ticks(y0, y1):
            draw_line(*project(x0, y, bottom_z), *project(x1, y, bottom_z),
                      fill=floor_color, width=1, tags=("grid3d",))

    # The cage retains the original metric proportions when the camera orbits.
    corners = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    for i, (x, y) in enumerate(corners):
        nx, ny = corners[(i + 1) % 4]
        draw_line(*project(x, y, top_z), *project(nx, ny, top_z),
                  fill=cage_color, width=1, dash=(3, 5), tags=("axis3d",))
        draw_line(*project(x, y, bottom_z), *project(x, y, top_z),
                  fill=cage_color, width=1, dash=(3, 5), tags=("axis3d",))

    # X/Y rulers use world-space lengths (not pixel-based tick assumptions).
    draw_line(*project(x0, y0, bottom_z), *project(x1, y0, bottom_z),
              fill=axis_color, width=2, tags=("axis3d",))
    draw_line(*project(x0, y0, bottom_z), *project(x0, y1, bottom_z),
              fill=axis_color, width=2, tags=("axis3d",))
    draw_line(*project(x0, y0, bottom_z), *project(x0, y0, top_z),
              fill=axis_color, width=2, tags=("axis3d",))

    if show_grid:
        for x in axis_ticks(x0, x1, limit=7):
            px, py = project(x, y0, bottom_z)
            draw_text(px, py + 11, text=f"{x:g}", fill=axis_color,
                      font=("TkDefaultFont", 8), tags=("axis3d",))
        for y in axis_ticks(y0, y1, limit=7):
            px, py = project(x0, y, bottom_z)
            draw_text(px - 10, py, text=f"{y:g}", anchor="e",
                      fill=axis_color, font=("TkDefaultFont", 8),
                      tags=("axis3d",))
        for z in axis_ticks(bottom_z, top_z, limit=6):
            px, py = project(x0, y0, z)
            draw_text(px - 11, py, text=f"{z:g}", anchor="e",
                      fill=axis_color, font=("TkDefaultFont", 8),
                      tags=("axis3d",))

    # Fixed screen-space axis captions do not collide with room roofs as
    # the user orbits. The numeric rulers above remain world-space metres.
    width_px = max(1, int(getattr(canvas, "winfo_width", lambda: 680)()))
    height_px = max(1, int(canvas.winfo_height()))
    if width_px >= 280 and height_px >= 170:
        x_label = width_px - 12
        for dy, title in ((66, "Length X (m)"), (44, "Width Y (m)"),
                          (22, "Height Z (m)")):
            draw_text(
                x_label, height_px - dy, text=title, anchor="ne",
                fill="#b8d1ef", font=("TkDefaultFont", 9, "bold"),
                tags=("axis3d", "axis_caption_3d"),
            )


def draw_3d_zone_legend(
    canvas: object,
    rooms: list[dict],
    colors: dict[str, str],
) -> None:
    """Draw a distinct design-zone legend, explicitly separate from CFD overlays."""
    visible = sorted(rooms, key=lambda room: (str(room["name"]), str(room["id"])))
    shown = visible[:7]
    total = len(visible)
    if not shown:
        return
    canvas_height = max(1, int(canvas.winfo_height()))
    box_height = 46 + len(shown) * 19 + (19 if total > 7 else 0)
    x, y, box_width = 12, max(10, canvas_height - box_height - 12), 250
    tag = ("zone_legend_3d",)
    canvas.create_rectangle(x, y, x + box_width, y + box_height,
                            fill="#101d30", outline="#416080", width=1, tags=tag)
    canvas.create_text(x + 10, y + 9, text="DESIGN ZONES", anchor="nw",
                       fill="#e6efff", font=("TkDefaultFont", 10, "bold"), tags=tag)
    for index, room in enumerate(shown):
        baseline = y + 30 + index * 19
        canvas.create_rectangle(x + 10, baseline, x + 24, baseline + 12,
                                fill=colors[room["id"]], outline="", tags=tag)
        label = str(room["name"])
        if len(label) > 29:
            label = label[:26] + "..."
        canvas.create_text(x + 32, baseline + 6, text=label, anchor="w",
                           fill="#cedcf0", font=("TkDefaultFont", 9), tags=tag)
    if total > 7:
        canvas.create_text(x + 32, y + 30 + 7 * 19 + 6,
                           text=f"+ {total - 7} more zones",
                           anchor="w", fill="#9aafcc", tags=tag)
    canvas.create_text(x + 10, y + box_height - 7, anchor="sw",
                       text="Colors identify rooms — not CFD or ISO verification",
                       fill="#91a9c6", font=("TkDefaultFont", 7), tags=tag)
    canvas.tag_raise("zone_legend_3d")
