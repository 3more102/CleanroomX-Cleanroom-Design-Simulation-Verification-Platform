from __future__ import annotations

from pathlib import Path

import cleanroomx.gui as gui_module
from cleanroomx.gui import CleanroomXApp
from cleanroomx.project import (
    ProjectFileRevision,
    ProjectRevisionRecord,
    ProjectRevisionScan,
    ProjectWriteConflictError,
)


class Value:
    def __init__(self, value=""):
        self.value = value

    def set(self, value):
        self.value = value


class Root:
    def wait_window(self, dialog):
        self.dialog = dialog


def _scan(path: Path) -> ProjectRevisionScan:
    return ProjectRevisionScan(
        revisions=(
            ProjectRevisionRecord(
                path=path,
                created_at_utc="2026-09-25T10:00:00Z",
                project_name="Demo",
                source_sha256="a" * 64,
                source_size=123,
                application_version="0.100.0",
            ),
        ),
        issues=(),
    )


def test_saved_revisions_requires_explicit_project_path():
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.project_path = None
    app.status_var = Value()

    assert app.show_saved_revisions() is False
    assert "Save the project" in app.status_var.value


def test_saved_revision_restore_writes_separate_copy_without_rebinding_open_project(
    tmp_path, monkeypatch
):
    project_path = tmp_path / "demo.cleanroomx.json"
    artifact = tmp_path / "revision.cleanroomx.revision.json"
    destination = tmp_path / "demo.restored.cleanroomx.json"
    scan = _scan(artifact)

    class Dialog:
        def __init__(self, parent, received_scan):
            assert received_scan == scan
            self.result = artifact

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = Root()
    app.project_path = project_path
    app.status_var = Value()
    restored = []

    monkeypatch.setattr(
        gui_module,
        "scan_project_revisions",
        lambda path: scan,
    )
    monkeypatch.setattr(gui_module, "ProjectRevisionCenter", Dialog)
    monkeypatch.setattr(
        gui_module.filedialog,
        "asksaveasfilename",
        lambda **kwargs: str(destination),
    )
    monkeypatch.setattr(
        gui_module,
        "restore_project_revision",
        lambda revision_path, target, expected_source_path: (
            restored.append(
                (
                    Path(revision_path),
                    Path(target),
                    Path(expected_source_path),
                )
            )
            or Path(target)
        ),
    )

    assert app.show_saved_revisions() is True
    assert restored == [(artifact, destination, project_path)]
    assert app.project_path == project_path
    assert "demo.restored.cleanroomx.json" in app.status_var.value


def test_saved_revision_restore_reports_destination_race(tmp_path, monkeypatch):
    project_path = tmp_path / "demo.cleanroomx.json"
    artifact = tmp_path / "revision.cleanroomx.revision.json"
    destination = tmp_path / "restore.cleanroomx.json"
    scan = _scan(artifact)

    class Dialog:
        def __init__(self, parent, received_scan):
            self.result = artifact

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = Root()
    app.project_path = project_path
    app.status_var = Value()
    warnings = []

    monkeypatch.setattr(
        gui_module,
        "scan_project_revisions",
        lambda path: scan,
    )
    monkeypatch.setattr(gui_module, "ProjectRevisionCenter", Dialog)
    monkeypatch.setattr(
        gui_module.filedialog,
        "asksaveasfilename",
        lambda **kwargs: str(destination),
    )

    expected = ProjectFileRevision(
        path=str(destination),
        exists=False,
        size=None,
        mtime_ns=None,
        sha256=None,
    )
    current = ProjectFileRevision(
        path=str(destination),
        exists=True,
        size=1,
        mtime_ns=1,
        sha256="b" * 64,
    )
    monkeypatch.setattr(
        gui_module,
        "restore_project_revision",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ProjectWriteConflictError(destination, expected, current)
        ),
    )
    monkeypatch.setattr(
        gui_module.messagebox,
        "showwarning",
        lambda title, message, parent=None: warnings.append((title, message)),
    )

    assert app.show_saved_revisions() is False
    assert warnings
    assert "changed on disk" in app.status_var.value
