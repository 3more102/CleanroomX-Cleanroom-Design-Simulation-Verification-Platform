from __future__ import annotations

import json
from pathlib import Path

import pytest

import cleanroomx.gui as gui_module
from cleanroomx.application import run_analysis
from cleanroomx.gui import (
    CleanroomXApp,
    _strict_json_loads,
    analysis_matches_filter,
    evaluate_pressure_cascade_visuals,
    extract_pressure_cascade,
    extract_room_visuals,
    flatten_json,
    main,
    room_visual_engineering_metrics,
    unit_hint,
)
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


def test_extract_room_visuals_preserves_real_dimensions_and_engineering_metadata():
    rooms = extract_room_visuals(
        {
            "name": "Demo",
            "rooms": [
                {
                    "name": "Process",
                    "length_m": 6.0,
                    "width_m": 5.0,
                    "height_m": 3.0,
                    "x_m": 12.5,
                    "y_m": -2.0,
                    "supply_airflow_m3_h": 2700.0,
                    "observed_pressure_pa": 30.0,
                }
            ],
        }
    )

    assert rooms == [
        {
            "name": "Process",
            "length_m": 6.0,
            "width_m": 5.0,
            "height_m": 3.0,
            "dimensions_real": True,
            "height_real": True,
            "position_real": True,
            "x_m": 12.5,
            "y_m": -2.0,
            "airflow_m3_h": 2700.0,
            "pressure_pa": 30.0,
            "min_ach": None,
            "min_pressure_pa": None,
        }
    ]


def test_extract_room_visuals_marks_display_defaults_when_geometry_is_missing():
    rooms = extract_room_visuals(
        {"rooms": [{"name": "Gowning", "cleanroom_airflow_m3_h": 900.0}]}
    )

    assert len(rooms) == 1
    assert rooms[0]["name"] == "Gowning"
    assert rooms[0]["dimensions_real"] is False
    assert rooms[0]["height_real"] is False
    assert rooms[0]["position_real"] is False
    assert rooms[0]["x_m"] is None
    assert rooms[0]["y_m"] is None
    assert rooms[0]["length_m"] == 4.0
    assert rooms[0]["width_m"] == 4.0
    assert rooms[0]["height_m"] == 3.0
    assert rooms[0]["airflow_m3_h"] == 900.0
    assert rooms[0]["min_ach"] is None
    assert rooms[0]["min_pressure_pa"] is None


def test_room_visual_engineering_metrics_reports_pass_fail_and_unknown():
    rooms = extract_room_visuals(
        {
            "rooms": [
                {
                    "name": "Passing",
                    "length_m": 6,
                    "width_m": 5,
                    "height_m": 3,
                    "supply_airflow_m3_h": 2700,
                    "min_ach": 25,
                    "observed_pressure_pa": 30,
                    "min_pressure_pa": 20,
                },
                {
                    "name": "Failing",
                    "length_m": 6,
                    "width_m": 5,
                    "height_m": 3,
                    "supply_airflow_m3_h": 900,
                    "min_ach": 25,
                    "observed_pressure_pa": 10,
                    "min_pressure_pa": 20,
                },
                {
                    "name": "Unknown",
                    "supply_airflow_m3_h": 900,
                    "min_ach": 20,
                },
            ]
        }
    )

    passing = room_visual_engineering_metrics(rooms[0])
    failing = room_visual_engineering_metrics(rooms[1])
    unknown = room_visual_engineering_metrics(rooms[2])

    assert passing["ach"] == pytest.approx(30.0)
    assert passing["ach_status"] == "pass"
    assert passing["pressure_status"] == "pass"
    assert passing["status"] == "pass"

    assert failing["ach"] == pytest.approx(10.0)
    assert failing["ach_status"] == "fail"
    assert failing["pressure_status"] == "fail"
    assert failing["status"] == "fail"

    assert unknown["ach"] is None
    assert unknown["ach_status"] == "unknown"
    assert unknown["status"] == "unknown"


