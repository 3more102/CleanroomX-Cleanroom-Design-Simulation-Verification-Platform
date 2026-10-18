import hashlib
import json

import pytest

from cleanroomx.cfd_result_analysis import AnalysisSession, _derive_two_room_region_statistics, build_analysis_graph
from cleanroomx.cfd_two_room import (
    SCHEMA,
    build_two_room_files,
    compute_pressure_difference_pa,
    execute_two_room_case,
    export_two_room_case,
    parse_pressure_probe_data,
    validate_two_room_spec,
    verify_two_room_case,
    verify_two_room_receipt,
)


def _spec():
    return {
        "schema_version": SCHEMA,
        "name": "SYNTHETIC two-room integration test",
        "room_m": [6.0, 4.0, 3.0],
        "mesh_cells_per_room": [12, 12, 8],
        "door_opening_m": [0.22, 0.2],
        "supply_flow_m3_s": 0.1,
        "density_kg_m3": 1.2,
        "kinematic_viscosity_m2_s": 1.5e-5,
        "target_delta_pressure_pa": 5.0,
        "pressure_tolerance_pa": 1.0,
        "max_iterations": 150,
        "output_interval": 1,
    }


def test_two_room_mesh_has_aligned_internal_opening_and_separate_wall_patches():
    files, metadata = build_two_room_files(_spec())
    mesh = files["system/blockMeshDict"]
    assert metadata["room_count"] == 2
    assert metadata["mesh_cell_count"] == 2 * 12 * 12 * 8
    assert metadata["door_opening_is_internal_face"] is True
    assert metadata["partition_boundary_face_count"] == 10
    assert mesh.count("    hex (") == 12
    assert "    partition\n    {\n        type wall;" in mesh
    assert "roomPressureProbes" in files["system/controlDict"]
    assert "libs (\"libsampling.so\");" in files["system/controlDict"]
    assert "partition" in files["0/U"] and "partition" in files["0/p"]
    assert metadata["scientific_validation"] == "BLOCKED"


def test_two_room_spec_rejects_unbounded_or_ambiguous_inputs():
    value = _spec()
    value["mesh_cells_per_room"] = [80, 80, 80]
    with pytest.raises(ValueError, match="20,000 cells"):
        validate_two_room_spec(value)

    value = _spec()
    value["door_opening_m"] = [True, 0.2]
    with pytest.raises(ValueError, match="finite and positive"):
        validate_two_room_spec(value)

    value = _spec()
    value["output_interval"] = 10
    with pytest.raises(ValueError, match="must be 1"):
        validate_two_room_spec(value)


def test_two_room_export_binds_all_inputs_and_refuses_overwrite(tmp_path):
    case = tmp_path / "case"
    generated = export_two_room_case(_spec(), case)
    audited = verify_two_room_case(case)
    assert generated["status"] == audited["status"] == "verified"
    assert len(audited["input_sha256"]) == 8
    assert audited["metadata"]["door_opening_area_m2"] == pytest.approx(0.044)
    with pytest.raises(ValueError, match="overwrite"):
        export_two_room_case(_spec(), case)

    block_mesh = case / "system" / "blockMeshDict"
    block_mesh.write_text(block_mesh.read_text() + "// changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="digest mismatch"):
        verify_two_room_case(case)


@pytest.mark.parametrize("tamper", ["rehash_input", "metadata", "release", "validation"])
def test_two_room_audit_rejects_self_consistent_but_noncanonical_manifest(tmp_path, tamper):
    case = tmp_path / "case"
    export_two_room_case(_spec(), case)
    manifest_path = case / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if tamper == "rehash_input":
        input_path = case / "0" / "U"
        changed = input_path.read_bytes().replace(b"type noSlip;", b"type slip;", 1)
        assert changed != input_path.read_bytes()
        input_path.write_bytes(changed)
        manifest["files"]["0/U"] = hashlib.sha256(changed).hexdigest()
        expected_error = "does not match its declared specification"
    elif tamper == "metadata":
        manifest["metadata"]["door_opening_area_m2"] = 0.05
        expected_error = "metadata does not match"
    elif tamper == "release":
        manifest["solver_release"] = "OpenFOAM Enterprise v10"
        expected_error = "unsupported solver release"
    else:
        manifest["scientific_validation"] = "PASS"
        expected_error = "unsupported solver release or validation status"

    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=expected_error):
        verify_two_room_case(case)


