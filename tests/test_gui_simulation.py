from __future__ import annotations

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


def test_simulation_workspace_distinguishes_calculation_from_verification():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    configure_ttk_theme(root, "dark")
    workspace = SimulationWorkspace(
        root,
        on_run=lambda: None,
        on_cancel=lambda: None,
        on_validate=lambda: None,
        on_open_inputs=lambda: None,
        on_open_results=lambda: None,
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