def test_pressure_cascade_visual_status_uses_observed_differential_pressure():
    rooms = extract_room_visuals(
        {
            "rooms": [
                {"name": "High", "length_m": 4, "width_m": 4, "height_m": 3, "supply_airflow_m3_h": 960, "observed_pressure_pa": 30},
                {"name": "Mid", "length_m": 4, "width_m": 4, "height_m": 3, "supply_airflow_m3_h": 960, "observed_pressure_pa": 18},
                {"name": "Low", "length_m": 4, "width_m": 4, "height_m": 3, "supply_airflow_m3_h": 960},
            ]
        }
    )
    links = [
        {"higher_pressure_room": "High", "lower_pressure_room": "Mid", "min_delta_pa": 10.0},
        {"higher_pressure_room": "Mid", "lower_pressure_room": "High", "min_delta_pa": 10.0},
        {"higher_pressure_room": "Mid", "lower_pressure_room": "Low", "min_delta_pa": 5.0},
    ]

    evaluated = evaluate_pressure_cascade_visuals(rooms, links)

    assert evaluated[0]["observed_delta_pa"] == pytest.approx(12.0)
    assert evaluated[0]["status"] == "pass"
    assert evaluated[1]["observed_delta_pa"] == pytest.approx(-12.0)
    assert evaluated[1]["status"] == "fail"
    assert evaluated[2]["observed_delta_pa"] is None
    assert evaluated[2]["status"] == "unknown"


def test_room_layout_uses_declared_coordinates_only_when_complete():
    app = CleanroomXApp.__new__(CleanroomXApp)
    rooms = extract_room_visuals(
        {
            "rooms": [
                {
                    "name": "A",
                    "length_m": 4,
                    "width_m": 3,
                    "height_m": 3,
                    "x_m": -1,
                    "y_m": 2,
                },
                {
                    "name": "B",
                    "length_m": 5,
                    "width_m": 2,
                    "height_m": 3,
                    "x_m": 8,
                    "y_m": 6,
                },
            ]
        }
    )

    placed, fully_scaled = app._room_layout(rooms)

    assert fully_scaled is True
    assert [(room["x"], room["y"]) for room in placed] == [(-1.0, 2.0), (8.0, 6.0)]


def test_room_layout_falls_back_to_auto_arrangement_for_partial_coordinates():
    app = CleanroomXApp.__new__(CleanroomXApp)
    rooms = extract_room_visuals(
        {
            "rooms": [
                {
                    "name": "A",
                    "length_m": 4,
                    "width_m": 3,
                    "height_m": 3,
                    "x_m": 10,
                    "y_m": 20,
                },
                {
                    "name": "B",
                    "length_m": 5,
                    "width_m": 2,
                    "height_m": 3,
                },
            ]
        }
    )

    placed, fully_scaled = app._room_layout(rooms)

    assert fully_scaled is True
    assert placed[0]["x"] == 0.0
    assert placed[0]["y"] == 0.0
    assert (placed[1]["x"], placed[1]["y"]) != (10.0, 20.0)


def test_extract_pressure_cascade_normalizes_declared_room_links():
    links = extract_pressure_cascade(
        {
            "pressure_cascade": [
                {
                    "higher_pressure_room": "Process",
                    "lower_pressure_room": "Preparation",
                    "min_delta_pa": 10,
                },
                {
                    "higher_pressure_room": "Preparation",
                    "lower_pressure_room": "Ante",
                    "min_delta_pa": "5",
                },
            ]
        }
    )

    assert links == [
        {
            "higher_pressure_room": "Process",
            "lower_pressure_room": "Preparation",
            "min_delta_pa": 10.0,
        },
        {
            "higher_pressure_room": "Preparation",
            "lower_pressure_room": "Ante",
            "min_delta_pa": 5.0,
        },
    ]


def test_analysis_filter_matches_name_kind_and_catalog_title():
    analysis = AnalysisDocument(
        id="a",
        name="Primary Process Check",
        kind="room_verification",
        input={},
    )

    assert analysis_matches_filter(analysis, "") is True
    assert analysis_matches_filter(analysis, "process") is True
    assert analysis_matches_filter(analysis, "ROOM_VERIFICATION") is True
    assert analysis_matches_filter(analysis, "verification") is True
    assert analysis_matches_filter(analysis, "fan curve") is False


