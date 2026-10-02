from pathlib import Path
from types import SimpleNamespace

import cleanroomx.gui as gui_module
import cleanroomx.strict_json as strict_json_module
from cleanroomx.gui import CleanroomXApp
from cleanroomx.project import AnalysisDocument, ProjectDocument


class _Status:
    def set(self, value):
        self.value = value


def _app_for_import(tmp_path, analysis):
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = object()
    app._running = False
    app.project = ProjectDocument(
        name="Demo",
        analyses=[analysis],
        active_analysis_id=analysis.id,
    )
    app.project_path = tmp_path / "project.cleanroomx.json"
    app.status_var = _Status()
    app._current_analysis = lambda: analysis
    app._perform_project_edit = lambda _label, edit: edit()
    app._invalidate_last_run_for = lambda _analysis_id: None
    app._load_analysis_into_editor = lambda _item: None
    app._update_title = lambda: None
    return app


def _capture_import_error(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        gui_module.messagebox,
        "showerror",
        lambda title, message, parent=None: captured.update(
            {"title": title, "message": message, "parent": parent}
        ),
    )
    return captured


def test_import_input_json_rejects_oversized_file_before_project_edit(
    tmp_path, monkeypatch
):
    source = tmp_path / "oversized.json"
    source.write_text('{"value": 12345}', encoding="utf-8")
    analysis = AnalysisDocument(
        id="a",
        name="Analysis",
        kind="room_verification",
        input={"sentinel": True},
    )
    app = _app_for_import(tmp_path, analysis)
    captured = _capture_import_error(monkeypatch)

    monkeypatch.setattr(
        gui_module.filedialog,
        "askopenfilename",
        lambda **_kwargs: str(source),
    )
    monkeypatch.setattr(strict_json_module, "STRICT_JSON_FILE_MAX_BYTES", 8)

    app.import_input_json()

    assert analysis.input == {"sentinel": True}
    assert captured["title"] == "Import failed"
    assert "exceeds maximum supported JSON size" in captured["message"]
    assert captured["parent"] is app.root


def test_import_input_json_rejects_live_path_identity_change(
    tmp_path, monkeypatch
):
    source = tmp_path / "replaced.json"
    source.write_text('{"value": 1}', encoding="utf-8")
    analysis = AnalysisDocument(
        id="a",
        name="Analysis",
        kind="room_verification",
        input={"sentinel": True},
    )
    app = _app_for_import(tmp_path, analysis)
    captured = _capture_import_error(monkeypatch)

    monkeypatch.setattr(
        gui_module.filedialog,
        "askopenfilename",
        lambda **_kwargs: str(source),
    )

    real_stat = Path.stat

    def replaced_identity(path, *args, **kwargs):
        stat_result = real_stat(path, *args, **kwargs)
        if path == source:
            return SimpleNamespace(
                st_dev=stat_result.st_dev,
                st_ino=stat_result.st_ino + 1,
                st_size=stat_result.st_size,
                st_mtime_ns=stat_result.st_mtime_ns,
            )
        return stat_result

    monkeypatch.setattr(Path, "stat", replaced_identity)

    app.import_input_json()

    assert analysis.input == {"sentinel": True}
    assert captured["title"] == "Import failed"
    assert "changed while reading JSON input" in captured["message"]
    assert captured["parent"] is app.root
