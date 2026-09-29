from __future__ import annotations

from hashlib import sha256
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable

from .spatial_integrity import (
    DEVICE_TYPES,
    SPATIAL_LAYOUT_VERSION,
    SPATIAL_METADATA_KEY,
    validate_spatial_layout_document,
)


IFC_LINK_METADATA_KEY = "ifc_link"
IFC_LINK_SCHEMA = "cleanroomx.ifc-link"
IFC_LINK_SCHEMA_VERSION = 1
IFC_SEMANTICS_SCHEMA = "cleanroomx.ifc-semantics"
IFC_SEMANTICS_SCHEMA_VERSION = 1

_IFC_DEVICE_TYPES = {
    "IfcDoor": "door",
    "IfcWindow": "window",
    "IfcAirTerminal": "supply",
    "IfcFlowTerminal": "supply",
    "IfcSensor": "sensor",
    "IfcFlowController": "equipment",
    "IfcUnitaryEquipment": "equipment",
    "IfcFan": "equipment",
    "IfcPump": "equipment",
    "IfcFurnishingElement": "equipment",
}


class IfcImportError(ValueError):
    """Raised when IFC data cannot be converted into a safe CleanroomX layout."""


def _non_empty_text(value: Any, fallback: str = "") -> str:
    text = str(value).strip() if value is not None else ""
    return text or fallback


