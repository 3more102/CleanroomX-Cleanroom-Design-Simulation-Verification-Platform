from __future__ import annotations

from pathlib import Path

import cleanroomx.gui as gui_module
from cleanroomx.gui import CleanroomXApp
from cleanroomx.project import (
    AnalysisDocument,
    ProjectDocument,
    load_project_document,
    save_project_document,
)


class _Status:
    def __init__(self) -> None:
        self.value = ""

    def set(self, value: str) -> None:
        self.value = value


def _saved_app(project_path: Path) -> CleanroomXApp:
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = object()
    app.project_path = project_path
    app.project = load_project_document(project_path)
    app.status_var = _Status()
    return app


def test_gui_generic_export_refuses_project_source(monkeypatch, tmp_path):
    project_path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        ProjectDocument(name="Protected GUI source"),
    )
    before = project_path.read_bytes()
    app = _saved_app(project_path)
    errors = []
    monkeypatch.setattr(
        gui_module.messagebox,
        "showerror",
        lambda title, message, parent=None: errors.append((title, message, parent)),
    )

    assert app._write_export_file(
        str(project_path),
        "replacement\n",
        label="Result",
    ) is False

    assert project_path.read_bytes() == before
    assert app.status_var.value == "Result export failed"
    assert errors
    assert "project source" in errors[-1][1]


def test_gui_generic_export_refuses_project_hardlink_alias(monkeypatch, tmp_path):
    project_path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        ProjectDocument(name="Protected GUI hardlink"),
    )
    alias = tmp_path / "result.json"
    alias.hardlink_to(project_path)
    before = project_path.read_bytes()
    app = _saved_app(project_path)
    errors = []
    monkeypatch.setattr(
        gui_module.messagebox,
        "showerror",
        lambda title, message, parent=None: errors.append((title, message, parent)),
    )

    assert app._write_export_file(
        str(alias),
        "replacement\n",
        label="Result",
    ) is False

    assert project_path.read_bytes() == before
    assert alias.read_bytes() == before
    assert errors
    assert "project source" in errors[-1][1]


def test_gui_generic_export_refuses_declared_dependency(monkeypatch, tmp_path):
    verification = tmp_path / "verification.json"
    dependency = tmp_path / "hvac.json"
    verification.write_text("{}\n", encoding="utf-8")
    dependency.write_text('{"engineering": "input"}\n', encoding="utf-8")
    before = dependency.read_bytes()
    project_path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        ProjectDocument(
            name="Protected GUI dependency",
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
    app = _saved_app(project_path)
    errors = []
    monkeypatch.setattr(
        gui_module.messagebox,
        "showerror",
        lambda title, message, parent=None: errors.append((title, message, parent)),
    )

    assert app._write_export_file(
        str(dependency),
        "replacement\n",
        label="Report",
    ) is False

    assert dependency.read_bytes() == before
    assert errors
    assert "external dependency" in errors[-1][1]


def test_gui_generic_export_refuses_dependency_hardlink_alias(monkeypatch, tmp_path):
    verification = tmp_path / "verification.json"
    dependency = tmp_path / "hvac.json"
    alias = tmp_path / "result.json"
    verification.write_text("{}\n", encoding="utf-8")
    dependency.write_text('{"engineering": "input"}\n', encoding="utf-8")
    alias.hardlink_to(dependency)
    before = dependency.read_bytes()
    project_path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        ProjectDocument(
            name="Protected GUI dependency hardlink",
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
    app = _saved_app(project_path)
    errors = []
    monkeypatch.setattr(
        gui_module.messagebox,
        "showerror",
        lambda title, message, parent=None: errors.append((title, message, parent)),
    )

    assert app._write_export_file(
        str(alias),
        "replacement\n",
        label="Report",
    ) is False

    assert dependency.read_bytes() == before
    assert alias.read_bytes() == before
    assert errors
    assert "external dependency" in errors[-1][1]


def test_gui_generic_export_rechecks_alias_before_replace(monkeypatch, tmp_path):
    project_path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        ProjectDocument(name="GUI publication race"),
    )
    before = project_path.read_bytes()
    destination = tmp_path / "result.json"
    app = _saved_app(project_path)
    errors = []

    def alias_then_publish(path, content, *, before_replace=None):
        assert Path(path) == destination
        assert content == "candidate\n"
        assert before_replace is not None
        destination.hardlink_to(project_path)
        before_replace()
        raise AssertionError("unsafe replacement should not be reached")

    monkeypatch.setattr(gui_module, "atomic_write_text", alias_then_publish)
    monkeypatch.setattr(
        gui_module.messagebox,
        "showerror",
        lambda title, message, parent=None: errors.append((title, message, parent)),
    )

    assert app._write_export_file(
        str(destination),
        "candidate\n",
        label="Run bundle",
    ) is False

    assert project_path.read_bytes() == before
    assert destination.read_bytes() == before
    assert errors
    assert "project source" in errors[-1][1]


def test_gui_generic_export_protects_recovery_source(monkeypatch, tmp_path):
    project_path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        ProjectDocument(name="Protected recovery source"),
    )
    before = project_path.read_bytes()
    app = _saved_app(project_path)
    app.project_path = None
    app._recovery_source_path = project_path
    errors = []
    monkeypatch.setattr(
        gui_module.messagebox,
        "showerror",
        lambda title, message, parent=None: errors.append((title, message, parent)),
    )

    assert app._write_export_file(
        str(project_path),
        "replacement\n",
        label="Result",
    ) is False

    assert project_path.read_bytes() == before
    assert errors
    assert "project source" in errors[-1][1]


