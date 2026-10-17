"""Synthetic regression fixtures for signed OpenFOAM internal-cell continuity."""
from __future__ import annotations

import hashlib
import json
import math

import pytest

from cleanroomx import cfd_two_room_internal_flux as internal
from cleanroomx.cfd_pipeline_cli import build_parser


def _spec():
    return {
        "schema_version": internal.SCHEMA,
        "max_sum_abs_cell_imbalance_percent_of_gross_inlet": 5.0,
        "max_worst_cell_imbalance_percent_of_gross_inlet": 5.0,
    }


def _header(kind: str, name: str) -> str:
    return (
        "FoamFile\n{\n"
        "  version 2.0;\n  format ascii;\n"
        f"  class {kind};\n  object {name};\n"
        "}\n"
    )


def _labels(name: str, entries: list[int]) -> str:
    return _header("labelList", name) + (
        f"{len(entries)}\n(\n" + "\n".join(str(x) for x in entries) + "\n)\n"
    )


def _fixture(tmp_path, monkeypatch, internal_flux: float = 0.1):
    case = tmp_path / "case"
    (case / "150").mkdir(parents=True)
    mesh = case / "constant" / "polyMesh"
    mesh.mkdir(parents=True)
    counts = {"inlet": 2, "outlet": 2, "walls": 2, "partition": 1}
    entries = (
        ("inlet", 2, 1), ("outlet", 2, 3),
        ("walls", 2, 5), ("partition", 1, 7),
    )
    boundary = "\n".join([
        _header("polyBoundaryMesh", "boundary"),
        "4\n(",
        *(f"{name}\n{{\n type patch;\n nFaces {count};\n startFace {start};\n}}"
          for name, count, start in entries),
        ")\n",
    ])
    (mesh / "boundary").write_text(boundary)
    # Face 0 joins owner 0 -> neighbour 1; remaining faces belong to patches.
    (mesh / "owner").write_text(_labels("owner", [0, 0, 0, 1, 1, 0, 1, 0]))
    (mesh / "neighbour").write_text(_labels("neighbour", [1]))
    fields = {
        "inlet": [-0.05, -0.05],
        "outlet": [0.05, 0.05],
        "walls": [0.0, 0.0],
        "partition": [0.0],
    }
    value_entries = [
        f"{name}\n{{\n type calculated;\n value nonuniform List<scalar> {len(values)}\n("
        + "\n".join(map(str, values)) + "\n);\n}"
        for name, values in fields.items()
    ]
    phi = case / "150" / "phi"
    phi.write_text(
        _header("surfaceScalarField", "phi")
        + "dimensions [0 3 -1 0 0 0 0];\n"
        + f"internalField nonuniform List<scalar> 1\n(\n{internal_flux}\n);\n"
        + "boundaryField\n{\n" + "\n".join(value_entries) + "\n}\n"
    )
    flow = {
        "phi_path": "150/phi",
        "last_solver_time": "150",
        "phi_sha256": hashlib.sha256(phi.read_bytes()).hexdigest(),
        "poly_mesh_boundary_sha256": hashlib.sha256((mesh / "boundary").read_bytes()).hexdigest(),
        "patch_face_counts": counts,
        "net_boundary_outward_m3_s": 0.0,
        "inlet": {"gross_inward_m3_s": 0.1},
    }
    (case / "manifest.json").write_text(json.dumps({"metadata": {"mesh_cell_count": 2}}))
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({
        "receipt_sha256": "a" * 64,
        "manifest_sha256": "b" * 64,
        "solver_flux": flow,
        "pressure_probe": {"last_solver_time": 150.0},
    }))
    calls = []
    monkeypatch.setattr(
        internal, "proofgraph_from_two_room_receipt",
        lambda case_path, receipt_path: calls.append((case_path, receipt_path)),
    )
    return case, receipt, phi, mesh, calls


def test_balanced_internal_mesh_cells_reconcile_to_zero(tmp_path, monkeypatch):
    case, receipt, _, _, calls = _fixture(tmp_path, monkeypatch)
    result = internal.screen_two_room_internal_flux(case, receipt, _spec())
    assert calls == [(case, receipt)]
    assert result["status"] == "PROJECT_INTERNAL_FLUX_SCREEN_MET"
    assert result["metrics"]["internal_face_count"] == 1
    assert result["metrics"]["boundary_face_count"] == 7
    assert result["metrics"]["cell_count"] == 2
    assert result["metrics"]["sum_absolute_cell_imbalance_m3_s"] == pytest.approx(0)
    assert result["metrics"]["net_boundary_outward_m3_s"] == pytest.approx(0)
    assert result["mesh_connectivity"] == "UNSIGNED_LOCAL_INPUT_HASHES_NOT_RECEIPT_BOUND"
    assert len(result["source_files_sha256"]) == 4
    assert result["scientific_validation"] == "BLOCKED"


