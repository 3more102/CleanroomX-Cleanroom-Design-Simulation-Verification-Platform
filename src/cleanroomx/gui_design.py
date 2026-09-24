from __future__ import annotations

from collections.abc import Mapping
from typing import Any


BG = "#0b1220"
PANEL = "#111827"
PANEL_ALT = "#172033"
GRID = "#263247"
TEXT = "#e5edf7"
MUTED = "#94a3b8"
ACCENT = "#38bdf8"
ACCENT_2 = "#22c55e"
WARN = "#f59e0b"
ROOM_FILLS = ("#164e63", "#1e3a5f", "#274060", "#314158", "#3b3f57")


def extract_design_rooms(payload: Any) -> list[dict[str, Any]]:
    """Return room-like dictionaries that contain usable plan dimensions."""
    if not isinstance(payload, Mapping):
        return []

    def normalize(items: Any) -> list[dict[str, Any]]:
        if not isinstance(items, list):
            return []
        rooms: list[dict[str, Any]] = []
        for index, item in enumerate(items):
            if not isinstance(item, Mapping):
                continue
            length = _positive_number(item.get("length_m"))
            width = _positive_number(item.get("width_m"))
            if length is None or width is None:
                continue
            room = dict(item)
            room.setdefault("name", f"Room {index + 1}")
            room["length_m"] = length
            room["width_m"] = width
            height = _positive_number(item.get("height_m"))
            if height is not None:
                room["height_m"] = height
            rooms.append(room)
        return rooms

    direct = normalize(payload.get("rooms"))
    if direct:
        return direct

    for value in payload.values():
        if isinstance(value, Mapping):
            nested = extract_design_rooms(value)
            if nested:
                return nested
    return []


def design_summary(payload: Any) -> str:
    rooms = extract_design_rooms(payload)
    if not rooms:
        return "No dimensional room geometry in the selected analysis"
    area = sum(room["length_m"] * room["width_m"] for room in rooms)
    airflow = sum(
        _number(room.get("supply_airflow_m3_h"))
        or _number(room.get("cleanroom_airflow_m3_h"))
        or 0.0
        for room in rooms
    )
    heights = [room.get("height_m") for room in rooms if room.get("height_m")]
    volume = sum(
        room["length_m"] * room["width_m"] * float(room.get("height_m", 0.0))
        for room in rooms
        if room.get("height_m")
    )
    pieces = [f"{len(rooms)} rooms", f"{area:.1f} m²"]
    if heights:
        pieces.append(f"{volume:.1f} m³")
    if airflow > 0:
        pieces.append(f"{airflow:,.0f} m³/h supply")
    return "  •  ".join(pieces)


