from __future__ import annotations

from pathlib import Path

import cleanroomx.gui as gui_module
import cleanroomx.strict_json as strict_json_module
from cleanroomx.gui import CleanroomXApp
from cleanroomx.project import AnalysisDocument, ProjectDocument


class _Status:
    def __init__(self) -> None:
        self.value = ""

    def set(self, value: str) -> None:
        self.value = value


def _import_app(tmp_path):
    analysis = AnalysisDocument(
        id="analysis",
        name="Analysis",
        kind="room_verification",
        input={"original": True},
    )
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = object()
    app._running = False
    app.project = ProjectDocument(
        name="Import boundary",
        analyses=[analysis],
        active_analysis_id=analysis.id,
    )
    app.project_path = tmp_path / "project.cleanroomx.json"
    app.status_var = _Status()
    app._current_analysis = lambda: analysis
    app._perform_project_edit = lambda _label, mutate: mutate()
    app._invalidate_last_run_for = lambda _analysis_id: None
    app._load_analysis_into_editor = lambda _analysis: None
    app._update_title = lambda: None
    return app, analysis


def _capture_errors(monkeypatch):
    errors = []
    monkeypatch.setattr(
        gui_module.messagebox,
        "showerror",
        lambda title, message, parent=None: errors.append((title, message, parent)),
    )
    return errors


def test_gui_import_routes_through_canonical_strict_json_reader(
    monkeypatch,
    tmp_path,
):
    source = tmp_path / "input.json"
    source.write_text('{"value": 1}\n', encoding="utf-8")
    app, analysis = _import_app(tmp_path)
    calls = []

    def read(path):
        calls.append(Path(path))
        return {"value": 1}

    monkeypatch.setattr(gui_module, "load_strict_json", read)
    monkeypatch.setattr(
        gui_module.filedialog,
        "askopenfilename",
        lambda **_kwargs: str(source),
    )

    app.import_input_json()

    assert calls == [source]
    assert analysis.input == {"value": 1}
    assert app.status_var.value == f"Imported {source.name}"


def test_gui_import_rejects_oversize_input_through_bounded_reader(
    monkeypatch,
    tmp_path,
):
    source = tmp_path / "oversize.json"
    source.write_text('{"payload":"' + ("x" * 64) + '"}\n', encoding="utf-8")
    app, analysis = _import_app(tmp_path)
    before = dict(analysis.input)
    errors = _capture_errors(monkeypatch)

    monkeypatch.setattr(
        gui_module,
        "load_strict_json",
        lambda path: strict_json_module.load_strict_json(path, max_bytes=32),
    )
    monkeypatch.setattr(
        gui_module.filedialog,
        "askopenfilename",
        lambda **_kwargs: str(source),
    )

    app.import_input_json()

    assert analysis.input == before
    assert errors
    assert errors[-1][0] == "Import failed"
    assert "exceeds maximum supported JSON size" in errors[-1][1]
    assert errors[-1][2] is app.root


def test_gui_import_fails_closed_when_live_path_identity_changes(
    monkeypatch,
    tmp_path,
):
    source = tmp_path / "input.json"
    replacement = tmp_path / "replacement.json"
    source.write_text('{"value": 1}\n', encoding="utf-8")
    replacement.write_text('{"value": 222}\n', encoding="utf-8")
    app, analysis = _import_app(tmp_path)
    before = dict(analysis.input)
    errors = _capture_errors(monkeypatch)

    original_stat = Path.stat

    def replacement_stat(self, *args, **kwargs):
        if self == source:
            return original_stat(replacement, *args, **kwargs)
        return original_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", replacement_stat)
    monkeypatch.setattr(
        gui_module.filedialog,
        "askopenfilename",
        lambda **_kwargs: str(source),
    )

    app.import_input_json()

    assert analysis.input == before
    assert errors
    assert errors[-1][0] == "Import failed"
    assert "changed while reading JSON input" in errors[-1][1]
    assert errors[-1][2] is app.root
