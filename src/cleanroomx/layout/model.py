from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Iterable
import uuid

LAYOUT_SCHEMA = "cleanroomx.layout"
LAYOUT_SCHEMA_VERSION = 1

OBJECT_KINDS = frozenset({
    "door",
    "supply_diffuser",
    "return_grille",
    "exhaust_grille",
    "ffu",
    "equipment",
    "sensor",
    "transfer_opening",
})
PRESSURE_SOURCES = frozenset({"user", "calculated", "unavailable"})


class LayoutFormatError(ValueError):
    pass


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _require_finite(value: Any, field_name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LayoutFormatError(f"{field_name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise LayoutFormatError(f"{field_name} must be finite")
    if positive and result <= 0.0:
        raise LayoutFormatError(f"{field_name} must be > 0")
    return result


def _require_string(value: Any, field_name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise LayoutFormatError(f"{field_name} must be a string")
    result = value.strip()
    if not allow_empty and not result:
        raise LayoutFormatError(f"{field_name} must be a non-empty string")
    return result


def _optional_string(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_string(value, field_name)


@dataclass(eq=True)
class GridConfig:
    size_m: float = 0.5
    snap_enabled: bool = True
    visible: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "size_m": self.size_m,
            "snap_enabled": self.snap_enabled,
            "visible": self.visible,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "GridConfig":
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise LayoutFormatError("grid must be an object")
        size = _require_finite(data.get("size_m", 0.5), "grid.size_m", positive=True)
        snap = data.get("snap_enabled", True)
        visible = data.get("visible", True)
        if not isinstance(snap, bool) or not isinstance(visible, bool):
            raise LayoutFormatError("grid snap_enabled and visible must be booleans")
        return cls(size_m=size, snap_enabled=snap, visible=visible)


@dataclass(eq=True)
class Room:
    id: str
    name: str
    x_m: float
    y_m: float
    width_m: float
    depth_m: float
    height_m: float = 3.0
    floor_elevation_m: float = 0.0
    pressure_pa: float | None = None
    pressure_source: str = "unavailable"
    classification: dict[str, Any] = field(default_factory=dict)
    analysis_room_ref: str | None = None

    @property
    def area_m2(self) -> float:
        return self.width_m * self.depth_m

    @property
    def volume_m3(self) -> float:
        return self.area_m2 * self.height_m

    @property
    def x2_m(self) -> float:
        return self.x_m + self.width_m

    @property
    def y2_m(self) -> float:
        return self.y_m + self.depth_m

    def contains(self, x_m: float, y_m: float, *, tolerance_m: float = 0.0) -> bool:
        return (
            self.x_m - tolerance_m <= x_m <= self.x2_m + tolerance_m
            and self.y_m - tolerance_m <= y_m <= self.y2_m + tolerance_m
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "x_m": self.x_m,
            "y_m": self.y_m,
            "width_m": self.width_m,
            "depth_m": self.depth_m,
            "height_m": self.height_m,
            "floor_elevation_m": self.floor_elevation_m,
            "pressure_pa": self.pressure_pa,
            "pressure_source": self.pressure_source,
            "classification": self.classification,
            "analysis_room_ref": self.analysis_room_ref,
        }

    @classmethod
    def create(
        cls,
        name: str,
        x_m: float,
        y_m: float,
        width_m: float,
        depth_m: float,
        *,
        height_m: float = 3.0,
        floor_elevation_m: float = 0.0,
        pressure_pa: float | None = None,
        pressure_source: str | None = None,
        classification: dict[str, Any] | None = None,
        analysis_room_ref: str | None = None,
    ) -> "Room":
        return cls.from_dict({
            "id": new_id("room"),
            "name": name,
            "x_m": x_m,
            "y_m": y_m,
            "width_m": width_m,
            "depth_m": depth_m,
            "height_m": height_m,
            "floor_elevation_m": floor_elevation_m,
            "pressure_pa": pressure_pa,
            "pressure_source": pressure_source or ("user" if pressure_pa is not None else "unavailable"),
            "classification": classification or {},
            "analysis_room_ref": analysis_room_ref,
        })

    @classmethod
    def from_dict(cls, data: Any) -> "Room":
        if not isinstance(data, dict):
            raise LayoutFormatError("room must be an object")
        pressure = data.get("pressure_pa")
        if pressure is not None:
            pressure = _require_finite(pressure, "room.pressure_pa")
        source = data.get("pressure_source", "user" if pressure is not None else "unavailable")
        source = _require_string(source, "room.pressure_source")
        if source not in PRESSURE_SOURCES:
            raise LayoutFormatError(
                "room.pressure_source must be one of user, calculated, unavailable"
            )
        if pressure is None and source != "unavailable":
            raise LayoutFormatError("room pressure source must be unavailable when pressure_pa is null")
        classification = data.get("classification", {})
        if not isinstance(classification, dict):
            raise LayoutFormatError("room.classification must be an object")
        return cls(
            id=_require_string(data.get("id"), "room.id"),
            name=_require_string(data.get("name"), "room.name"),
            x_m=_require_finite(data.get("x_m"), "room.x_m"),
            y_m=_require_finite(data.get("y_m"), "room.y_m"),
            width_m=_require_finite(data.get("width_m"), "room.width_m", positive=True),
            depth_m=_require_finite(data.get("depth_m"), "room.depth_m", positive=True),
            height_m=_require_finite(data.get("height_m", 3.0), "room.height_m", positive=True),
            floor_elevation_m=_require_finite(
                data.get("floor_elevation_m", 0.0), "room.floor_elevation_m"
            ),
            pressure_pa=pressure,
            pressure_source=source,
            classification=dict(classification),
            analysis_room_ref=_optional_string(data.get("analysis_room_ref"), "room.analysis_room_ref"),
        )


@dataclass(eq=True)
class LayoutObject:
    id: str
    kind: str
    name: str
    x_m: float
    y_m: float
    z_m: float = 0.0
    width_m: float = 0.6
    depth_m: float = 0.6
    height_m: float = 0.2
    room_id: str | None = None
    orientation_deg: float = 0.0
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "x_m": self.x_m,
            "y_m": self.y_m,
            "z_m": self.z_m,
            "width_m": self.width_m,
            "depth_m": self.depth_m,
            "height_m": self.height_m,
            "room_id": self.room_id,
            "orientation_deg": self.orientation_deg,
            "properties": self.properties,
        }

    @classmethod
    def create(
        cls,
        kind: str,
        x_m: float,
        y_m: float,
        *,
        name: str | None = None,
        room_id: str | None = None,
        z_m: float = 0.0,
        width_m: float | None = None,
        depth_m: float | None = None,
        height_m: float | None = None,
        orientation_deg: float = 0.0,
        properties: dict[str, Any] | None = None,
    ) -> "LayoutObject":
        defaults = {
            "door": (0.9, 0.12, 2.1),
            "transfer_opening": (0.6, 0.12, 0.6),
            "supply_diffuser": (0.6, 0.6, 0.08),
            "return_grille": (0.6, 0.3, 0.08),
            "exhaust_grille": (0.6, 0.3, 0.08),
            "ffu": (1.2, 0.6, 0.25),
            "equipment": (1.0, 0.8, 1.5),
            "sensor": (0.15, 0.15, 0.15),
        }
        if kind not in OBJECT_KINDS:
            raise LayoutFormatError(f"unsupported layout object kind: {kind}")
        dw, dd, dh = defaults[kind]
        label = name or kind.replace("_", " ").title()
        return cls.from_dict({
            "id": new_id(kind),
            "kind": kind,
            "name": label,
            "x_m": x_m,
            "y_m": y_m,
            "z_m": z_m,
            "width_m": dw if width_m is None else width_m,
            "depth_m": dd if depth_m is None else depth_m,
            "height_m": dh if height_m is None else height_m,
            "room_id": room_id,
            "orientation_deg": orientation_deg,
            "properties": properties or {},
        })

    @classmethod
    def from_dict(cls, data: Any) -> "LayoutObject":
        if not isinstance(data, dict):
            raise LayoutFormatError("layout object must be an object")
        kind = _require_string(data.get("kind"), "object.kind")
        if kind not in OBJECT_KINDS:
            raise LayoutFormatError(f"unsupported layout object kind: {kind}")
        properties = data.get("properties", {})
        if not isinstance(properties, dict):
            raise LayoutFormatError("object.properties must be an object")
        return cls(
            id=_require_string(data.get("id"), "object.id"),
            kind=kind,
            name=_require_string(data.get("name", kind.replace("_", " ").title()), "object.name"),
            x_m=_require_finite(data.get("x_m"), "object.x_m"),
            y_m=_require_finite(data.get("y_m"), "object.y_m"),
            z_m=_require_finite(data.get("z_m", 0.0), "object.z_m"),
            width_m=_require_finite(data.get("width_m", 0.6), "object.width_m", positive=True),
            depth_m=_require_finite(data.get("depth_m", 0.6), "object.depth_m", positive=True),
            height_m=_require_finite(data.get("height_m", 0.2), "object.height_m", positive=True),
            room_id=_optional_string(data.get("room_id"), "object.room_id"),
            orientation_deg=_require_finite(data.get("orientation_deg", 0.0), "object.orientation_deg"),
            properties=dict(properties),
        )


@dataclass(eq=True)
class Floor:
    id: str
    name: str
    elevation_m: float = 0.0
    default_ceiling_height_m: float = 3.0
    units: str = "m"
    grid: GridConfig = field(default_factory=GridConfig)
    rooms: list[Room] = field(default_factory=list)
    objects: list[LayoutObject] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "elevation_m": self.elevation_m,
            "default_ceiling_height_m": self.default_ceiling_height_m,
            "units": self.units,
            "grid": self.grid.to_dict(),
            "rooms": [room.to_dict() for room in self.rooms],
            "objects": [obj.to_dict() for obj in self.objects],
        }

    @classmethod
    def create(
        cls,
        name: str = "Floor 1",
        *,
        elevation_m: float = 0.0,
        default_ceiling_height_m: float = 3.0,
        units: str = "m",
    ) -> "Floor":
        return cls.from_dict({
            "id": new_id("floor"),
            "name": name,
            "elevation_m": elevation_m,
            "default_ceiling_height_m": default_ceiling_height_m,
            "units": units,
            "grid": GridConfig().to_dict(),
            "rooms": [],
            "objects": [],
        })

    @classmethod
    def from_dict(cls, data: Any) -> "Floor":
        if not isinstance(data, dict):
            raise LayoutFormatError("floor must be an object")
        units = _require_string(data.get("units", "m"), "floor.units")
        if units != "m":
            raise LayoutFormatError("only metre-based spatial geometry is currently supported")
        rooms_raw = data.get("rooms", [])
        objects_raw = data.get("objects", [])
        if not isinstance(rooms_raw, list) or not isinstance(objects_raw, list):
            raise LayoutFormatError("floor rooms and objects must be arrays")
        return cls(
            id=_require_string(data.get("id"), "floor.id"),
            name=_require_string(data.get("name"), "floor.name"),
            elevation_m=_require_finite(data.get("elevation_m", 0.0), "floor.elevation_m"),
            default_ceiling_height_m=_require_finite(
                data.get("default_ceiling_height_m", 3.0),
                "floor.default_ceiling_height_m",
                positive=True,
            ),
            units=units,
            grid=GridConfig.from_dict(data.get("grid")),
            rooms=[Room.from_dict(item) for item in rooms_raw],
            objects=[LayoutObject.from_dict(item) for item in objects_raw],
        )

    def room_by_id(self, room_id: str) -> Room:
        for room in self.rooms:
            if room.id == room_id:
                return room
        raise KeyError(room_id)

    def object_by_id(self, object_id: str) -> LayoutObject:
        for obj in self.objects:
            if obj.id == object_id:
                return obj
        raise KeyError(object_id)

    def entity_by_id(self, entity_id: str) -> Room | LayoutObject:
        try:
            return self.room_by_id(entity_id)
        except KeyError:
            return self.object_by_id(entity_id)

    def remove_entity(self, entity_id: str) -> bool:
        old_room_count = len(self.rooms)
        self.rooms = [room for room in self.rooms if room.id != entity_id]
        if len(self.rooms) != old_room_count:
            self.objects = [obj for obj in self.objects if obj.room_id != entity_id]
            return True
        old_object_count = len(self.objects)
        self.objects = [obj for obj in self.objects if obj.id != entity_id]
        return len(self.objects) != old_object_count


@dataclass(eq=True)
class SpatialLayout:
    floors: list[Floor] = field(default_factory=list)
    active_floor_id: str | None = None

    @classmethod
    def empty(cls) -> "SpatialLayout":
        return cls()

    def ensure_floor(self) -> Floor:
        if not self.floors:
            floor = Floor.create()
            self.floors.append(floor)
            self.active_floor_id = floor.id
            return floor
        if self.active_floor_id is None or not any(
            floor.id == self.active_floor_id for floor in self.floors
        ):
            self.active_floor_id = self.floors[0].id
        return self.floor_by_id(self.active_floor_id)

    def floor_by_id(self, floor_id: str) -> Floor:
        for floor in self.floors:
            if floor.id == floor_id:
                return floor
        raise KeyError(floor_id)

    def active_floor(self) -> Floor | None:
        if self.active_floor_id is None:
            return None
        try:
            return self.floor_by_id(self.active_floor_id)
        except KeyError:
            return None

    def iter_rooms(self) -> Iterable[Room]:
        for floor in self.floors:
            yield from floor.rooms

    def iter_objects(self) -> Iterable[LayoutObject]:
        for floor in self.floors:
            yield from floor.objects

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": LAYOUT_SCHEMA,
            "schema_version": LAYOUT_SCHEMA_VERSION,
            "active_floor_id": self.active_floor_id,
            "floors": [floor.to_dict() for floor in self.floors],
        }

    @classmethod
    def from_dict(cls, data: Any) -> "SpatialLayout":
        if data is None:
            return cls.empty()
        if not isinstance(data, dict):
            raise LayoutFormatError("layout must be an object")
        if data.get("schema", LAYOUT_SCHEMA) != LAYOUT_SCHEMA:
            raise LayoutFormatError(f"layout schema must be {LAYOUT_SCHEMA!r}")
        version = data.get("schema_version", LAYOUT_SCHEMA_VERSION)
        if not isinstance(version, int):
            raise LayoutFormatError("layout.schema_version must be an integer")
        if version != LAYOUT_SCHEMA_VERSION:
            if version > LAYOUT_SCHEMA_VERSION:
                raise LayoutFormatError(
                    f"unsupported future layout schema version {version}; "
                    f"this build supports {LAYOUT_SCHEMA_VERSION}"
                )
            raise LayoutFormatError(f"unsupported legacy layout schema version {version}")
        floors_raw = data.get("floors", [])
        if not isinstance(floors_raw, list):
            raise LayoutFormatError("layout.floors must be an array")
        floors = [Floor.from_dict(item) for item in floors_raw]
        active = data.get("active_floor_id")
        if active is not None:
            active = _require_string(active, "layout.active_floor_id")
        floor_ids = {floor.id for floor in floors}
        if active is not None and active not in floor_ids:
            raise LayoutFormatError("layout.active_floor_id must reference a layout floor")
        return cls(floors=floors, active_floor_id=active)
