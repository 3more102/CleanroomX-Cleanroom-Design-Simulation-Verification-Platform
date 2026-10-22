"""Regression contract for project-native FFU/closed-door OpenFOAM case preparation.

Uses synthetic example values; never substitutes for real CFD solver evidence.
"""
from __future__ import annotations

import copy
import hashlib
import json
import shutil

import pytest

from cleanroomx.cfd_pipeline_cli import build_parser
from cleanroomx.cfd_project_rooms import (
    PROJECT_CFD_SCHEMA,
    _collect_door_regions, _face_layout,
    generate_project_room_cases, run_project_room_cases,
)
from cleanroomx.gui import bundled_demo_project_path
from cleanroomx.project import load_project_document


def _layout():
    project = load_project_document(bundled_demo_project_path())
    return project.metadata["spatial_layout"]


def _generate(tmp_path, **kwargs):
    return generate_project_room_cases(
        bundled_demo_project_path(), tmp_path / "rooms",
        kinematic_viscosity_m2_s=1.5e-5,
        **kwargs,
    )


def test_all_three_clean_rooms_have_solver_input_receipts_and_opaque_closed_doors(tmp_path):
    manifest = _generate(tmp_path)
    root = tmp_path / "rooms"
    assert manifest["schema_version"] == PROJECT_CFD_SCHEMA
    assert set(manifest["cases"]) == {"process", "preparation", "ante"}
    assert len(manifest["files"]) == 24
    assert len(manifest["project_source_sha256"]) == 64
    assert "NOT coupled" in manifest["warning"]
    for room_id, expected_doors in (
        ("process", 1), ("preparation", 2), ("ante", 2),
    ):
        case = manifest["cases"][room_id]
        boundary = case["boundary"]
        assert len(boundary["door_regions"]) == expected_doors
        assert set(boundary["boundary_counts"]) == {
            "inlet", "outlet", "walls", "closedDoors"
        }
        assert all(boundary["boundary_counts"][key] > 0
                   for key in ("inlet", "outlet", "walls", "closedDoors"))
        assert case["inlet_volume_flow_check_m3_s"] == pytest.approx(
            case["supply_flow_m3_h"] / 3600
        )
        assert "NOT the 5 Pa" in case["pressure_reference"]
        mesh = (root / f"room_{room_id}/system/blockMeshDict").read_text()
        u = (root / f"room_{room_id}/0/U").read_text()
        p = (root / f"room_{room_id}/0/p").read_text()
        assert "closedDoors" in mesh
        assert "type wall;" in mesh
        assert "closedDoors\n    {\n        type noSlip;" in u
        assert "closedDoors\n    {\n        type zeroGradient;" in p
        assert "inlet\n    {\n        type fixedValue;" in u
        assert "outlet\n    {\n        type pressureInletOutletVelocity;" in u
        assert "application simpleFoam;" in (
            root / f"room_{room_id}/system/controlDict"
        ).read_text()
        assert case["validation"].startswith("NOT EXECUTED")
        assert boundary["closed_door_mesh_area_m2"] > 0
        assert all(area > 0 for area in boundary["closed_door_per_leaf_mesh_area_m2"].values())
        assert all(area > 0 for area in boundary["per_ffu_mesh_area_m2"].values())
        assert all(area > 0 for area in boundary["per_return_mesh_area_m2"].values())
        assert "stair-step approximations" in boundary["area_reporting_note"]
    for relative, sha in manifest["files"].items():
        assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == sha
    assert json.loads((root / "manifest.json").read_text()) == manifest
    with pytest.raises(FileExistsError):
        _generate(tmp_path)