def test_gui_generic_export_rechecks_dependency_alias_before_replace(
    monkeypatch,
    tmp_path,
):
    verification = tmp_path / "verification.json"
    dependency = tmp_path / "hvac.json"
    verification.write_text("{}\n", encoding="utf-8")
    dependency.write_text('{"engineering": "input"}\n', encoding="utf-8")
    before = dependency.read_bytes()
    project_path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        ProjectDocument(
            name="GUI dependency publication race",
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
    destination = tmp_path / "result.json"
    app = _saved_app(project_path)
    errors = []

    def alias_then_publish(path, content, *, before_replace=None):
        assert Path(path) == destination
        assert content == "candidate\n"
        assert before_replace is not None
        destination.hardlink_to(dependency)
        before_replace()
        raise AssertionError("unsafe replacement should not be reached")

    monkeypatch.setattr(gui_module, "atomic_write_text", alias_then_publish)
    monkeypatch.setattr(
        gui_module.messagebox,
        "showerror",
        lambda title, message, parent=None: errors.append((title, message, parent)),
    )

    assert app._write_export_file(
        str(destination),
        "candidate\n",
        label="Result",
    ) is False

    assert dependency.read_bytes() == before
    assert destination.read_bytes() == before
    assert errors
    assert "external dependency" in errors[-1][1]


def test_gui_generic_export_composes_caller_before_replace_guard(
    monkeypatch,
    tmp_path,
):
    project_path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        ProjectDocument(name="Composed GUI publication guard"),
    )
    destination = tmp_path / "result.json"
    app = _saved_app(project_path)
    events = []

    monkeypatch.setattr(
        gui_module,
        "_assert_project_output_is_safe",
        lambda *args, **kwargs: events.append("generic"),
    )

    def publish(path, content, *, before_replace=None):
        assert Path(path) == destination
        assert content == "candidate\n"
        assert before_replace is not None
        before_replace()
        Path(path).write_text(content, encoding="utf-8")

    monkeypatch.setattr(gui_module, "atomic_write_text", publish)

    def caller_guard():
        events.append("caller")

    assert app._write_export_file(
        str(destination),
        "candidate\n",
        label="Result",
        before_replace=caller_guard,
    ) is True

    assert events == ["generic", "generic", "caller"]
    assert destination.read_text(encoding="utf-8") == "candidate\n"


