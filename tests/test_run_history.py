from __future__ import annotations

import json
from pathlib import Path

import pytest

from cleanroomx.application import run_analysis
from cleanroomx.project import (
    AnalysisDocument,
    ProjectDocument,
    capture_project_file_revision,
    save_project_document,
)
from cleanroomx.run_history import (
    RunHistoryFormatError,
    RunHistoryManager,
    analysis_run_from_history_record,
    archive_analysis_run,
    load_run_history_record,
    scan_run_history,
)


ROOT = Path(__file__).resolve().parents[1]


def _payload() -> dict:
    return json.loads(
        (ROOT / "examples" / "basic_room.json").read_text(encoding="utf-8")
    )


def _saved_project(tmp_path: Path) -> tuple[Path, object]:
    payload = _payload()
    project = ProjectDocument(
        name="Run History Demo",
        analyses=[
            AnalysisDocument(
                id="room-1",
                name="Room verification",
                kind="room_verification",
                input=payload,
            )
        ],
        active_analysis_id="room-1",
    )
    path = save_project_document(tmp_path / "demo.cleanroomx.json", project)
    return path, capture_project_file_revision(path)


def _archive(
    tmp_path: Path,
    *,
    recorded_at_utc: str = "2026-09-25T12:00:00.000000Z",
    history_limit: int = 100,
):
    project_path, revision = _saved_project(tmp_path)
    payload = _payload()
    run = run_analysis("room_verification", payload)
    path = archive_analysis_run(
        tmp_path / "history",
        project_path=project_path,
        expected_project_revision=revision,
        project_dirty=False,
        analysis_id="room-1",
        analysis_name="Room verification",
        analysis_kind="room_verification",
        analysis_input=payload,
        run=run,
        history_limit=history_limit,
        recorded_at_utc=recorded_at_utc,
    )
    return project_path, revision, payload, run, path


def test_archive_round_trip_preserves_exact_input_run_and_project_revision(tmp_path):
    project_path, revision, payload, run, artifact = _archive(tmp_path)

    record = load_run_history_record(artifact)
    restored_run = analysis_run_from_history_record(record)
    scan = scan_run_history(tmp_path / "history", project_path)

    assert record["schema"] == "cleanroomx.run-history"
    assert record["schema_version"] == 1
    assert record["project"]["path"] == str(project_path.resolve())
    assert record["project"]["source_relation"] == "matches_loaded_revision"
    assert record["project"]["dirty"] is False
    assert record["project"]["loaded_revision"]["sha256"] == revision.sha256
    assert record["analysis"]["input"] == payload
    assert restored_run == run
    assert len(scan.entries) == 1
    assert scan.issues == ()
    assert scan.entries[0].record_id == record["record_id"]


def test_archive_rejects_run_that_does_not_match_supplied_input(tmp_path):
    project_path, revision = _saved_project(tmp_path)
    payload = _payload()
    run = run_analysis("room_verification", payload)
    changed = dict(payload)
    changed["_changed_after_run"] = True

    with pytest.raises(RunHistoryFormatError, match="provenance"):
        archive_analysis_run(
            tmp_path / "history",
            project_path=project_path,
            expected_project_revision=revision,
            project_dirty=True,
            analysis_id="room-1",
            analysis_name="Room verification",
            analysis_kind="room_verification",
            analysis_input=changed,
            run=run,
        )

    assert not (tmp_path / "history").exists()


def test_load_rejects_tampered_integrity_evidence(tmp_path):
    _project_path, _revision, _payload_value, _run, artifact = _archive(tmp_path)
    data = json.loads(artifact.read_text(encoding="utf-8"))
    data["integrity"]["payload_sha256"] = "0" * 64
    artifact.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RunHistoryFormatError, match="integrity digest mismatch"):
        load_run_history_record(artifact)


