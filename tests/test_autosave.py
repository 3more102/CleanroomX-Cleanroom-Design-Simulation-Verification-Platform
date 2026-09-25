from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from cleanroomx.autosave import (
    AutosaveManager,
    RECOVERY_SCHEMA,
    load_recovery_artifact,
    scan_recovery_artifacts,
)
from cleanroomx.project import AnalysisDocument, ProjectDocument, save_project_document


def _project() -> ProjectDocument:
    return ProjectDocument(
        name="Autosave Demo",
        analyses=[
            AnalysisDocument(
                id="room-1",
                name="Room",
                kind="room_verification",
                input={"room": {"length_m": 5.0, "width_m": 4.0, "height_m": 3.0}},
            )
        ],
        active_analysis_id="room-1",
    )


def _snapshot(project: ProjectDocument, *, marker: int = 0) -> dict:
    return {
        "project": project.to_dict(),
        "ui_state": {
            "name_text": project.name,
            "description_text": project.description,
            "editor_analysis_id": project.active_analysis_id,
            "editor_text": "{}",
            "editor_json_valid": True,
            "marker": marker,
        },
    }


def test_autosave_writes_separate_artifact_and_preserves_source(tmp_path):
    source = save_project_document(tmp_path / "project.cleanroomx.json", _project())
    before = source.read_bytes()
    recovery_dir = tmp_path / "recovery"
    manager = AutosaveManager(
        recovery_dir,
        history_limit=3,
        session_id="session-a",
    )
    try:
        manager.begin_project(source)
        assert manager.request_autosave(_snapshot(_project()), source_path=source) is True
        manager.wait_for_idle()

        status = manager.status()
        assert status.state == "saved"
        assert status.artifact_path is not None
        assert status.artifact_path.parent == recovery_dir
        assert source.read_bytes() == before

        artifact = load_recovery_artifact(status.artifact_path)
        assert artifact["schema"] == RECOVERY_SCHEMA
        assert artifact["source"]["path"] == str(source.resolve())
        assert artifact["source"]["sha256"]
        assert artifact["snapshot"]["project"]["project"]["name"] == "Autosave Demo"
    finally:
        manager.shutdown(wait=True)


def test_autosave_skips_identical_snapshot(tmp_path):
    source = save_project_document(tmp_path / "project.cleanroomx.json", _project())
    manager = AutosaveManager(tmp_path / "recovery", session_id="session-a")
    try:
        manager.begin_project(source)
        snapshot = _snapshot(_project())
        assert manager.request_autosave(snapshot, source_path=source) is True
        manager.wait_for_idle()
        assert manager.request_autosave(snapshot, source_path=source) is False
        assert len(list((tmp_path / "recovery").glob("*.recovery.json"))) == 1
    finally:
        manager.shutdown(wait=True)


def test_done_future_remains_owned_until_completion_callback_finishes(tmp_path):
    source = save_project_document(tmp_path / "project.cleanroomx.json", _project())
    manager = AutosaveManager(tmp_path / "recovery", session_id="session-a")

    callback_entered = threading.Event()
    release_callback = threading.Event()
    second_write_started = threading.Event()
    release_second_write = threading.Event()
    write_count = {"value": 0}
    callback_count = {"value": 0}
    counter_lock = threading.Lock()

    original_write_recovery = manager._write_recovery
    original_on_write_done = manager._on_write_done

    def controlled_write(request):
        with counter_lock:
            write_count["value"] += 1
            write_index = write_count["value"]
        if write_index == 2:
            second_write_started.set()
            if not release_second_write.wait(5.0):
                raise TimeoutError("test did not release second autosave write")
        return original_write_recovery(request)

    def controlled_done(request, future):
        with counter_lock:
            callback_count["value"] += 1
            callback_index = callback_count["value"]
        if callback_index == 1:
            callback_entered.set()
            if not release_callback.wait(5.0):
                raise TimeoutError("test did not release first completion callback")
        return original_on_write_done(request, future)

    manager._write_recovery = controlled_write
    manager._on_write_done = controlled_done

    try:
        manager.begin_project(source)
        assert manager.request_autosave(
            _snapshot(_project(), marker=1),
            source_path=source,
        ) is True
        assert callback_entered.wait(5.0)

        # The first Future is already done here, but its completion callback has
        # not finalized coordinator state. A newer snapshot must be queued rather
        # than replacing the tracked Future/request pair.
        assert manager.request_autosave(
            _snapshot(_project(), marker=2),
            source_path=source,
        ) is True
        assert manager.status().message == "Autosave queued"

        release_callback.set()
        assert second_write_started.wait(5.0)

        # The queued write is deliberately blocked. wait_for_idle() must continue
        # to observe it as owned work instead of returning during the race window.
        with pytest.raises(TimeoutError, match="did not become idle"):
            manager.wait_for_idle(timeout=0.05)

        release_second_write.set()
        manager.wait_for_idle(timeout=5.0)

        status = manager.status()
        assert status.state == "saved"
        assert status.artifact_path is not None
        artifact = load_recovery_artifact(status.artifact_path)
        assert artifact["snapshot"]["ui_state"]["marker"] == 2
        assert write_count["value"] == 2
    finally:
        release_callback.set()
        release_second_write.set()
        manager.shutdown(wait=True)


