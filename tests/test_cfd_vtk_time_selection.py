import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

import cleanroomx.cfd_vtk_time_selection as time_selection
from cleanroomx.cfd_vtk_time_selection import (
    _validated_selected_times,
    _verified_patch_face_count,
    audit_openfoam_vtk_time_selection,
    parse_foam_to_vtk_time_log,
)


def test_v10_foam_to_vtk_log_accepts_only_the_requested_time():
    log = "OpenFOAM Foundation Version: 10\nTime: 100\nWriting VTK files\nEnd\n"

    assert parse_foam_to_vtk_time_log(log, "100") == ["100"]


def test_v10_foam_to_vtk_log_accepts_the_exact_ordered_multi_time_selection():
    log = "OpenFOAM Foundation Version: 10\nTime: 50\nTime: 100\nWriting VTK files\nEnd\n"

    assert parse_foam_to_vtk_time_log(log, "50,100") == ["50", "100"]


@pytest.mark.parametrize(
    ("log", "expected_times"),
    [
        ("Time: 50\nEnd\n", "50,100"),
        ("Time: 50\nTime: 150\nEnd\n", "50,100"),
        ("Time: 100\nTime: 50\nEnd\n", "50,100"),
        ("Time: 50\nTime: 100\nTime: 150\nEnd\n", "50,100"),
    ],
)
def test_v10_foam_to_vtk_log_rejects_a_partial_extra_or_reordered_multi_time_selection(
    log, expected_times
):
    with pytest.raises(ValueError):
        parse_foam_to_vtk_time_log(log, expected_times)


@pytest.mark.parametrize(
    "selected_times",
    [
        "",
        "50,,100",
        "50,50",
        "50,50.0",
        "100,50",
        "latestTime",
        "50,nan",
        "50,inf",
        "-1,50",
    ],
)
def test_selected_time_list_must_be_finite_unique_and_strictly_increasing(selected_times):
    with pytest.raises(ValueError):
        _validated_selected_times(selected_times)