def test_sidebar_filter_does_not_switch_away_from_hidden_active_editor():
    class Value:
        def get(self):
            return "second"

    class Tree:
        def __init__(self):
            self.items = {}

        def get_children(self):
            return tuple(self.items)

        def delete(self, item):
            self.items.pop(item, None)

        def insert(self, parent, index, iid, text, values):
            self.items[iid] = (text, values)

        def exists(self, iid):
            return iid in self.items

        def selection_set(self, iid):
            raise AssertionError("filtering should not select another analysis")

        def focus(self, iid):
            raise AssertionError("filtering should not move focus")

        def see(self, iid):
            raise AssertionError("filtering should not scroll to another analysis")

    first = AnalysisDocument(
        id="a",
        name="First",
        kind="room_verification",
        input={"value": 1},
    )
    second = AnalysisDocument(
        id="b",
        name="Second",
        kind="room_verification",
        input={"value": 2},
    )
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.project = ProjectDocument(
        name="Demo",
        analyses=[first, second],
        active_analysis_id="a",
    )
    app.analysis_tree = Tree()
    app.analysis_filter_var = Value()
    app._editor_analysis_id = "a"
    app._refresh_dashboard = lambda: None
    app._load_analysis_into_editor = lambda analysis: (_ for _ in ()).throw(
        AssertionError("filtering should preserve the active editor")
    )

    app._refresh_analysis_list()

    assert app.project.active_analysis_id == "a"
    assert tuple(app.analysis_tree.items) == ("b",)


def test_visual_zoom_is_bounded_and_3d_rotation_wraps():
    app = CleanroomXApp.__new__(CleanroomXApp)
    app._visual_zoom = 1.0
    app._visual3d_yaw_deg = 350.0
    refreshes = []
    app._refresh_visuals = lambda: refreshes.append("refresh")
    app._draw_3d_workspace = lambda: refreshes.append("3d")

    app._change_visual_zoom(100.0)
    assert app._visual_zoom == 3.0
    app._change_visual_zoom(0.001)
    assert app._visual_zoom == 0.45

    app._rotate_3d(30.0)
    assert app._visual3d_yaw_deg == 20.0
    assert refreshes[-1] == "3d"


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


def test_abandon_waits_for_worker_exit_before_reenabling_ui():
    import queue

    class Widget:
        def __init__(self):
            self.state = None

        def configure(self, **kwargs):
            if "state" in kwargs:
                self.state = kwargs["state"]

    class Status:
        def set(self, value):
            self.value = value

    class Root:
        def after(self, delay, callback):
            self.delay = delay
            self.callback = callback

    app = CleanroomXApp.__new__(CleanroomXApp)
    app._running = True
    app._abandon_requested = False
    app._run_generation = 7
    app._queue = queue.Queue()
    app.run_button = Widget()
    app.cancel_button = Widget()
    app.input_text = Widget()
    app.status_var = Status()
    app.root = Root()

    app.cancel_run()

    assert app._running is True
    assert app._abandon_requested is True
    assert app._run_generation == 7
    assert app.cancel_button.state == "disabled"
    assert "waiting" in app.status_var.value.lower()

    app._queue.put(("success", 7, "analysis-a", object()))
    app._poll_worker()

    assert app._running is False
    assert app._abandon_requested is False
    assert app.run_button.state == "normal"
    assert app.cancel_button.state == "disabled"
    assert app.input_text.state == "normal"
    assert "worker finished" in app.status_var.value.lower()
    assert app.root.delay == 100


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


def test_save_project_as_invalidates_results_when_base_directory_changes(
    tmp_path, monkeypatch
):
    class Value:
        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value

        def set(self, value):
            self.value = value

    old_dir = tmp_path / "old"
    new_dir = tmp_path / "new"
    old_dir.mkdir()
    new_dir.mkdir()

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.project = ProjectDocument(name="Demo")
    app.project_path = old_dir / "demo.cleanroomx.json"
    app._editor_analysis_id = None
    app.name_var = Value("Demo")
    app.description_var = Value("")
    app.status_var = Value("")
    app.root = object()
    app._baseline_state = None

    app._runs_by_analysis = {"analysis-a": object()}
    app.last_run = app._runs_by_analysis["analysis-a"]
    app.last_run_analysis_id = "analysis-a"
    app.result_text = object()
    app.report_text = object()
    app.diagnostics_text = object()
    app._set_text = lambda widget, value: None
    app._draw_plot = lambda: None

    destination = new_dir / "demo.cleanroomx.json"
    monkeypatch.setattr(
        gui_module.filedialog,
        "asksaveasfilename",
        lambda **kwargs: str(destination),
    )

    app.save_project_as()

    assert app.project_path == destination
    assert app._runs_by_analysis == {}
    assert app.last_run is None
    assert app.last_run_analysis_id is None