def draw_plan_2d(canvas: Any, payload: Any) -> None:
    canvas.delete("all")
    width = max(int(canvas.winfo_width()), 620)
    height = max(int(canvas.winfo_height()), 420)
    canvas.configure(background=BG)

    _draw_grid(canvas, width, height, spacing=32)
    rooms = extract_design_rooms(payload)
    if not rooms:
        _empty_state(
            canvas,
            width,
            height,
            "2D PLAN",
            "Add room length_m and width_m fields to render a scaled cleanroom plan.",
        )
        return

    margin_x, margin_y = 56, 82
    usable_w = max(width - margin_x * 2, 100)
    usable_h = max(height - margin_y * 2, 100)
    gap_m = 0.8
    total_length = sum(room["length_m"] for room in rooms) + gap_m * max(len(rooms) - 1, 0)
    max_width = max(room["width_m"] for room in rooms)
    scale = min(usable_w / max(total_length, 1.0), usable_h / max(max_width, 1.0))
    scale = max(min(scale, 90.0), 16.0)

    canvas.create_text(
        margin_x,
        30,
        anchor="w",
        text="FACILITY PLAN · LIVE FROM ANALYSIS INPUT",
        fill=MUTED,
        font=("Segoe UI", 10, "bold"),
    )
    canvas.create_text(
        margin_x,
        52,
        anchor="w",
        text=design_summary(payload),
        fill=TEXT,
        font=("Segoe UI", 11),
    )

    x = margin_x
    y_center = margin_y + usable_h / 2
    centers: dict[str, tuple[float, float]] = {}
    for index, room in enumerate(rooms):
        rw = room["length_m"] * scale
        rh = room["width_m"] * scale
        y1 = y_center - rh / 2
        y2 = y_center + rh / 2
        x1, x2 = x, x + rw

        fill = ROOM_FILLS[index % len(ROOM_FILLS)]
        canvas.create_rectangle(x1, y1, x2, y2, fill=fill, outline=ACCENT, width=2)
        canvas.create_rectangle(
            x1 + 5, y1 + 5, x2 - 5, y2 - 5, outline="#2b6f87", width=1
        )

        name = str(room.get("name", f"Room {index + 1}"))
        centers[name] = ((x1 + x2) / 2, (y1 + y2) / 2)
        canvas.create_text(
            (x1 + x2) / 2,
            (y1 + y2) / 2 - 15,
            text=name,
            fill=TEXT,
            font=("Segoe UI", 11, "bold"),
            width=max(int(rw - 16), 80),
        )
        canvas.create_text(
            (x1 + x2) / 2,
            (y1 + y2) / 2 + 8,
            text=f'{room["length_m"]:g} × {room["width_m"]:g} m',
            fill=MUTED,
            font=("Segoe UI", 9),
        )
        pressure = _number(room.get("observed_pressure_pa"))
        airflow = _number(room.get("supply_airflow_m3_h"))
        if airflow is None:
            airflow = _number(room.get("cleanroom_airflow_m3_h"))
        details = []
        if pressure is not None:
            details.append(f"{pressure:g} Pa")
        if airflow is not None:
            details.append(f"{airflow:,.0f} m³/h")
        if details:
            canvas.create_text(
                (x1 + x2) / 2,
                y2 + 18,
                text="  |  ".join(details),
                fill=MUTED,
                font=("Segoe UI", 8),
            )
        x = x2 + gap_m * scale

    cascades = payload.get("pressure_cascade", []) if isinstance(payload, Mapping) else []
    if isinstance(cascades, list):
        for relation in cascades:
            if not isinstance(relation, Mapping):
                continue
            high = centers.get(str(relation.get("higher_pressure_room", "")))
            low = centers.get(str(relation.get("lower_pressure_room", "")))
            if high is None or low is None:
                continue
            x1, y1 = high
            x2, y2 = low
            canvas.create_line(
                x1,
                y1 - 34,
                x2,
                y2 - 34,
                fill=ACCENT_2,
                width=2,
                arrow="last",
                arrowshape=(10, 12, 5),
            )
            delta = _number(relation.get("min_delta_pa"))
            if delta is not None:
                canvas.create_text(
                    (x1 + x2) / 2,
                    (y1 + y2) / 2 - 47,
                    text=f"ΔP ≥ {delta:g} Pa",
                    fill=ACCENT_2,
                    font=("Segoe UI", 8, "bold"),
                )

    canvas.create_text(
        width - 24,
        height - 22,
        anchor="e",
        text="Scaled engineering preview · not construction CAD",
        fill=MUTED,
        font=("Segoe UI", 8),
    )


