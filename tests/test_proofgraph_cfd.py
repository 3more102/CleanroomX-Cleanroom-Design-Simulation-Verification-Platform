"""Synthetic receipt fixtures test evidence mapping, not CFD model validity."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from cleanroomx.cfd_grid_family import SCHEMA as FAMILY_SCHEMA, generate_grid_family
from cleanroomx.cfd_grid_runner import run_grid_family
from cleanroomx.proofgraph_cfd import proofgraph_from_cfd_grid_family
from cleanroomx.proofgraph_io import proofgraph_from_dict


def _family_spec():
    return {
        "schema_version": FAMILY_SCHEMA,
        "base_case": {
            "schema_version": "cleanroomx.openfoam.v1",
            "name": "Synthetic ProofGraph fixture (not a real cleanroom)",
            "room_m": [1, 1, 1],
            "mesh_cells": [6, 6, 6],
            "supply_flow_m3_s": 0.1,
            "kinematic_viscosity_m2_s": 1.5e-5,
            "max_iterations": 12,
            "output_interval": 6,
        },
        "mesh_levels": {
            "coarse": [6, 6, 6],
            "medium": [9, 9, 9],
            "fine": [12, 12, 12],
        },
    }


@pytest.fixture
def family(tmp_path):
    target = tmp_path / "family"
    generate_grid_family(_family_spec(), target)
    return target


def _run_fake_openfoam(family, monkeypatch, *, failure=None):
    import cleanroomx.cfd_grid_runner as runner

    calls = []
    monkeypatch.setattr(runner.shutil, "which", lambda tool: "/fake/" + tool)

    def run(command, **kwargs):
        name = Path(command[0]).name
        if name == "foamVersion":
            return SimpleNamespace(returncode=0, stdout="10\n", stderr="")
        case = kwargs["cwd"].relative_to(family).as_posix()
        calls.append((case, name))
        kwargs["stdout"].write(
            f"Synthetic process-exit fixture for {case} {name}; not CFD evidence.\n"
        )
        return SimpleNamespace(returncode=1 if (case, name) == failure else 0)

    monkeypatch.setattr(runner.subprocess, "run", run)
    return calls


def _statuses(graph):
    return {finding.requirement_id: finding.status for finding in graph.findings}


def test_complete_receipt_maps_only_local_integrity_to_pass(family, monkeypatch):
    calls = _run_fake_openfoam(family, monkeypatch)
    run_grid_family(family, timeout_seconds=60)

    graph = proofgraph_from_cfd_grid_family(family)
    statuses = _statuses(graph)

    assert len(calls) == 27
    assert statuses["cfd-nine-case-local-execution-integrity"] == "pass"
    assert statuses["cfd-independent-measured-correlation"] == "unknown"
    assert [statuses[f"cfd-grid-screening-configuration-{i}"] for i in (1, 2, 3)] == [
        "not_checked", "not_checked", "not_checked"
    ]
    assert graph.verification_runs[0].metadata["engineering_review"] == "BLOCKED"
    assert graph.verification_runs[0].metadata["solver_authenticity"] == "not_verified"
    assert graph.verification_runs[0].metadata["independent_custody"] == "not_verified"
    assert graph.verification_runs[0].metadata["physical_validation"] == "not_available"
    assert graph.verification_runs[0].metadata["certification"] == "not_claimed"

    document = graph.to_dict()
    restored = proofgraph_from_dict(copy.deepcopy(document))
    assert restored.to_dict() == document


def test_generated_family_without_receipt_remains_unknown(family):
    graph = proofgraph_from_cfd_grid_family(family)

    assert _statuses(graph)["cfd-nine-case-local-execution-integrity"] == "unknown"
    receipt_evidence = [
        item for item in graph.evidence
        if item.property_name == "cfd_grid_execution_receipt_snapshot"
    ]
    assert receipt_evidence == []
    assert graph.verification_runs[0].metadata["engineering_review"] == "BLOCKED"


def test_incomplete_execution_receipt_does_not_pass(family, monkeypatch):
    _run_fake_openfoam(
        family,
        monkeypatch,
        failure=("configuration_1/coarse", "simpleFoam"),
    )
    report = run_grid_family(family, timeout_seconds=60)
    assert report["status"] == "incomplete"

    graph = proofgraph_from_cfd_grid_family(family)

    assert _statuses(graph)["cfd-nine-case-local-execution-integrity"] == "unknown"
    assert graph.verification_runs[0].metadata["local_execution_integrity_status"] == (
        "incomplete_execution_logs_integrity_verified"
    )


def test_tampered_solver_log_fails_local_integrity_finding(family, monkeypatch):
    _run_fake_openfoam(family, monkeypatch)
    run_grid_family(family, timeout_seconds=60)
    log = family / "configuration_1/coarse/blockMesh.log"
    log.write_text(log.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")

    graph = proofgraph_from_cfd_grid_family(family)

    assert _statuses(graph)["cfd-nine-case-local-execution-integrity"] == "fail"
    verification = next(
        item for item in graph.evidence
        if item.property_name == "cfd_grid_local_integrity_verification"
    )
    assert any("log_digest_mismatch" in item for item in verification.value["findings"])


def _study_spec(configuration: int):
    criteria = {
        "min_refinement_ratio": 1.1,
        "max_relative_volume_error": 0.001,
        "min_observed_order": 0.5,
        "max_observed_order": 6.0,
        "max_fine_gci_percent": 5.0,
        "safety_factor": 1.25,
        "max_axis_ratio_spread": 0.05,
    }
    return {
        "schema_version": "cleanroomx.cfd-grid-study.v1",
        "name": f"Synthetic grid screen {configuration}",
        "configuration": configuration,
        "room_volume_m3": 1.0,
        "quantity": "velocity_mean_m_s",
        "unit": "m/s",
        "criteria": criteria,
        "log_audit": {
            "fields": ["Ux", "Uy", "Uz", "p"],
            "window": 3,
            "max_initial_residual": 1e-5,
            "max_final_residual": 1e-7,
            "max_global_continuity": 1e-6,
        },
        "runs": [
            {
                "level": level,
                "mesh_cells": [n, n, n],
                "vtk_file": f"{level}.vtu",
                "solver_log": f"{level}.log",
                "run_id": f"{configuration}-{level}",
                "conditions_sha256": "a" * 64,
            }
            for level, n in (("fine", 8), ("medium", 4), ("coarse", 2))
        ],
    }


def _write_uniform_vtu(path: Path, cells_per_axis: int, value: float):
    vtk = pytest.importorskip("vtk")
    points = vtk.vtkPoints()
    for k in range(cells_per_axis + 1):
        for j in range(cells_per_axis + 1):
            for i in range(cells_per_axis + 1):
                points.InsertNextPoint(
                    i / cells_per_axis,
                    j / cells_per_axis,
                    k / cells_per_axis,
                )
    grid = vtk.vtkUnstructuredGrid()
    grid.SetPoints(points)
    velocity = vtk.vtkDoubleArray()
    velocity.SetName("U")
    velocity.SetNumberOfComponents(3)
    contaminant = vtk.vtkDoubleArray()
    contaminant.SetName("T")
    index = lambda i, j, k: (k * (cells_per_axis + 1) + j) * (cells_per_axis + 1) + i
    for k in range(cells_per_axis):
        for j in range(cells_per_axis):
            for i in range(cells_per_axis):
                vertices = (
                    index(i, j, k),
                    index(i + 1, j, k),
                    index(i + 1, j + 1, k),
                    index(i, j + 1, k),
                    index(i, j, k + 1),
                    index(i + 1, j, k + 1),
                    index(i + 1, j + 1, k + 1),
                    index(i, j + 1, k + 1),
                )
                cell = vtk.vtkHexahedron()
                for slot, point_id in enumerate(vertices):
                    cell.GetPointIds().SetId(slot, point_id)
                grid.InsertNextCell(cell.GetCellType(), cell.GetPointIds())
                velocity.InsertNextTuple3(value, 0.0, 0.0)
                contaminant.InsertNextValue(value)
    grid.GetCellData().AddArray(velocity)
    grid.GetCellData().AddArray(contaminant)
    writer = vtk.vtkXMLUnstructuredGridWriter()
    writer.SetFileName(str(path))
    writer.SetInputData(grid)
    assert writer.Write() == 1


def _write_screened_solver_log(path: Path, run_id: str):
    lines = [f"Synthetic run identifier: {run_id}"]
    for _ in range(3):
        for field in ("Ux", "Uy", "Uz", "p"):
            lines.append(
                f"Solving for {field}, Initial residual = 1e-8, "
                "Final residual = 1e-11, No Iterations 3"
            )
        lines.append(
            "time step continuity errors : sum local = 1e-9, "
            "global = 1e-10, cumulative = 3e-10"
        )
    path.write_text("\n".join(lines) + "\nEnd\n", encoding="utf-8")


@pytest.mark.parametrize(
    ("screening_status", "expected_status"),
    [
        ("eligible_for_engineering_review", "warning"),
        ("indeterminate_or_failed", "indeterminate"),
    ],
)
def test_grid_study_screen_is_exported_without_physical_promotion(
    family, tmp_path, monkeypatch, screening_status, expected_status
):
    import cleanroomx.proofgraph_cfd as adapter

    studies = tmp_path / "studies"
    studies.mkdir()
    paths = []
    for configuration in (1, 2, 3):
        path = studies / f"configuration_{configuration}.json"
        path.write_text(json.dumps(_study_spec(configuration)), encoding="utf-8")
        paths.append(path)
    monkeypatch.setattr(
        adapter,
        "analyze_vtk_grid_study",
        lambda spec, base_directory: {
            "schema_version": "cleanroomx.cfd-grid-study.v1",
            "configuration": spec["configuration"],
            "status": screening_status,
            "blockers": [] if screening_status.startswith("eligible") else ["screen blocked"],
        },
    )

    graph = proofgraph_from_cfd_grid_family(family, grid_study_specs=paths)

    statuses = _statuses(graph)
    assert [statuses[f"cfd-grid-screening-configuration-{i}"] for i in (1, 2, 3)] == [
        expected_status, expected_status, expected_status
    ]
    assert statuses["cfd-independent-measured-correlation"] == "unknown"
    assert graph.verification_runs[0].metadata["engineering_review"] == "BLOCKED"
    assert len([item for item in graph.evidence if item.property_name == "cfd_three_grid_screening_result"]) == 3


def test_duplicate_grid_configuration_is_rejected(family, tmp_path, monkeypatch):
    import cleanroomx.proofgraph_cfd as adapter

    monkeypatch.setattr(
        adapter,
        "analyze_vtk_grid_study",
        lambda spec, base_directory: {"status": "eligible_for_engineering_review", "blockers": []},
    )
    studies = tmp_path / "studies"
    studies.mkdir()
    paths = []
    for index in (1, 2):
        path = studies / f"{index}.json"
        path.write_text(json.dumps(_study_spec(1)), encoding="utf-8")
        paths.append(path)

    with pytest.raises(ValueError, match="duplicate CFD grid-study configuration"):
        proofgraph_from_cfd_grid_family(family, grid_study_specs=paths)


def test_grid_proofgraph_runs_three_real_vtk_screens(tmp_path):
    pytest.importorskip("vtk")
    family = tmp_path / "family"
    generate_grid_family(_family_spec(), family)
    studies = tmp_path / "studies"
    studies.mkdir()
    paths = []
    for configuration in (1, 2, 3):
        study_dir = studies / f"configuration_{configuration}"
        study_dir.mkdir()
        spec = _study_spec(configuration)
        for record in spec["runs"]:
            cells_per_axis = record["mesh_cells"][0]
            record["vtk_file"] = f"{record['level']}.vtu"
            record["solver_log"] = f"{record['level']}.log"
            value = 1.0 + 0.1 * (1 / cells_per_axis) ** 2
            _write_uniform_vtu(
                study_dir / record["vtk_file"], cells_per_axis, value
            )
            _write_screened_solver_log(
                study_dir / record["solver_log"],
                f"configuration-{configuration}-{record['level']}",
            )
        spec_path = study_dir / "study.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        paths.append(spec_path)

    graph = proofgraph_from_cfd_grid_family(family, grid_study_specs=paths)

    statuses = _statuses(graph)
    assert [statuses[f"cfd-grid-screening-configuration-{i}"] for i in (1, 2, 3)] == [
        "warning", "warning", "warning"
    ]
    assert statuses["cfd-independent-measured-correlation"] == "unknown"
    reports = [
        item.value["report"] for item in graph.evidence
        if item.property_name == "cfd_three_grid_screening_result"
    ]
    assert len(reports) == 3
    assert all(report["status"] == "eligible_for_engineering_review" for report in reports)
    assert all(len({grid["vtk_sha256"] for grid in report["grids"]}) == 3 for report in reports)
    assert graph.verification_runs[0].metadata["engineering_review"] == "BLOCKED"


def test_grid_proofgraph_cli_publishes_canonical_json_outside_family(
    family, tmp_path, monkeypatch
):
    from cleanroomx.cfd_pipeline_cli import main

    output = tmp_path / "evidence" / "cfd-grid.proofgraph.json"
    monkeypatch.setattr(sys, "argv", [
        "cleanroomx-cfd-pipeline", "grid-proofgraph", str(family), "--output", str(output)
    ])

    assert main() == 0
    document = json.loads(output.read_text(encoding="utf-8"))
    graph = proofgraph_from_dict(document)
    assert graph.id.startswith("proofgraph:cfd-grid:")
    assert _statuses(graph)["cfd-independent-measured-correlation"] == "unknown"


def test_grid_proofgraph_cli_refuses_output_inside_evidence_family(family, monkeypatch):
    from cleanroomx.cfd_pipeline_cli import main

    output = family / "proofgraph.json"
    monkeypatch.setattr(sys, "argv", [
        "cleanroomx-cfd-pipeline", "grid-proofgraph", str(family), "--output", str(output)
    ])

    assert main() == 1
    assert not output.exists()
