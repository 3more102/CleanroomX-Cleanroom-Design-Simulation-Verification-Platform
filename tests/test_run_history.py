from __future__ import annotations

import copy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from cleanroomx.application import run_analysis
from cleanroomx.project import (
    AnalysisDocument,
    ProjectDocument,
    load_project_document,
    save_project_document,
)
from cleanroomx.run_history import (
    RUN_HISTORY_METADATA_KEY,
    RUN_HISTORY_SCHEMA,
    RunHistoryError,
    append_run_history,
    latest_matching_run,
    restore_matching_run_cache,
    scan_run_history,
    validated_run_history_document,
)

ROOT = Path(__file__).resolve().parents[1]


def _payload() -> dict:
    return json.loads((ROOT / "examples" / "basic_room.json").read_text(encoding="utf-8"))


def _project_and_run() -> tuple[ProjectDocument, AnalysisDocument, object]:
    payload = _payload()
    analysis = AnalysisDocument(
        id="room-a",
        name="Room A",
        kind="room_verification",
        input=payload,
    )
    project = ProjectDocument(
        name="History demo",
        analyses=[analysis],
        active_analysis_id=analysis.id,
    )
    return project, analysis, run_analysis(analysis.kind, analysis.input)


def test_run_history_persists_and_restores_exact_matching_run(tmp_path):
    project, analysis, run = _project_and_run()
    entry = append_run_history(
        project,
        analysis,
        run,
        recorded_at_utc="2026-09-25T11:00:00.000000Z",
    )

    assert len(entry.sha256) == 64
    history = validated_run_history_document(project)
    assert history is not None
    assert history["schema"] == RUN_HISTORY_SCHEMA
    assert len(history["entries"]) == 1

    path = save_project_document(tmp_path / "history.cleanroomx.json", project)
    loaded = load_project_document(path)
    restored, issues = restore_matching_run_cache(loaded)

    assert issues == ()
    assert set(restored) == {"room-a"}
    assert restored["room-a"].to_dict() == run.to_dict()
    assert latest_matching_run(loaded, "room-a").to_dict() == run.to_dict()


def test_run_history_fails_closed_after_persisted_tampering():
    project, analysis, run = _project_and_run()
    append_run_history(project, analysis, run)
    project.metadata[RUN_HISTORY_METADATA_KEY]["entries"][0]["run"]["status"] = "tampered"

    scan = scan_run_history(project)
    restored, issues = restore_matching_run_cache(project)

    assert scan.entries == ()
    assert scan.issues
    assert "integrity mismatch" in scan.issues[0].error
    assert restored == {}
    assert issues == scan.issues
    with pytest.raises(RunHistoryError, match="failed integrity validation"):
        validated_run_history_document(project)


def test_run_history_keeps_stale_evidence_but_does_not_restore_it():
    project, analysis, run = _project_and_run()
    append_run_history(project, analysis, run)
    analysis.input = {**analysis.input, "name": "Changed after run"}

    scan = scan_run_history(project)
    restored, issues = restore_matching_run_cache(project)

    assert len(scan.entries) == 1
    assert scan.issues == ()
    assert restored == {}
    assert issues == ()
    assert latest_matching_run(project, analysis.id) is None


def test_run_history_is_bounded_per_analysis_and_globally():
    project, analysis, run = _project_and_run()
    for index in range(4):
        append_run_history(
            project,
            analysis,
            run,
            max_entries=3,
            max_entries_per_analysis=2,
            max_bytes=1024 * 1024,
            recorded_at_utc=f"2026-09-25T11:00:0{index}.000000Z",
        )

    scan = scan_run_history(project)
    assert scan.issues == ()
    assert [entry.recorded_at_utc for entry in scan.entries] == [
        "2026-09-25T11:00:02.000000Z",
        "2026-09-25T11:00:03.000000Z",
    ]


def test_run_history_refuses_to_overwrite_invalid_existing_evidence():
    project, analysis, run = _project_and_run()
    append_run_history(project, analysis, run)
    before = copy.deepcopy(project.metadata[RUN_HISTORY_METADATA_KEY])
    project.metadata[RUN_HISTORY_METADATA_KEY]["entries"][0]["analysis"]["name"] = "Corrupted"
    corrupted = copy.deepcopy(project.metadata[RUN_HISTORY_METADATA_KEY])

    with pytest.raises(RunHistoryError, match="refusing to overwrite preserved evidence"):
        append_run_history(project, analysis, run)

    assert project.metadata[RUN_HISTORY_METADATA_KEY] == corrupted
    assert project.metadata[RUN_HISTORY_METADATA_KEY] != before


def test_run_history_rejects_future_history_schema_without_affecting_project():
    project, _analysis, _run = _project_and_run()
    project.metadata[RUN_HISTORY_METADATA_KEY] = {
        "schema": RUN_HISTORY_SCHEMA,
        "schema_version": 999,
        "policy": {},
        "entries": [],
        "integrity": {},
    }

    scan = scan_run_history(project)
    assert scan.entries == ()
    assert len(scan.issues) == 1
    assert "unsupported run-history schema version" in scan.issues[0].error


def test_run_history_preserves_removed_analysis_as_audit_evidence():
    project, analysis, run = _project_and_run()
    append_run_history(project, analysis, run)
    project.analyses.clear()
    project.active_analysis_id = None

    scan = scan_run_history(project)
    restored, issues = restore_matching_run_cache(project)

    assert len(scan.entries) == 1
    assert scan.entries[0].analysis_id == "room-a"
    assert restored == {}
    assert issues == ()


def test_run_history_rejects_oversized_single_record_transactionally():
    project, analysis, run = _project_and_run()
    oversized_run = replace(run, markdown="x" * 5000)
    before = copy.deepcopy(project.metadata)

    with pytest.raises(RunHistoryError, match="too large"):
        append_run_history(
            project,
            analysis,
            oversized_run,
            max_entries=25,
            max_entries_per_analysis=5,
            max_bytes=1024,
        )

    assert project.metadata == before