def _finite_number(value: Any, *, field: str, default: float | None = None) -> float:
    if value is None and default is not None:
        return default
    if isinstance(value, bool):
        raise IfcImportError(f"{field} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise IfcImportError(f"{field} must be a finite number") from exc
    if not math.isfinite(number):
        raise IfcImportError(f"{field} must be a finite number")
    return number


def _positive_number(value: Any, *, field: str) -> float:
    number = _finite_number(value, field=field)
    if number <= 0:
        raise IfcImportError(f"{field} must be greater than zero")
    return number


def _optional_positive_number(value: Any, *, field: str) -> float | None:
    if value is None:
        return None
    return _positive_number(value, field=field)


def _slug(value: str, *, fallback: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z]+", "-", value).strip("-").lower()
    return slug or fallback


def _unique_id(preferred: str, used: set[str], *, fallback: str) -> str:
    base = _slug(preferred, fallback=fallback)
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _ifc_managed_layout_sha256(layout: Any) -> str:
    if not isinstance(layout, dict):
        raise IfcImportError("IFC-linked spatial layout must be an object")
    managed = {key: value for key, value in layout.items() if key != "view"}
    return sha256(_canonical_json(managed)).hexdigest()


def _device_type(ifc_class: str, predefined_type: str = "") -> str:
    if ifc_class == "IfcAirTerminal":
        token = predefined_type.upper()
        if "RETURN" in token:
            return "return"
        if "EXHAUST" in token:
            return "exhaust"
        if "SUPPLY" in token:
            return "supply"
    return _IFC_DEVICE_TYPES.get(ifc_class, "equipment")


def normalize_ifc_semantic_records(
    records: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Normalize IFC-derived records into a deterministic semantic bridge document.

    The bridge intentionally uses plain records so integrations and tests do not
    require IfcOpenShell. Geometry is limited to CleanroomX's current axis-aligned
    room/device model. Arbitrary solids remain outside this semantic layer.
    """
    if isinstance(records, (str, bytes, bytearray)) or not isinstance(
        records, Iterable
    ):
        raise IfcImportError("IFC semantic records must be an iterable of objects")

    normalized: list[dict[str, Any]] = []
    seen_global_ids: set[str] = set()
    for index, raw in enumerate(records):
        if not isinstance(raw, dict):
            raise IfcImportError(f"IFC semantic record {index} must be an object")

        ifc_class = _non_empty_text(raw.get("ifc_class"))
        if not ifc_class.startswith("Ifc"):
            raise IfcImportError(
                f"IFC semantic record {index}.ifc_class must be an IFC entity name"
            )

        global_id = _non_empty_text(raw.get("global_id"))
        if not global_id:
            raise IfcImportError(
                f"IFC semantic record {index}.global_id is required"
            )
        if global_id in seen_global_ids:
            raise IfcImportError(f"duplicate IFC GlobalId {global_id!r}")
        seen_global_ids.add(global_id)

        record: dict[str, Any] = {
            "global_id": global_id,
            "ifc_class": ifc_class,
            "name": _non_empty_text(raw.get("name"), global_id),
            "x_m": _finite_number(
                raw.get("x_m"), field=f"{global_id}.x_m", default=0.0
            ),
            "y_m": _finite_number(
                raw.get("y_m"), field=f"{global_id}.y_m", default=0.0
            ),
            "z_m": _finite_number(
                raw.get("z_m"), field=f"{global_id}.z_m", default=0.0
            ),
        }

        if ifc_class == "IfcSpace":
            record["length_m"] = _positive_number(
                raw.get("length_m"), field=f"{global_id}.length_m"
            )
            record["width_m"] = _positive_number(
                raw.get("width_m"), field=f"{global_id}.width_m"
            )
            record["height_m"] = _positive_number(
                raw.get("height_m"), field=f"{global_id}.height_m"
            )
            for field in ("classification", "analysis_room_name"):
                value = _non_empty_text(raw.get(field))
                if value:
                    record[field] = value
        else:
            room_global_id = _non_empty_text(raw.get("room_global_id"))
            if room_global_id:
                record["room_global_id"] = room_global_id
            predefined_type = _non_empty_text(raw.get("predefined_type"))
            if predefined_type:
                record["predefined_type"] = predefined_type
            width = _optional_positive_number(
                raw.get("width_m"), field=f"{global_id}.width_m"
            )
            height = _optional_positive_number(
                raw.get("height_m"), field=f"{global_id}.height_m"
            )
            if width is not None:
                record["width_m"] = width
            if height is not None:
                record["height_m"] = height
            record["orientation_deg"] = _finite_number(
                raw.get("orientation_deg"),
                field=f"{global_id}.orientation_deg",
                default=0.0,
            )

        normalized.append(record)

    normalized.sort(key=lambda item: (item["ifc_class"], item["global_id"]))
    space_ids = {
        item["global_id"]
        for item in normalized
        if item["ifc_class"] == "IfcSpace"
    }
    for item in normalized:
        room_global_id = item.get("room_global_id")
        if room_global_id and room_global_id not in space_ids:
            raise IfcImportError(
                f"IFC entity {item['global_id']!r} references missing space "
                f"{room_global_id!r}"
            )

    document = {
        "schema": IFC_SEMANTICS_SCHEMA,
        "schema_version": IFC_SEMANTICS_SCHEMA_VERSION,
        "records": normalized,
    }
    document["semantic_sha256"] = sha256(_canonical_json(document)).hexdigest()
    return document


def layout_from_ifc_semantics(
    semantics: dict[str, Any],
    *,
    id_bindings: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Convert a verified semantic bridge document into a CleanroomX layout.

    id_bindings may bind IFC GlobalId values to existing CleanroomX spatial IDs.
    Re-import uses this to avoid identity churn when IFC entities are renamed.
    """
    if not isinstance(semantics, dict):
        raise IfcImportError("IFC semantics must be an object")
    if semantics.get("schema") != IFC_SEMANTICS_SCHEMA:
        raise IfcImportError("unsupported IFC semantic schema")
    if semantics.get("schema_version") != IFC_SEMANTICS_SCHEMA_VERSION:
        raise IfcImportError("unsupported IFC semantic schema version")

    records = semantics.get("records")
    if not isinstance(records, list):
        raise IfcImportError("IFC semantics records must be an array")
    if id_bindings is None:
        id_bindings = {}
    elif not isinstance(id_bindings, dict):
        raise IfcImportError("IFC id_bindings must be an object")
    else:
        id_bindings = {
            _non_empty_text(global_id): _non_empty_text(spatial_id)
            for global_id, spatial_id in id_bindings.items()
            if _non_empty_text(global_id) and _non_empty_text(spatial_id)
        }

    checked = normalize_ifc_semantic_records(records)
    expected_digest = semantics.get("semantic_sha256")
    if expected_digest is not None and expected_digest != checked["semantic_sha256"]:
        raise IfcImportError("IFC semantic digest does not match its records")

    layout: dict[str, Any] = {
        "version": SPATIAL_LAYOUT_VERSION,
        "floor": {
            "id": "floor-1",
            "name": "IFC import",
            "elevation_m": 0.0,
            "default_ceiling_height_m": 3.0,
            "units": "m",
        },
        "grid_m": 0.5,
        "rooms": [],
        "devices": [],
        "view": {
            "zoom_2d": 1.0,
            "pan_x": 0.0,
            "pan_y": 0.0,
            "azimuth_deg": 35.0,
            "elevation_deg": 28.0,
            "zoom_3d": 1.0,
            "pan_3d_x": 0.0,
            "pan_3d_y": 0.0,
            "snap_to_grid": True,
            "show_pressure": True,
            "show_labels": True,
            "show_devices": True,
            "show_relationships": True,
        },
    }

    def bound_or_unique_id(
        global_id: str,
        preferred: str,
        used: set[str],
        *,
        fallback: str,
    ) -> str:
        bound = id_bindings.get(global_id, "")
        if bound:
            if bound in used:
                raise IfcImportError(
                    f"IFC id binding {bound!r} is assigned to more than one entity"
                )
            used.add(bound)
            return bound
        return _unique_id(preferred, used, fallback=fallback)

    used_room_ids: set[str] = set()
    room_id_by_global_id: dict[str, str] = {}
    spaces = [
        item for item in checked["records"] if item["ifc_class"] == "IfcSpace"
    ]
    for index, item in enumerate(spaces):
        room_id = bound_or_unique_id(
            item["global_id"],
            item["name"],
            used_room_ids,
            fallback=f"ifc-space-{index + 1}",
        )
        room_id_by_global_id[item["global_id"]] = room_id
        room = {
            "id": room_id,
            "name": item["name"],
            "x_m": item["x_m"],
            "y_m": item["y_m"],
            "length_m": item["length_m"],
            "width_m": item["width_m"],
            "height_m": item["height_m"],
            "floor_elevation_m": item["z_m"],
        }
        for field in ("classification", "analysis_room_name"):
            if field in item:
                room[field] = item[field]
        layout["rooms"].append(room)

    used_device_ids: set[str] = set()
    device_records = [
        item for item in checked["records"] if item["ifc_class"] != "IfcSpace"
    ]
    for index, item in enumerate(device_records):
        device_type = _device_type(
            item["ifc_class"], _non_empty_text(item.get("predefined_type"))
        )
        if device_type not in DEVICE_TYPES:
            device_type = "equipment"
        device = {
            "id": bound_or_unique_id(
                item["global_id"],
                item["name"],
                used_device_ids,
                fallback=f"ifc-device-{index + 1}",
            ),
            "type": device_type,
            "name": item["name"],
            "room_id": room_id_by_global_id.get(item.get("room_global_id")),
            "x_m": item["x_m"],
            "y_m": item["y_m"],
            "z_m": item["z_m"],
            "orientation_deg": item["orientation_deg"],
        }
        if "width_m" in item:
            device["width_m"] = item["width_m"]
        if "height_m" in item:
            device["height_m"] = item["height_m"]
        layout["devices"].append(device)

    validate_spatial_layout_document(layout)
    return layout


def apply_ifc_semantics_to_project(
    project: Any,
    semantics: dict[str, Any],
    *,
    source_name: str,
    source_sha256: str,
    allow_local_changes: bool = False,
) -> dict[str, Any]:
    """Replace project spatial data with a verified, provenance-bound IFC import.

    Re-import preserves CleanroomX spatial IDs for IFC entities that retain the
    same GlobalId. Once an IFC-linked layout has a recorded import digest, local
    spatial edits are rejected by default instead of being overwritten silently.
    """
    metadata = getattr(project, "metadata", None)
    if not isinstance(metadata, dict):
        raise IfcImportError("project metadata must be an object")

    source_name = _non_empty_text(source_name)
    if not source_name:
        raise IfcImportError("source_name is required")
    source_sha256 = _non_empty_text(source_sha256).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
        raise IfcImportError("source_sha256 must be a SHA-256 hex digest")
    if not isinstance(allow_local_changes, bool):
        raise IfcImportError("allow_local_changes must be a boolean")

    previous_link = metadata.get(IFC_LINK_METADATA_KEY)
    current_layout = metadata.get(SPATIAL_METADATA_KEY)
    id_bindings: dict[str, str] = {}
    if isinstance(previous_link, dict):
        raw_bindings = previous_link.get("entity_bindings")
        if isinstance(raw_bindings, dict):
            id_bindings = {
                _non_empty_text(global_id): _non_empty_text(spatial_id)
                for global_id, spatial_id in raw_bindings.items()
                if _non_empty_text(global_id) and _non_empty_text(spatial_id)
            }

        expected_layout_digest = _non_empty_text(
            previous_link.get("layout_sha256")
        ).lower()
        if expected_layout_digest and current_layout is not None:
            try:
                current_layout_digest = _ifc_managed_layout_sha256(current_layout)
            except (TypeError, ValueError) as exc:
                if not allow_local_changes:
                    raise IfcImportError(
                        "existing IFC-linked spatial layout has local changes; "
                        "re-import would overwrite them"
                    ) from exc
            else:
                if (
                    current_layout_digest != expected_layout_digest
                    and not allow_local_changes
                ):
                    raise IfcImportError(
                        "existing IFC-linked spatial layout has local changes; "
                        "re-import would overwrite them"
                    )

    layout = layout_from_ifc_semantics(semantics, id_bindings=id_bindings)
    if isinstance(previous_link, dict) and isinstance(current_layout, dict):
        current_view = current_layout.get("view")
        if isinstance(current_view, dict):
            layout["view"] = dict(current_view)
            validate_spatial_layout_document(layout)

    checked = normalize_ifc_semantic_records(semantics["records"])

    spaces = [
        item for item in checked["records"] if item["ifc_class"] == "IfcSpace"
    ]
    devices = [
        item for item in checked["records"] if item["ifc_class"] != "IfcSpace"
    ]
    entity_bindings = {
        item["global_id"]: room["id"]
        for item, room in zip(spaces, layout["rooms"])
    }
    entity_bindings.update(
        {
            item["global_id"]: device["id"]
            for item, device in zip(devices, layout["devices"])
        }
    )
    layout_sha256 = _ifc_managed_layout_sha256(layout)

    metadata[SPATIAL_METADATA_KEY] = layout
    metadata[IFC_LINK_METADATA_KEY] = {
        "schema": IFC_LINK_SCHEMA,
        "schema_version": IFC_LINK_SCHEMA_VERSION,
        "source_name": source_name,
        "source_sha256": source_sha256,
        "semantic_sha256": checked["semantic_sha256"],
        "layout_sha256": layout_sha256,
        "entity_bindings": entity_bindings,
        "room_count": len(layout["rooms"]),
        "device_count": len(layout["devices"]),
    }
    return layout


def _placement_xyz_m(entity: Any, unit_scale: float) -> tuple[float, float, float]:
    """Resolve nested IfcLocalPlacement translations into metres."""
    x = y = z = 0.0
    placement = getattr(entity, "ObjectPlacement", None)
    visited: set[int] = set()
    while placement is not None:
        marker = id(placement)
        if marker in visited:
            raise IfcImportError("cyclic IFC object placement detected")
        visited.add(marker)
        relative = getattr(placement, "RelativePlacement", None)
        location = getattr(relative, "Location", None)
        coordinates = getattr(location, "Coordinates", None)
        if coordinates:
            values = list(coordinates)
            if len(values) > 0:
                x += float(values[0]) * unit_scale
            if len(values) > 1:
                y += float(values[1]) * unit_scale
            if len(values) > 2:
                z += float(values[2]) * unit_scale
        placement = getattr(placement, "PlacementRelTo", None)
    return x, y, z


def _space_dimensions_m(
    entity: Any,
    unit_scale: float,
    element_util: Any,
) -> tuple[float, float, float]:
    quantities = element_util.get_psets(entity, qtos_only=True)
    candidates: dict[str, float] = {}
    if isinstance(quantities, dict):
        for values in quantities.values():
            if not isinstance(values, dict):
                continue
            for key, value in values.items():
                if key in {"Length", "Width", "Height"} and isinstance(
                    value, (int, float)
                ):
                    candidates.setdefault(key, float(value) * unit_scale)
    try:
        return (
            _positive_number(
                candidates.get("Length"), field=f"{entity.GlobalId}.Length"
            ),
            _positive_number(
                candidates.get("Width"), field=f"{entity.GlobalId}.Width"
            ),
            _positive_number(
                candidates.get("Height"), field=f"{entity.GlobalId}.Height"
            ),
        )
    except IfcImportError as exc:
        raise IfcImportError(
            f"IfcSpace {getattr(entity, 'GlobalId', '?')!r} needs positive "
            "Length, Width, and Height base quantities for the current "
            "CleanroomX axis-aligned IFC bridge"
        ) from exc


def _containing_space_global_id(entity: Any) -> str:
    for relation in getattr(entity, "ContainedInStructure", ()) or ():
        structure = getattr(relation, "RelatingStructure", None)
        try:
            is_space = bool(structure and structure.is_a("IfcSpace"))
        except Exception:
            is_space = False
        if is_space:
            return _non_empty_text(getattr(structure, "GlobalId", ""))
    return ""


def extract_ifc_semantics(
    path: str | Path,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Read an IFC file through optional IfcOpenShell.

    This stage consumes semantic entities, space base quantities, and placement
    origins. It does not claim complete B-Rep/tessellation interoperability.
    """
    source = Path(path)
    payload = source.read_bytes()
    source_digest = sha256(payload).hexdigest()

    try:
        import ifcopenshell  # type: ignore[import-not-found]
        import ifcopenshell.util.element as element_util  # type: ignore[import-not-found]
        import ifcopenshell.util.unit as unit_util  # type: ignore[import-not-found]
    except ImportError as exc:
        raise IfcImportError(
            "IfcOpenShell is required to read .ifc files; install CleanroomX "
            "with the optional 'bim' dependency"
        ) from exc

    try:
        model = ifcopenshell.open(str(source))
    except Exception as exc:
        raise IfcImportError(f"unable to open IFC file {source}") from exc

    unit_scale = float(unit_util.calculate_unit_scale(model))
    records: list[dict[str, Any]] = []

    for entity in model.by_type("IfcSpace"):
        x, y, z = _placement_xyz_m(entity, unit_scale)
        length, width, height = _space_dimensions_m(
            entity, unit_scale, element_util
        )
        global_id = _non_empty_text(getattr(entity, "GlobalId", ""))
        records.append(
            {
                "global_id": global_id,
                "ifc_class": "IfcSpace",
                "name": _non_empty_text(
                    getattr(entity, "LongName", None),
                    _non_empty_text(getattr(entity, "Name", None), global_id),
                ),
                "x_m": x,
                "y_m": y,
                "z_m": z,
                "length_m": length,
                "width_m": width,
                "height_m": height,
            }
        )

    seen = {item["global_id"] for item in records}
    for ifc_class in _IFC_DEVICE_TYPES:
        try:
            entities = model.by_type(ifc_class)
        except Exception:
            continue
        for entity in entities:
            global_id = _non_empty_text(getattr(entity, "GlobalId", ""))
            if not global_id or global_id in seen:
                continue
            seen.add(global_id)
            x, y, z = _placement_xyz_m(entity, unit_scale)
            record: dict[str, Any] = {
                "global_id": global_id,
                "ifc_class": ifc_class,
                "name": _non_empty_text(
                    getattr(entity, "Name", None), global_id
                ),
                "x_m": x,
                "y_m": y,
                "z_m": z,
            }
            room_global_id = _containing_space_global_id(entity)
            if room_global_id:
                record["room_global_id"] = room_global_id
            predefined_type = _non_empty_text(
                getattr(entity, "PredefinedType", None)
            )
            if predefined_type:
                record["predefined_type"] = predefined_type
            for source_field, target_field in (
                ("OverallWidth", "width_m"),
                ("OverallHeight", "height_m"),
            ):
                value = getattr(entity, source_field, None)
                if isinstance(value, (int, float)) and float(value) > 0:
                    record[target_field] = float(value) * unit_scale
            records.append(record)

    semantics = normalize_ifc_semantic_records(records)
    return semantics, {
        "source_name": source.name,
        "source_sha256": source_digest,
    }
