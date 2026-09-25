from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

import cleanroomx.application as application_module
from cleanroomx.application import application_info, run_analysis
from cleanroomx.runtime_provenance import (
    EXECUTION_IMPLEMENTATION_SCHEMA,
    IMPLEMENTATION_REVISION_SCHEMA,
    ImplementationChangedError,
    ImplementationProvenanceError,
    capture_implementation_revision,
    compare_implementation_revisions,
)


ROOT = Path(__file__).resolve().parents[1]


def _example(name: str) -> dict:
    return json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))


def _write_source_tree(root: Path, *, newline: bytes = b"\n") -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "__init__.py").write_bytes(b'VALUE = 1' + newline)
    (root / "solver.py").write_bytes(
        b'def solve(value):' + newline + b'    return value + 1' + newline
    )


def test_source_tree_identity_is_location_and_newline_independent(tmp_path):
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    _write_source_tree(first_root, newline=b"\n")
    _write_source_tree(second_root, newline=b"\r\n")

    first = capture_implementation_revision(first_root)
    second = capture_implementation_revision(second_root)

    assert first.source_tree_sha256 == second.source_tree_sha256
    assert first.source_file_count == 2
    assert [item.path for item in first.source_files] == ["__init__.py", "solver.py"]


def test_source_tree_identity_ignores_non_python_files(tmp_path):
    root = tmp_path / "package"
    _write_source_tree(root)
    before = capture_implementation_revision(root)
    (root / "notes.txt").write_text("operator note", encoding="utf-8")
    after = capture_implementation_revision(root)
    assert before.source_tree_sha256 == after.source_tree_sha256


def test_source_tree_change_is_localized_deterministically(tmp_path):
    root = tmp_path / "package"
    _write_source_tree(root)
    before = capture_implementation_revision(root)
    (root / "solver.py").write_text(
        "def solve(value):\n    return value + 2\n", encoding="utf-8"
    )
    after = capture_implementation_revision(root)

    evidence = compare_implementation_revisions(
        before,
        after,
        entrypoints={"execution": "cleanroomx.solver:solve"},
    )

    assert evidence["stable_during_run"] is False
    assert evidence["changed_source_files"] == ["solver.py"]
    assert evidence["source_tree_sha256_before"] != evidence["source_tree_sha256_after"]


def test_source_tree_requires_python_source(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    with pytest.raises(ImplementationProvenanceError, match="contains no Python source"):
        capture_implementation_revision(root)


def test_analysis_run_records_exact_implementation_and_runtime_evidence():
    run = run_analysis("room_verification", _example("basic_room.json"))
    evidence = run.diagnostics["application_execution_provenance"]["implementation"]

    assert evidence["schema"] == EXECUTION_IMPLEMENTATION_SCHEMA
    assert evidence["schema_version"] == 1
    assert evidence["stable_during_run"] is True
    assert evidence["runtime_stable"] is True
    assert evidence["changed_source_files"] == []
    assert len(evidence["source_tree_sha256_before"]) == 64
    assert evidence["source_tree_sha256_before"] == evidence["source_tree_sha256_after"]
    assert evidence["source_file_count_before"] > 1
    assert evidence["source_file_count_before"] == evidence["source_file_count_after"]
    assert evidence["entrypoints"] == {
        "execution": "cleanroomx.verification:verify_room",
        "reporting": "cleanroomx.application:_fallback_markdown",
        "validation": "cleanroomx.io:room_from_dict",
    }
    assert evidence["runtime"]["python_version"]
    assert evidence["runtime"]["python_implementation"]


def test_custom_adapter_run_records_application_adapter_entrypoints():
    payload = {
        "verification_project": "facility_project.json",
        "hvac_project": "consistency_hvac_demo.json",
        "room_airflow_abs_tolerance_m3_h": 0.0,
        "require_same_room_set": True,
    }
    run = run_analysis("consistency", payload, base_dir=ROOT / "examples")
    evidence = run.diagnostics["application_execution_provenance"]["implementation"]
    assert evidence["entrypoints"] == {
        "execution": "cleanroomx.application:_run_consistency",
        "reporting": "cleanroomx.consistency_report:markdown_consistency_report",
        "validation": "cleanroomx.application:_validate_consistency",
    }


def test_analysis_result_is_discarded_if_implementation_changes(monkeypatch):
    before = capture_implementation_revision()
    changed_file = replace(before.source_files[0], sha256="0" * 64)
    after = replace(
        before,
        source_tree_sha256="1" * 64,
        source_files=(changed_file,) + before.source_files[1:],
    )
    revisions = iter((before, after))
    monkeypatch.setattr(
        application_module,
        "capture_implementation_revision",
        lambda: next(revisions),
    )

    with pytest.raises(ImplementationChangedError, match="result was discarded") as exc:
        run_analysis("room_verification", _example("basic_room.json"))

    assert exc.value.evidence["stable_during_run"] is False
    assert exc.value.evidence["changed_source_files"] == [before.source_files[0].path]


def test_application_info_exposes_reproducible_implementation_revision():
    info = application_info()
    implementation = info["implementation"]
    assert implementation["schema"] == IMPLEMENTATION_REVISION_SCHEMA
    assert implementation["schema_version"] == 1
    assert len(implementation["source_tree_sha256"]) == 64
    assert implementation["source_file_count"] > 1
    assert implementation["runtime"]["python_version"]
    assert "source_files" not in implementation