def test_autosave_rotates_history_per_project_identity(tmp_path):
    source = save_project_document(tmp_path / "project.cleanroomx.json", _project())
    manager = AutosaveManager(
        tmp_path / "recovery",
        history_limit=2,
        session_id="session-a",
    )
    try:
        manager.begin_project(source)
        for marker in range(5):
            assert manager.request_autosave(
                _snapshot(_project(), marker=marker),
                source_path=source,
            )
            manager.wait_for_idle()

        artifacts = list((tmp_path / "recovery").glob("*.recovery.json"))
        assert len(artifacts) == 2
    finally:
        manager.shutdown(wait=True)


def test_explicit_save_cleanup_preserves_prior_session_recovery(tmp_path):
    source = save_project_document(tmp_path / "project.cleanroomx.json", _project())
    recovery_dir = tmp_path / "recovery"

    old_manager = AutosaveManager(recovery_dir, session_id="old-session")
    try:
        old_manager.begin_project(source)
        old_manager.request_autosave(
            _snapshot(_project(), marker=1),
            source_path=source,
        )
        old_manager.wait_for_idle()
        old_path = old_manager.status().artifact_path
        assert old_path is not None and old_path.exists()
    finally:
        old_manager.shutdown(wait=True)

    current_manager = AutosaveManager(recovery_dir, session_id="current-session")
    try:
        current_manager.begin_project(source)
        current_manager.request_autosave(
            _snapshot(_project(), marker=2),
            source_path=source,
        )
        current_manager.wait_for_idle()
        current_path = current_manager.status().artifact_path
        assert current_path is not None and current_path.exists()

        current_manager.notify_explicit_save(source)

        assert old_path.exists()
        assert not current_path.exists()
        assert source.exists()
    finally:
        current_manager.shutdown(wait=True)


def test_recovery_scan_detects_newer_changed_source(tmp_path):
    source = save_project_document(tmp_path / "project.cleanroomx.json", _project())
    recovery_dir = tmp_path / "recovery"
    manager = AutosaveManager(recovery_dir, session_id="session-a")
    try:
        manager.begin_project(source)
        manager.request_autosave(_snapshot(_project()), source_path=source)
        manager.wait_for_idle()
        artifact_path = manager.status().artifact_path
        assert artifact_path is not None
        artifact = load_recovery_artifact(artifact_path)
    finally:
        manager.shutdown(wait=True)

    source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    current_ns = source.stat().st_mtime_ns
    os.utime(source, ns=(current_ns + 2_000_000_000, current_ns + 2_000_000_000))

    scan = scan_recovery_artifacts(recovery_dir)
    assert scan.issues == ()
    assert len(scan.candidates) == 1
    candidate = scan.candidates[0]
    assert candidate.source_path == source.resolve()
    assert candidate.source_relation == "source_newer"
    assert candidate.source_is_newer is True


def test_recovery_scan_reports_malformed_artifacts_without_hiding_valid_ones(tmp_path):
    recovery_dir = tmp_path / "recovery"
    source = save_project_document(tmp_path / "project.cleanroomx.json", _project())
    manager = AutosaveManager(recovery_dir, session_id="session-a")
    try:
        manager.begin_project(source)
        manager.request_autosave(_snapshot(_project()), source_path=source)
        manager.wait_for_idle()
    finally:
        manager.shutdown(wait=True)

    bad = recovery_dir / "broken.recovery.json"
    bad.write_text("{broken", encoding="utf-8")

    scan = scan_recovery_artifacts(recovery_dir)

    assert len(scan.candidates) == 1
    assert len(scan.issues) == 1
    assert scan.issues[0].path == bad
    assert "invalid recovery JSON" in scan.issues[0].error


def test_autosave_rejects_non_finite_snapshot_before_background_write(tmp_path):
    manager = AutosaveManager(tmp_path / "recovery")
    try:
        with pytest.raises(ValueError):
            manager.request_autosave(
                {"project": {"value": float("nan")}, "ui_state": {}},
                source_path=None,
            )
        assert not (tmp_path / "recovery").exists()
    finally:
        manager.shutdown(wait=True)
