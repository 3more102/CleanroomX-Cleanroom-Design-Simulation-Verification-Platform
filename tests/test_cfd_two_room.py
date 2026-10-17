import hashlib
import json

import pytest

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
