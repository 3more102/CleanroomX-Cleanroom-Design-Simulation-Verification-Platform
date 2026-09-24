from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

from .model import Floor, LayoutObject, Room


@dataclass
class Viewport2D:
    scale_px_per_m: float = 60.0
    origin_x_px: float = 60.0
    origin_y_px: float = 60.0

    def world_to_screen(self, x_m: float, y_m: float) -> tuple[float, float]:
        return (
            self.origin_x_px + x_m * self.scale_px_per_m,
            self.origin_y_px + y_m * self.scale_px_per_m,
        )

    def screen_to_world(self, x_px: float, y_px: float) -> tuple[float, float]:
        return (
            (x_px - self.origin_x_px) / self.scale_px_per_m,
            (y_px - self.origin_y_px) / self.scale_px_per_m,
        )

    def zoom_at(self, factor: float, x_px: float, y_px: float) -> None:
        if not math.isfinite(factor) or factor <= 0:
            raise ValueError("zoom factor must be positive and finite")
        wx, wy = self.screen_to_world(x_px, y_px)
        self.scale_px_per_m = min(500.0, max(8.0, self.scale_px_per_m * factor))
        self.origin_x_px = x_px - wx * self.scale_px_per_m
        self.origin_y_px = y_px - wy * self.scale_px_per_m

    def pan(self, dx_px: float, dy_px: float) -> None:
        self.origin_x_px += dx_px
        self.origin_y_px += dy_px

    def fit(self, bounds: tuple[float, float, float, float], width_px: float, height_px: float, *, padding_px: float = 50.0) -> None:
        min_x, min_y, max_x, max_y = bounds
        span_x = max(max_x - min_x, 1.0)
        span_y = max(max_y - min_y, 1.0)
        usable_w = max(width_px - 2 * padding_px, 1.0)
        usable_h = max(height_px - 2 * padding_px, 1.0)
        self.scale_px_per_m = min(500.0, max(8.0, min(usable_w / span_x, usable_h / span_y)))
        content_w = span_x * self.scale_px_per_m
        content_h = span_y * self.scale_px_per_m
        self.origin_x_px = (width_px - content_w) / 2.0 - min_x * self.scale_px_per_m
        self.origin_y_px = (height_px - content_h) / 2.0 - min_y * self.scale_px_per_m


def snap_value(value: float, grid_m: float) -> float:
    if grid_m <= 0 or not math.isfinite(grid_m):
        raise ValueError("grid size must be positive and finite")
    return round(value / grid_m) * grid_m


def snap_point(x_m: float, y_m: float, grid_m: float) -> tuple[float, float]:
    return snap_value(x_m, grid_m), snap_value(y_m, grid_m)


def floor_bounds(floor: Floor, *, include_objects: bool = True) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for room in floor.rooms:
        xs.extend((room.x_m, room.x2_m))
        ys.extend((room.y_m, room.y2_m))
    if include_objects:
        for obj in floor.objects:
            xs.extend((obj.x_m - obj.width_m / 2.0, obj.x_m + obj.width_m / 2.0))
            ys.extend((obj.y_m - obj.depth_m / 2.0, obj.y_m + obj.depth_m / 2.0))
    if not xs:
        return (0.0, 0.0, 10.0, 8.0)
    return min(xs), min(ys), max(xs), max(ys)


def hit_test_room(floor: Floor, x_m: float, y_m: float) -> Room | None:
    for room in reversed(floor.rooms):
        if room.contains(x_m, y_m):
            return room
    return None


def hit_test_object(floor: Floor, x_m: float, y_m: float, *, tolerance_m: float = 0.15) -> LayoutObject | None:
    for obj in reversed(floor.objects):
        half_w = max(obj.width_m / 2.0, tolerance_m)
        half_d = max(obj.depth_m / 2.0, tolerance_m)
        if abs(x_m - obj.x_m) <= half_w and abs(y_m - obj.y_m) <= half_d:
            return obj
    return None


def nearest_room_wall(room: Room, x_m: float, y_m: float) -> tuple[str, float, float]:
    candidates = [
        (abs(y_m - room.y_m), "north", min(max(x_m, room.x_m), room.x2_m), room.y_m),
        (abs(y_m - room.y2_m), "south", min(max(x_m, room.x_m), room.x2_m), room.y2_m),
        (abs(x_m - room.x_m), "west", room.x_m, min(max(y_m, room.y_m), room.y2_m)),
        (abs(x_m - room.x2_m), "east", room.x2_m, min(max(y_m, room.y_m), room.y2_m)),
    ]
    _, wall, sx, sy = min(candidates, key=lambda item: item[0])
    return wall, sx, sy


