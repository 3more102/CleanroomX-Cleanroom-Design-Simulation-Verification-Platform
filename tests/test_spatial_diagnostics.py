from __future__ import annotations

from cleanroomx.project import AnalysisDocument
from cleanroomx.spatial import (
    SpatialDesignWorkspace,
    derive_layout_from_analysis,
    engineering_sync_diagnostics,
)


class _Flag:
    def __init__(self, value: bool):
        self.value = value

    def get(self) -> bool:
        return self.value


def _analysis() -> AnalysisDocument:
    return AnalysisDocument(
        id="verification",
        name="Facility",
        kind="project_verification",
        input={
            "rooms": [
                {
                    "name": "Process",
                    "length_m": 6,
                    "width_m": 5,
                    "height_m": 3,
                    "observed_pressure_pa": 30,
                },
                {
                    "name": "Ante",
                    "length_m": 4,
                    "width_m": 3,
                    "height_m": 3,
                    "observed_pressure_pa": 8,
                },
            ],
            "pressure_cascade": [
                {
                    "higher_pressure_room": "Process",
                    "lower_pressure_room": "Ante",
                    "min_delta_pa": 10,
                }
            ],
        },
    )


def test_engineering_sync_diagnostics_report_synchronized_and_conflicting_rooms() -> None:
    analysis = _analysis()
    layout = derive_layout_from_analysis(analysis)

    records = engineering_sync_diagnostics(layout, analysis)
    assert [record["state"] for record in records] == [
        "synchronized",
        "synchronized",
    ]

    layout["rooms"][0]["length_m"] = 7
    records = engineering_sync_diagnostics(layout, analysis)
    process = records[0]
    assert process["state"] == "conflicting"
    assert process["differences"] == [
        {
            "field": "length_m",
            "spatial": 7,
            "engineering": 6,
        }
    ]


def test_engineering_sync_diagnostics_keep_stable_links_and_report_unmapped_targets() -> None:
    analysis = _analysis()
    layout = derive_layout_from_analysis(analysis)
    process = layout["rooms"][0]
    process["name"] = "ISO Process Display"
    process["analysis_room_name"] = "Process"

    records = engineering_sync_diagnostics(layout, analysis)
    assert records[0]["state"] == "synchronized"
    assert records[0]["analysis_room_name"] == "Process"

    process["analysis_room_name"] = "Missing Engineering Room"
    records = engineering_sync_diagnostics(layout, analysis)
    assert records[0]["state"] == "unmapped"
    assert "No matching room" in records[0]["message"]


def test_engineering_sync_diagnostics_report_duplicate_mapping_conflict() -> None:
    analysis = _analysis()
    layout = derive_layout_from_analysis(analysis)
    layout["rooms"][1]["analysis_room_name"] = "Process"

    records = engineering_sync_diagnostics(layout, analysis)
    assert records[0]["state"] == "conflicting"
    assert records[1]["state"] == "conflicting"
    assert "same analysis room" in records[0]["message"]


def test_pressure_relationship_status_uses_only_supplied_room_pressures() -> None:
    analysis = _analysis()
    layout = derive_layout_from_analysis(analysis)
    workspace = object.__new__(SpatialDesignWorkspace)
    workspace.layout = layout
    workspace._show_relationships = _Flag(True)
    workspace._analysis_getter = lambda: analysis

    relation = workspace._pressure_relationships()[0]
    assert relation[2:] == (10.0, 22.0, "pass")

    layout["rooms"][1]["pressure_pa"] = 25
    relation = workspace._pressure_relationships()[0]
    assert relation[2:] == (10.0, 5.0, "fail")

    layout["rooms"][1].pop("pressure_pa")
    relation = workspace._pressure_relationships()[0]
    assert relation[2:] == (10.0, None, "unavailable")
