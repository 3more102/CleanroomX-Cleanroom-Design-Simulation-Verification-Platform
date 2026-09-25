from __future__ import annotations

import json

import pytest

from cleanroomx.project import (
    AnalysisDocument,
    ProjectDocument,
    ProjectFormatError,
    load_project_document,
    project_from_dict,
    save_project_document,
)
from cleanroomx.spatial import derive_layout_from_analysis, normalize_layout


def _project_payload(spatial_layout: object) -> dict:
    return {
        "schema": "cleanroomx.project",
        "schema_version": 1,
        "application_version": "test",
        "project": {
            "name": "Spatial integrity",
            "description": "",
            "metadata": {"spatial_layout": spatial_layout},
        },
        "analyses": [],
        "active_analysis_id": None,
    }


def test_normalize_layout_repairs_room_and_device_ids_deterministically():
    raw = {
        "version": 1,
        "rooms": [
            {"name": "Process"},
            {"id": "process", "name": "Explicit Process"},
            {"id": "same", "name": "Duplicate A"},
            {"id": "same", "name": "Duplicate B"},
            {"name": "!!!"},
        ],
        "devices": [
            {"type": "ffu", "name": "FFU"},
            {"id": "device-ffu", "type": "sensor", "name": "Explicit Device"},
            {"id": "same-device", "type": "sensor", "name": "Duplicate A"},
            {"id": "same-device", "type": "sensor", "name": "Duplicate B"},
        ],
    }

    first = normalize_layout(raw)
    second = normalize_layout(raw)

    assert first == second
    room_ids = [room["id"] for room in first["rooms"]]
    device_ids = [device["id"] for device in first["devices"]]
    assert room_ids == ["process-2", "process", "same", "same-2", "room"]
    assert device_ids == [
        "device-ffu-2",
        "device-ffu",
        "same-device",
        "same-device-2",
    ]
    assert len(room_ids) == len(set(room_ids))
    assert len(device_ids) == len(set(device_ids))


def test_derive_layout_from_duplicate_room_names_has_stable_unique_ids():
    analysis = AnalysisDocument(
        id="verification",
        name="Facility",
        kind="project_verification",
        input={
            "rooms": [
                {"name": "Process", "length_m": 4, "width_m": 4, "height_m": 3},
                {"name": "Process", "length_m": 5, "width_m": 4, "height_m": 3},
            ]
        },
    )

    first = derive_layout_from_analysis(analysis)
    second = derive_layout_from_analysis(analysis)

    assert first == second
    assert [room["id"] for room in first["rooms"]] == ["process", "process-2"]


def test_normalize_layout_preserves_unknown_extension_fields():
    raw = {
        "version": 1,
        "grid_m": 0.25,
        "vendor_extension": {"revision": 7},
        "rooms": [
            {
                "id": "r1",
                "name": "Room",
                "x_m": 0,
                "y_m": 0,
                "length_m": 4,
                "width_m": 3,
                "height_m": 2.8,
                "vendor_room": {"classification": "custom"},
            }
        ],
        "devices": [
            {
                "id": "d1",
                "type": "sensor",
                "name": "S1",
                "room_id": "r1",
                "x_m": 1,
                "y_m": 1,
                "z_m": 1.2,
                "vendor_device": {"serial": "ABC"},
            }
        ],
        "view": {
            "zoom_2d": 1.5,
            "projection_mode": "vendor-perspective",
        },
    }

    normalized = normalize_layout(raw)

    assert normalized["vendor_extension"] == {"revision": 7}
    assert normalized["rooms"][0]["vendor_room"] == {"classification": "custom"}
    assert normalized["devices"][0]["vendor_device"] == {"serial": "ABC"}
    assert normalized["view"]["projection_mode"] == "vendor-perspective"


@pytest.mark.parametrize(
    ("collection", "duplicate_id", "message"),
    [
        ("rooms", "room-a", "spatial_layout room ids must be unique"),
        ("devices", "device-a", "spatial_layout device ids must be unique"),
    ],
)
def test_project_loader_rejects_duplicate_persisted_spatial_ids(
    collection,
    duplicate_id,
    message,
):
    spatial = {"version": 1, "rooms": [], "devices": []}
    if collection == "rooms":
        spatial["rooms"] = [
            {"id": duplicate_id, "name": "A"},
            {"id": duplicate_id, "name": "B"},
        ]
    else:
        spatial["devices"] = [
            {"id": duplicate_id, "type": "sensor", "name": "A"},
            {"id": duplicate_id, "type": "sensor", "name": "B"},
        ]

    with pytest.raises(ProjectFormatError, match=message):
        project_from_dict(_project_payload(spatial))


def test_project_loader_rejects_future_spatial_layout_version():
    with pytest.raises(
        ProjectFormatError,
        match="unsupported future spatial layout version 2",
    ):
        project_from_dict(_project_payload({"version": 2, "rooms": [], "devices": []}))


@pytest.mark.parametrize(
    ("spatial_layout", "message"),
    [
        ({"version": 1, "rooms": {}, "devices": []}, "spatial_layout.rooms must be an array"),
        ({"version": 1, "rooms": [], "devices": {}}, "spatial_layout.devices must be an array"),
        ({"version": 1, "rooms": [], "devices": [], "view": []}, "spatial_layout.view must be an object"),
    ],
)
def test_project_loader_rejects_malformed_spatial_collection_shapes(
    spatial_layout,
    message,
):
    with pytest.raises(ProjectFormatError, match=message):
        project_from_dict(_project_payload(spatial_layout))


def test_project_save_canonicalizes_spatial_identity_and_round_trips(tmp_path):
    project = ProjectDocument(
        name="Canonical save",
        metadata={
            "spatial_layout": {
                "vendor_extension": {"keep": True},
                "rooms": [
                    {"name": "Process"},
                    {"id": "process", "name": "Explicit Process"},
                ],
                "devices": [
                    {"type": "sensor", "name": "S1", "room_id": "process"},
                    {"id": "device-s1", "type": "sensor", "name": "Explicit"},
                ],
            }
        },
    )
    path = tmp_path / "canonical.cleanroomx.json"

    save_project_document(path, project)

    payload = json.loads(path.read_text(encoding="utf-8"))
    saved = payload["project"]["metadata"]["spatial_layout"]
    assert saved["version"] == 1
    assert [room["id"] for room in saved["rooms"]] == ["process-2", "process"]
    assert [device["id"] for device in saved["devices"]] == [
        "device-s1-2",
        "device-s1",
    ]
    assert saved["vendor_extension"] == {"keep": True}

    loaded = load_project_document(path)
    assert loaded.metadata["spatial_layout"] == saved