def test_save_project_as_rebases_relative_external_references(tmp_path, monkeypatch):
    class Value:
        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value

        def set(self, value):
            self.value = value

    source_dir = tmp_path / "source"
    target_dir = tmp_path / "archive" / "nested"
    source_dir.mkdir()
    target_dir.mkdir(parents=True)
    destination = target_dir / "portable.cleanroomx.json"
    analysis = AnalysisDocument(
        id="c",
        name="Consistency",
        kind="consistency",
        input={
            "verification_project": "inputs/facility.json",
            "hvac_project": "../shared/hvac.json",
        },
    )

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = object()
    app.project = ProjectDocument(
        name="Portable", analyses=[analysis], active_analysis_id="c"
    )
    app.project_path = source_dir / "source.cleanroomx.json"
    app._editor_analysis_id = None
    app.name_var = Value("Portable")
    app.description_var = Value("")
    app.status_var = Value("")
    app._capture_saved_state = lambda: None
    app._update_title = lambda: None
    app._runs_by_analysis = {}
    app.last_run = None
    app.last_run_analysis_id = None
    app.result_text = object()
    app.report_text = object()
    app.diagnostics_text = object()
    app._set_text = lambda widget, value: None
    app._draw_plot = lambda: None

    monkeypatch.setattr(
        gui_module.filedialog, "asksaveasfilename", lambda **kwargs: str(destination)
    )

    app.save_project_as()

    saved = load_project_document(destination)
    saved_input = saved.analysis_by_id("c").input
    original_input = analysis.input
    for key in ("verification_project", "hvac_project"):
        assert (destination.parent / saved_input[key]).resolve() == (
            source_dir / original_input[key]
        ).resolve()
    assert app.project_path == destination


def test_import_input_json_preserves_source_file_reference_context(tmp_path, monkeypatch):
    class Status:
        def set(self, value):
            self.value = value

    project_dir = tmp_path / "project"
    import_dir = tmp_path / "import"
    project_dir.mkdir()
    import_dir.mkdir()
    import_path = import_dir / "consistency.json"
    import_path.write_text(
        json.dumps({
            "verification_project": "facility.json",
            "hvac_project": "hvac.json",
        }),
        encoding="utf-8",
    )
    analysis = AnalysisDocument(id="c", name="Consistency", kind="consistency", input={})

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = object()
    app._running = False
    app.project_path = project_dir / "project.cleanroomx.json"
    app.status_var = Status()
    app._current_analysis = lambda: analysis
    app._invalidate_last_run_for = lambda analysis_id: None
    app._load_analysis_into_editor = lambda item: None
    app._update_title = lambda: None

    monkeypatch.setattr(
        gui_module.filedialog, "askopenfilename", lambda **kwargs: str(import_path)
    )

    app.import_input_json()

    for key, filename in (
        ("verification_project", "facility.json"),
        ("hvac_project", "hvac.json"),
    ):
        assert (project_dir / analysis.input[key]).resolve() == (
            import_dir / filename
        ).resolve()


def test_export_writer_uses_atomic_write_and_reports_failure(monkeypatch, tmp_path):
    class Status:
        def set(self, value):
            self.value = value

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = object()
    app.status_var = Status()
    target = tmp_path / "result.json"
    calls = []

    monkeypatch.setattr(
        gui_module,
        "atomic_write_text",
        lambda path, content: calls.append((Path(path), content)),
    )
    assert app._write_export_file(str(target), "payload", label="Result") is True
    assert calls == [(target, "payload")]
    assert "Exported result" in app.status_var.value

    captured = {}

    def fail_write(path, content):
        raise OSError("disk full")

    monkeypatch.setattr(gui_module, "atomic_write_text", fail_write)
    monkeypatch.setattr(
        gui_module.messagebox,
        "showerror",
        lambda title, message, parent=None: captured.update(
            {"title": title, "message": message, "parent": parent}
        ),
    )
    assert app._write_export_file(str(target), "payload", label="Result") is False
    assert app.status_var.value == "Result export failed"
    assert captured["title"] == "Result export failed"
    assert captured["message"] == "disk full"
    assert captured["parent"] is app.root


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
    assert app._runs_by_analysis == {}


