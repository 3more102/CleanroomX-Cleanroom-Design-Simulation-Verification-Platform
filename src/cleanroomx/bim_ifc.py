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
IFC_LINK_SCHEMA_VERSION = 2
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


def _canonical_sha256(value: Any) -> str:
    return sha256(_canonical_json(value)).hexdigest()


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


def layout_from_ifc_semantics(semantics: dict[str, Any]) -> dict[str, Any]:
    """Convert a verified semantic bridge document into a CleanroomX layout."""
    if not isinstance(semantics, dict):
        raise IfcImportError("IFC semantics must be an object")
    if semantics.get("schema") != IFC_SEMANTICS_SCHEMA:
        raise IfcImportError("unsupported IFC semantic schema")
    if semantics.get("schema_version") != IFC_SEMANTICS_SCHEMA_VERSION:
        raise IfcImportError("unsupported IFC semantic schema version")

    records = semantics.get("records")
    if not isinstance(records, list):
        raise IfcImportError("IFC semantics records must be an array")

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

    used_room_ids: set[str] = set()
    room_id_by_global_id: dict[str, str] = {}
    spaces = [
        item for item in checked["records"] if item["ifc_class"] == "IfcSpace"
    ]
    for index, item in enumerate(spaces):
        room_id = _unique_id(
            item["name"], used_room_ids, fallback=f"ifc-space-{index + 1}"
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
            "id": _unique_id(
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


def _semantic_spatial_bindings(
    semantics: dict[str, Any],
    layout: dict[str, Any],
) -> list[dict[str, Any]]:
    """Bind normalized IFC GlobalIds to deterministic CleanroomX spatial objects."""
    checked = normalize_ifc_semantic_records(semantics["records"])
    spaces = [
        item for item in checked["records"] if item["ifc_class"] == "IfcSpace"
    ]
    devices = [
        item for item in checked["records"] if item["ifc_class"] != "IfcSpace"
    ]
    if len(spaces) != len(layout["rooms"]) or len(devices) != len(layout["devices"]):
        raise IfcImportError("IFC semantic/layout cardinality mismatch")

    bindings: list[dict[str, Any]] = []
    for record, room in zip(spaces, layout["rooms"]):
        bindings.append(
            {
                "global_id": record["global_id"],
                "ifc_class": record["ifc_class"],
                "kind": "room",
                "spatial_id": room["id"],
                "record_sha256": _canonical_sha256(record),
                "source_spatial_sha256": _canonical_sha256(room),
            }
        )
    for record, device in zip(devices, layout["devices"]):
        bindings.append(
            {
                "global_id": record["global_id"],
                "ifc_class": record["ifc_class"],
                "kind": "device",
                "spatial_id": device["id"],
                "record_sha256": _canonical_sha256(record),
                "source_spatial_sha256": _canonical_sha256(device),
            }
        )
    bindings.sort(key=lambda item: item["global_id"])
    return bindings


def _validate_source_provenance(
    source_name: str,
    source_sha256: str,
) -> tuple[str, str]:
    checked_name = _non_empty_text(source_name)
    if not checked_name:
        raise IfcImportError("source_name is required")
    checked_digest = _non_empty_text(source_sha256).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", checked_digest):
        raise IfcImportError("source_sha256 must be a SHA-256 hex digest")
    return checked_name, checked_digest


def _validate_link_bindings(link: Any) -> list[dict[str, Any]]:
    if not isinstance(link, dict):
        raise IfcImportError(
            "project has no IFC identity link; perform a fresh IFC import first"
        )
    if link.get("schema") != IFC_LINK_SCHEMA:
        raise IfcImportError("unsupported IFC link schema")
    if link.get("schema_version") != IFC_LINK_SCHEMA_VERSION:
        raise IfcImportError(
            "conflict-aware IFC re-import requires IFC link schema version 2; "
            "perform a fresh IFC import to establish GlobalId bindings"
        )
    bindings = link.get("bindings")
    if not isinstance(bindings, list):
        raise IfcImportError("IFC link bindings must be an array")

    seen_global_ids: set[str] = set()
    seen_spatial: set[tuple[str, str]] = set()
    checked: list[dict[str, Any]] = []
    for index, raw in enumerate(bindings):
        if not isinstance(raw, dict):
            raise IfcImportError(f"IFC link binding {index} must be an object")
        global_id = _non_empty_text(raw.get("global_id"))
        if not global_id or global_id in seen_global_ids:
            raise IfcImportError("IFC link bindings contain invalid GlobalId identity")
        seen_global_ids.add(global_id)
        kind = raw.get("kind")
        if kind not in {"room", "device"}:
            raise IfcImportError(f"IFC link binding {global_id!r} has invalid kind")
        spatial_id = _non_empty_text(raw.get("spatial_id"))
        if not spatial_id or (kind, spatial_id) in seen_spatial:
            raise IfcImportError("IFC link bindings contain duplicate spatial identity")
        seen_spatial.add((kind, spatial_id))
        ifc_class = _non_empty_text(raw.get("ifc_class"))
        if not ifc_class.startswith("Ifc"):
            raise IfcImportError(f"IFC link binding {global_id!r} has invalid IFC class")

        binding = {
            "global_id": global_id,
            "ifc_class": ifc_class,
            "kind": kind,
            "spatial_id": spatial_id,
        }
        for field in ("record_sha256", "source_spatial_sha256"):
            digest = _non_empty_text(raw.get(field)).lower()
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise IfcImportError(
                    f"IFC link binding {global_id!r}.{field} must be a SHA-256 digest"
                )
            binding[field] = digest
        checked.append(binding)

    checked.sort(key=lambda item: item["global_id"])
    expected_digest = _non_empty_text(link.get("bindings_sha256")).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_digest):
        raise IfcImportError("IFC link bindings_sha256 must be a SHA-256 digest")
    if expected_digest != _canonical_sha256(checked):
        raise IfcImportError("IFC link binding digest does not match its bindings")
    return checked


def _incoming_objects_by_global_id(
    semantics: dict[str, Any],
    layout: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    checked = normalize_ifc_semantic_records(semantics["records"])
    spaces = [
        item for item in checked["records"] if item["ifc_class"] == "IfcSpace"
    ]
    devices = [
        item for item in checked["records"] if item["ifc_class"] != "IfcSpace"
    ]
    room_objects = {
        record["global_id"]: dict(room)
        for record, room in zip(spaces, layout["rooms"])
    }
    device_objects = {
        record["global_id"]: dict(device)
        for record, device in zip(devices, layout["devices"])
    }
    return room_objects, device_objects


def _stabilize_incoming_spatial_ids(
    *,
    semantics: dict[str, Any],
    incoming_layout: dict[str, Any],
    bindings: list[dict[str, Any]],
    current_layout: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    checked = normalize_ifc_semantic_records(semantics["records"])
    room_objects, device_objects = _incoming_objects_by_global_id(
        checked, incoming_layout
    )
    binding_by_global_id = {item["global_id"]: item for item in bindings}

    bound_room_ids = {
        item["spatial_id"] for item in bindings if item["kind"] == "room"
    }
    bound_device_ids = {
        item["spatial_id"] for item in bindings if item["kind"] == "device"
    }
    used_room_ids = {
        room["id"]
        for room in current_layout["rooms"]
        if room["id"] not in bound_room_ids
    }
    used_device_ids = {
        device["id"]
        for device in current_layout["devices"]
        if device["id"] not in bound_device_ids
    }

    room_id_by_global_id: dict[str, str] = {}
    spaces = [
        item for item in checked["records"] if item["ifc_class"] == "IfcSpace"
    ]
    for index, record in enumerate(spaces):
        global_id = record["global_id"]
        room = room_objects[global_id]
        previous = binding_by_global_id.get(global_id)
        if previous is not None:
            if previous["kind"] != "room":
                raise IfcImportError(
                    f"IFC GlobalId {global_id!r} changed spatial kind"
                )
            spatial_id = previous["spatial_id"]
            if spatial_id in used_room_ids:
                raise IfcImportError(
                    f"IFC room identity {spatial_id!r} collides with a local room"
                )
            used_room_ids.add(spatial_id)
        else:
            spatial_id = _unique_id(
                room["id"],
                used_room_ids,
                fallback=f"ifc-space-{index + 1}",
            )
        room["id"] = spatial_id
        room_id_by_global_id[global_id] = spatial_id

    devices = [
        item for item in checked["records"] if item["ifc_class"] != "IfcSpace"
    ]
    for index, record in enumerate(devices):
        global_id = record["global_id"]
        device = device_objects[global_id]
        previous = binding_by_global_id.get(global_id)
        if previous is not None:
            if previous["kind"] != "device":
                raise IfcImportError(
                    f"IFC GlobalId {global_id!r} changed spatial kind"
                )
            spatial_id = previous["spatial_id"]
            if spatial_id in used_device_ids:
                raise IfcImportError(
                    f"IFC device identity {spatial_id!r} collides with a local device"
                )
            used_device_ids.add(spatial_id)
        else:
            spatial_id = _unique_id(
                device["id"],
                used_device_ids,
                fallback=f"ifc-device-{index + 1}",
            )
        device["id"] = spatial_id
        room_global_id = record.get("room_global_id")
        device["room_id"] = (
            room_id_by_global_id.get(room_global_id)
            if room_global_id
            else None
        )

    return room_objects, device_objects


def _plan_ifc_semantic_reimport(
    project: Any,
    semantics: dict[str, Any],
    *,
    source_name: str,
    source_sha256: str,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    list[dict[str, Any]],
    dict[str, Any],
]:
    metadata = getattr(project, "metadata", None)
    if not isinstance(metadata, dict):
        raise IfcImportError("project metadata must be an object")
    checked_name, checked_source_digest = _validate_source_provenance(
        source_name, source_sha256
    )

    current_layout = metadata.get(SPATIAL_METADATA_KEY)
    if not isinstance(current_layout, dict):
        raise IfcImportError("project has no spatial layout to re-import")
    validate_spatial_layout_document(current_layout)

    link = metadata.get(IFC_LINK_METADATA_KEY)
    bindings = _validate_link_bindings(link)
    binding_by_global_id = {item["global_id"]: item for item in bindings}

    checked_semantics = normalize_ifc_semantic_records(semantics["records"])
    supplied_digest = semantics.get("semantic_sha256")
    if (
        supplied_digest is not None
        and supplied_digest != checked_semantics["semantic_sha256"]
    ):
        raise IfcImportError("IFC semantic digest does not match its records")

    incoming_layout = layout_from_ifc_semantics(checked_semantics)
    incoming_rooms, incoming_devices = _stabilize_incoming_spatial_ids(
        semantics=checked_semantics,
        incoming_layout=incoming_layout,
        bindings=bindings,
        current_layout=current_layout,
    )
    incoming_by_global_id = {**incoming_rooms, **incoming_devices}

    current_rooms = {room["id"]: room for room in current_layout["rooms"]}
    current_devices = {
        device["id"]: device for device in current_layout["devices"]
    }
    current_by_kind = {"room": current_rooms, "device": current_devices}

    changes: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    action_by_global_id: dict[str, str] = {}

    for binding in bindings:
        global_id = binding["global_id"]
        current = current_by_kind[binding["kind"]].get(binding["spatial_id"])
        incoming = incoming_by_global_id.get(global_id)
        baseline_digest = binding["source_spatial_sha256"]
        local_changed = (
            current is None or _canonical_sha256(current) != baseline_digest
        )
        source_changed = (
            incoming is None or _canonical_sha256(incoming) != baseline_digest
        )

        if current is None and incoming is None:
            action = "removed_both"
        elif current is None:
            action = "conflict" if source_changed else "preserve_local_deletion"
        elif incoming is None:
            action = "conflict" if local_changed else "remove"
        elif not local_changed and not source_changed:
            action = "unchanged"
        elif not local_changed and source_changed:
            action = "update"
        elif local_changed and not source_changed:
            action = "preserve_local"
        elif _canonical_sha256(current) == _canonical_sha256(incoming):
            action = "converged"
        else:
            action = "conflict"

        item = {
            "global_id": global_id,
            "ifc_class": binding["ifc_class"],
            "kind": binding["kind"],
            "spatial_id": binding["spatial_id"],
            "action": action,
            "local_changed": local_changed,
            "source_changed": source_changed,
        }
        changes.append(item)
        action_by_global_id[global_id] = action
        if action == "conflict":
            conflicts.append(item)

    for global_id, incoming in incoming_by_global_id.items():
        if global_id in binding_by_global_id:
            continue
        kind = "room" if global_id in incoming_rooms else "device"
        item = {
            "global_id": global_id,
            "ifc_class": next(
                record["ifc_class"]
                for record in checked_semantics["records"]
                if record["global_id"] == global_id
            ),
            "kind": kind,
            "spatial_id": incoming["id"],
            "action": "add",
            "local_changed": False,
            "source_changed": True,
        }
        changes.append(item)
        action_by_global_id[global_id] = "add"

    merged_layout = {
        key: json.loads(json.dumps(value))
        for key, value in current_layout.items()
    }
    merged_rooms = {
        room["id"]: room for room in merged_layout["rooms"]
    }
    merged_devices = {
        device["id"]: device for device in merged_layout["devices"]
    }

    for binding in bindings:
        global_id = binding["global_id"]
        action = action_by_global_id[global_id]
        target = merged_rooms if binding["kind"] == "room" else merged_devices
        if action == "update":
            target[binding["spatial_id"]] = dict(incoming_by_global_id[global_id])
        elif action in {"remove", "removed_both"}:
            target.pop(binding["spatial_id"], None)

    for global_id, incoming in incoming_by_global_id.items():
        if action_by_global_id.get(global_id) != "add":
            continue
        target = merged_rooms if global_id in incoming_rooms else merged_devices
        target[incoming["id"]] = dict(incoming)

    current_room_order = [room["id"] for room in current_layout["rooms"]]
    current_device_order = [device["id"] for device in current_layout["devices"]]
    merged_layout["rooms"] = [
        merged_rooms[item_id]
        for item_id in current_room_order
        if item_id in merged_rooms
    ] + [
        room
        for item_id, room in merged_rooms.items()
        if item_id not in current_room_order
    ]
    merged_layout["devices"] = [
        merged_devices[item_id]
        for item_id in current_device_order
        if item_id in merged_devices
    ] + [
        device
        for item_id, device in merged_devices.items()
        if item_id not in current_device_order
    ]

    candidate_validation_error = None
    if not conflicts:
        try:
            validate_spatial_layout_document(merged_layout)
        except Exception as exc:
            candidate_validation_error = str(exc)

    incoming_records = {
        item["global_id"]: item for item in checked_semantics["records"]
    }
    new_bindings: list[dict[str, Any]] = []
    for global_id, incoming in incoming_by_global_id.items():
        kind = "room" if global_id in incoming_rooms else "device"
        new_bindings.append(
            {
                "global_id": global_id,
                "ifc_class": incoming_records[global_id]["ifc_class"],
                "kind": kind,
                "spatial_id": incoming["id"],
                "record_sha256": _canonical_sha256(
                    incoming_records[global_id]
                ),
                "source_spatial_sha256": _canonical_sha256(incoming),
            }
        )
    new_bindings.sort(key=lambda item: item["global_id"])

    changes.sort(key=lambda item: item["global_id"])
    summary: dict[str, int] = {}
    for item in changes:
        summary[item["action"]] = summary.get(item["action"], 0) + 1

    report = {
        "source_name": checked_name,
        "source_sha256": checked_source_digest,
        "previous_source_name": link.get("source_name"),
        "previous_source_sha256": link.get("source_sha256"),
        "previous_semantic_sha256": link.get("semantic_sha256"),
        "semantic_sha256": checked_semantics["semantic_sha256"],
        "changes": changes,
        "summary": summary,
        "conflict_count": len(conflicts),
        "candidate_validation_error": candidate_validation_error,
        "can_apply": not conflicts and candidate_validation_error is None,
    }
    return report, merged_layout, new_bindings, checked_semantics


def apply_ifc_semantics_to_project(
    project: Any,
    semantics: dict[str, Any],
    *,
    source_name: str,
    source_sha256: str,
) -> dict[str, Any]:
    """Replace project spatial data with a verified, provenance-bound IFC import."""
    metadata = getattr(project, "metadata", None)
    if not isinstance(metadata, dict):
        raise IfcImportError("project metadata must be an object")

    source_name, source_sha256 = _validate_source_provenance(
        source_name, source_sha256
    )
    layout = layout_from_ifc_semantics(semantics)
    checked = normalize_ifc_semantic_records(semantics["records"])
    bindings = _semantic_spatial_bindings(checked, layout)
    metadata[SPATIAL_METADATA_KEY] = layout
    metadata[IFC_LINK_METADATA_KEY] = {
        "schema": IFC_LINK_SCHEMA,
        "schema_version": IFC_LINK_SCHEMA_VERSION,
        "source_name": source_name,
        "source_sha256": source_sha256,
        "semantic_sha256": checked["semantic_sha256"],
        "room_count": len(layout["rooms"]),
        "device_count": len(layout["devices"]),
        "bindings": bindings,
        "bindings_sha256": _canonical_sha256(bindings),
    }
    return layout


def plan_ifc_semantic_reimport(
    project: Any,
    semantics: dict[str, Any],
    *,
    source_name: str,
    source_sha256: str,
) -> dict[str, Any]:
    """Return a deterministic, read-only IFC re-import conflict plan."""
    report, _, _, _ = _plan_ifc_semantic_reimport(
        project,
        semantics,
        source_name=source_name,
        source_sha256=source_sha256,
    )
    return report


def reimport_ifc_semantics_to_project(
    project: Any,
    semantics: dict[str, Any],
    *,
    source_name: str,
    source_sha256: str,
) -> dict[str, Any]:
    """Apply a conflict-free IFC re-import transactionally.

    Local-only spatial edits are preserved when the corresponding IFC source
    object is unchanged. If both sides changed differently, the project is left
    untouched and an explicit conflict is raised.
    """
    metadata = getattr(project, "metadata", None)
    if not isinstance(metadata, dict):
        raise IfcImportError("project metadata must be an object")

    report, merged_layout, bindings, checked = _plan_ifc_semantic_reimport(
        project,
        semantics,
        source_name=source_name,
        source_sha256=source_sha256,
    )
    if not report["can_apply"]:
        if report["conflict_count"]:
            raise IfcImportError(
                f"IFC re-import has {report['conflict_count']} conflict(s); "
                "inspect plan_ifc_semantic_reimport() before applying"
            )
        raise IfcImportError(
            "IFC re-import candidate is not spatially valid: "
            f"{report['candidate_validation_error']}"
        )

    metadata[SPATIAL_METADATA_KEY] = merged_layout
    metadata[IFC_LINK_METADATA_KEY] = {
        "schema": IFC_LINK_SCHEMA,
        "schema_version": IFC_LINK_SCHEMA_VERSION,
        "source_name": report["source_name"],
        "source_sha256": report["source_sha256"],
        "semantic_sha256": checked["semantic_sha256"],
        "room_count": sum(
            1 for item in checked["records"] if item["ifc_class"] == "IfcSpace"
        ),
        "device_count": sum(
            1 for item in checked["records"] if item["ifc_class"] != "IfcSpace"
        ),
        "bindings": bindings,
        "bindings_sha256": _canonical_sha256(bindings),
    }
    return report


def _placement_xyz_m(
    entity: Any,
    unit_scale: float,
    placement_util: Any,
) -> tuple[float, float, float]:
    """Resolve an IFC object's full nested local-placement transform into metres."""
    placement = getattr(entity, "ObjectPlacement", None)
    if placement is None:
        return 0.0, 0.0, 0.0

    try:
        matrix = placement_util.get_local_placement(placement)
        x = _finite_number(
            matrix[0][3], field=f"{getattr(entity, 'GlobalId', '?')}.placement_x"
        )
        y = _finite_number(
            matrix[1][3], field=f"{getattr(entity, 'GlobalId', '?')}.placement_y"
        )
        z = _finite_number(
            matrix[2][3], field=f"{getattr(entity, 'GlobalId', '?')}.placement_z"
        )
    except IfcImportError:
        raise
    except Exception as exc:
        raise IfcImportError(
            f"unable to resolve IFC local placement for "
            f"{getattr(entity, 'GlobalId', '?')!r}"
        ) from exc

    return x * unit_scale, y * unit_scale, z * unit_scale


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


def _containing_space_global_id(entity: Any, element_util: Any) -> str:
    """Resolve an explicit or indirect IfcSpace container without geometric inference."""
    for relation in getattr(entity, "ContainedInStructure", ()) or ():
        structure = getattr(relation, "RelatingStructure", None)
        try:
            is_space = bool(structure and structure.is_a("IfcSpace"))
        except Exception:
            is_space = False
        if is_space:
            return _non_empty_text(getattr(structure, "GlobalId", ""))

    get_container = getattr(element_util, "get_container", None)
    if not callable(get_container):
        return ""
    try:
        structure = get_container(
            entity,
            should_get_direct=False,
            ifc_class="IfcSpace",
        )
    except Exception as exc:
        raise IfcImportError(
            f"unable to resolve IFC spatial container for "
            f"{getattr(entity, 'GlobalId', '?')!r}"
        ) from exc
    if structure is None:
        return ""
    try:
        if not structure.is_a("IfcSpace"):
            return ""
    except Exception:
        return ""
    return _non_empty_text(getattr(structure, "GlobalId", ""))


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_ifc_semantics(
    path: str | Path,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Read an IFC file through optional IfcOpenShell.

    This stage consumes semantic entities, space base quantities, and placement
    origins. It does not claim complete B-Rep/tessellation interoperability.
    """
    source = Path(path)
    source_digest = _file_sha256(source)

    try:
        import ifcopenshell  # type: ignore[import-not-found]
        import ifcopenshell.util.element as element_util  # type: ignore[import-not-found]
        import ifcopenshell.util.placement as placement_util  # type: ignore[import-not-found]
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

    unit_scale = _positive_number(
        unit_util.calculate_unit_scale(model),
        field="IFC length unit scale",
    )
    records: list[dict[str, Any]] = []

    for entity in model.by_type("IfcSpace"):
        x, y, z = _placement_xyz_m(entity, unit_scale, placement_util)
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
            x, y, z = _placement_xyz_m(entity, unit_scale, placement_util)
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
            room_global_id = _containing_space_global_id(entity, element_util)
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

    try:
        final_source_digest = _file_sha256(source)
    except OSError as exc:
        raise IfcImportError(
            "IFC source became unavailable while it was being read; extraction "
            "was discarded"
        ) from exc
    if final_source_digest != source_digest:
        raise IfcImportError(
            "IFC source changed while it was being read; extraction was discarded"
        )

    semantics = normalize_ifc_semantic_records(records)
    return semantics, {
        "source_name": source.name,
        "source_sha256": source_digest,
    }