def test_pressure_probe_parser_converts_kinematic_pressure_with_declared_density():
    samples = parse_pressure_probe_data(
        "# Probe 0 (3 2 1.5)\n# Probe 1 (9 2 1.5)\n"
        "# Time p_room_1 p_room_2\n0 0 0\n100 4.2 0.1\n"
    )
    assert samples["sample_count"] == 2
    pressure = compute_pressure_difference_pa(samples, 1.2)
    assert pressure["delta_pressure_pa_room_1_minus_room_2"] == pytest.approx(4.92)


@pytest.mark.parametrize(
    "data",
    [
        "# Time p1 p2\n0 1\n",
        "# Time p1 p2\n0 nan 1\n",
        "# Time p1 p2\n2 1 1\n1 2 0\n",
    ],
)
def test_pressure_probe_parser_fails_closed(data):
    with pytest.raises(ValueError):
        parse_pressure_probe_data(data)


def test_two_room_execution_without_foundation_v10_writes_blocked_receipt(tmp_path, monkeypatch):
    case = tmp_path / "case"
    receipt_dir = tmp_path / "receipt"
    export_two_room_case(_spec(), case)
    monkeypatch.delenv("WM_PROJECT", raising=False)
    monkeypatch.delenv("WM_PROJECT_VERSION", raising=False)

    receipt = execute_two_room_case(case, receipt_dir)

    assert receipt["status"] == "execution_or_evidence_incomplete"
    assert receipt["scientific_validation"] == "BLOCKED"
    assert any("Expected OpenFOAM Foundation v10" in item for item in receipt["failures"])
    checked_receipt = verify_two_room_receipt(receipt_dir / "two_room_run_receipt.json")
    assert checked_receipt["status"] == "verified"
    assert checked_receipt["vtk_assets_bound"] is False
    receipt_path = receipt_dir / "two_room_run_receipt.json"
    original = json.loads(receipt_path.read_text(encoding="utf-8"))
    original["scientific_validation"] = "PASS"
    receipt_path.write_text(json.dumps(original), encoding="utf-8")
    with pytest.raises(ValueError, match="digest mismatch|cannot promote"):
        verify_two_room_receipt(receipt_path)


def _synthetic_two_room_cells():
    centers = [[index + 0.5, 0.5, 0.5] for index in range(12)]
    volumes = [1.0] * 12
    speed = [float(index + 1) for index in range(12)]
    return {
        "centers": centers,
        "volumes": volumes,
        "bounds_m": [0.0, 12.0, 0.0, 1.0, 0.0, 1.0],
        "values": {
            "speed": speed,
            "U_x": [float(index - 5) for index in range(12)],
            "p": [float(index) / 10 for index in range(12)],
        },
        "labels": {
            "speed": {"label": "Speed", "units": "m/s", "array_name": "U"},
            "U_x": {"label": "Velocity x", "units": "m/s", "array_name": "U"},
            "p": {"label": "Kinematic pressure", "units": "m^2/s^2", "array_name": "p"},
        },
    }


