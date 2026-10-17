"""Synthetic fixture checks for receipt-bound, face-level phi diagnostics."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cleanroomx import cfd_two_room_boundary as boundary
from cleanroomx.cfd_convergence_triage import diagnose_grid_flux
from cleanroomx.cfd_pipeline_cli import build_parser


def _fixture(tmp_path, monkeypatch):
    case = tmp_path / "case"
    (case / "150").mkdir(parents=True)
    (case / "constant" / "polyMesh").mkdir(parents=True)
    counts = {"inlet": 2, "outlet": 2, "walls": 2, "partition": 1}
    boundary_text = "FoamFile\n{ version 2; }\n4\n(\n" + "\n".join(
        f"{name}\n{{\n type patch;\n nFaces {count};\n startFace {offset};\n}}"
        for (name, count, offset) in (
            ("inlet", 2, 0), ("outlet", 2, 2),
            ("walls", 2, 4), ("partition", 1, 6),
        )
    ) + "\n)\n"
    (case / "constant" / "polyMesh" / "boundary").write_text(boundary_text)
    fluxes = {
        "inlet": [-0.05, -0.05],
        "outlet": [0.049, 0.05],
        "walls": [0.0003, -0.0001],
        "partition": [0.0002],
    }
    entries = []
    for name, numbers in fluxes.items():
        lines = "\n".join(str(v) for v in numbers)
        entries.append(
            f"{name}\n{{\n type calculated;\n value nonuniform List<scalar> "
            f"{len(numbers)}\n(\n{lines}\n);\n}}"
        )
    phi_text = (
        "FoamFile { version 2; }\n"
        "dimensions [0 3 -1 0 0 0 0];\n"
        "boundaryField\n{\n" + "\n".join(entries) + "\n}\n"
    )
    phi = case / "150" / "phi"
    phi.write_text(phi_text)
    flow = diagnose_grid_flux(case, "150", family_root=tmp_path)
    assert flow["status"] == "MEASURED_DIAGNOSTIC_ONLY"
    assert flow["patch_face_counts"] == counts
    flow = {**flow, "phi_path": "150/phi", "case_id": "two_room_case"}
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({
        "receipt_sha256": "a" * 64,
        "manifest_sha256": "b" * 64,
        "solver_flux": flow,
        "pressure_probe": {"last_solver_time": 150.0},
    }), encoding="utf-8")
    calls = []
    monkeypatch.setattr(
        boundary, "proofgraph_from_two_room_receipt",
        lambda cp, rp: calls.append((cp, rp)),
    )
    return case, receipt, phi, calls


def _policy():
    return {
        "schema_version": boundary.SCHEMA,
        "max_total_boundary_imbalance_percent": 1.0,
        "max_wall_gross_leakage_percent": 1.0,
        "max_reverse_inlet_percent": 0.0,
        "max_reverse_outlet_percent": 0.0,
    }


def test_complete_derived_patch_fluxes_and_source_receipt_binding(tmp_path, monkeypatch):
    case, receipt, _, calls = _fixture(tmp_path, monkeypatch)
    result = boundary.screen_two_room_boundary_flow(case, receipt, _policy())
    assert calls == [(case, receipt)]
    assert result["status"] == "PROJECT_BOUNDARY_SCREEN_MET"
    assert result["source_receipt_sha256"] == "a" * 64
    assert result["patch_face_counts"]["partition"] == 1
    assert result["fluxes_m3_s"]["gross_inlet"] == pytest.approx(0.1)
    assert result["fluxes_m3_s"]["gross_wall_and_partition_leakage"] == pytest.approx(0.0006)
    assert result["percent_of_gross_inlet"]["wall_gross_leakage_percent"] == pytest.approx(0.6)
    assert result["percent_of_gross_inlet"]["total_boundary_imbalance_percent"] == pytest.approx(0.6)
    assert result["scientific_validation"] == "BLOCKED"
    assert result["solver_convergence"] == "NOT_ASSESSED"
    assert result["mesh_independence"] == "NOT_ASSESSED"
    assert len(result["unsigned_policy_sha256"]) == 64


def test_stricter_user_limits_report_not_met_without_claiming_validation(tmp_path, monkeypatch):
    case, receipt, _, _ = _fixture(tmp_path, monkeypatch)
    criteria = _policy()
    criteria["max_total_boundary_imbalance_percent"] = 0.01
    criteria["max_wall_gross_leakage_percent"] = 0.01
    result = boundary.screen_two_room_boundary_flow(case, receipt, criteria)
    assert result["status"] == "PROJECT_BOUNDARY_SCREEN_NOT_MET"
    assert set(result["violations"]) == {
        "total_boundary_imbalance_percent", "wall_gross_leakage_percent"
    }
    assert result["scientific_validation"] == "BLOCKED"


def test_replayed_or_mutated_phi_fails_receipt_hash_gate(tmp_path, monkeypatch):
    case, receipt, phi, _ = _fixture(tmp_path, monkeypatch)
    phi.write_text(phi.read_text() + "\n// mutation\n")
    with pytest.raises(ValueError, match="source hash changed"):
        boundary.screen_two_room_boundary_flow(case, receipt, _policy())


@pytest.mark.parametrize("which", [
    "net_boundary_outward_m3_s", "walls_net_outward_m3_s",
    "relative_flux_imbalance_percent",
])
def test_receipt_summary_forgery_fails_arithmetic_cross_check(tmp_path, monkeypatch, which):
    case, receipt, _, _ = _fixture(tmp_path, monkeypatch)
    document = json.loads(receipt.read_text())
    document["solver_flux"][which] = 0.55
    receipt.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="disagree with receipt"):
        boundary.screen_two_room_boundary_flow(case, receipt, _policy())


@pytest.mark.parametrize("path", ["../phi", "150/../phi", "/tmp/phi", "150/other", "nan/phi", "150\\phi"])
def test_unsafe_or_ambiguous_source_location_rejected(tmp_path, monkeypatch, path):
    case, receipt, _, _ = _fixture(tmp_path, monkeypatch)
    document = json.loads(receipt.read_text())
    document["solver_flux"]["phi_path"] = path
    receipt.write_text(json.dumps(document))
    with pytest.raises(ValueError):
        boundary.screen_two_room_boundary_flow(case, receipt, _policy())


@pytest.mark.parametrize("mutation", [
    {"max_wall_gross_leakage_percent": True},
    {"max_reverse_inlet_percent": -1},
    {"max_reverse_outlet_percent": float("nan")},
    {"max_total_boundary_imbalance_percent": float("inf")},
    {"schema_version": "unknown"},
    {"extra": 100},
])
def test_unsafe_policy_rejected(mutation):
    policy = _policy()
    policy.update(mutation)
    with pytest.raises(ValueError):
        boundary.validate_boundary_policy(policy)


def test_cli_requires_explicit_boundary_policy_file():
    parser = build_parser()
    args = parser.parse_args([
        "two-room-boundary-screen", "case", "receipt.json", "flow_policy.json",
        "--output", "result.json",
    ])
    assert args.criteria == "flow_policy.json"
    assert args.output == "result.json"
    with pytest.raises(SystemExit):
        parser.parse_args(["two-room-boundary-screen", "case", "receipt.json"])