def room_resize(room: Room, handle: str, x_m: float, y_m: float, *, min_size_m: float = 0.1) -> None:
    right = room.x2_m
    bottom = room.y2_m
    if handle in {"nw", "sw"}:
        new_x = min(x_m, right - min_size_m)
        room.width_m = right - new_x
        room.x_m = new_x
    if handle in {"ne", "se"}:
        room.width_m = max(min_size_m, x_m - room.x_m)
    if handle in {"nw", "ne"}:
        new_y = min(y_m, bottom - min_size_m)
        room.depth_m = bottom - new_y
        room.y_m = new_y
    if handle in {"sw", "se"}:
        room.depth_m = max(min_size_m, y_m - room.y_m)


Point3D = tuple[float, float, float]


@dataclass
class Camera3D:
    yaw_deg: float = 38.0
    pitch_deg: float = 28.0
    zoom: float = 1.0
    pan_x_px: float = 0.0
    pan_y_px: float = 0.0

    def reset(self) -> None:
        self.yaw_deg = 38.0
        self.pitch_deg = 28.0
        self.zoom = 1.0
        self.pan_x_px = 0.0
        self.pan_y_px = 0.0

    def orbit(self, delta_yaw_deg: float, delta_pitch_deg: float) -> None:
        self.yaw_deg = (self.yaw_deg + delta_yaw_deg) % 360.0
        self.pitch_deg = max(-80.0, min(80.0, self.pitch_deg + delta_pitch_deg))

    def project(
        self,
        point: Point3D,
        *,
        center_world: Point3D,
        center_screen: tuple[float, float],
        scale_px_per_m: float,
    ) -> tuple[float, float, float]:
        x = point[0] - center_world[0]
        y = point[1] - center_world[1]
        z = point[2] - center_world[2]
        yaw = math.radians(self.yaw_deg)
        pitch = math.radians(self.pitch_deg)
        x1 = math.cos(yaw) * x - math.sin(yaw) * y
        y1 = math.sin(yaw) * x + math.cos(yaw) * y
        y2 = math.cos(pitch) * y1 - math.sin(pitch) * z
        depth = math.sin(pitch) * y1 + math.cos(pitch) * z
        scale = scale_px_per_m * self.zoom
        sx = center_screen[0] + self.pan_x_px + x1 * scale
        sy = center_screen[1] + self.pan_y_px - y2 * scale
        return sx, sy, depth


def room_prism(room: Room) -> tuple[list[Point3D], tuple[tuple[int, int], ...]]:
    z0 = room.floor_elevation_m
    z1 = z0 + room.height_m
    x0, x1 = room.x_m, room.x2_m
    y0, y1 = room.y_m, room.y2_m
    vertices = [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    ]
    edges = (
        (0, 1), (1, 2), (2, 3), (3, 0),
        (4, 5), (5, 6), (6, 7), (7, 4),
        (0, 4), (1, 5), (2, 6), (3, 7),
    )
    return vertices, edges


def object_prism(obj: LayoutObject, floor: Floor) -> tuple[list[Point3D], tuple[tuple[int, int], ...]]:
    room = None
    if obj.room_id is not None:
        try:
            room = floor.room_by_id(obj.room_id)
        except KeyError:
            room = None
    ceiling_kind = obj.kind in {"supply_diffuser", "return_grille", "exhaust_grille", "ffu", "sensor"}
    base_z = obj.z_m + floor.elevation_m
    if ceiling_kind and room is not None and obj.z_m == 0.0:
        base_z = room.floor_elevation_m + room.height_m - obj.height_m
    width, depth = obj.width_m, obj.depth_m
    if int(round(obj.orientation_deg / 90.0)) % 2:
        width, depth = depth, width
    x0 = obj.x_m - width / 2.0
    x1 = obj.x_m + width / 2.0
    y0 = obj.y_m - depth / 2.0
    y1 = obj.y_m + depth / 2.0
    z0, z1 = base_z, base_z + obj.height_m
    vertices = [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    ]
    edges = (
        (0, 1), (1, 2), (2, 3), (3, 0),
        (4, 5), (5, 6), (6, 7), (7, 4),
        (0, 4), (1, 5), (2, 6), (3, 7),
    )
    return vertices, edges


def point_in_polygon(point: tuple[float, float], polygon: Iterable[tuple[float, float]]) -> bool:
    x, y = point
    points = list(polygon)
    if len(points) < 3:
        return False
    inside = False
    j = len(points) - 1
    for i, (xi, yi) in enumerate(points):
        xj, yj = points[j]
        intersects = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-15) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside
