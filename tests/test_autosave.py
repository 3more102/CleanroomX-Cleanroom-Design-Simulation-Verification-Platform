from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
from threading import Event

import pytest

import cleanroomx.autosave as autosave_module

from cleanroomx.autosave import (
    AutosaveManager,
    RECOVERY_SCHEMA,
    load_recovery_artifact,
    scan_recovery_artifacts,
    source_fingerprint,
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


def test_autosave_rotation_isolated_between_sessions_for_same_project(tmp_path):
    source = save_project_document(tmp_path / "project.cleanroomx.json", _project())
    recovery_dir = tmp_path / "recovery"

    first = AutosaveManager(
        recovery_dir,
        history_limit=3,
        session_id="session-a",
    )
    try:
        first.begin_project(source)
        for marker in range(3):
            assert first.request_autosave(
                _snapshot(_project(), marker=marker),
                source_path=source,
            )
            first.wait_for_idle()

        first_paths = set(recovery_dir.glob("*.recovery.json"))
        assert len(first_paths) == 3
        assert {
            load_recovery_artifact(path)["session_id"] for path in first_paths
        } == {"session-a"}
    finally:
        first.shutdown(wait=True)

    second = AutosaveManager(
        recovery_dir,
        history_limit=1,
        session_id="session-b",
    )
    try:
        second.begin_project(source)
        for marker in range(10, 13):
            assert second.request_autosave(
                _snapshot(_project(), marker=marker),
                source_path=source,
            )
            second.wait_for_idle()

        all_paths = set(recovery_dir.glob("*.recovery.json"))
        assert first_paths <= all_paths
        by_session: dict[str, list[Path]] = {}
        for path in all_paths:
            session_id = load_recovery_artifact(path)["session_id"]
            by_session.setdefault(session_id, []).append(path)

        assert len(by_session["session-a"]) == 3
        assert len(by_session["session-b"]) == 1
    finally:
        second.shutdown(wait=True)


def test_autosave_rotation_preserves_unverifiable_session_artifact(tmp_path):
    source = save_project_document(tmp_path / "project.cleanroomx.json", _project())
    recovery_dir = tmp_path / "recovery"
    recovery_dir.mkdir()
    manager = AutosaveManager(
        recovery_dir,
        history_limit=1,
        session_id="session-a",
    )
    try:
        identity = manager.begin_project(source)
        session_token = sha256(b"session-a").hexdigest()
        suspect = recovery_dir / (
            f"{identity}-session-{session_token}-"
            "00000000T000000000000Z-broken.recovery.json"
        )
        suspect.write_text("{broken", encoding="utf-8")

        for marker in range(2):
            assert manager.request_autosave(
                _snapshot(_project(), marker=marker),
                source_path=source,
            )
            manager.wait_for_idle()

        assert suspect.exists()
        scan = scan_recovery_artifacts(recovery_dir)
        assert len(scan.candidates) == 1
        assert load_recovery_artifact(scan.candidates[0].path)["session_id"] == "session-a"
        assert len(scan.issues) == 1
        assert scan.issues[0].path == suspect
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


def test_recovery_scan_accepts_legacy_recovery_filename(tmp_path):
    source = save_project_document(tmp_path / "project.cleanroomx.json", _project())
    recovery_dir = tmp_path / "recovery"
    manager = AutosaveManager(recovery_dir, session_id="session-a")
    try:
        manager.begin_project(source)
        assert manager.request_autosave(
            _snapshot(_project(), marker=1),
            source_path=source,
        )
        manager.wait_for_idle()
        current_path = manager.status().artifact_path
        assert current_path is not None
        payload = load_recovery_artifact(current_path)
    finally:
        manager.shutdown(wait=True)

    legacy_path = recovery_dir / (
        f"{payload['project_identity']}-20260925T000000000000Z-"
        f"{payload['recovery_id'][:8]}.recovery.json"
    )
    current_path.replace(legacy_path)

    scan = scan_recovery_artifacts(recovery_dir)

    assert scan.issues == ()
    assert len(scan.candidates) == 1
    assert scan.candidates[0].path == legacy_path
    assert load_recovery_artifact(legacy_path)["session_id"] == "session-a"


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


def test_source_fingerprint_retries_when_path_is_replaced_during_hash(
    tmp_path, monkeypatch
):
    path = tmp_path / "source.cleanroomx.json"
    old_bytes = b"old-data"
    new_bytes = b"new-data"
    path.write_bytes(old_bytes)
    original_stat = path.stat()

    replacement = tmp_path / "replacement.tmp"
    replacement.write_bytes(new_bytes)
    os.utime(
        replacement,
        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
    )

    original_open = Path.open
    read_count = 0

    def replace_after_open(self, *args, **kwargs):
        nonlocal read_count
        handle = original_open(self, *args, **kwargs)
        mode = args[0] if args else kwargs.get("mode", "r")
        if Path(self) == path and mode == "rb":
            read_count += 1
            if read_count == 1:
                os.replace(replacement, path)
        return handle

    monkeypatch.setattr(Path, "open", replace_after_open)

    fingerprint = source_fingerprint(path)

    assert read_count == 2
    assert fingerprint["size"] == len(new_bytes)
    assert fingerprint["sha256"] == sha256(new_bytes).hexdigest()


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


def test_stale_inflight_autosave_cannot_rotate_prior_session_recovery(
    tmp_path, monkeypatch
):
    source = save_project_document(tmp_path / "project.cleanroomx.json", _project())
    recovery_dir = tmp_path / "recovery"

    old_manager = AutosaveManager(
        recovery_dir,
        history_limit=1,
        session_id="old-session",
    )
    try:
        old_manager.begin_project(source)
        assert old_manager.request_autosave(
            _snapshot(_project(), marker=1),
            source_path=source,
        )
        old_manager.wait_for_idle()
        old_path = old_manager.status().artifact_path
        assert old_path is not None and old_path.exists()
    finally:
        old_manager.shutdown(wait=True)

    write_completed = Event()
    release_worker = Event()
    original_atomic_write = autosave_module.atomic_write_text

    def blocking_atomic_write(path, text):
        original_atomic_write(path, text)
        write_completed.set()
        if not release_worker.wait(5.0):
            raise TimeoutError("test did not release blocked autosave worker")

    monkeypatch.setattr(autosave_module, "atomic_write_text", blocking_atomic_write)

    current_manager = AutosaveManager(
        recovery_dir,
        history_limit=1,
        session_id="current-session",
    )
    try:
        current_manager.begin_project(source)
        assert current_manager.request_autosave(
            _snapshot(_project(), marker=2),
            source_path=source,
        )
        assert write_completed.wait(5.0)

        # Explicit save invalidates the in-flight recovery before its worker
        # completes. The stale generation must not get a chance to evict the
        # older accepted recovery during history rotation.
        current_manager.notify_explicit_save(source)
        release_worker.set()
        current_manager.wait_for_idle()

        assert current_manager.status().state == "idle"
        assert old_path.exists()
        assert list(recovery_dir.glob("*.recovery.json")) == [old_path]
    finally:
        release_worker.set()
        current_manager.shutdown(wait=True)


def test_history_rotation_failure_preserves_written_recovery_and_reports_failure(
    tmp_path, monkeypatch
):
    source = save_project_document(tmp_path / "project.cleanroomx.json", _project())
    manager = AutosaveManager(tmp_path / "recovery", session_id="session-a")
    manager.begin_project(source)

    def fail_rotation(_identity):
        raise OSError("retention cleanup blocked")

    monkeypatch.setattr(manager, "_rotate_history", fail_rotation)
    try:
        assert manager.request_autosave(
            _snapshot(_project(), marker=7),
            source_path=source,
        )
        with pytest.raises(RuntimeError, match="history cleanup failed"):
            manager.wait_for_idle()

        status = manager.status()
        assert status.state == "failed"
        assert status.artifact_path is not None
        assert status.artifact_path.exists()
        assert "retention cleanup blocked" in status.message
    finally:
        manager.shutdown(wait=True)


def test_stale_artifact_cleanup_failure_is_reported(tmp_path, monkeypatch):
    source = save_project_document(tmp_path / "project.cleanroomx.json", _project())
    manager = AutosaveManager(tmp_path / "recovery", session_id="session-a")

    write_completed = Event()
    release_worker = Event()
    original_atomic_write = autosave_module.atomic_write_text
    original_unlink = Path.unlink

    def blocking_atomic_write(path, text):
        original_atomic_write(path, text)
        write_completed.set()
        if not release_worker.wait(5.0):
            raise TimeoutError("test did not release blocked autosave worker")

    def failing_recovery_unlink(path, *args, **kwargs):
        if path.name.endswith(".recovery.json"):
            raise OSError("recovery cleanup permission denied")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(autosave_module, "atomic_write_text", blocking_atomic_write)
    try:
        manager.begin_project(source)
        assert manager.request_autosave(
            _snapshot(_project(), marker=9),
            source_path=source,
        )
        assert write_completed.wait(5.0)

        manager.notify_explicit_save(source)
        monkeypatch.setattr(Path, "unlink", failing_recovery_unlink)
        release_worker.set()

        with pytest.raises(RuntimeError, match="invalidated recovery cleanup failed"):
            manager.wait_for_idle()

        status = manager.status()
        assert status.state == "failed"
        assert status.artifact_path is not None
        assert status.artifact_path.exists()
        assert "permission denied" in status.message
    finally:
        release_worker.set()
        manager.shutdown(wait=True)


def test_explicit_save_cleanup_failure_is_tracked_and_retryable(tmp_path, monkeypatch):
    source = save_project_document(tmp_path / "project.cleanroomx.json", _project())
    manager = AutosaveManager(tmp_path / "recovery", session_id="session-a")
    try:
        manager.begin_project(source)
        assert manager.request_autosave(
            _snapshot(_project(), marker=10),
            source_path=source,
        )
        manager.wait_for_idle()
        artifact = manager.status().artifact_path
        assert artifact is not None and artifact.exists()

        original_unlink = Path.unlink
        attempts = {"count": 0}

        def fail_once(path, *args, **kwargs):
            if path == artifact and attempts["count"] == 0:
                attempts["count"] += 1
                raise PermissionError("cleanup permission denied")
            return original_unlink(path, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", fail_once)

        failed = manager.notify_explicit_save(source)
        assert failed.state == "failed"
        assert failed.artifact_path == artifact
        assert "Project saved" in failed.message
        assert "permission denied" in failed.message
        assert artifact.exists()

        retried = manager.notify_explicit_save(source)
        assert retried.state == "idle"
        assert not artifact.exists()
    finally:
        manager.shutdown(wait=True)


def test_discard_cleanup_failure_is_tracked_and_retryable(tmp_path, monkeypatch):
    source = save_project_document(tmp_path / "project.cleanroomx.json", _project())
    manager = AutosaveManager(tmp_path / "recovery", session_id="session-a")
    try:
        manager.begin_project(source)
        assert manager.request_autosave(
            _snapshot(_project(), marker=11),
            source_path=source,
        )
        manager.wait_for_idle()
        artifact = manager.status().artifact_path
        assert artifact is not None and artifact.exists()

        original_unlink = Path.unlink
        attempts = {"count": 0}

        def fail_once(path, *args, **kwargs):
            if path == artifact and attempts["count"] == 0:
                attempts["count"] += 1
                raise OSError("discard blocked")
            return original_unlink(path, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", fail_once)

        failed = manager.discard_current_recoveries()
        assert failed.state == "failed"
        assert failed.artifact_path == artifact
        assert "discard incomplete" in failed.message
        assert artifact.exists()

        retried = manager.discard_current_recoveries()
        assert retried.state == "idle"
        assert not artifact.exists()
    finally:
        manager.shutdown(wait=True)
