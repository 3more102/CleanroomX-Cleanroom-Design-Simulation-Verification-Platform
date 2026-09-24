from __future__ import annotations

import json
from pathlib import Path

import pytest

import cleanroomx.gui as gui_module
from cleanroomx.application import run_analysis
from cleanroomx.gui import CleanroomXApp, _strict_json_loads, flatten_json, main, unit_hint
from cleanroomx.project import AnalysisDocument, ProjectDocument, load_project_document


ROOT = Path(__file__).resolve().parents[1]


def test_unit_hint_recognizes_engineering_units():
    assert unit_hint("$.fan_curve.points[0].airflow_m3_h") == "m³/h"
    assert unit_hint("$.air_density_kg_m3") == "kg/m³"
    assert unit_hint("$.kinematic_viscosity_m2_s") == "m²/s"
    assert unit_hint("$.pressure_pa") == "Pa"
    assert unit_hint("$.temperature_c") == "°C"
    assert unit_hint("$.value") == ""


def test_gui_json_parser_rejects_non_finite_constants():
    with pytest.raises(ValueError, match="non-finite"):
        _strict_json_loads('{"value": NaN}')


def test_flatten_json_preserves_paths_and_units():
    rows = flatten_json({"room": {"supply_airflow_m3_h": 1200.0, "enabled": True}})
    assert ("$.room.supply_airflow_m3_h", "1200.0", "m³/h") in rows
    assert ("$.room.enabled", "true", "") in rows


def test_commit_editor_updates_loaded_analysis_even_if_selection_has_moved():
    class Value:
        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value

    class Text:
        def get(self, *args):
            return '{"value": 2}'

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.project = ProjectDocument(
        name="Demo",
        analyses=[
            AnalysisDocument(id="a", name="A", kind="room_verification", input={"value": 1}),
            AnalysisDocument(id="b", name="B", kind="room_verification", input={"value": 9}),
        ],
        active_analysis_id="b",
    )
    app._editor_analysis_id = "a"
    app.input_text = Text()
    app.name_var = Value("Demo")
    app.description_var = Value("Preserve editor state")

    committed = app._commit_editor()

    assert committed.id == "a"
    assert app.project.analysis_by_id("a").input == {"value": 2}
    assert app.project.analysis_by_id("b").input == {"value": 9}
    assert app.project.description == "Preserve editor state"


def test_running_analysis_prevents_switching_to_another_analysis():
    class Tree:
        def __init__(self):
            self.selected = ("b",)

        def selection(self):
            return self.selected

        def exists(self, analysis_id):
            return analysis_id == "a"

        def selection_set(self, analysis_id):
            self.selected = (analysis_id,)

        def focus(self, analysis_id):
            self.focused = analysis_id

        def see(self, analysis_id):
            self.seen = analysis_id

    class Status:
        def set(self, value):
            self.value = value

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.project = ProjectDocument(
        name="Demo",
        analyses=[
            AnalysisDocument(id="a", name="A", kind="room_verification", input={}),
            AnalysisDocument(id="b", name="B", kind="room_verification", input={}),
        ],
        active_analysis_id="a",
    )
    app._editor_analysis_id = "a"
    app._selection_guard = False
    app._running = True
    app.analysis_tree = Tree()
    app.status_var = Status()

    app._on_analysis_selected()

    assert app.analysis_tree.selection() == ("a",)
    assert app.project.active_analysis_id == "a"
    assert "abandon" in app.status_var.value.lower()


def test_unsaved_state_detects_uncommitted_editor_changes():
    class Value:
        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value

    class Text:
        def __init__(self, value):
            self.value = value

        def get(self, *args):
            return self.value

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.project = ProjectDocument(
        name="Demo",
        analyses=[
            AnalysisDocument(id="a", name="A", kind="room_verification", input={"value": 1}),
        ],
        active_analysis_id="a",
    )
    app._editor_analysis_id = "a"
    app.name_var = Value("Demo")
    app.description_var = Value("")
    app.input_text = Text('{"value": 1}')
    app._baseline_state = app._project_state_signature()

    assert app._has_unsaved_changes() is False

    app.input_text.value = '{"value": 2}'
    assert app._has_unsaved_changes() is True

    app.input_text.value = "{broken"
    assert app._has_unsaved_changes() is True


def test_save_project_commits_loaded_editor_when_tree_selection_is_absent(tmp_path):
    class Value:
        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value

        def set(self, value):
            self.value = value

    class Text:
        def get(self, *args):
            return '{"value": 2}'

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.project = ProjectDocument(
        name="Demo",
        analyses=[
            AnalysisDocument(
                id="a",
                name="A",
                kind="room_verification",
                input={"value": 1},
            ),
        ],
        active_analysis_id="a",
    )
    app._editor_analysis_id = "a"
    app.input_text = Text()
    app.name_var = Value("Demo")
    app.description_var = Value("")
    app.status_var = Value("")
    app.root = object()
    app.project_path = tmp_path / "demo.cleanroomx.json"
    app._capture_saved_state = lambda: None

    app.save_project()

    saved = load_project_document(app.project_path)
    assert saved.analysis_by_id("a").input == {"value": 2}
    assert "Saved" in app.status_var.value


def test_remove_analysis_invalidates_matching_result(monkeypatch):
    analysis = AnalysisDocument(
        id="a", name="A", kind="room_verification", input={"value": 1}
    )
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = object()
    app._running = False
    app.project = ProjectDocument(
        name="Demo", analyses=[analysis], active_analysis_id="a"
    )
    app.last_run = object()
    app.last_run_analysis_id = "a"
    app._runs_by_analysis = {"a": app.last_run}
    app.result_text = object()
    app.report_text = object()
    app.diagnostics_text = object()
    app._current_analysis = lambda: analysis
    app._refresh_analysis_list = lambda: None
    app._set_text = lambda widget, value: None
    app._draw_plot = lambda: None
    monkeypatch.setattr(
        gui_module.messagebox,
        "askyesno",
        lambda *args, **kwargs: True,
    )

    app.remove_analysis()

    assert app.project.analyses == []
    assert app.project.active_analysis_id is None
    assert app.last_run is None
    assert app.last_run_analysis_id is None


def test_gui_check_mode_needs_no_display(capsys):
    assert main(["--check"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["name"] == "CleanroomX"
    assert payload["version"] == "0.98.0"
    assert payload["analysis_count"] >= 20
    assert payload["bindings_valid"] is True


def test_gui_demo_project_round_trips_and_active_analysis_runs():
    path = ROOT / "examples" / "gui_demo.cleanroomx.json"
    project = load_project_document(path)
    assert len(project.analyses) >= 5
    active = project.analysis_by_id(project.active_analysis_id)
    run = run_analysis(active.kind, active.input, base_dir=path.parent)
    assert run.result
    json.dumps(run.to_dict(), allow_nan=False)


def test_stale_result_is_invalidated_when_matching_analysis_input_changes():
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.last_run = object()
    app.last_run_analysis_id = "analysis-a"
    app._runs_by_analysis = {
        "analysis-a": app.last_run,
        "analysis-b": object(),
    }
    app.result_text = object()
    app.report_text = object()
    app.diagnostics_text = object()

    cleared = []
    app._set_text = lambda widget, value: cleared.append((widget, value))
    app._draw_plot = lambda: cleared.append(("plot", None))

    app._invalidate_last_run_for("analysis-b")
    assert app.last_run is not None
    assert app.last_run_analysis_id == "analysis-a"
    assert "analysis-a" in app._runs_by_analysis
    assert "analysis-b" not in app._runs_by_analysis
    assert cleared == []

    app._invalidate_last_run_for("analysis-a")
    assert app.last_run is None
    assert app.last_run_analysis_id is None
    assert app._runs_by_analysis == {}
    assert cleared[:-1] == [
        (app.result_text, ""),
        (app.report_text, ""),
        (app.diagnostics_text, ""),
    ]
    assert cleared[-1] == ("plot", None)


def test_open_project_reports_invalid_project_instead_of_raising(monkeypatch):
    app = CleanroomXApp.__new__(CleanroomXApp)
    app._running = False
    app.root = object()
    app._confirm_project_replacement = lambda: True

    def fail_load(path):
        raise ValueError("invalid project")

    app.load_project_path = fail_load
    captured = {}
    monkeypatch.setattr(
        gui_module.filedialog,
        "askopenfilename",
        lambda **kwargs: "broken.cleanroomx.json",
    )
    monkeypatch.setattr(
        gui_module.messagebox,
        "showerror",
        lambda title, message, parent=None: captured.update(
            {"title": title, "message": message, "parent": parent}
        ),
    )

    app.open_project()

    assert captured["title"] == "Open failed"
    assert captured["message"] == "invalid project"
    assert captured["parent"] is app.root


def test_per_analysis_run_cache_restores_without_forcing_result_tab():
    run_a = object()
    run_b = object()
    app = CleanroomXApp.__new__(CleanroomXApp)
    app._runs_by_analysis = {"analysis-a": run_a, "analysis-b": run_b}
    app.last_run = None
    app.last_run_analysis_id = None

    rendered = []
    app._render_run = lambda run, select_results=True: rendered.append(
        (run, select_results)
    )

    assert app._restore_run_for("analysis-a") is True
    assert app.last_run is run_a
    assert app.last_run_analysis_id == "analysis-a"
    assert rendered == [(run_a, False)]

    assert app._restore_run_for("analysis-b") is True
    assert app.last_run is run_b
    assert app.last_run_analysis_id == "analysis-b"
    assert rendered[-1] == (run_b, False)


def test_clear_run_cache_discards_all_session_results_and_rendered_output():
    app = CleanroomXApp.__new__(CleanroomXApp)
    app._runs_by_analysis = {"analysis-a": object(), "analysis-b": object()}
    app.last_run = object()
    app.last_run_analysis_id = "analysis-a"
    app.result_text = object()
    app.report_text = object()
    app.diagnostics_text = object()

    cleared = []
    app._set_text = lambda widget, value: cleared.append((widget, value))
    app._draw_plot = lambda: cleared.append(("plot", None))

    app._clear_run_cache()

    assert app._runs_by_analysis == {}
    assert app.last_run is None
    assert app.last_run_analysis_id is None
    assert cleared[-1] == ("plot", None)


def test_window_title_marks_unsaved_editor_changes():
    class Root:
        def title(self, value):
            self.value = value

    class Value:
        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value

    class Text:
        def __init__(self, value):
            self.value = value

        def get(self, *args):
            return self.value

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = Root()
    app.project_path = None
    app.project = ProjectDocument(
        name="Demo",
        analyses=[
            AnalysisDocument(
                id="a",
                name="A",
                kind="room_verification",
                input={"value": 1},
            )
        ],
        active_analysis_id="a",
    )
    app._editor_analysis_id = "a"
    app.name_var = Value("Demo")
    app.description_var = Value("")
    app.input_text = Text('{"value": 1}')
    app._baseline_state = app._project_state_signature()

    app._update_title()
    assert not app.root.value.endswith("*")

    app.input_text.value = '{"value": 2}'
    app._update_title()
    assert app.root.value.endswith("*")
