from __future__ import annotations

import copy
import os
from types import SimpleNamespace
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.gui_simulation import (
    SimulationWorkspace,
    _diagnostic_count,
    _explicit_convergence,
    _leaf_count,
    filter_run_history_records,
    run_history_diff_rows,
    run_history_filter_options,
)
from cleanroomx.gui_theme import configure_ttk_theme


def test_simulation_projection_helpers_do_not_invent_backend_state():
    assert _diagnostic_count({"issues": [{}, {}]}) == 2
    assert _diagnostic_count([{}, {}, {}]) == 3
    assert _leaf_count({"a": 1, "b": {"c": 2, "d": [3, 4]}}) == 4

    assert _explicit_convergence({"solver": {"converged": True}}) == "CONVERGED"
    assert _explicit_convergence({"solver_converged": False}) == "NOT CONVERGED"
    assert _explicit_convergence({"convergence_status": "residual target reached"}) == (
        "RESIDUAL TARGET REACHED"
    )
    assert _explicit_convergence({"status": "pass", "iterations": 7}) == "NOT REPORTED"




def test_run_history_filter_and_diff_use_only_retained_canonical_fields():
    records = [
        {
            "sequence": 1,
            "completed_at_utc": "2026-10-05T08:00:00Z",
            "analysis_name": "Baseline",
            "analysis_kind": "airflow_balance",
            "run_title": "Baseline flow",
            "status": "pass",
            "input_sha256": "a" * 64,
            "result_sha256": "b" * 64,
            "input_snapshot": {"supply_m3_h": 1000.0, "mode": "design"},
            "result": {"balance_m3_h": 0.0, "rooms": [{"ach": 20.0}]},
            "diagnostics": {"issues": []},
        },
        {
            "sequence": 2,
            "completed_at_utc": "2026-10-05T09:00:00Z",
            "analysis_name": "Modified",
            "analysis_kind": "airflow_balance",
            "run_title": "Modified flow",
            "status": "warning",
            "input_sha256": "c" * 64,
            "result_sha256": "d" * 64,
            "input_snapshot": {"supply_m3_h": 1100.0, "mode": "design"},
            "result": {"balance_m3_h": 15.0, "rooms": [{"ach": 22.0}]},
            "diagnostics": {"issues": [{"severity": "warning", "code": "FLOW"}]},
        },
    ]
    snapshot = copy.deepcopy(records)

    assert run_history_filter_options(records, "analysis_name") == (
        "All",
        "Baseline",
        "Modified",
    )
    assert [item["sequence"] for item in filter_run_history_records(
        records,
        query="modified",
        kind="airflow_balance",
        status="warning",
    )] == [2]

    rows = run_history_diff_rows(records[0], records[1])
    changed = {path: (left, right) for path, left, right in rows}
    assert "input_snapshot.supply_m3_h" in changed
    assert "result.balance_m3_h" in changed
    assert "result.rooms[0].ach" in changed
    assert "diagnostics.issues[0].code" in changed
    assert "input_snapshot.mode" not in changed
    assert records == snapshot


def test_run_history_diff_marks_missing_legacy_payload_explicitly():
    rows = run_history_diff_rows(
        {
            "analysis_name": "Legacy",
            "analysis_kind": "room_verification",
            "run_title": "Legacy",
            "status": "pass",
            "input_snapshot": {"room": "A"},
        },
        {
            "analysis_name": "Current",
            "analysis_kind": "room_verification",
            "run_title": "Current",
            "status": "pass",
            "input_snapshot": {"room": "A"},
            "result": {"ach": 25.0},
            "diagnostics": {"issues": []},
        },
    )
    changed = {path: (left, right) for path, left, right in rows}
    assert changed["result.ach"][0] == "— MISSING"
    assert changed["result.ach"][1] == "25.0"

def test_simulation_workspace_distinguishes_calculation_from_verification():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    configure_ttk_theme(root, "dark")
    history_calls = []
    workspace = SimulationWorkspace(
        root,
        on_run=lambda: None,
        on_cancel=lambda: None,
        on_validate=lambda: None,
        on_open_inputs=lambda: None,
        on_open_results=lambda: None,
        on_open_history=lambda: history_calls.append(True),
    )
    try:
        workspace.set_context(
            analysis_name="Airflow Balance",
            analysis_kind="airflow_balance",
            analysis_input={"rooms": [], "requirements": {}},
        )
        root.update_idletasks()
        assert workspace.state_var.get() == "READY"
        assert workspace.input_var.get() == "2 top-level fields"
        assert workspace.verification_var.get() == "Separate verification workspace"

        run = SimpleNamespace(
            title="Airflow Balance",
            status="pass",
            result={
                "supply_airflow_m3_h": 1250.0,
                "solver": {"converged": True, "iterations": 7},
            },
            diagnostics={"issues": [{"severity": "info"}]},
            plot={"series": []},
        )
        workspace.set_completed(run)
        root.update_idletasks()

        assert workspace.state_var.get() == "PASS"
        assert workspace.convergence_var.get() == "CONVERGED"
        assert workspace.result_fields_var.get() == "3"
        assert workspace.diagnostics_var.get() == "1"
        assert workspace.plot_var.get() == "AVAILABLE"
        assert workspace.verification_var.get() == "Separate verification workspace"
        workspace.history_button.invoke()
        assert history_calls == [True]
    finally:
        root.destroy()


@pytest.fixture
def app(tmp_path):
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    callback_errors = []
    root.report_callback_exception = lambda *args: callback_errors.append(args)
    application = CleanroomXApp(
        root,
        autosave_interval_seconds=0,
        ui_state_path=tmp_path / "gui-layout.json",
    )
    application.load_project_path(bundled_demo_project_path())
    root.update()
    try:
        yield application
        assert callback_errors == []
    finally:
        root.destroy()


def test_navigator_routes_simulation_to_first_class_workspace(app):
    app.analysis_tree.selection_set("nav-simulation")
    app.analysis_tree.focus("nav-simulation")
    app._on_navigator_selected()
    app.root.update_idletasks()

    assert app.notebook.select() == str(app.simulation_workspace)
    assert app.workspace_status_var.get() == "Workspace: Simulation"
    assert app.simulation_workspace.analysis_var.get() != "No active analysis"


def test_canonical_demo_run_populates_simulation_summary(app):
    run = app.smoke_run_active()
    app.root.update_idletasks()

    assert app.simulation_workspace.state_var.get() == str(run.status).upper()
    assert app.simulation_workspace.result_var.get()
    assert int(app.simulation_workspace.result_fields_var.get()) >= 1
    assert app.simulation_workspace.verification_var.get() == (
        "Separate verification workspace"
    )