def test_closed_door_both_sides_export_at_same_world_height_and_width():
    layout = _layout()
    rooms = layout["rooms"]
    doors = [d for d in layout["devices"] if d["type"] == "door"]
    assert len(doors) == 3
    by_id = {r["id"]: r for r in rooms}
    for door in doors:
        owner = by_id[door["room_id"]]
        source = [
            r for r in _collect_door_regions(owner, rooms, doors)
            if r["door_id"] == door["id"]
        ]
        assert len(source) == 1
        adjacent = by_id[source[0]["other_room_id"]]
        target = [
            r for r in _collect_door_regions(adjacent, rooms, doors)
            if r["door_id"] == door["id"]
        ]
        assert len(target) == 1
        assert {source[0]["side"], target[0]["side"]} == {"east", "west"}
        assert source[0]["design_area_m2"] == target[0]["design_area_m2"]
        assert (owner["pressure_pa"] - adjacent["pressure_pa"]) == 5


def test_mesh_boundary_partition_is_complete_and_pressure_not_prescribed():
    layout = _layout()
    owner = layout["rooms"][0]
    cells = (24, 24, 12)
    faces, info = _face_layout(owner, layout["devices"], layout["rooms"], cells)
    expected = 2 * (cells[0] * cells[1] + cells[1] * cells[2] + cells[0] * cells[2])
    assert sum(map(len, faces.values())) == expected
    assert len(set(tuple(sorted(face)) for group in faces.values() for face in group)) == expected
    assert info["boundary_counts"]["closedDoors"] > 0
    assert "impermeable noSlip" in info["closed_door_assumption"]


@pytest.mark.parametrize("modifier,pattern", [
    (lambda layout: layout["devices"][0].update(x_m=5.8), "off-wall"),
    (lambda layout: layout["devices"][3].update(z_m=2.0), "ceiling"),
    (lambda layout: next(d for d in layout["devices"] if d["id"] == "return-process").update(wall_side="north"), "designated north wall"),
])
def test_invalid_geometry_is_rejected_during_case_preparation(modifier, pattern):
    layout = _layout()
    room = layout["rooms"][0]
    modifier(layout)
    with pytest.raises(ValueError, match=pattern):
        _face_layout(room, layout["devices"], layout["rooms"], (24, 24, 12))


def test_low_wall_return_cannot_overlap_a_closed_door_even_if_outlet_faces_remain():
    layout = _layout()
    prep = next(r for r in layout["rooms"] if r["id"] == "preparation")
    grille = next(d for d in layout["devices"] if d["id"] == "return-preparation")
    grille.update(wall_side="west", x_m=prep["x_m"], y_m=2.0)
    with pytest.raises(ValueError, match="overlaps closed door panel"):
        _face_layout(prep, layout["devices"], layout["rooms"], (24, 24, 12))


def test_explicit_cfd_parameters_cannot_silently_default_physical_inputs(tmp_path):
    with pytest.raises(TypeError):
        generate_project_room_cases(bundled_demo_project_path(), tmp_path / "missing")
    with pytest.raises(ValueError):
        generate_project_room_cases(
            bundled_demo_project_path(), tmp_path / "bad",
            kinematic_viscosity_m2_s=-1,
        )
    with pytest.raises(ValueError, match="Mesh"):
        _generate(tmp_path, mesh_cells=(80, 80, 80))


def test_runner_rejects_tampered_inputs_before_external_executables(tmp_path, monkeypatch):
    _generate(tmp_path)
    root = tmp_path / "rooms"
    monkeypatch.setattr(
        "cleanroomx.cfd_project_rooms.shutil.which", lambda _name: None
    )
    with pytest.raises(RuntimeError, match="blockMesh not found"):
        run_project_room_cases(root)
    f = root / "room_process/0/U"
    f.write_text(f.read_text() + "\n// tamper", encoding="utf-8")
    with pytest.raises(ValueError, match="Tampered CFD input"):
        run_project_room_cases(root)


def test_cli_exposes_explicit_generated_room_case_workflows():
    args = build_parser().parse_args([
        "project-rooms-generate", "input.json", "out",
        "--kinematic-viscosity-m2-s", "1.5e-5",
    ])
    assert args.command == "project-rooms-generate"
    assert args.mesh_cells == [24, 24, 12]
    assert args.kinematic_viscosity_m2_s == pytest.approx(1.5e-5)
    assert build_parser().parse_args(
        ["project-rooms-run", "out"]
    ).command == "project-rooms-run"