def test_multi_time_vtk_audit_records_each_time_without_colliding_with_latest_output(
    tmp_path, monkeypatch
):
    family = tmp_path / "family"
    family.mkdir()
    case_ids = [
        f"configuration_{configuration}/{level}"
        for configuration in (1, 2, 3)
        for level in ("coarse", "medium", "fine")
    ]
    family_spec_sha = "a" * 64
    manifest = {
        "schema_version": "cleanroomx.cfd-grid-family.v1",
        "family_spec_sha256": family_spec_sha,
        "case_inputs": {case_id: {"mesh_cells": 2} for case_id in case_ids},
    }
    receipt = {
        "schema_version": "cleanroomx.openfoam-grid-execution-evidence.v1",
        "status": "executed_requires_convergence_review",
        "family_spec_sha256": family_spec_sha,
        "scientific_validation": "BLOCKED",
        "executables": {"foamToVTK": str(Path(sys.executable).resolve())},
        "solver_build": "Foundation-v10-test-build",
        "cases": {
            case_id: {
                "stages": [
                    {"command": command, "returncode": 0}
                    for command in ("blockMesh", "checkMesh", "simpleFoam", "foamToVTK")
                ]
            }
            for case_id in case_ids
        },
    }
    (family / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (family / "grid_execution_evidence.json").write_text(json.dumps(receipt), encoding="utf-8")

    for case_id in case_ids:
        case_dir = family / case_id
        vtk_dir = case_dir / "VTK"
        (case_dir / "constant" / "polyMesh").mkdir(parents=True)
        (vtk_dir / "inlet").mkdir(parents=True)
        (vtk_dir / "outlet").mkdir()
        (vtk_dir / "walls").mkdir()
        (vtk_dir / "surfaceFields").mkdir()
        # The baseline latestTime export already owns time 150; the new audit
        # selects 50 and 100 into the same VTK tree without overwriting it.
        (vtk_dir / f"{case_dir.name}_150.vtk").write_text("baseline latest time\n", encoding="utf-8")
        for selected_time in ("50", "100"):
            time_dir = case_dir / selected_time
            time_dir.mkdir()
            for field in ("U", "p", "phi"):
                (time_dir / field).write_text(f"{case_id} {selected_time} {field}\n", encoding="utf-8")

    monkeypatch.setenv("WM_PROJECT", "OpenFOAM")
    monkeypatch.setenv("WM_PROJECT_VERSION", "10")
    monkeypatch.setattr(time_selection.shutil, "which", lambda tool: sys.executable)
    monkeypatch.setattr(
        time_selection,
        "_foundation_v10_banner",
        lambda log: {"is_foundation_v10": True, "build": "Foundation-v10-test-build"},
    )
    monkeypatch.setattr(time_selection, "import_vtk_case", lambda path: {"mesh_cells": 2})
    monkeypatch.setattr(
        time_selection,
        "audit_openfoam_vtk_velocity",
        lambda *args: {
            "status": "PASS",
            "cell_count": 2,
            "compared_velocity_components": 6,
        },
    )
    monkeypatch.setattr(
        time_selection,
        "audit_openfoam_vtk_pressure",
        lambda *args: {"status": "PASS", "cell_count": 2, "compared_scalar_values": 2},
    )
    monkeypatch.setattr(
        time_selection,
        "audit_openfoam_vtk_boundary_patch",
        lambda *args: {"status": "PASS", "native_face_count": 1, "vtk_face_count": 1},
    )
    monkeypatch.setattr(
        time_selection,
        "audit_openfoam_vtk_surface_flux",
        lambda *args: {
            "status": "PASS",
            "face_count": 3,
            "compared_flux_vector_components": 9,
        },
    )

    calls = []

    def fake_foam_to_vtk(command, *, cwd, **kwargs):
        calls.append((cwd.relative_to(family).as_posix(), command[command.index("-time") + 1]))
        assert command[command.index("-time") + 1] == "50,100"
        vtk_dir = cwd / "VTK"
        for selected_time in ("50", "100"):
            (vtk_dir / f"{cwd.name}_{selected_time}.vtk").write_text(
                f"internal {selected_time}\n", encoding="utf-8"
            )
            for patch in ("inlet", "outlet", "walls"):
                (vtk_dir / patch / f"{patch}_{selected_time}.vtk").write_text(
                    f"{patch} {selected_time}\n", encoding="utf-8"
                )
            (vtk_dir / "surfaceFields" / f"surfaceFields_{selected_time}.vtk").write_text(
                f"phi {selected_time}\n", encoding="utf-8"
            )
        log = (
            "OpenFOAM Foundation Version: 10\n"
            "Time: 50\nTime: 100\nEnd\n"
        ).encode("utf-8")
        return SimpleNamespace(returncode=0, stdout=log)

    monkeypatch.setattr(time_selection.subprocess, "run", fake_foam_to_vtk)

    report = audit_openfoam_vtk_time_selection(family, selected_times="50,100")

    assert len(calls) == 9
    assert report["schema_version"] == "cleanroomx.openfoam-vtk-time-selection-evidence.v2"
    assert report["selected_times"] == ["50", "100"]
    assert all(set(case["times"]) == {"50", "100"} for case in report["cases"].values())
    assert report["summary"] == {
        "cases": 9,
        "selected_times_per_case": ["50", "100"],
        "selected_time_count_per_case": 2,
        "internal_cell_datasets": 18,
        "patch_datasets": 54,
        "surface_phi_datasets": 18,
        "internal_cells_compared": 36,
        "velocity_components_compared": 108,
        "pressure_values_compared": 36,
        "patch_faces_compared": 54,
        "surface_flux_faces_compared": 54,
        "surface_flux_components_compared": 162,
    }
    assert (family / "configuration_1/coarse/VTK/coarse_150.vtk").read_text(
        encoding="utf-8"
    ) == "baseline latest time\n"


def test_explicit_time_summary_counts_only_complete_native_vtk_patch_coverage():
    parity = {
        "inlet": {"status": "PASS", "native_face_count": 4, "vtk_face_count": 4},
        "outlet": {"status": "PASS", "native_face_count": 24, "vtk_face_count": 24},
        "walls": {"status": "PASS", "native_face_count": 188, "vtk_face_count": 188},
    }

    assert _verified_patch_face_count(parity) == 216


@pytest.mark.parametrize(
    "parity",
    [
        {"inlet": {"status": "PASS", "native_face_count": 4, "vtk_face_count": 4}},
        {
            "inlet": {"status": "PASS", "native_face_count": 4, "vtk_face_count": 4},
            "outlet": {"status": "PASS", "native_face_count": 24, "vtk_face_count": 23},
            "walls": {"status": "PASS", "native_face_count": 188, "vtk_face_count": 188},
        },
        {
            "inlet": {"status": "FAIL", "native_face_count": 4, "vtk_face_count": 4},
            "outlet": {"status": "PASS", "native_face_count": 24, "vtk_face_count": 24},
            "walls": {"status": "PASS", "native_face_count": 188, "vtk_face_count": 188},
        },
    ],
)
def test_explicit_time_summary_rejects_incomplete_or_mismatched_patch_receipts(parity):
    with pytest.raises(ValueError):
        _verified_patch_face_count(parity)


@pytest.mark.parametrize(
    ("log", "expected_time"),
    [
        ("OpenFOAM\nEnd\n", "100"),
        ("Time: 50\nEnd\n", "100"),
        ("Time: 100\nTime: 150\nEnd\n", "100"),
        ("Time: 100\nEnd\nTime: 100\n", "100"),
        ("Time: 100\n", "100"),
        ("Time: 100\nFOAM FATAL ERROR: failed\nEnd\n", "100"),
    ],
)
def test_v10_foam_to_vtk_log_rejects_missing_wrong_or_incomplete_selection(log, expected_time):
    with pytest.raises(ValueError):
        parse_foam_to_vtk_time_log(log, expected_time)


@pytest.mark.parametrize("expected_time", ["", "latestTime", "nan", "inf", "-1"])
def test_v10_foam_to_vtk_log_requires_one_finite_numeric_time_name(expected_time):
    with pytest.raises(ValueError):
        parse_foam_to_vtk_time_log("Time: 100\nEnd\n", expected_time)
