from types import SimpleNamespace

from cleanroomx.gui_search import (
    SearchEntry,
    build_engineering_search_entries,
    filter_search_entries,
)


def test_filter_search_entries_requires_all_tokens_and_ranks_label_hits():
    entries = [
        SearchEntry("a", "Room", "ISO 7 Prep", "Level 01", target_type="room"),
        SearchEntry("b", "Analysis", "Prep ACH", "ach", target_type="analysis"),
        SearchEntry("c", "Room", "Packaging", "ISO 8", target_type="room"),
    ]

    results = filter_search_entries(entries, "prep")
    assert [item.key for item in results] == ["b", "a"]
    assert [item.key for item in filter_search_entries(entries, "iso 7")] == ["a"]
    assert [
        item.key
        for item in filter_search_entries(entries, "", category="Analysis")
    ] == ["b"]


def test_build_engineering_search_entries_uses_only_present_canonical_data():
    project = SimpleNamespace(
        name="Facility Alpha",
        description="Sterile manufacturing cleanroom",
        analyses=[
            SimpleNamespace(id="ach-1", name="Room ACH", kind="ach"),
            SimpleNamespace(
                id="pressure-1",
                name="Pressure Cascade",
                kind="pressure",
            ),
        ],
    )
    spatial_layout = {
        "rooms": [{"id": "R-101", "name": "Compounding", "level": "L1"}],
        "devices": [{"id": "D-1", "name": "Supply HEPA", "type": "supply"}],
    }
    diagnostics = {
        "issues": [
            {
                "severity": "warning",
                "rule": "AIRFLOW_BALANCE",
                "message": "Supply and extract differ",
                "element": {"type": "spatial_element", "id": "R-101"},
            }
        ]
    }
    requirements = {
        "requirements": [
            {
                "id": "REQ-1",
                "title": "Maintain positive pressure",
                "status": "active",
                "source": "URS",
            }
        ]
    }
    proofgraphs = [
        {
            "id": "graph-1",
            "nodes": [
                {
                    "id": "ev-1",
                    "key": "evidence:ev-1",
                    "label": "Pressure verification evidence",
                    "type": "evidence",
                    "status": "pass",
                }
            ],
        }
    ]

    entries = build_engineering_search_entries(
        project=project,
        spatial_layout=spatial_layout,
        diagnostics=diagnostics,
        requirement_snapshot=requirements,
        proofgraph_documents=proofgraphs,
    )

    targets = {(entry.target_type, entry.target_id) for entry in entries}
    assert ("project", "") in targets
    assert ("analysis", "ach-1") in targets
    assert ("analysis", "pressure-1") in targets
    assert ("room", "R-101") in targets
    assert ("device", "D-1") in targets
    assert ("diagnostic", "AIRFLOW_BALANCE") in targets
    assert ("requirement", "REQ-1") in targets
    assert ("evidence", "evidence:ev-1") in targets


def test_build_engineering_search_entries_does_not_turn_missing_values_into_zero():
    project = SimpleNamespace(name="P", description="", analyses=[])
    entries = build_engineering_search_entries(
        project=project,
        spatial_layout={"rooms": [{"id": "R1", "name": "Room 1"}]},
        diagnostics={"issues": []},
    )

    room = next(entry for entry in entries if entry.target_type == "room")
    assert "0" not in room.detail
    assert room.detail.endswith("R1")