def draw_preview_3d(canvas: Any, payload: Any) -> None:
    canvas.delete("all")
    width = max(int(canvas.winfo_width()), 620)
    height = max(int(canvas.winfo_height()), 420)
    canvas.configure(background=BG)

    rooms = extract_design_rooms(payload)
    if not rooms:
        _empty_state(
            canvas,
            width,
            height,
            "3D PREVIEW",
            "Dimensional rooms will appear here as an isometric engineering preview.",
        )
        return

    canvas.create_text(
        56,
        30,
        anchor="w",
        text="ISOMETRIC CLEANROOM PREVIEW",
        fill=MUTED,
        font=("Segoe UI", 10, "bold"),
    )
    canvas.create_text(
        56,
        52,
        anchor="w",
        text=design_summary(payload),
        fill=TEXT,
        font=("Segoe UI", 11),
    )

    total_length = sum(room["length_m"] for room in rooms)
    max_width = max(room["width_m"] for room in rooms)
    max_height = max(float(room.get("height_m", 3.0)) for room in rooms)
    base_scale = min(
        (width - 150) / max(total_length * 1.12 + max_width * 0.55, 1.0),
        (height - 180) / max(max_width * 0.65 + max_height * 0.95, 1.0),
    )
    scale = max(min(base_scale, 66.0), 12.0)
    origin_x = 74
    origin_y = height * 0.67

    cursor = 0.0
    for index, room in enumerate(rooms):
        length = room["length_m"] * scale
        depth = room["width_m"] * scale * 0.55
        rise = float(room.get("height_m", 3.0)) * scale * 0.72

        x = origin_x + cursor * scale
        y = origin_y
        dx = depth * 0.62
        dy = depth * 0.36

        a = (x, y)
        b = (x + length, y)
        c = (x + length + dx, y - dy)
        d = (x + dx, y - dy)
        at = (a[0], a[1] - rise)
        bt = (b[0], b[1] - rise)
        ct = (c[0], c[1] - rise)
        dt = (d[0], d[1] - rise)

        canvas.create_polygon(*_flat(a, b, c, d), fill="#102a3a", outline=ACCENT)
        canvas.create_polygon(*_flat(a, d, dt, at), fill="#17324b", outline=ACCENT)
        canvas.create_polygon(*_flat(b, c, ct, bt), fill="#1e3a4d", outline=ACCENT)
        canvas.create_polygon(*_flat(at, bt, ct, dt), fill=ROOM_FILLS[index % len(ROOM_FILLS)], outline="#67d5ff", width=2)

        name = str(room.get("name", f"Room {index + 1}"))
        pressure = _number(room.get("observed_pressure_pa"))
        label = name if pressure is None else f"{name}  ·  {pressure:g} Pa"
        canvas.create_text(
            (at[0] + bt[0] + ct[0] + dt[0]) / 4,
            min(at[1], bt[1], ct[1], dt[1]) - 16,
            text=label,
            fill=TEXT,
            font=("Segoe UI", 9, "bold"),
        )

        airflow = _number(room.get("supply_airflow_m3_h"))
        if airflow is None:
            airflow = _number(room.get("cleanroom_airflow_m3_h"))
        if airflow is not None:
            center_x = (a[0] + c[0]) / 2
            center_y = (a[1] + c[1]) / 2 - rise * 0.45
            canvas.create_line(
                center_x,
                center_y - 26,
                center_x,
                center_y + 18,
                fill=ACCENT_2,
                width=3,
                arrow="last",
                arrowshape=(9, 11, 5),
            )
            canvas.create_text(
                center_x + 8,
                center_y - 30,
                anchor="w",
                text=f"{airflow:,.0f} m³/h",
                fill=ACCENT_2,
                font=("Segoe UI", 8, "bold"),
            )

        cursor += room["length_m"] + 0.75

    canvas.create_text(
        width - 24,
        height - 22,
        anchor="e",
        text="Isometric visualization · dimensions derived from the current analysis JSON",
        fill=MUTED,
        font=("Segoe UI", 8),
    )


def _draw_grid(canvas: Any, width: int, height: int, *, spacing: int) -> None:
    for x in range(0, width, spacing):
        canvas.create_line(x, 0, x, height, fill=GRID, width=1)
    for y in range(0, height, spacing):
        canvas.create_line(0, y, width, y, fill=GRID, width=1)


def _empty_state(canvas: Any, width: int, height: int, title: str, message: str) -> None:
    canvas.create_text(
        width / 2,
        height / 2 - 20,
        text=title,
        fill=TEXT,
        font=("Segoe UI", 18, "bold"),
    )
    canvas.create_text(
        width / 2,
        height / 2 + 18,
        text=message,
        fill=MUTED,
        font=("Segoe UI", 10),
        width=max(width - 160, 280),
        justify="center",
    )


def _positive_number(value: Any) -> float | None:
    number = _number(value)
    if number is None or number <= 0:
        return None
    return number


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _flat(*points: tuple[float, float]) -> tuple[float, ...]:
    values: list[float] = []
    for x, y in points:
        values.extend((x, y))
    return tuple(values)
