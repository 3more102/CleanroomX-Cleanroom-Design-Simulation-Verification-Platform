from __future__ import annotations

import json
from pathlib import Path

import pytest

from cleanroomx.autosave import (
    AutosaveManager,
    RecoveryFormatError,
    discard_recovery_artifact,
    load_recovery_artifact,
    restore_recovery_artifact,
    scan_recovery_artifacts,
)
from cleanroomx.project import AnalysisDocument, ProjectDocument, save_project_document
from cleanroomx.recovery_ui import (
    inspect_recovery,
    recovery_integrity_label,
    recovery_relation_label,
    recovery_safety_message,
)


def _project(name: str = "Recovery Demo") -> ProjectDocument:
    return ProjectDocument(
        name=name,
        analyses=[
            AnalysisDocument(
                id="room-1",
                name="Room",
                kind="room_verification",
                input={"value": 1},
            )
        ],
        active_analysis_id="room-1",
    )


def _snapshot(project: ProjectDocument, *, editor_text: str = '{"value": 2}') -> dict:
    return {
        "project": project.to_dict(),
        "ui_state": {
            "name_text": project.name,
            "description_text": "Recovered description",
            "editor_analysis_id": "room-1",
            "editor_text": editor_text,
            "editor_json_valid": editor_text.startswith("{") and "broken" not in editor_text,
        },
    }


def _write_recovery(tmp_path, *, editor_text='{"value": 2}'):
    source = save_project_document(tmp_path / "source.cleanroomx.json", _project())
    manager = AutosaveManager(tmp_path / "recovery", session_id="crashed-session")
    try:
        manager.begin_project(source)
        assert manager.request_autosave(
            _snapshot(_project(), editor_text=editor_text),
            source_path=source,
        )
        manager.wait_for_idle()
        artifact = manager.status().artifact_path
        assert artifact is not None
        return source, artifact
    finally:
        manager.shutdown(wait=True)


def test_restore_recovery_returns_valid_project_and_raw_ui_state(tmp_path):
    source, artifact = _write_recovery(tmp_path, editor_text="{broken")

    recovered = restore_recovery_artifact(artifact)

    assert recovered.project.name == "Recovery Demo"
    assert recovered.project.analysis_by_id("room-1").input == {"value": 1}
    assert recovered.ui_state["editor_text"] == "{broken"
    assert recovered.ui_state["editor_json_valid"] is False
    assert recovered.source_path == source.resolve()
    assert recovered.artifact_path == artifact
    assert artifact.exists()
    assert source.exists()


def test_restore_failure_preserves_artifact_and_source(tmp_path):
    source, artifact = _write_recovery(tmp_path)
    source_before = source.read_bytes()
    payload = load_recovery_artifact(artifact)
    # Exercise semantic restore validation independently of the newer envelope
    # integrity layer by converting this fixture to the supported legacy shape.
    payload.pop("integrity")
    payload["snapshot"]["project"]["schema_version"] = 999
    artifact.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RecoveryFormatError, match="recovered project is invalid"):
        restore_recovery_artifact(artifact)

    assert artifact.exists()
    assert source.read_bytes() == source_before


def test_discard_recovery_deletes_only_selected_artifact(tmp_path):
    source, first = _write_recovery(tmp_path)
    recovery_dir = tmp_path / "recovery"

    manager = AutosaveManager(recovery_dir, session_id="second-session")
    try:
        manager.begin_project(source)
        manager.request_autosave(
            _snapshot(_project("Recovery Demo"), editor_text='{"value": 3}'),
            source_path=source,
        )
        manager.wait_for_idle()
        second = manager.status().artifact_path
        assert second is not None
    finally:
        manager.shutdown(wait=True)

    source_before = source.read_bytes()
    discard_recovery_artifact(first, recovery_dir=recovery_dir)

    assert not first.exists()
    assert second.exists()
    assert source.read_bytes() == source_before


def test_discard_refuses_file_outside_recovery_directory(tmp_path):
    outside = tmp_path / "outside.recovery.json"
    outside.write_text("{}", encoding="utf-8")
    recovery_dir = tmp_path / "recovery"
    recovery_dir.mkdir()

    with pytest.raises(RecoveryFormatError, match="inside the recovery directory"):
        discard_recovery_artifact(outside, recovery_dir=recovery_dir)

    assert outside.exists()


def test_recovery_inspection_exposes_identity_timestamp_source_and_draft(tmp_path):
    source, artifact = _write_recovery(tmp_path, editor_text="{broken")
    scan = scan_recovery_artifacts(tmp_path / "recovery")
    candidate = next(item for item in scan.candidates if item.path == artifact)

    inspection = inspect_recovery(candidate)

    assert inspection.project_identity == candidate.project_identity
    assert inspection.saved_at_utc == candidate.saved_at_utc
    assert inspection.source_path == str(source.resolve())
    assert inspection.integrity_status == "Verified SHA-256"
    assert candidate.integrity_status == "verified"
    assert recovery_integrity_label(candidate) == "Verified SHA-256"
    assert inspection.analysis_count == 1
    assert inspection.analysis_names == ("Room [room_verification]",)
    assert inspection.editor_analysis_id == "room-1"
    assert inspection.editor_json_valid is False
    assert inspection.editor_text == "{broken"
    assert recovery_relation_label(candidate) == "Original unchanged"
    assert "separate unsaved copy" in recovery_safety_message(candidate)


def test_newer_source_warning_explicitly_promises_no_overwrite(tmp_path):
    source, artifact = _write_recovery(tmp_path)
    source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    stat = source.stat()
    source.touch()
    source_stat = source.stat()
    # Force a timestamp safely beyond the recovery timestamp across filesystems.
    import os
    os.utime(
        source,
        ns=(
            source_stat.st_atime_ns + 2_000_000_000,
            max(stat.st_mtime_ns, source_stat.st_mtime_ns) + 2_000_000_000,
        ),
    )

    scan = scan_recovery_artifacts(tmp_path / "recovery")
    candidate = next(item for item in scan.candidates if item.path == artifact)

    assert candidate.source_relation == "source_newer"
    message = recovery_safety_message(candidate).lower()
    assert "newer" in message
    assert "never overwrites" in message
