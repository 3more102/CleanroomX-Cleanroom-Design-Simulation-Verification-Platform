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


def _import_app(analysis: AnalysisDocument, base_dir: Path) -> CleanroomXApp:
    app = CleanroomXApp.__new__(CleanroomXApp)
    app._running = False
    app.root = object()
    app.project = ProjectDocument(
        name="GUI import safety",
        analyses=[analysis],
        active_analysis_id=analysis.id,
    )
    app.project_path = None
    app._recovery_source_path = None
    app.status_var = _Status()
    app._current_analysis = lambda: analysis
    app._base_dir = lambda: base_dir
    app._perform_project_edit = lambda _description, mutate: mutate()
    app._invalidate_last_run_for = lambda _analysis_id: None
    app._load_analysis_into_editor = lambda _analysis: None
    app._update_title = lambda: None
    return app


def _saved_app(project_path: Path) -> CleanroomXApp:
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = object()
    app.project_path = project_path
    app._recovery_source_path = None
    app.project = load_project_document(project_path)
    app.status_var = _Status()
    return app


def test_gui_import_rejects_oversize_without_mutating_analysis(
    monkeypatch,
    tmp_path,
):
    source = tmp_path / "input.json"
    source.write_text('{"airflow_m3_h": 500}\n', encoding="utf-8")
    analysis = AnalysisDocument(
        id="a",
        name="A",
        kind="room_verification",
        input={"sentinel": "unchanged"},
    )
    app = _import_app(analysis, tmp_path)
    before = dict(analysis.input)
    errors = []

    monkeypatch.setattr(
        gui_module.filedialog,
        "askopenfilename",
        lambda **_kwargs: str(source),
    )
    monkeypatch.setattr(
        gui_module.messagebox,
        "showerror",
        lambda title, message, **kwargs: errors.append((title, message)),
    )
    monkeypatch.setattr(
        strict_json_module,
        "STRICT_JSON_FILE_MAX_BYTES",
        source.stat().st_size - 1,
    )

    app.import_input_json()

    assert analysis.input == before
    assert errors
    assert "exceeds maximum supported JSON size" in errors[-1][1]


def test_gui_import_rejects_live_path_replacement_without_mutating_analysis(
    monkeypatch,
    tmp_path,
):
    source = tmp_path / "input.json"
    replacement = tmp_path / "replacement.json"
    source.write_text('{"value": 1}\n', encoding="utf-8")
    replacement.write_text('{"value": 2, "different": true}\n', encoding="utf-8")
    analysis = AnalysisDocument(
        id="a",
        name="A",
        kind="room_verification",
        input={"sentinel": "unchanged"},
    )
    app = _import_app(analysis, tmp_path)
    before = dict(analysis.input)
    errors = []
    real_stat = Path.stat
    replacement_stat = real_stat(replacement)

    def report_replacement(self: Path, *args, **kwargs):
        if self == source:
            return replacement_stat
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(
        gui_module.filedialog,
        "askopenfilename",
        lambda **_kwargs: str(source),
    )
    monkeypatch.setattr(
        gui_module.messagebox,
        "showerror",
        lambda title, message, **kwargs: errors.append((title, message)),
    )
    monkeypatch.setattr(Path, "stat", report_replacement)

    app.import_input_json()

    assert analysis.input == before
    assert errors
    assert "changed while reading JSON input" in errors[-1][1]


def test_gui_import_rebases_only_after_revision_stable_read(
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
        id="a",
        name="A",
        kind="room_verification",
        input={"sentinel": "old"},
    )
    app = _import_app(analysis, target_base)
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
        lambda **_kwargs: str(source),
    )
    monkeypatch.setattr(
        gui_module.rebase_analysis_file_references,
        record_rebase,
    )

    app.import_input_json()

    assert calls["source_base"] == source.parent
    assert calls["target_base"] == target_base
    assert calls["payload"] == {"value": 7}
    assert analysis.input == {"rebased": True}


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
        lambda title, message, **kwargs: errors.append((title, message)),
    )

    assert app._write_export_file(
        str(project_path),
        "replacement\n",
        label="Result",
    ) is False

    assert project_path.read_bytes() == before
    assert errors
    assert "project source" in errors[-1][1]


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
        lambda title, message, **kwargs: errors.append((title, message)),
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
        lambda title, message, **kwargs: errors.append((title, message)),
    )

    assert app._write_export_file(
        str(dependency),
        "replacement\n",
        label="Result",
    ) is False

    assert dependency.read_bytes() == before
    assert errors
    assert "external dependency" in errors[-1][1]