def test_scan_preserves_and_reports_corrupt_artifact_beside_valid_history(tmp_path):
    project_path, _revision, _payload_value, _run, artifact = _archive(tmp_path)
    corrupt = artifact.parent / "broken.run.json"
    corrupt.write_text("{broken", encoding="utf-8")

    scan = scan_run_history(tmp_path / "history", project_path)

    assert len(scan.entries) == 1
    assert scan.entries[0].path == artifact
    assert len(scan.issues) == 1
    assert scan.issues[0].path == corrupt
    assert corrupt.exists()


def test_history_rotation_removes_oldest_verified_record_but_preserves_corrupt_files(tmp_path):
    project_path, revision = _saved_project(tmp_path)
    payload = _payload()
    run = run_analysis("room_verification", payload)
    history_dir = tmp_path / "history"

    first = archive_analysis_run(
        history_dir,
        project_path=project_path,
        expected_project_revision=revision,
        project_dirty=False,
        analysis_id="room-1",
        analysis_name="Room verification",
        analysis_kind="room_verification",
        analysis_input=payload,
        run=run,
        history_limit=2,
        recorded_at_utc="2026-09-25T12:00:00.000000Z",
    )
    corrupt = first.parent / "damaged.run.json"
    corrupt.write_text("not-json", encoding="utf-8")

    second = archive_analysis_run(
        history_dir,
        project_path=project_path,
        expected_project_revision=revision,
        project_dirty=False,
        analysis_id="room-1",
        analysis_name="Room verification",
        analysis_kind="room_verification",
        analysis_input=payload,
        run=run,
        history_limit=2,
        recorded_at_utc="2026-09-25T12:01:00.000000Z",
    )
    third = archive_analysis_run(
        history_dir,
        project_path=project_path,
        expected_project_revision=revision,
        project_dirty=False,
        analysis_id="room-1",
        analysis_name="Room verification",
        analysis_kind="room_verification",
        analysis_input=payload,
        run=run,
        history_limit=2,
        recorded_at_utc="2026-09-25T12:02:00.000000Z",
    )

    scan = scan_run_history(history_dir, project_path)

    assert not first.exists()
    assert second.exists()
    assert third.exists()
    assert corrupt.exists()
    assert [entry.path for entry in scan.entries] == [third, second]
    assert [issue.path for issue in scan.issues] == [corrupt]


def test_archive_records_when_saved_project_changed_on_disk_after_load(tmp_path):
    project_path, revision = _saved_project(tmp_path)
    payload = _payload()
    run = run_analysis("room_verification", payload)

    project_path.write_text(
        project_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    artifact = archive_analysis_run(
        tmp_path / "history",
        project_path=project_path,
        expected_project_revision=revision,
        project_dirty=False,
        analysis_id="room-1",
        analysis_name="Room verification",
        analysis_kind="room_verification",
        analysis_input=payload,
        run=run,
    )
    record = load_run_history_record(artifact)

    assert record["project"]["source_relation"] == "changed_on_disk"
    assert record["project"]["loaded_revision"]["sha256"] == revision.sha256
    assert (
        record["project"]["current_disk_revision"]["sha256"]
        != revision.sha256
    )


def test_manager_snapshots_mutable_input_before_background_write(tmp_path):
    project_path, revision = _saved_project(tmp_path)
    payload = _payload()
    run = run_analysis("room_verification", payload)
    manager = RunHistoryManager(tmp_path / "history")
    try:
        future = manager.submit(
            project_path=project_path,
            expected_project_revision=revision,
            project_dirty=True,
            analysis_id="room-1",
            analysis_name="Room verification",
            analysis_kind="room_verification",
            analysis_input=payload,
            run=run,
        )
        payload["_mutated_after_submit"] = True
        artifact = future.result()
        record = load_run_history_record(artifact)

        assert "_mutated_after_submit" not in record["analysis"]["input"]
        assert record["project"]["dirty"] is True
    finally:
        manager.shutdown(wait=True)
