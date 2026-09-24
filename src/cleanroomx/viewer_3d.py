from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .layout import (
    Camera3D,
    Room,
    floor_bounds,
    object_prism,
    point_in_polygon,
    room_prism,
)

_DEVICE_ABBR = {
    "door": "D",
    "supply_diffuser": "S",
    "return_grille": "R",
    "exhaust_grille": "E",
    "ffu": "FFU",
    "equipment": "EQ",
    "sensor": "●",
    "transfer_opening": "T",
}


class Layout3DFrame(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, workspace):
        super().__init__(parent)
        self.workspace = workspace
        self.camera = Camera3D()
        self._drag_anchor: tuple[float, float] | None = None
        self._drag_mode: str | None = None
        self._drag_distance = 0.0
        self._pick_regions: list[
            tuple[float, str, list[tuple[float, float]]]
        ] = []
        self.status_var = tk.StringVar(
            value="Orbit: left-drag · Pan: right-drag · Zoom: wheel"
        )
        self._build()

    def _build(self) -> None:
        toolbar = ttk.Frame(self, padding=(5, 4))
        toolbar.pack(fill="x")
        ttk.Button(
            toolbar, text="Reset Camera", command=self.reset_camera
        ).pack(side="left", padx=2)
        ttk.Button(
            toolbar, text="Fit Project", command=self.fit_project
        ).pack(side="left", padx=2)
        ttk.Label(
            toolbar, text="Same canonical geometry as 2D Layout"
        ).pack(side="right")

        self.canvas = tk.Canvas(
            self,
            background="#f8f8fa",
            highlightthickness=1,
            highlightbackground="#aaa",
        )
        self.canvas.pack(fill="both", expand=True, padx=4, pady=4)
        self.canvas.bind("<Configure>", lambda event: self.refresh())
        self.canvas.bind(
            "<ButtonPress-1>", lambda event: self._drag_start(event, "orbit")
        )
        self.canvas.bind("<B1-Motion>", self._drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self._drag_end)
        self.canvas.bind(
            "<ButtonPress-3>", lambda event: self._drag_start(event, "pan")
        )
        self.canvas.bind("<B3-Motion>", self._drag_motion)
        self.canvas.bind("<ButtonRelease-3>", self._drag_end)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<Button-4>", lambda event: self._wheel_delta(1))
        self.canvas.bind("<Button-5>", lambda event: self._wheel_delta(-1))
        ttk.Label(self, textvariable=self.status_var, padding=(6, 2)).pack(
            fill="x"
        )

    def reset_camera(self) -> None:
        self.camera.reset()
        self.refresh()

    def fit_project(self) -> None:
        self.camera.zoom = 1.0
        self.camera.pan_x_px = 0.0
        self.camera.pan_y_px = 0.0
        self.refresh()

    def _drag_start(self, event, mode: str) -> None:
        self._drag_anchor = (event.x, event.y)
        self._drag_mode = mode
        self._drag_distance = 0.0

    def _drag_motion(self, event) -> None:
        if self._drag_anchor is None:
            return
        x, y = self._drag_anchor
        dx, dy = event.x - x, event.y - y
        self._drag_distance += abs(dx) + abs(dy)
        if self._drag_mode == "orbit":
            self.camera.orbit(dx * 0.45, -dy * 0.35)
        else:
            self.camera.pan_x_px += dx
            self.camera.pan_y_px += dy
        self._drag_anchor = (event.x, event.y)
        self.refresh()

    def _drag_end(self, event) -> None:
        if self._drag_mode == "orbit" and self._drag_distance < 4:
            self._pick(event.x, event.y)
        self._drag_anchor = None
        self._drag_mode = None

    def _wheel(self, event) -> None:
        self._wheel_delta(1 if event.delta > 0 else -1)

    def _wheel_delta(self, direction: int) -> None:
        factor = 1.15 if direction > 0 else 1 / 1.15
        self.camera.zoom = min(8.0, max(0.15, self.camera.zoom * factor))
        self.refresh()

    def _pick(self, x: float, y: float) -> None:
        matches = [
            (depth, entity_id)
            for depth, entity_id, polygon in self._pick_regions
            if point_in_polygon((x, y), polygon)
        ]
        if not matches:
            self.workspace.set_selection(None)
            return
        _, entity_id = max(matches, key=lambda item: item[0])
        self.workspace.set_selection(entity_id)
        entity = self.workspace.selected_entity()
        if entity is not None:
            kind = "room" if isinstance(entity, Room) else entity.kind
            self.status_var.set(f"Selected: {entity.name} ({kind})")

    def refresh(self, event=None) -> None:
        canvas = self.canvas
        canvas.delete("all")
        self._pick_regions.clear()
        floor = self.workspace.current_floor()
        if floor is None:
            canvas.create_text(
                max(canvas.winfo_width() / 2, 180),
                max(canvas.winfo_height() / 2, 120),
                text="No spatial floor. Create one in 2D Layout.",
            )
            return

        width = max(canvas.winfo_width(), 400)
        height = max(canvas.winfo_height(), 300)
        min_x, min_y, max_x, max_y = floor_bounds(floor)
        span = max(max_x - min_x, max_y - min_y, 1.0)
        max_room_h = max(
            (room.height_m for room in floor.rooms),
            default=floor.default_ceiling_height_m,
        )
        center_world = (
            (min_x + max_x) / 2,
            (min_y + max_y) / 2,
            floor.elevation_m + max_room_h / 2,
        )
        scale = max(12.0, min(width, height) * 0.55 / span)
        center_screen = (width / 2, height * 0.58)

        def project(point):
            return self.camera.project(
                point,
                center_world=center_world,
                center_screen=center_screen,
                scale_px_per_m=scale,
            )

        ground = [
            (min_x, min_y, floor.elevation_m),
            (max_x, min_y, floor.elevation_m),
            (max_x, max_y, floor.elevation_m),
            (min_x, max_y, floor.elevation_m),
        ]
        projected_ground = [project(point) for point in ground]
        canvas.create_polygon(
            *[coord for point in projected_ground for coord in point[:2]],
            fill="#f1f1f1",
            outline="#bbb",
        )

        room_items = []
        for room in floor.rooms:
            vertices, edges = room_prism(room)
            projected = [project(point) for point in vertices]
            depth = sum(point[2] for point in projected) / len(projected)
            room_items.append((depth, room, projected, edges))

        for depth, room, projected, edges in sorted(
            room_items, key=lambda item: item[0]
        ):
            top = [projected[index][:2] for index in (4, 5, 6, 7)]
            selected = room.id == self.workspace.selected_id
            canvas.create_polygon(
                *[coord for point in top for coord in point],
                fill="#d6eaff" if selected else "#e9f2fb",
                outline="",
            )
            for start, end in edges:
                canvas.create_line(
                    *projected[start][:2],
                    *projected[end][:2],
                    fill="#0066cc" if selected else "#31566f",
                    width=3 if selected else 1,
                )
            self._pick_regions.append((depth, room.id, top))
            tx = sum(point[0] for point in top) / 4
            ty = sum(point[1] for point in top) / 4
            canvas.create_text(
                tx,
                ty - 10,
                text=room.name,
                font=("TkDefaultFont", 9, "bold"),
            )

        if self.workspace.layout_2d.devices_var.get():
            for obj in floor.objects:
                vertices, edges = object_prism(obj, floor)
                projected = [project(point) for point in vertices]
                depth = sum(point[2] for point in projected) / len(projected)
                selected = obj.id == self.workspace.selected_id
                for start, end in edges:
                    canvas.create_line(
                        *projected[start][:2],
                        *projected[end][:2],
                        fill="#cc5500" if selected else "#8a4f13",
                        width=3 if selected else 1,
                    )
                top = [projected[index][:2] for index in (4, 5, 6, 7)]
                self._pick_regions.append((depth + 0.01, obj.id, top))
                cx = sum(point[0] for point in top) / 4
                cy = sum(point[1] for point in top) / 4
                canvas.create_text(
                    cx,
                    cy,
                    text=_DEVICE_ABBR.get(obj.kind, "?"),
                    font=("TkDefaultFont", 7, "bold"),
                )

        self.status_var.set(
            "Orbit: left-drag · Pan: right-drag · Zoom: wheel · "
            f"yaw {self.camera.yaw_deg:.0f}° · pitch {self.camera.pitch_deg:.0f}°"
        )