def test_gui_launch_validates_registry_before_creating_tk_root(monkeypatch):
    root_created = []

    def fail_registry_validation():
        raise RuntimeError("broken registry")

    monkeypatch.setattr(gui_module, "validate_application_registry", fail_registry_validation)
    monkeypatch.setattr(gui_module.tk, "Tk", lambda: root_created.append(True))

    with pytest.raises(RuntimeError, match="broken registry"):
        main([])
    assert root_created == []


def test_gui_check_mode_needs_no_display(capsys):
    assert main(["--check"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["name"] == "CleanroomX"
    assert payload["version"] == "0.100.0"
    assert payload["analysis_count"] >= 20
    assert payload["bindings_valid"] is True
    assert payload["registry_validation"]["status"] == "ok"
    assert payload["registry_validation"]["analysis_count"] == payload["analysis_count"]
    assert set(payload["registry_validation"]["custom_adapters"]) == {"consistency", "dossier"}


def test_export_run_bundle_json_preserves_execution_provenance(tmp_path, monkeypatch):
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = object()

    class Status:
        def set(self, value):
            self.value = value

    app.status_var = Status()
    app.last_run = run_analysis(
        "fan_operating_point",
        json.loads(
            (ROOT / "examples" / "fan_operating_point_demo.json").read_text(
                encoding="utf-8"
            )
        ),
    )
    output = tmp_path / "run-bundle.json"
    monkeypatch.setattr(
        gui_module.filedialog,
        "asksaveasfilename",
        lambda **kwargs: str(output),
    )

    app.export_run_bundle_json()

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["kind"] == "fan_operating_point"
    provenance = payload["diagnostics"]["application_execution_provenance"]
    assert provenance["analysis_kind"] == "fan_operating_point"
    assert len(provenance["input_sha256"]) == 64



def test_bundled_demo_project_is_self_contained_and_active_analysis_runs():
    path = gui_module.bundled_demo_project_path()
    assert path.is_file()
    for dependency in (
        "facility_project.json",
        "consistency_hvac_demo.json",
        "fan_variable_friction_uncertainty_demo.json",
    ):
        assert (path.parent / dependency).is_file()

    project = load_project_document(path)
    assert len(project.analyses) >= 5
    active = project.analysis_by_id(project.active_analysis_id)
    run = run_analysis(active.kind, active.input, base_dir=path.parent)
    assert run.result
    json.dumps(run.to_dict(), allow_nan=False)


def test_gui_demo_project_round_trips_and_active_analysis_runs():
    path = ROOT / "examples" / "gui_demo.cleanroomx.json"
    project = load_project_document(path)
    assert len(project.analyses) >= 5
    active = project.analysis_by_id(project.active_analysis_id)
    run = run_analysis(active.kind, active.input, base_dir=path.parent)
    assert run.result
    json.dumps(run.to_dict(), allow_nan=False)


def test_gui_demo_opens_on_positioned_passing_engineering_visualization():
    path = ROOT / "examples" / "gui_demo.cleanroomx.json"
    project = load_project_document(path)
    active = project.analysis_by_id(project.active_analysis_id)

    assert active.id == "verification"
    rooms = extract_room_visuals(active.input)
    assert len(rooms) == 3
    assert all(room["position_real"] for room in rooms)

    metrics = [room_visual_engineering_metrics(room) for room in rooms]
    assert all(item["status"] == "pass" for item in metrics)

    cascade = evaluate_pressure_cascade_visuals(
        rooms,
        extract_pressure_cascade(active.input),
    )
    assert len(cascade) == 2
    assert all(item["status"] == "pass" for item in cascade)


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
