from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from cleanroomx.application import run_analysis
from cleanroomx.project import (
    AnalysisDocument,
    ProjectDocument,
    ProjectFileRevision,
    capture_project_file_revision,
    save_project_document,
)
from cleanroomx.run_history import (
    RUN_HISTORY_SCHEMA,
    RunHistoryError,
    RunHistoryIntegrityError,
    append_run_history_record,
    load_run_history_record,
    run_history_directory,
    scan_run_history,
)


ROOT = Path(__file__).resolve().parents[1]


def _payload() -> dict:
    return json.loads(
        (ROOT / "examples" / "basic_room.json").read_text(encoding="utf-8")
    )


def _saved_project(tmp_path: Path):
    payload = _payload()
    project = ProjectDocument(
        name="Run history",
        analyses=[
            AnalysisDocument(
                id="room-a",
                name="Room A",
                kind="room_verification",
                input=payload,
            )
        ],
        active_analysis_id="room-a",
    )
    path = save_project_document(tmp_path / "history.cleanroomx.json", project)
    return path, capture_project_file_revision(path), payload


def test_run_history_round_trip_binds_saved_revision_input_and_run(tmp_path):
    project_path, revision, payload = _saved_project(tmp_path)
    run = run_analysis("room_verification", payload)
    completed_at = datetime(2026, 9, 25, 11, 30, tzinfo=timezone.utc)

    record_path = append_run_history_record(
        project_path,
        project_revision=revision,
        project_dirty=True,
        analysis_id="room-a",
        analysis_name="Room A",
        input_snapshot=payload,
        run=run,
        completed_at=completed_at,
    )
    loaded = load_run_history_record(record_path)

    assert record_path.parent == run_history_directory(project_path)
    assert loaded.completed_at_utc == "2026-09-25T11:30:00.000000Z"
    assert loaded.project_filename == project_path.name
    assert loaded.project_revision.sha256 == revision.sha256
    assert loaded.project_dirty is True
    assert loaded.analysis_id == "room-a"
    assert loaded.analysis_name == "Room A"
    assert loaded.analysis_kind == "room_verification"
    assert loaded.input_snapshot == payload
    assert loaded.run == run

    raw = json.loads(record_path.read_text(encoding="utf-8"))
    assert raw["schema"] == RUN_HISTORY_SCHEMA
    assert raw["record_id"] == loaded.record_id
    assert raw["integrity"]["algorithm"] == "sha256"


def test_run_history_rejects_tampered_immutable_record(tmp_path):
    project_path, revision, payload = _saved_project(tmp_path)
    record_path = append_run_history_record(
        project_path,
        project_revision=revision,
        project_dirty=False,
        analysis_id="room-a",
        analysis_name="Room A",
        input_snapshot=payload,
        run=run_analysis("room_verification", payload),
    )
    raw = json.loads(record_path.read_text(encoding="utf-8"))
    raw["run"]["status"] = "tampered"
    record_path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(RunHistoryIntegrityError, match="SHA-256 mismatch"):
        load_run_history_record(record_path)


def test_run_history_rejects_run_that_does_not_match_input_snapshot(tmp_path):
    project_path, revision, payload = _saved_project(tmp_path)
    run = run_analysis("room_verification", payload)
    changed = dict(payload)
    changed["supply_airflow_m3_h"] = payload["supply_airflow_m3_h"] + 1.0

    with pytest.raises(RunHistoryError, match="does not match"):
        append_run_history_record(
            project_path,
            project_revision=revision,
            project_dirty=True,
            analysis_id="room-a",
            analysis_name="Room A",
            input_snapshot=changed,
            run=run,
        )

    assert not run_history_directory(project_path).exists()


def test_run_history_rejects_revision_from_another_project(tmp_path):
    project_path, _revision, payload = _saved_project(tmp_path)
    other_path = tmp_path / "other.cleanroomx.json"
    other_path.write_text("{}\n", encoding="utf-8")
    other_revision = capture_project_file_revision(other_path)

    with pytest.raises(RunHistoryError, match="does not belong"):
        append_run_history_record(
            project_path,
            project_revision=other_revision,
            project_dirty=False,
            analysis_id="room-a",
            analysis_name="Room A",
            input_snapshot=payload,
            run=run_analysis("room_verification", payload),
        )


def test_scan_run_history_preserves_and_reports_corrupt_evidence(tmp_path):
    project_path, revision, payload = _saved_project(tmp_path)
    run = run_analysis("room_verification", payload)
    older = append_run_history_record(
        project_path,
        project_revision=revision,
        project_dirty=False,
        analysis_id="room-a",
        analysis_name="Room A",
        input_snapshot=payload,
        run=run,
        completed_at=datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc),
    )
    newer = append_run_history_record(
        project_path,
        project_revision=revision,
        project_dirty=False,
        analysis_id="room-a",
        analysis_name="Room A",
        input_snapshot=payload,
        run=run,
        completed_at=datetime(2026, 9, 25, 11, 0, tzinfo=timezone.utc),
    )
    corrupt = run_history_directory(project_path) / "99999999_corrupt.json"
    corrupt.write_text("{broken", encoding="utf-8")

    items = scan_run_history(project_path)

    assert [item.path for item in items] == [corrupt, newer, older]
    assert items[0].record is None
    assert "invalid run-history JSON" in items[0].error
    assert items[1].record is not None
    assert items[2].record is not None
    assert corrupt.exists()


def test_run_history_is_idempotent_for_same_record_identity(tmp_path):
    project_path, revision, payload = _saved_project(tmp_path)
    run = run_analysis("room_verification", payload)
    completed_at = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
    kwargs = dict(
        project_revision=revision,
        project_dirty=False,
        analysis_id="room-a",
        analysis_name="Room A",
        input_snapshot=payload,
        run=run,
        completed_at=completed_at,
    )

    first = append_run_history_record(project_path, **kwargs)
    second = append_run_history_record(project_path, **kwargs)

    assert second == first
    assert len(list(run_history_directory(project_path).glob("*.json"))) == 1


def test_run_history_rejects_missing_saved_project_revision(tmp_path):
    project_path = tmp_path / "missing.cleanroomx.json"
    payload = _payload()
    missing = ProjectFileRevision(
        path=str(project_path.resolve()),
        exists=False,
        size=None,
        mtime_ns=None,
        sha256=None,
    )

    with pytest.raises(RunHistoryError, match="existing saved project revision"):
        append_run_history_record(
            project_path,
            project_revision=missing,
            project_dirty=False,
            analysis_id="room-a",
            analysis_name="Room A",
            input_snapshot=payload,
            run=run_analysis("room_verification", payload),
        )
