from __future__ import annotations

from pathlib import Path

import pytest

import cleanroomx.gui as gui_module
from cleanroomx.gui import CleanroomXApp
from cleanroomx.project import (
    AnalysisDocument,
    ProjectDocument,
    capture_project_file_revision,
    load_project_document,
    save_project_document,
    save_project_document_guarded,
)


class _Status:
    def __init__(self) -> None:
        self.value = ""

    def set(self, value: str) -> None:
        self.value = value


def _project_with_dependency(project_path: Path, dependency: Path) -> Path:
    verification = dependency.with_name("verification.json")
    verification.write_text("{}\n", encoding="utf-8")
    dependency.write_text('{"engineering": "input"}\n', encoding="utf-8")
    return save_project_document(
        project_path,
        ProjectDocument(
            name="Protected Save As",
            analyses=[
                AnalysisDocument(
                    id="consistency",
                    name="Consistency",
                    kind="consistency",
                    input={
                        "verification_project": verification.name,
                        "hvac_project": dependency.name,
                        "room_airflow_abs_tolerance_m3_h": 0.0,
                        "require_same_room_set": True,
                    },
                )
            ],
            active_analysis_id="consistency",
        ),
    )


def _saved_app(project_path: Path) -> CleanroomXApp:
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = object()
    app.project_path = project_path
    app.project = load_project_document(project_path)
    app.status_var = _Status()
    app._editor_analysis_id = None
    app._editor_analysis = lambda: None
    app._sync_metadata = lambda: None
    app._migration_source_path = None
    app._recovery_source_path = None
    app._restored_recovery_artifact = None
    return app


def test_gui_save_as_refuses_declared_external_dependency(monkeypatch, tmp_path):
    dependency = tmp_path / "hvac.json"
    project_path = _project_with_dependency(
        tmp_path / "project.cleanroomx.json",
        dependency,
    )
    before = dependency.read_bytes()
    app = _saved_app(project_path)
    errors = []

    monkeypatch.setattr(
        gui_module.filedialog,
        "asksaveasfilename",
        lambda **_kwargs: str(dependency),
    )
    monkeypatch.setattr(
        gui_module,
        "save_project_document_guarded",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("unsafe Save As target must be rejected before persistence")
        ),
    )
    monkeypatch.setattr(
        gui_module.messagebox,
        "showerror",
        lambda title, message, parent=None: errors.append((title, message, parent)),
    )

    app.save_project_as()

    assert dependency.read_bytes() == before
    assert app.status_var.value == "Save blocked"
    assert errors
    assert "external dependency" in errors[-1][1]


def test_gui_save_as_rechecks_dependency_alias_at_publication(monkeypatch, tmp_path):
    dependency = tmp_path / "hvac.json"
    project_path = _project_with_dependency(
        tmp_path / "project.cleanroomx.json",
        dependency,
    )
    before = dependency.read_bytes()
    destination = tmp_path / "copy.cleanroomx.json"
    app = _saved_app(project_path)
    errors = []

    monkeypatch.setattr(
        gui_module.filedialog,
        "asksaveasfilename",
        lambda **_kwargs: str(destination),
    )

    def race_guarded_save(
        path,
        project,
        *,
        expected_revision,
        revision_history_limit=5,
        before_replace=None,
    ):
        assert Path(path) == destination
        assert before_replace is not None
        destination.hardlink_to(dependency)
        before_replace(destination)
        raise AssertionError("unsafe replacement should not be reached")

    monkeypatch.setattr(
        gui_module,
        "save_project_document_guarded",
        race_guarded_save,
    )
    monkeypatch.setattr(
        gui_module.messagebox,
        "showerror",
        lambda title, message, parent=None: errors.append((title, message, parent)),
    )

    app.save_project_as()

    assert dependency.read_bytes() == before
    assert destination.read_bytes() == before
    assert errors
    assert errors[-1][0] == "Save failed"
    assert "external dependency" in errors[-1][1]


def test_guarded_project_save_runs_caller_publication_guard_before_replace(tmp_path):
    destination = save_project_document(
        tmp_path / "project.cleanroomx.json",
        ProjectDocument(name="Original"),
    )
    expected = capture_project_file_revision(destination)
    before = destination.read_bytes()
    guarded_targets = []

    def block(target: Path) -> None:
        guarded_targets.append(target)
        raise ValueError("blocked protected project destination")

    with pytest.raises(ValueError, match="blocked protected project destination"):
        save_project_document_guarded(
            destination,
            ProjectDocument(name="Replacement"),
            expected_revision=expected,
            before_replace=block,
        )

    assert destination.read_bytes() == before
    assert guarded_targets == [destination.resolve(strict=False)]

def test_gui_save_as_treats_tilde_dependency_as_project_relative(
    monkeypatch,
    tmp_path,
):
    project_dir = tmp_path / "project-dir"
    project_dir.mkdir()
    tilde_dir = project_dir / "~"
    tilde_dir.mkdir()
    dependency = tilde_dir / "hvac.json"
    verification = project_dir / "verification.json"
    verification.write_text("{}\n", encoding="utf-8")
    dependency.write_text('{"engineering": "input"}\n', encoding="utf-8")
    project_path = save_project_document(
        project_dir / "project.cleanroomx.json",
        ProjectDocument(
            name="Tilde dependency",
            analyses=[
                AnalysisDocument(
                    id="consistency",
                    name="Consistency",
                    kind="consistency",
                    input={
                        "verification_project": verification.name,
                        "hvac_project": "~/hvac.json",
                        "room_airflow_abs_tolerance_m3_h": 0.0,
                        "require_same_room_set": True,
                    },
                )
            ],
            active_analysis_id="consistency",
        ),
    )
    before = dependency.read_bytes()
    app = _saved_app(project_path)
    errors = []

    monkeypatch.setattr(
        gui_module.filedialog,
        "asksaveasfilename",
        lambda **_kwargs: str(dependency),
    )
    monkeypatch.setattr(
        gui_module,
        "save_project_document_guarded",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("project-relative tilde dependency must be rejected")
        ),
    )
    monkeypatch.setattr(
        gui_module.messagebox,
        "showerror",
        lambda title, message, parent=None: errors.append((title, message, parent)),
    )

    app.save_project_as()

    assert dependency.read_bytes() == before
    assert app.status_var.value == "Save blocked"
    assert errors
    assert "external dependency" in errors[-1][1]

