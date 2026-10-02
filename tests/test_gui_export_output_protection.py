from __future__ import annotations

from pathlib import Path

import cleanroomx.gui as gui_module
import cleanroomx.strict_json as strict_json_module
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

def test_gui_input_import_uses_bounded_strict_json_reader(
    monkeypatch,
    tmp_path,
):
    source = tmp_path / "oversized-input.json"
    source.write_text('{"airflow_m3_h": 1200}\n', encoding="utf-8")
    original_input = {"sentinel": True}
    analysis = AnalysisDocument(
        id="room",
        name="Room",
        kind="room_verification",
        input=dict(original_input),
    )

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = object()
    app._running = False
    app._current_analysis = lambda: analysis
    app._base_dir = lambda: tmp_path
    app._perform_project_edit = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("oversized input must fail before project mutation")
    )

    errors = []
    monkeypatch.setattr(
        gui_module.filedialog,
        "askopenfilename",
        lambda **kwargs: str(source),
    )
    monkeypatch.setattr(
        gui_module.messagebox,
        "showerror",
        lambda title, message, parent=None: errors.append((title, message, parent)),
    )
    monkeypatch.setattr(
        strict_json_module,
        "STRICT_JSON_FILE_MAX_BYTES",
        len(source.read_bytes()) - 1,
    )

    app.import_input_json()

    assert analysis.input == original_input
    assert errors
    assert errors[-1][0] == "Import failed"
    assert "exceeds maximum supported JSON size" in errors[-1][1]



def test_gui_input_import_rejects_live_path_identity_replacement(
    monkeypatch,
    tmp_path,
):
    source = tmp_path / "input.json"
    replacement = tmp_path / "replacement.json"
    source.write_text('{"revision": 1}\n', encoding="utf-8")
    replacement.write_text('{"revision": 2}\n', encoding="utf-8")
    original_input = {"sentinel": True}
    analysis = AnalysisDocument(
        id="room",
        name="Room",
        kind="room_verification",
        input=dict(original_input),
    )

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = object()
    app._running = False
    app._current_analysis = lambda: analysis
    app._base_dir = lambda: tmp_path
    app._perform_project_edit = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("replaced-path input must fail before project mutation")
    )

    errors = []
    monkeypatch.setattr(
        gui_module.filedialog,
        "askopenfilename",
        lambda **kwargs: str(source),
    )
    monkeypatch.setattr(
        gui_module.messagebox,
        "showerror",
        lambda title, message, parent=None: errors.append((title, message, parent)),
    )
    monkeypatch.setattr(
        gui_module,
        "rebase_analysis_file_references",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("rebasing must not run after an unstable file read")
        ),
    )

    real_stat = Path.stat
    replacement_stat = real_stat(replacement)

    def report_replacement_identity(self: Path, *args, **kwargs):
        if self == source:
            return replacement_stat
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", report_replacement_identity)

    app.import_input_json()

    assert analysis.input == original_input
    assert errors
    assert errors[-1][0] == "Import failed"
    assert "changed while reading JSON input" in errors[-1][1]


def test_gui_input_import_rebases_after_revision_stable_read(
    monkeypatch,
    tmp_path,
):
    source_dir = tmp_path / "imports"
    source_dir.mkdir()
    source = source_dir / "input.json"
    source.write_text('{"value": 7}\n', encoding="utf-8")
    target_base = tmp_path / "project"
    target_base.mkdir()
    analysis = AnalysisDocument(
        id="room",
        name="Room",
        kind="room_verification",
        input={"sentinel": "old"},
    )

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = object()
    app._running = False
    app._current_analysis = lambda: analysis
    app._base_dir = lambda: target_base
    app._perform_project_edit = lambda _description, mutate: mutate()
    app._invalidate_last_run_for = lambda _analysis_id: None
    app._load_analysis_into_editor = lambda _analysis: None
    app._update_title = lambda: None
    app.status_var = _Status()

    calls = {}

    def record_rebase(kind, payload, *, source_base, target_base):
        calls["kind"] = kind
        calls["payload"] = payload
        calls["source_base"] = source_base
        calls["target_base"] = target_base
        return {"rebased": True}

    monkeypatch.setattr(
        gui_module.filedialog,
        "askopenfilename",
        lambda **kwargs: str(source),
    )
    monkeypatch.setattr(
        gui_module.rebase_analysis_file_references,
        record_rebase,
    )

    app.import_input_json()

    assert calls["kind"] == analysis.kind
    assert calls["payload"] == {"value": 7}
    assert calls["source_base"] == source.parent
    assert calls["target_base"] == target_base
    assert analysis.input == {"rebased": True}
