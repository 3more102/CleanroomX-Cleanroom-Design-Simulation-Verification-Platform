"""Real Tk coverage for recovery and saved-revision workstation browsers."""
from __future__ import annotations

from pathlib import Path
import os
import tkinter as tk

import pytest

from cleanroomx.autosave import RecoveryCandidate, RecoveryScan
from cleanroomx.project_revisions import (
    ProjectRevisionRecord,
    ProjectRevisionScan,
)
from cleanroomx.recovery_ui import RecoveryCenter
from cleanroomx.revision_ui import ProjectRevisionCenter


@pytest.fixture
def root():
    try:
        window = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    callback_errors = []
    window.report_callback_exception = lambda *args: callback_errors.append(args)
    window.withdraw()
    try:
        yield window
        assert callback_errors == []
    finally:
        window.destroy()


def _revision(
    path: Path,
    *,
    project_name: str,
    created_at: str,
    version: str,
    digest_char: str,
) -> ProjectRevisionRecord:
    return ProjectRevisionRecord(
        path=path,
        created_at_utc=created_at,
        project_name=project_name,
        source_sha256=digest_char * 64,
        source_size=1024,
        application_version=version,
        artifact_size=1400,
        artifact_sha256=digest_char.upper() * 64,
    )


def test_saved_revision_center_filters_verified_records_and_preserves_metadata(root, tmp_path):
    first = _revision(
        tmp_path / "alpha.revision.json",
        project_name="Alpha",
        created_at="2026-10-01T10:00:00Z",
        version="0.10.2",
        digest_char="a",
    )
    second = _revision(
        tmp_path / "beta.revision.json",
        project_name="Beta",
        created_at="2026-10-02T10:00:00Z",
        version="0.10.3",
        digest_char="b",
    )
    dialog = ProjectRevisionCenter(
        root,
        ProjectRevisionScan(revisions=(first, second), issues=()),
    )
    root.update()

    assert dialog.count_var.get() == "2 of 2 verified revisions"

    dialog.version_var.set("0.10.2")
    dialog.search_var.set("Alpha")
    root.update()
    assert dialog.tree.get_children() == (str(first.path),)
    assert first.source_sha256 in dialog.detail.get("1.0", "end")

    dialog.search_var.set("missing-revision")
    root.update()
    assert dialog.tree.get_children() == ()
    assert str(dialog.restore_button.cget("state")) == "disabled"
    assert "matches the active filters" in dialog.detail.get("1.0", "end")

    dialog._clear_filters()
    root.update()
    assert len(dialog.tree.get_children()) == 2
    dialog.destroy()


def _candidate(
    path: Path,
    *,
    name: str,
    saved_at: str,
    source_relation: str,
    integrity_status: str,
) -> RecoveryCandidate:
    return RecoveryCandidate(
        path=path,
        project_identity=f"identity-{name}",
        saved_at_utc=saved_at,
        project_name=name,
        source_path=path.with_suffix(".cleanroomx.json"),
        source_relation=source_relation,
        source_is_newer=source_relation == "source_newer",
        integrity_status=integrity_status,
    )


def test_recovery_center_filters_relation_integrity_and_search(root, tmp_path):
    unchanged = _candidate(
        tmp_path / "alpha.recovery.json",
        name="Alpha",
        saved_at="2026-10-02T08:00:00Z",
        source_relation="source_unchanged",
        integrity_status="verified",
    )
    changed = _candidate(
        tmp_path / "beta.recovery.json",
        name="Beta",
        saved_at="2026-10-03T08:00:00Z",
        source_relation="source_changed",
        integrity_status="legacy_unverified",
    )
    dialog = RecoveryCenter(
        root,
        RecoveryScan(candidates=(unchanged, changed), issues=()),
    )
    root.update()

    assert dialog.count_var.get() == "2 of 2 recoverable sessions"

    dialog.relation_var.set("Original changed")
    dialog.integrity_var.set("Legacy artifact — no embedded checksum")
    root.update()
    assert dialog.tree.get_children() == (str(changed.path),)
    assert "differs from the file fingerprint" in dialog.message_var.get()

    dialog.search_var.set("Alpha")
    root.update()
    assert dialog.tree.get_children() == ()
    assert str(dialog.restore_button.cget("state")) == "disabled"
    assert str(dialog.inspect_button.cget("state")) == "disabled"

    dialog._clear_filters()
    root.update()
    assert len(dialog.tree.get_children()) == 2
    dialog.destroy()