def test_global_balance_can_hide_worst_cell_divergence(tmp_path, monkeypatch):
    case, receipt, _, _, _ = _fixture(tmp_path, monkeypatch, internal_flux=0.09)
    result = internal.screen_two_room_internal_flux(case, receipt, _spec())
    assert result["status"] == "PROJECT_INTERNAL_FLUX_SCREEN_NOT_MET"
    assert result["metrics"]["net_boundary_outward_m3_s"] == 0.0
    assert result["metrics"]["sum_absolute_cell_imbalance_m3_s"] == pytest.approx(0.02)
    assert result["metrics"]["sum_abs_cell_imbalance_percent_of_gross_inlet"] == pytest.approx(20)
    assert result["metrics"]["worst_cell_imbalance_percent_of_gross_inlet"] == pytest.approx(10)
    assert result["violations"] == ["sum_abs_cell_imbalance", "worst_cell_imbalance"]


def test_receipt_phi_hash_mismatch_rejected(tmp_path, monkeypatch):
    case, receipt, phi, _, _ = _fixture(tmp_path, monkeypatch)
    phi.write_text(phi.read_text() + "\n// changed\n")
    with pytest.raises(ValueError, match="Receipt-bound phi/boundary digest mismatch"):
        internal.screen_two_room_internal_flux(case, receipt, _spec())


@pytest.mark.parametrize("which", ["owner", "neighbour"])
def test_corrupt_or_replayed_mesh_owner_neighbour_labels_fail(tmp_path, monkeypatch, which):
    case, receipt, _, mesh, _ = _fixture(tmp_path, monkeypatch)
    path = mesh / which
    if which == "owner":
        path.write_text(_labels("owner", [0, 0, 0, 1, 1, 0, 1, 99]))
    else:
        path.write_text(_labels("neighbour", [0]))
    with pytest.raises(ValueError, match="outside declared|self-adjacent"):
        internal.screen_two_room_internal_flux(case, receipt, _spec())


def test_missing_mesh_sources_fail_without_marking_valid(tmp_path, monkeypatch):
    case, receipt, _, mesh, _ = _fixture(tmp_path, monkeypatch)
    (mesh / "neighbour").unlink()
    with pytest.raises(ValueError):
        internal.screen_two_room_internal_flux(case, receipt, _spec())


def test_non_ascii_mesh_label_list_rejected():
    text = _labels("owner", [0, 1]).replace("format ascii", "format binary")
    with pytest.raises(ValueError, match="not ASCII"):
        internal._label_list(text, "owner", max_entries=10)


def test_malformed_internal_phi_and_face_count_rejected():
    phi = _header("surfaceScalarField", "phi") + "internalField uniform 0.1;\n"
    with pytest.raises(ValueError, match="explicit nonuniform"):
        internal._internal_phi(phi, 1)
    phi = _header("surfaceScalarField", "phi") + "internalField nonuniform List<scalar> 2\n(\n0.2\n0.3\n);\n"
    with pytest.raises(ValueError, match="count differs"):
        internal._internal_phi(phi, 1)


@pytest.mark.parametrize("difference", [
    {"max_sum_abs_cell_imbalance_percent_of_gross_inlet": True},
    {"max_sum_abs_cell_imbalance_percent_of_gross_inlet": -1},
    {"max_worst_cell_imbalance_percent_of_gross_inlet": float("nan")},
    {"max_worst_cell_imbalance_percent_of_gross_inlet": float("inf")},
    {"schema_version": "unknown"},
    {"extra": 1},
])
def test_bad_numerical_policy_is_rejected(difference):
    policy = _spec()
    policy.update(difference)
    with pytest.raises(ValueError):
        internal.validate_internal_flux_criteria(policy)


def test_internal_phi_cli_requires_explicit_criteria():
    args = build_parser().parse_args([
        "two-room-internal-flux", "case", "receipt.json", "criteria.json",
        "--output", "diagnostics.json",
    ])
    assert args.criteria == "criteria.json"
    assert args.output == "diagnostics.json"
    with pytest.raises(SystemExit):
        build_parser().parse_args(["two-room-internal-flux", "case", "receipt.json"])