def test_gui_unsaved_project_protects_absolute_dependency(monkeypatch, tmp_path):
    verification = tmp_path / "verification.json"
    dependency = tmp_path / "hvac.json"
    verification.write_text("{}\n", encoding="utf-8")
    dependency.write_text('{"engineering": "input"}\n', encoding="utf-8")
    before = dependency.read_bytes()

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = object()
    app.project_path = None
    app._recovery_source_path = None
    app.project = ProjectDocument(
        name="Unsaved protected dependencies",
        analyses=[
            AnalysisDocument(
                id="consistency",
                name="Consistency",
                kind="consistency",
                input={
                    "verification_project": str(verification),
                    "hvac_project": str(dependency),
                    "room_airflow_abs_tolerance_m3_h": 0.0,
                    "require_same_room_set": True,
                },
            )
        ],
        active_analysis_id="consistency",
    )
    app.status_var = _Status()
    errors = []
    monkeypatch.setattr(
        gui_module.messagebox,
        "showerror",
        lambda title, message, parent=None: errors.append((title, message, parent)),
    )

    assert app._write_export_file(
        str(dependency),
        "replacement\n",
        label="Result",
    ) is False

    assert dependency.read_bytes() == before
    assert app.status_var.value == "Result export failed"
    assert errors
    assert "external dependency" in errors[-1][1]


def test_gui_unsaved_project_allows_unresolved_relative_dependencies(tmp_path):
    output = tmp_path / "result.json"

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = object()
    app.project_path = None
    app._recovery_source_path = None
    app.project = ProjectDocument(
        name="Unsaved relative dependencies",
        analyses=[
            AnalysisDocument(
                id="consistency",
                name="Consistency",
                kind="consistency",
                input={
                    "verification_project": "verification.json",
                    "hvac_project": "hvac.json",
                    "room_airflow_abs_tolerance_m3_h": 0.0,
                    "require_same_room_set": True,
                },
            )
        ],
        active_analysis_id="consistency",
    )
    app.status_var = _Status()

    assert app._write_export_file(
        str(output),
        "safe export\n",
        label="Result",
    ) is True

    assert output.read_text(encoding="utf-8") == "safe export\n"

def test_gui_revision_restore_refuses_declared_dependency(monkeypatch, tmp_path):
    verification = tmp_path / "verification.json"
    dependency = tmp_path / "hvac.json"
    verification.write_text("{}\n", encoding="utf-8")
    dependency.write_text('{"engineering": "input"}\n', encoding="utf-8")
    before = dependency.read_bytes()
    project_path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        ProjectDocument(
            name="Protected revision restore dependency",
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
    app = _saved_app(project_path)

    class _Root:
        def wait_window(self, _dialog):
            return None

    revision = tmp_path / "saved.cleanroomx.revision.json"
    scan = type("_Scan", (), {"revisions": [revision], "issues": []})()

    class _Dialog:
        def __init__(self, _root, _scan):
            self.result = revision

    app.root = _Root()
    errors = []
    monkeypatch.setattr(gui_module, "scan_project_revisions", lambda _path: scan)
    monkeypatch.setattr(gui_module, "ProjectRevisionCenter", _Dialog)
    monkeypatch.setattr(
        gui_module.filedialog,
        "asksaveasfilename",
        lambda **_kwargs: str(dependency),
    )
    monkeypatch.setattr(
        gui_module,
        "restore_project_revision",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("unsafe restore destination must be rejected before restore")
        ),
    )
    monkeypatch.setattr(
        gui_module.messagebox,
        "showerror",
        lambda title, message, parent=None: errors.append((title, message, parent)),
    )

    assert app.show_saved_revisions() is False

    assert dependency.read_bytes() == before
    assert errors
    assert "external dependency" in errors[-1][1]

