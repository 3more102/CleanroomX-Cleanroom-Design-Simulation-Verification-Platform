"""Synthetic geometry tests, not OpenFOAM meshing or cleanroom qualification."""
from __future__ import annotations

import copy
import json
import sys

import pytest

from cleanroomx.cfd_suite_topology import SCHEMA, assess_suite_topology
from cleanroomx.cfd_pipeline_cli import main as cfd_main


def layout():
    return {
        "version": 1,
        "floor": {"name": "Suite", "units": "m", "elevation_m": 0,
                  "default_ceiling_height_m": 3},
        "rooms": [
            {"id": "process", "name": "Process", "x_m": 0, "y_m": 0,
             "length_m": 4, "width_m": 3, "height_m": 3,
             "floor_elevation_m": 0, "pressure_pa": 30},
            {"id": "prep", "name": "Prep", "x_m": 4, "y_m": 0,
             "length_m": 3, "width_m": 3, "height_m": 3,
             "floor_elevation_m": 0, "pressure_pa": 15},
        ],
        "devices": [
            {"id": "door-1", "name": "Connecting door", "type": "door",
             "room_id": "process", "x_m": 4, "y_m": 1.5, "z_m": 0,
             "wall_side": "east", "width_m": 0.9, "height_m": 2.1},
        ],
    }


def codes(report):
    return {issue["code"] for issue in report["issues"]}


def test_adjacent_rooms_and_internal_door_have_valid_topology_only():
    model = layout()
    before = copy.deepcopy(model)
    report = assess_suite_topology(model)
    assert model == before
    assert report["schema_version"] == SCHEMA
    assert report["topology_status"] == "valid"
    assert report["shared_walls"][0]["room_a_id"] == "prep"  # sorted by stable IDs
    assert report["shared_walls"][0]["room_b_id"] == "process"
    assert report["shared_walls"][0]["side_a"] == "west"
    assert report["shared_walls"][0]["opening_ids"] == ["door-1"]
    assert report["shared_walls"][0]["shared_area_m2"] == pytest.approx(9)
    assert report["ready_for_solver"] is False
    assert report["openfoam_case_status"] == "not_generated"
    assert report == assess_suite_topology(model)


def test_3d_overlap_is_blocked_even_when_xy_rectangles_touch_others():
    model = layout()
    model["rooms"][1]["x_m"] = 3
    assert "room_volume_overlap" in codes(assess_suite_topology(model))
    assert "disconnected_suite" in codes(assess_suite_topology(model))


@pytest.mark.parametrize("distance", [0.05, 1.0])
def test_positive_wall_gap_never_closes_automatically(distance):
    model = layout()
    model["rooms"][1]["x_m"] = 4 + distance
    assert "disconnected_suite" in codes(assess_suite_topology(model))
    assert "opening_unmapped" in codes(assess_suite_topology(model))


def test_external_door_not_promoted_to_internal_airflow_path():
    model = layout()
    model["devices"][0].update(x_m=2, y_m=0, wall_side="south")
    report = assess_suite_topology(model)
    assert "disconnected_suite" in codes(report)
    assert "opening_unmapped" not in codes(report)
    assert any(item["code"] == "exterior_opening" for item in report["warnings"])
    assert report["shared_walls"][0]["opening_ids"] == []


def test_missing_or_oversized_opening_dimensions_fail_closed():
    model = layout()
    del model["devices"][0]["width_m"]
    assert "opening_dimensions_missing" in codes(assess_suite_topology(model))
    model = layout()
    model["devices"][0]["width_m"] = 4
    assert "opening_unmapped" in codes(assess_suite_topology(model))


def test_wrong_wall_side_and_missing_assignment():
    model = layout()
    model["devices"][0]["wall_side"] = "west"
    assert "opening_unmapped" in codes(assess_suite_topology(model))
    model = layout()
    model["devices"][0].pop("room_id")
    assert "opening_unassigned" in codes(assess_suite_topology(model))


def test_valid_internal_passage_and_an_exterior_door_remain_geometrically_valid():
    model = layout()
    model["devices"].append({
        "id": "entry", "name": "Exterior access", "type": "door",
        "room_id": "process", "x_m": 2, "y_m": 0, "z_m": 0,
        "wall_side": "south", "width_m": 1, "height_m": 2,
    })
    report = assess_suite_topology(model)
    assert report["topology_status"] == "valid"
    assert report["shared_walls"][0]["opening_ids"] == ["door-1"]
    assert [item["code"] for item in report["warnings"]] == ["exterior_opening"]


def test_overflowing_box_bounds_are_rejected_before_serialization():
    model = layout()
    model["rooms"][0]["x_m"] = 1e308
    model["rooms"][0]["length_m"] = 1e308
    with pytest.raises(ValueError, match="overflowing"):
        assess_suite_topology(model)


def test_geometry_vertical_mismatch_is_not_silently_extruded():
    model = layout()
    model["rooms"][1]["height_m"] = 2.6
    assert "stepped_shared_wall" in codes(assess_suite_topology(model))


def test_duplicate_geometrically_overlapping_doors_are_blocked():
    model = layout()
    door = dict(model["devices"][0], id="door-2", name="Second door")
    door["y_m"] = 1.55
    model["devices"].append(door)
    assert "overlapping_openings" in codes(assess_suite_topology(model))


def test_diagonal_corner_touch_is_not_a_shared_partition():
    model = layout()
    model["rooms"][1].update(x_m=4, y_m=3)
    report = assess_suite_topology(model)
    assert not report["shared_walls"]
    assert "disconnected_suite" in codes(report)


def test_invalid_physical_inputs_do_not_get_normalized_into_a_pass():
    model = layout()
    model["rooms"][0]["length_m"] = float("nan")
    with pytest.raises(ValueError):
        assess_suite_topology(model)
    model = layout()
    model["rooms"][0]["pressure_pa"] = True
    with pytest.raises(ValueError):
        assess_suite_topology(model)


def test_unchanged_geometry_has_stable_sha_and_geometry_edits_change_it():
    model = layout()
    digest = assess_suite_topology(model)["spatial_layout_sha256"]
    model["rooms"][0]["width_m"] = 2.9
    assert digest != assess_suite_topology(model)["spatial_layout_sha256"]


def test_cli_topology_preflight_does_not_overwrite_project(tmp_path, monkeypatch):
    project_file = tmp_path / "design.cleanroomx.json"
    project = {
        "schema": "cleanroomx.project",
        "schema_version": 1,
        "project": {
            "name": "Two room suite",
            "description": "",
            "metadata": {"spatial_layout": layout()},
        },
        "analyses": [],
    }
    project_file.write_text(json.dumps(project), encoding="utf-8")
    before = project_file.read_bytes()
    report_file = tmp_path / "report.json"
    monkeypatch.setattr(sys, "argv", [
        "cleanroomx-cfd-pipeline", "suite-preflight",
        str(project_file), "--output", str(report_file)
    ])
    assert cfd_main() == 0
    report = json.loads(report_file.read_text(encoding="utf-8"))
    assert report["topology_status"] == "valid"
    assert report["ready_for_solver"] is False
    assert project_file.read_bytes() == before
