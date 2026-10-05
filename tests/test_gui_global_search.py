from __future__ import annotations

from types import SimpleNamespace

from cleanroomx.gui_global_search import (
    EngineeringSearchItem,
    build_engineering_search_index,
    filter_engineering_search_items,
)


def test_global_search_index_uses_existing_project_sources_without_calculation():
    analysis = SimpleNamespace(id="a-1", name="Room ACH", kind="room_verification")
    index = build_engineering_search_index(
        analyses=[analysis],
        spatial_layout={
            "rooms": [{"id": "R-101", "name": "ISO 7 Bay", "level": "L1"}],
            "devices": [
                {
                    "id": "FFU-1",
                    "name": "FFU 1",
                    "type": "ffu",
                    "room_id": "R-101",
                }
            ],
        },
        diagnostics={
            "issues": [
                {
                    "sequence": 4,
                    "rule": "spatial.room_overlap",
                    "severity": "error",
                    "category": "spatial",
                    "message": "Rooms overlap.",
                    "element": {"id": "R-101", "name": "ISO 7 Bay"},
                }
            ]
        },
        traceability={
            "requirements": [
                {
                    "id": "REQ-ACH-01",
                    "title": "Minimum ACH",
                    "description": "Maintain required ACH.",
                    "discipline": "HVAC",
                    "category": "air_changes",
                    "source": "URS",
                    "status": "approved",
                    "applicability": "applicable",
                    "set": {"title": "Cleanroom URS"},
                }
            ]
        },
        evidence_records=[
            {
                "sequence": 9,
                "analysis_id": "a-1",
                "analysis_name": "Room ACH",
                "completed_at_utc": "2026-10-05T08:00:00Z",
                "verification": {"status": "pass"},
                "record_sha256": "d" * 64,
            }
        ],
    )

    categories = {item.category for item in index}
    assert categories == {"Analysis", "Room", "Device", "Diagnostic", "Requirement", "Evidence"}
    assert next(item for item in index if item.category == "Diagnostic").state == "error"
    requirement = next(item for item in index if item.category == "Requirement")
    assert requirement.target_id == "REQ-ACH-01"
    assert "approved" in requirement.state
    evidence = next(item for item in index if item.category == "Evidence")
    assert evidence.state == "pass"


def test_global_search_filter_ranks_exact_ids_and_respects_category():
    items = [
        EngineeringSearchItem(
            category="Room",
            title="ISO 7 Bay",
            context="R-101",
            state="model",
            target_kind="room",
            target_id="R-101",
        ),
        EngineeringSearchItem(
            category="Diagnostic",
            title="room.pressure_warning",
            context="ISO 7 Bay",
            state="warning",
            target_kind="diagnostic",
            target_id="3",
        ),
        EngineeringSearchItem(
            category="Requirement",
            title="Room pressure",
            context="URS",
            state="approved",
            target_kind="requirement",
            target_id="REQ-P-01",
        ),
    ]

    exact = filter_engineering_search_items(items, "R-101")
    assert exact[0].target_id == "R-101"

    room_only = filter_engineering_search_items(items, "ISO", category="Room")
    assert [item.target_kind for item in room_only] == ["room"]

    pressure = filter_engineering_search_items(items, "pressure")
    assert {item.target_kind for item in pressure} == {"diagnostic", "requirement"}


def test_global_search_missing_sources_produce_empty_index_not_fake_entities():
    assert build_engineering_search_index() == ()
