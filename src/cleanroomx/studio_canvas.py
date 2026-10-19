"""Live, model-backed Canvas presentation for the Design Studio.

The geometry, device symbols, pressure relationships and room panels all use
the same spatial model as the editor. No screenshot or demo-specific geometry
is used by this renderer.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from .spatial_transforms import fit_3d_view
from .studio_summary import dashboard_snapshot, device_snapshot, navigator_device_markers, navigator_rectangles
from .studio_widgets import blend, draw_icon, draw_metrics, fit_text, rounded_rect

if TYPE_CHECKING:
    from .spatial import SpatialDesignWorkspace


ROOM_COLORS = ("#f58290", "#719eff", "#3fc8b9", "#b49af7", "#e7bc78")


def room_color(layout: dict, room_id: str) -> str:
    index = next((i for i, room in enumerate(layout["rooms"])
                  if room["id"] == room_id), 0)
    return ROOM_COLORS[index % len(ROOM_COLORS)]


def studio_regions(width: int, height: int, inspector: bool = False) -> dict:
    """Reserve disjoint model and panel areas before fitting the actual camera."""
    navigator_width = min(280, max(220, round(width * .179)))
    card_width = min(350, max(270, round(width * .223)))
    right = width - (20 if inspector else card_width + 32)
    left = min(navigator_width + 45, max(20, right - 320))
    return {
        "navigator_width": navigator_width,
        "card_width": card_width,
        "scene": (left, 16, max(left + 100, right), max(140, height - 58)),
    }


def fit_camera(workspace: SpatialDesignWorkspace, points: list[tuple[float, float, float]]) -> None:
    canvas = workspace.canvas_3d
    width, height = max(200, canvas.winfo_width()), max(200, canvas.winfo_height())
    left, top, right, bottom = studio_regions(
        width, height, workspace.inspector_visible()
    )["scene"]
    view = workspace.layout["view"]
    zoom, pan_x, pan_y = fit_3d_view(
        points, width_px=right - left, height_px=bottom - top,
        azimuth_deg=view["azimuth_deg"], elevation_deg=view["elevation_deg"],
        padding_fraction=.08, projection_mode=view.get("projection_mode", "orthographic"),
    )
    view["zoom_3d"] = zoom
    view["pan_3d_x"] = pan_x + (left + right) / 2 - width / 2
    view["pan_3d_y"] = pan_y + top + .66 * (bottom - top) - .66 * height


def _selected_room_id(workspace: SpatialDesignWorkspace) -> str | None:
    selected = workspace.selected
    if selected is None:
        return None
    if selected.kind == "room":
        return selected.item_id
    device = next((d for d in workspace.layout["devices"]
                   if d["id"] == selected.item_id), None)
    return device.get("room_id") if device else None


def draw_navigator(workspace: SpatialDesignWorkspace) -> None:
    canvas, palette = workspace.navigator_canvas, workspace._theme_palette
    canvas.delete("all")
    workspace._navigator_item_to_room.clear()
    workspace._navigator_item_to_device.clear()
    width = int(float(canvas.cget("width")))
    height = int(float(canvas.cget("height")))
    canvas.configure(background=palette["canvas_3d"], highlightthickness=0)
    rounded_rect(canvas, (3, 5, width, height), fill=palette["canvas_3d"], outline="")
    rounded_rect(canvas, (0, 0, width - 3, height - 3), radius=14,
                 fill=palette["panel"], outline=palette["border"])
    draw_icon(canvas, "rooms", 18, 22, 12, palette["accent"])
    canvas.create_text(33, 22, text="ROOM NAVIGATOR", anchor="w",
                       fill=palette["text"], font=("TkDefaultFont", 8, "bold"))
    canvas.create_text(width - 18, 22, text=f'{len(workspace.layout["rooms"]):02d}', anchor="e",
                       fill=palette["muted"], font=("TkDefaultFont", 8))
    rounded_rect(canvas, (12, 42, width - 15, 131), radius=8,
                 fill=palette["field"], outline="")
    rooms = workspace.layout["rooms"]
    selected_id = _selected_room_id(workspace)
    miniatures = navigator_rectangles(
        workspace.layout, width_px=width, height_px=128, padding_px=20, header_px=48
    )
    for index, room in enumerate(miniatures):
        selected = room["id"] == selected_id
        color = room_color(workspace.layout, room["id"])
        x0, y0, x1, y1 = room["rect"]
        items = [canvas.create_rectangle(
            x0, y0, x1, y1, fill=blend(color, palette["panel"], .65),
            outline=blend(color, palette["text"], .5) if selected else color,
            width=2 if selected else 1,
            tags=(f"navigator-room:{room['id']}",),
        ), canvas.create_text(
            (x0 + x1) / 2, (y0 + y1) / 2, text=str(index + 1),
            fill=palette["text"], font=("TkDefaultFont", 10, "bold"),
        )]
        for item in items:
            workspace._navigator_item_to_room[item] = room["id"]
    # Native Canvas markers use actual x/y locations from the spatial model.
    # Markers are created after room outlines so direct clicks select devices.
    for marker in navigator_device_markers(
        workspace.layout, width_px=width, height_px=128,
        padding_px=20, header_px=48,
    ):
        px, py = marker["point"]
        tags = (f'navigator-device:{marker["id"]}', "navigator-device")
        selected_device = (
            workspace.selected is not None
            and workspace.selected.kind == "device"
            and workspace.selected.item_id == marker["id"]
        )
        color = {
            "air": palette["accent"], "opening": "#e7bc78", "other": "#b49af7",
        }[marker["category"]]
        items = []
        if selected_device:
            items.append(canvas.create_oval(
                px - 8, py - 8, px + 8, py + 8,
                fill=palette["panel"], outline=palette["text"], width=2, tags=tags,
            ))
        if marker["category"] == "opening":
            items.append(canvas.create_polygon(
                px, py - 5, px + 5, py, px, py + 5, px - 5, py,
                fill=color, outline=palette["panel"], width=1, tags=tags,
            ))
        elif marker["category"] == "other":
            items.append(canvas.create_rectangle(
                px - 4, py - 4, px + 4, py + 4,
                fill=color, outline=palette["panel"], width=1, tags=tags,
            ))
        else:
            items.append(canvas.create_oval(
                px - 5, py - 5, px + 5, py + 5,
                fill=color, outline=palette["panel"], width=1, tags=tags,
            ))
        for item in items:
            workspace._navigator_item_to_device[item] = marker["id"]
    room_device_counts = {room["id"]: 0 for room in rooms}
    for device in workspace.layout["devices"]:
        room_id = device.get("room_id")
        if room_id in room_device_counts:
            room_device_counts[room_id] += 1
    row_height = 27
    visible_rows = max(1, (height - 167) // row_height)
    start = min(workspace._navigator_scroll, max(0, len(rooms) - visible_rows))
    workspace._navigator_scroll = start
    for index in range(start, min(len(rooms), start + visible_rows)):
        room = rooms[index]
        y = 148 + (index - start) * row_height
        selected = room["id"] == selected_id
        color = room_color(workspace.layout, room["id"])
        items = [rounded_rect(canvas, (10, y - 12, width - 13, y + 12), radius=6,
            fill=blend(color, palette["panel"], .17) if selected else palette["panel"], outline=""),
            canvas.create_oval(18, y - 3, 24, y + 3, fill=color, outline=""),
            canvas.create_text(34, y, text=f'{index + 1:02d}', anchor="w",
                               fill=palette["muted"], font=("TkDefaultFont", 7)),
            canvas.create_text(58, y, text=fit_text(canvas, room["name"], width - 125,
                               ("TkDefaultFont", 8, "bold" if selected else "normal")), anchor="w",
                               fill=palette["text"], font=("TkDefaultFont", 8, "bold" if selected else "normal")),
            canvas.create_text(width - 22, y,
                               text=f'{room_device_counts[room["id"]]} dev · {room["length_m"] * room["width_m"]:g} m²',
                               anchor="e", fill=palette["muted"], font=("TkDefaultFont", 7),
                               tags=(f'navigator-room-data:{room["id"]}',))]
        for item in items:
            workspace._navigator_item_to_room[item] = room["id"]
    canvas.create_text(17, height - 17,
                       text="", anchor="w", fill=palette["muted"],
                       font=("TkDefaultFont", 7), tags=("navigator-hint",))
    update_navigator_hint(workspace)


def update_navigator_hint(workspace: SpatialDesignWorkspace) -> None:
    """Make dense device/room markers discoverable without changing selection."""
    target = getattr(workspace, "_navigator_hover_target", None)
    label = "● Air   ◆ Opening   ■ Other   ↑↓ Rooms"
    if target is not None:
        kind, item_id = target
        collection = "devices" if kind == "device" else "rooms"
        item = next((e for e in workspace.layout[collection]
                     if e["id"] == item_id), None)
        if item is not None:
            name = str(item.get("name") or item["id"])
            if kind == "device":
                label = f'{name}  ·  {item.get("type") or "Device"}'
            else:
                label = f'{name}  ·  {item["length_m"] * item["width_m"]:g} m²'
    canvas = workspace.navigator_canvas
    canvas.itemconfigure("navigator-hint", text=fit_text(
        canvas, label, int(float(canvas.cget("width"))) - 34,
        ("TkDefaultFont", 7),
    ))


def _panel(workspace, x, y, width, height, *, selected=False):
    canvas, p = workspace.canvas_3d, workspace._theme_palette
    rounded_rect(canvas, (x + 2, y + 4, x + width + 2, y + height + 4), radius=12,
                 fill=blend(p["canvas_3d"], p["background"], .6), outline="", tags=("studio-ui",))
    rounded_rect(canvas, (x, y, x + width, y + height), radius=12,
                 fill=p["panel"], outline=p["border"], tags=("studio-ui",))
    if selected:
        canvas.create_line(x + 1, y + 15, x + 1, y + height - 15,
                           fill=p["accent"], width=3, capstyle="round", tags=("studio-ui",))


def _action(workspace, rect, label, action, *, primary=False, active=False):
    canvas, p = workspace.canvas_3d, workspace._theme_palette
    x0, y0, x1, y1 = rect
    tags = (f"studio-action:{action}", "studio-ui")
    normal = p["accent"] if primary else p["selection"] if active else p["surface_alt"]
    foreground = p["accent_text"] if primary else p["accent"] if active else p["text"]
    hovered = p["accent_hover"] if primary else blend(p["accent"], p["surface_alt"], .2)
    workspace._studio_action_styles[action] = (normal, hovered)
    fill = hovered if workspace._studio_hover_action == action else normal
    rounded_rect(canvas, rect, radius=7, fill=fill,
                 outline=p["accent"] if primary or active else p["border"],
                 tags=tags + (f"studio-action-bg:{action}",))
    canvas.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=label,
                       fill=foreground, font=("TkDefaultFont", 8, "bold"), tags=tags)


def hover_action(workspace, action):
    previous = workspace._studio_hover_action
    if previous == action:
        return
    workspace._studio_hover_action = action
    for key, hovered in ((previous, False), (action, True)):
        colors = workspace._studio_action_styles.get(key)
        if colors:
            workspace.canvas_3d.itemconfigure(f"studio-action-bg:{key}", fill=colors[int(hovered)])


def _room_panels(workspace, width, height, card_width):
    canvas = workspace.canvas_3d
    previous = set(canvas.find_all())
    _room_panel_contents(workspace, width, card_width)
    scale = min(1.0, max(.4, (height - (12 if height < 430 else 70)) / 346))
    for item in set(canvas.find_all()) - previous:
        canvas.addtag_withtag("studio-room-panel", item)
        if scale < 1:
            canvas.scale(item, 0, 0, 1, scale)
            if canvas.type(item) == "text":
                family, size, *style = canvas.tk.splitlist(canvas.itemcget(item, "font"))
                canvas.itemconfigure(item, font=(family, max(6, round(int(size) * scale)), *style))


def _room_panel_contents(workspace, width, card_width):
    canvas, p = workspace.canvas_3d, workspace._theme_palette
    room = dashboard_snapshot(workspace.layout, _selected_room_id(workspace))["selected_room"]
    selected_device = device_snapshot(
        workspace.layout,
        workspace.selected.item_id
        if workspace.selected is not None and workspace.selected.kind == "device"
        else None,
    )
    x, y = width - card_width - 14, 12
    _panel(workspace, x, y, card_width, 180, selected=True)
    text = lambda yy, value, **kw: canvas.create_text(
        x + 12, yy, text=value, anchor="nw", fill=kw.pop("fill", p["muted"]),
        font=kw.pop("font", ("TkDefaultFont", 9)),
        tags=("studio-ui",) + tuple(kw.pop("tags", ())), **kw
    )
    text(y + 14, "SELECTED ROOM", fill=p["muted"], font=("TkDefaultFont", 7, "bold"))
    if room is None:
        text(y + 38, "Select a room in the scene or navigator", width=card_width - 24)
        return
    _action(workspace, (x + card_width - 54, y + 9, x + card_width - 12, y + 31), "Edit", "properties")
    text(y + 37, fit_text(canvas, room["name"], card_width - 30, ("TkDefaultFont", 15, "bold")),
         fill=p["text"], font=("TkDefaultFont", 15, "bold"))
    text(y + 67, fit_text(canvas, room["classification"], card_width - 30, ("TkDefaultFont", 8)),
         font=("TkDefaultFont", 8))
    for column, (label, value) in enumerate((("LENGTH", room["length_m"]),
                                            ("WIDTH", room["width_m"]), ("HEIGHT", room["height_m"]))):
        xx = x + 14 + column * (card_width - 28) / 3
        canvas.create_text(xx, y + 100, text=f"{value:g} m", anchor="w", fill=p["text"],
                           font=("TkDefaultFont", 11, "bold"), tags=("studio-ui",))
        canvas.create_text(xx, y + 119, text=label, anchor="w", fill=p["muted"],
                           font=("TkDefaultFont", 6, "bold"), tags=("studio-ui",))
    text(y + 133, f'{room["floor_area_m2"]:g} m² floor  ·  {room["volume_m3"]:g} m³ volume',
         font=("TkDefaultFont", 7))
    pressure = room["pressure_setpoint_pa"]
    text(y + 157, "PRESSURE SETPOINT", font=("TkDefaultFont", 7))
    canvas.create_text(x + card_width - 16, y + 162,
                       text="Not set" if pressure is None else f'{pressure:+g} Pa', anchor="e",
                       fill=p["accent"], font=("TkDefaultFont", 10, "bold"), tags=("studio-ui",))
    y += 194
    _panel(workspace, x, y, card_width, 140)
    if selected_device is None:
        text(y + 13, "PLACED IN THIS ROOM", font=("TkDefaultFont", 7, "bold"))
        canvas.create_text(x + card_width - 16, y + 18, text=f'{room["device_count"]:02d} total',
                           anchor="e", fill=p["muted"], font=("TkDefaultFont", 7), tags=("studio-ui",))
        groups = room["device_groups"]
        for column, key, label, yy in (
            (0, "ffu", "FFU", 48), (1, "supply", "Supply", 48),
            (0, "return_exhaust", "Return / exhaust", 76), (1, "other", "Other", 76),
        ):
            xx = x + 12 + column * ((card_width - 24) / 2)
            draw_icon(canvas, key, xx + 8, y + yy, 12, p["accent"], ("studio-ui",))
            canvas.create_text(xx + 24, y + yy, text=str(groups[key]), anchor="w", fill=p["text"],
                               font=("TkDefaultFont", 12 if len(str(groups[key])) < 4 else 8, "bold"), tags=("studio-ui",))
            canvas.create_text(xx + 50, y + yy, text=label, anchor="w", fill=p["muted"],
                               font=("TkDefaultFont", 7), tags=("studio-ui",))
    else:
        text(y + 13, "SELECTED DEVICE", font=("TkDefaultFont", 7, "bold"))
        _action(workspace, (x + card_width - 79, y + 8, x + card_width - 12, y + 31),
                "Inspect", "inspect-device")
        text(y + 31, fit_text(canvas, selected_device["name"], card_width - 30,
                              ("TkDefaultFont", 12, "bold")),
             fill=p["text"], font=("TkDefaultFont", 12, "bold"),
             tags=("studio-selected-device-name",))
        text(y + 56, fit_text(canvas,
                              f'{selected_device["type"]}  ·  {selected_device["room_name"]}',
                              card_width - 30, ("TkDefaultFont", 8)),
             font=("TkDefaultFont", 8))
        text(y + 78, (f'X {selected_device["x_m"]:g} m   '
                       f'Y {selected_device["y_m"]:g} m   '
                       f'Z {selected_device["z_above_floor_m"]:+g} m'),
             font=("TkDefaultFont", 8), tags=("studio-selected-device-position",))
    middle = x + card_width / 2
    _action(workspace, (x + 11, y + 104, middle - 3, y + 129), "Focus room", "focus", primary=True)
    _action(workspace, (middle + 3, y + 104, x + card_width - 11, y + 129),
            "Restore rooms" if workspace._isolated_item else "Isolate room",
            "restore" if workspace._isolated_item else "isolate")


def draw_scene(workspace: SpatialDesignWorkspace, overlay: dict) -> None:
    """Render actual cutaway volumes, attached devices and functional panels."""
    canvas, p, layout = workspace.canvas_3d, workspace._theme_palette, workspace.layout
    width, height = max(200, canvas.winfo_width()), max(200, canvas.winfo_height())
    workspace._studio_action_styles.clear()
    regions = studio_regions(width, height, workspace.inspector_visible())
    # Canvas-native gradient, painted before geometry and UI. This is not an image.
    for y in range(0, height, 6):
        canvas.create_rectangle(0, y, width, min(height, y + 6), outline="",
                                fill=blend(p["panel"], p["canvas_3d"], 1 - y / height),
                                tags=("studio-background",))
    nav_height = min(330, max(225, 172 + len(layout["rooms"]) * 27), height - 25)
    workspace.navigator_canvas.configure(width=regions["navigator_width"], height=nav_height)
    workspace.navigator_canvas.place(relx=0, x=14, rely=1, y=-14, anchor="sw")
    workspace._draw_room_navigator()
    if height >= 430:
        canvas.create_text(18, 24, text="ROOM COMPOSITION", anchor="w", fill=p["text"],
                           font=("TkDefaultFont", 11, "bold"), tags=("studio-ui",))
        canvas.create_text(18, 48, text=("Interior" if workspace._interior_3d.get() else "Exterior")
                           + " view  ·  " + workspace._projection_mode.get(), anchor="w", fill=p["muted"],
                           font=("TkDefaultFont", 8), tags=("studio-ui",))
    if not layout["rooms"]:
        canvas.create_text(width / 2, height / 2, text="Add a room to begin designing",
                           fill=p["muted"], tags=("studio-ui",))
    else:
        _geometry(workspace, overlay)
    if not workspace.inspector_visible():
        _room_panels(workspace, width, height, regions["card_width"])
    center = sum(regions["scene"][::2]) / 2
    rounded_rect(canvas, (center - 137, height - 51, center + 137, height - 7), radius=12,
                 fill=p["panel"], outline=p["border"], tags=("studio-ui",))
    view = layout["view"]
    angles = {"top": (0, 90), "front": (0, 0), "iso": (35, 28)}
    for i, (label, action) in enumerate((("TOP", "top"), ("FRONT", "front"), ("ISO", "iso"))):
        xx = center - 125 + i * 58
        azimuth, elevation = angles[action]
        active = (abs((view["azimuth_deg"] - azimuth + 180) % 360 - 180) < .05
                  and abs(view["elevation_deg"] - elevation) < .05)
        _action(workspace, (xx + 2, height - 43, xx + 56, height - 15), label, action, active=active)
    xx = center + 49
    _action(workspace, (xx + 4, height - 43, xx + 76, height - 15),
            f'{layout["view"]["zoom_3d"] * 100:.0f}%', "fit")
    if height >= 430:
        canvas.create_text(width - 16, height - 18, anchor="se",
                           text="Length X (m)\nWidth Y (m)\nHeight Z (m)",
                           justify="right", fill=p["muted"], font=("TkDefaultFont", 8, "bold"),
                           tags=("studio-ui", "studio-dimension-labels"))
    workspace._draw_studio_axes(canvas)


def _geometry(workspace, overlay):
    canvas, p, layout = workspace.canvas_3d, workspace._theme_palette, workspace.layout
    min_x, min_y, max_x, max_y = workspace._bounds()
    cx, cy = (min_x + max_x) / 2, (min_y + max_y) / 2
    floor_z = layout["floor"]["elevation_m"]
    project = lambda x, y, z: workspace._project_3d(x - cx, y - cy, z)
    pad = max(.5, layout["grid_m"])
    floor = [project(x, y, floor_z) for x, y in (
        (min_x - pad, min_y - pad), (max_x + pad, min_y - pad),
        (max_x + pad, max_y + pad), (min_x - pad, max_y + pad))]
    canvas.create_polygon(*sum(floor, ()), fill=blend(p["panel"], p["canvas_3d"], .7),
                          outline=p["border"], tags=("floor3d",))
    if workspace._show_grid.get():
        step = max(1, math.ceil(max(max_x - min_x, max_y - min_y) / 40))
        for x in range(math.floor(min_x), math.ceil(max_x) + 1, step):
            canvas.create_line(*project(x, min_y - pad, floor_z),
                               *project(x, max_y + pad, floor_z), fill=p["border"],
                               tags=("studio-grid",))
        for y in range(math.floor(min_y), math.ceil(max_y) + 1, step):
            canvas.create_line(*project(min_x - pad, y, floor_z),
                               *project(max_x + pad, y, floor_z), fill=p["border"],
                               tags=("studio-grid",))
    section = workspace._active_section_height()
    az = math.radians(layout["view"]["azimuth_deg"])
    colors = {room["room_id"]: room["fill"] for room in overlay["rooms"]}
    ordered = sorted((r for r in layout["rooms"] if workspace._is_item_visible("room", r["id"])),
                     key=lambda r: r["x_m"] * math.sin(az) + r["y_m"] * math.cos(az))
    for room in ordered:
        x0, y0 = room["x_m"], room["y_m"]
        x1, y1 = x0 + room["length_m"], y0 + room["width_m"]
        z0 = room.get("floor_elevation_m", floor_z)
        z1 = z0 + room["height_m"]
        if section is not None:
            if z0 >= section:
                continue
            z1 = min(z1, section)
        corners = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
        base = [project(x, y, z0) for x, y in corners]
        top = [project(x, y, z1) for x, y in corners]
        color = room_color(layout, room["id"]) if overlay["mode"] == "none" else colors[room["id"]]
        tag = f'room:{room["id"]}'
        selected = _selected_room_id(workspace) == room["id"]
        hovered = workspace._hovered_3d is not None and workspace._hovered_3d.item_id == room["id"]
        outline = "#8bddf7" if selected or hovered else blend(color, p["text"], .7)
        if selected or hovered:
            canvas.create_polygon(*sum(base, ()), fill="", outline=blend(color, p["canvas_3d"], .3),
                                  width=7, tags=(tag, "room3d", "studio-selection-glow"))
        canvas.create_polygon(*sum(base, ()), fill=blend(color, p["canvas_3d"], .26),
                              outline=outline, width=2 if selected else 1,
                              tags=(tag, "room3d", "studio-floor"))
        far_edges = ((0, 1) if math.cos(az) >= 0 else (3, 2),
                     (0, 3) if math.sin(az) >= 0 else (1, 2))
        edges = far_edges if workspace._interior_3d.get() else ((0, 1), (1, 2), (2, 3), (3, 0))
        for face_index, (a, b) in enumerate(edges):
            face = (base[a], base[b], top[b], top[a])
            shaded = blend(color, p["canvas_3d"], .88 if face_index % 2 else 1)
            canvas.create_polygon(*sum(face, ()), fill=shaded if overlay["mode"] == "none" else color, outline=outline,
                                  width=2 if selected else 1,
                                  stipple="gray50" if workspace._xray_3d.get() else "",
                                  tags=(tag, "room3d", "studio-wall"))
        if not workspace._interior_3d.get():
            canvas.create_polygon(*sum(top, ()), fill=color, outline=outline,
                                  tags=(tag, "room3d", "studio-roof"))
        for i in range(4):
            canvas.create_line(*base[i], *top[i], fill=blend(outline, p["canvas_3d"], .55),
                               dash=(2, 5), tags=(tag, "room3d", "studio-bounds"))
            canvas.create_line(*top[i], *top[(i + 1) % 4], fill=blend(outline, p["canvas_3d"], .4),
                               dash=(2, 5), tags=(tag, "room3d", "studio-bounds"))
        if section is not None:
            canvas.create_polygon(*sum(top, ()), fill="", outline=p["accent"],
                                  dash=(4, 3), tags=(tag, "section_plane"))
        if workspace._show_labels.get():
            anchor = project(x0 + room["length_m"] * .22, y0 + room["width_m"] * .18, z1 + .15)
            label = canvas.create_text(*anchor, text=fit_text(canvas, room["name"], 190,
                                       ("TkDefaultFont", 10, "bold")), fill=p["text"],
                                       font=("TkDefaultFont", 10, "bold"),
                                       tags=(tag, "room3d", "studio-room-label"))
            x, y, xx, yy = canvas.bbox(label)
            box = rounded_rect(canvas, (x - 11, y - 5, xx + 11, yy + 5), radius=7,
                               fill=p["panel"], outline=blend(color, p["border"], .6),
                               tags=(tag, "room3d", "studio-room-label"))
            canvas.tag_lower(box, label)
        if workspace._show_devices.get():
            for device in layout["devices"]:
                if device.get("room_id") == room["id"] and workspace._is_item_visible("device", device["id"]):
                    _device(workspace, device, z0, section, project)
    workspace._draw_relationships_3d(center_x_m=cx, center_y_m=cy, floor_z_m=floor_z)
    room_ids = {room["id"] for room in layout["rooms"]}
    if workspace._show_devices.get():
        for device in layout["devices"]:
            if device.get("room_id") not in room_ids and workspace._is_item_visible("device", device["id"]):
                _device(workspace, device, floor_z, section, project)
    if overlay["mode"] != "none":
        workspace._draw_engineering_legend(canvas, overlay)


def _device(workspace, device, floor_z, section, project):
    canvas, p = workspace.canvas_3d, workspace._theme_palette
    x, y, z = device["x_m"], device["y_m"], floor_z + device["z_m"]
    if section is not None and z >= section:
        return
    tags = (f'device:{device["id"]}', "device3d")
    if device["type"] in {"door", "window", "opening", "transfer"}:
        angle = math.radians(device.get("orientation_deg", 0))
        half = device.get("width_m", .4) / 2
        dx, dy = math.cos(angle) * half, math.sin(angle) * half
        top_z = z + device.get("height_m", .4)
        if section is not None:
            top_z = min(top_z, section)
        corners = [project(x - dx, y - dy, z), project(x + dx, y + dy, z),
                   project(x + dx, y + dy, top_z), project(x - dx, y - dy, top_z)]
        canvas.create_polygon(*sum(corners, ()), fill="", outline="#f5cf4d", width=2,
                              tags=tags + ("studio-opening",))
        if device["type"] != "door":
            canvas.create_line(*corners[0], *corners[2], fill="#f5cf4d", tags=tags)
    else:
        px, py = project(x, y, z)
        if device["z_m"] > .2:
            canvas.create_line(*project(x, y, floor_z), px, py, fill=p["muted"],
                               dash=(2, 5), tags=tags)
            bx, by = project(x, y, floor_z)
            canvas.create_rectangle(bx - 2, by - 2, bx + 2, by + 2,
                                    fill=p["muted"], outline="", tags=tags)
        selected = workspace.selected is not None and workspace.selected.item_id == device["id"]
        canvas.create_rectangle(px - 4, py - 4, px + 4, py + 4,
                                fill=p["panel"], outline=p["accent"] if selected else "#a7dbdf",
                                width=2 if selected else 1, tags=tags)
        canvas.create_line(px - 2, py, px + 2, py, fill=p["muted"], tags=tags)