def test_manifest_derived_two_room_masks_check_geometry_and_volume():
    result = _derive_two_room_region_statistics(
        _synthetic_two_room_cells(), [6.0, 1.0, 1.0],
        time_name="100", case_manifest_sha256="a" * 64, vtk_sha256="b" * 64,
    )
    assert result["integrity_checks"] == {
        "domain_bounds_match_manifest": True,
        "room_volumes_match_manifest": True,
        "all_cells_assigned_exactly_once": True,
        "room_identity_source": "verified_two_room_case_manifest_and_hash-bound_VTK_asset",
    }
    room1, room2 = result["regions"]
    assert [room1["cell_count"], room2["cell_count"]] == [6, 6]
    assert [room1["volume_m3"], room2["volume_m3"]] == [6.0, 6.0]
    assert room1["statistics"]["speed"]["mean"] == pytest.approx(3.5)
    assert room2["statistics"]["speed"]["mean"] == pytest.approx(9.5)


def test_manifest_derived_two_room_masks_reject_wrong_bounds_or_volume():
    cells = _synthetic_two_room_cells()
    cells["bounds_m"] = [0.0, 13.0, 0.0, 1.0, 0.0, 1.0]
    with pytest.raises(ValueError, match="bounds differ"):
        _derive_two_room_region_statistics(
            cells, [6.0, 1.0, 1.0], time_name="100",
            case_manifest_sha256="a" * 64, vtk_sha256="b" * 64,
        )
    cells = _synthetic_two_room_cells()
    cells["volumes"][0] = 2.0
    with pytest.raises(ValueError, match="cell volume does not match"):
        _derive_two_room_region_statistics(
            cells, [6.0, 1.0, 1.0], time_name="100",
            case_manifest_sha256="a" * 64, vtk_sha256="b" * 64,
        )


def test_manifest_derived_two_room_masks_reject_interface_center():
    cells = _synthetic_two_room_cells()
    cells["centers"][5][0] = 6.0
    with pytest.raises(ValueError, match="room interface"):
        _derive_two_room_region_statistics(
            cells, [6.0, 1.0, 1.0], time_name="100",
            case_manifest_sha256="a" * 64, vtk_sha256="b" * 64,
        )


def test_two_room_field_comparison_graph_uses_room_statistics_not_user_boxes():
    regions = _derive_two_room_region_statistics(
        _synthetic_two_room_cells(), [6.0, 1.0, 1.0],
        time_name="100", case_manifest_sha256="a" * 64, vtk_sha256="b" * 64,
    )
    report = {
        "simulation_id": "synthetic-two-room",
        "mode": "two_room_receipt",
        "snapshots": [],
        "diagnostics": [],
        "sources": [],
        "room_regions": regions,
    }
    session = AnalysisSession(report, None, ())
    graph = build_analysis_graph(
        [session], kind="room_field_comparison", field_name="speed",
        case_id="two_room_case", time_name="100",
    )
    assert graph["status"] == "computed_diagnostic"
    assert [item["points"][0]["x"] for item in graph["series"]] == ["Room 1", "Room 2"]
    assert [item["points"][0]["y"] for item in graph["series"]] == pytest.approx([3.5, 9.5])
    assert graph["room_comparisons"] == [{
        "run_id": "synthetic-two-room",
        "time_name": "100",
        "field": "speed",
        "units": "m/s",
        "room_1_mean": 3.5,
        "room_2_mean": 9.5,
        "difference_room_2_minus_room_1": 6.0,
        "room_1_range": [1.0, 6.0],
        "room_2_range": [7.0, 12.0],
        "interpretation": "Room 2 volume-weighted mean minus Room 1 volume-weighted mean; diagnostic only",
    }]
    assert graph["scientific_validation"] == "BLOCKED"

    pytest.importorskip("matplotlib")
    from matplotlib.container import ErrorbarContainer
    from matplotlib.figure import Figure
    from cleanroomx.cfd_analysis_export import draw_analysis_graph

    figure = Figure(figsize=(7, 4))
    draw_analysis_graph(figure, graph, include_provenance=False)
    assert any(isinstance(container, ErrorbarContainer) for container in figure.axes[0].containers)
    assert "Δ mean" in figure.axes[0].get_title()
