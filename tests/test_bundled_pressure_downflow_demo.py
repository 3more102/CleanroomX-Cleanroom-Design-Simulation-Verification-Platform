"""Regression checks for the bundled connected-room pressure/downflow demo.

This is a SYNTHETIC DESIGN EXAMPLE, not an OpenFOAM/commissioning result.
"""
from __future__ import annotations

import pytest

from cleanroomx.application import run_analysis
from cleanroomx.gui import bundled_demo_project_path
from cleanroomx.project import load_project_document
from cleanroomx.spatial_integrity import validate_spatial_layout_document


EXPECTED_PRESSURES_PA = {
    "process": 15.0,
    "preparation": 10.0,
    "ante": 5.0,
    "corridor": 0.0,
}
DOOR_PAIRS = (
    ("process", "preparation"),
    ("preparation", "ante"),
    ("ante", "corridor"),
)


def _demo():
    project = load_project_document(bundled_demo_project_path())
    layout = project.metadata["spatial_layout"]
    return project, layout


def test_demo_has_connected_shared_wall_doors_and_exact_pressure_steps():
    project, layout = _demo()
    validate_spatial_layout_document(layout)
    rooms = {room["id"]: room for room in layout["rooms"]}
    assert set(rooms) == set(EXPECTED_PRESSURES_PA)
    assert {name: item["pressure_pa"] for name, item in rooms.items()} == (
        EXPECTED_PRESSURES_PA
    )
    doors = [item for item in layout["devices"] if item["type"] == "door"]
    assert len(doors) == len(DOOR_PAIRS)
    for door, (higher, lower) in zip(doors, DOOR_PAIRS, strict=True):
        high_room, low_room = rooms[higher], rooms[lower]
        assert door["room_id"] == higher
        assert door["wall_side"] == "east"
        assert high_room["x_m"] + high_room["length_m"] == pytest.approx(
            low_room["x_m"]
        )
        assert door["x_m"] == pytest.approx(low_room["x_m"])
        assert 0 <= door["y_m"] - door["width_m"] / 2
        assert door["y_m"] + door["width_m"] / 2 <= min(
            high_room["width_m"], low_room["width_m"]
        )
        assert (
            high_room["pressure_pa"] - low_room["pressure_pa"]
        ) == pytest.approx(5.0)
    assert "SYNTHETIC" in project.metadata["demo_scenario"]["evidence_status"]


def test_demo_ceiling_ffus_and_low_level_returns_are_explicitly_design_only():
    project, layout = _demo()
    rooms = {room["id"]: room for room in layout["rooms"]}
    ffus = [item for item in layout["devices"] if item["type"] == "ffu"]
    returns = [item for item in layout["devices"] if item["type"] == "return"]
    assert len(ffus) == 12
    assert {item["room_id"] for item in ffus} == {
        "process", "preparation", "ante"
    }
    for item in ffus:
        room = rooms[item["room_id"]]
        assert item["z_m"] == pytest.approx(room["height_m"])
        assert room["x_m"] < item["x_m"] < room["x_m"] + room["length_m"]
        assert room["y_m"] < item["y_m"] < room["y_m"] + room["width_m"]
    assert {item["room_id"] for item in returns} == {
        "process", "preparation", "ante"
    }
    assert all(item["z_m"] < 0.5 for item in returns)
    scenario = project.metadata["demo_scenario"]
    assert scenario["downflow_velocity_m_s"] is None
    assert "do not represent a computed 3-D velocity field" in scenario["airflow"]


def test_synthetic_pressure_network_solves_five_pascal_steps_and_mass_balance():
    project, _ = _demo()
    analysis = project.analysis_by_id("demo-5pa-pressure-network")
    assert analysis.kind == "pressure_network"
    output = run_analysis(analysis.kind, analysis.input).result
    assert output["status"] == "solved"
    pressures = {item["name"]: item["pressure_pa"] for item in output["nodes"]}
    for name, expected in {
        "Process": 15.0, "Preparation": 10.0, "Ante": 5.0, "Corridor": 0.0
    }.items():
        assert pressures[name] == pytest.approx(expected, abs=1e-6)
    assert output["target_summary"]["passed"] == 3
    assert output["target_summary"]["failed"] == 0
    assert output["solver"][
        "max_abs_unknown_node_mass_balance_residual_m3_h"
    ] < 1e-6
    for item in output["paths"]:
        assert item["pressure_difference_pa"] == pytest.approx(5.0, abs=1e-6)
        assert item["airflow_m3_h"] == pytest.approx(36.0, abs=1e-6)
        assert item["kind"] == "door"
