from __future__ import annotations

import os
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path


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
    root.update()
    try:
        yield application
        assert callback_errors == []
    finally:
        root.destroy()


def test_start_center_is_initial_workspace(app):
    assert app.notebook.select() == str(app.start_center)
    assert app.workspace_status_var.get() == "Workspace: Start"
    assert app.start_center.recent_tree.get_children() == ()


def test_loading_project_switches_to_design_and_updates_recent_projects(app):
    path = bundled_demo_project_path()

    app.load_project_path(path)
    app.root.update()

    assert app.notebook.select() == str(app.spatial_workspace)
    assert app.workspace_profile_var.get() == "design"
    assert app.workspace_status_var.get() == "Workspace: Design"
    recent = app.start_center.recent_tree.get_children()
    assert len(recent) == 1
    values = app.start_center.recent_tree.item(recent[0], "values")
    assert values[0] == str(path.resolve(strict=False))


def test_start_center_can_be_reopened_without_mutating_project(app):
    path = bundled_demo_project_path()
    app.load_project_path(path)
    project_before = app.project.to_dict()

    app._activate_start_workspace()
    app.root.update()

    assert app.notebook.select() == str(app.start_center)
    assert app.workspace_status_var.get() == "Workspace: Start"
    assert app.project.to_dict() == project_before


def test_recent_project_list_is_deduplicated(app):
    path = bundled_demo_project_path()

    app._remember_recent_project(path)
    app._remember_recent_project(path)
    app.root.update()

    recent = app.start_center.recent_tree.get_children()
    assert len(recent) == 1



def test_start_center_recent_search_and_remove_only_updates_recent_state(app, tmp_path):
    alpha = tmp_path / "Alpha.cleanroomx.json"
    beta = tmp_path / "Beta.cleanroomx.json"
    alpha.write_text("{}\n", encoding="utf-8")
    beta.write_text("{}\n", encoding="utf-8")

    app._remember_recent_project(alpha)
    app._remember_recent_project(beta)
    app.root.update()

    assert app.start_center.recent_count_var.get() == "2 of 2 recent projects"

    app.start_center.recent_search_var.set("alpha")
    app.root.update()
    visible = app.start_center.recent_tree.get_children()
    assert len(visible) == 1
    assert app.start_center._recent_paths[visible[0]] == str(alpha.resolve(strict=False))

    app.start_center.recent_tree.selection_set(visible[0])
    app.start_center.recent_tree.focus(visible[0])
    app.start_center._forget_selected_recent()
    app.root.update()

    assert alpha.is_file()
    assert beta.is_file()
    assert alpha.resolve(strict=False) not in app._recent_project_paths
    assert beta.resolve(strict=False) in app._recent_project_paths
    assert app.start_center.recent_count_var.get() == "0 of 1 recent projects"
    assert "match the search" in app.start_center.recent_hint.cget("text").lower()

    app.start_center.recent_search_var.set("")
    app.root.update()
    assert len(app.start_center.recent_tree.get_children()) == 1

def test_start_center_project_health_reflects_canonical_project_state(app):
    path = bundled_demo_project_path()
    app.load_project_path(path)
    project_before = app.project.to_dict()

    app._activate_start_workspace()
    app.root.update()

    snapshot = app._start_center_health_snapshot()
    center = app.start_center
    assert center.project_name_var.get() == app.project.name
    assert center.project_path_var.get() == str(path)
    assert center.project_counts_var.get() == (
        f"{len(app.project.analyses)} analyses • "
        f"{snapshot['room_count']} rooms • {snapshot['device_count']} devices"
    )

    diagnostics = app.problems_panel.last_result
    assert diagnostics is not None
    diagnostic_summary = diagnostics["summary"]
    if diagnostic_summary["error_count"]:
        assert f"{diagnostic_summary['error_count']} error" in center.project_diagnostics_var.get()
    elif diagnostic_summary["warning_count"]:
        assert f"{diagnostic_summary['warning_count']} warning" in center.project_diagnostics_var.get()
    else:
        assert center.project_diagnostics_var.get() == "Problems: clear"

    assert center.project_verification_var.get().startswith("Verification:")
    assert center.project_evidence_var.get().startswith("Evidence:")
    assert center.project_recovery_var.get().startswith("Recovery:")
    assert app.project.to_dict() == project_before


def test_start_center_workspace_shortcuts_use_canonical_profiles_without_mutation(app):
    app.load_project_path(bundled_demo_project_path())
    project_before = app.project.to_dict()

    expectations = (
        ("design", app.spatial_workspace),
        ("simulation", app.simulation_workspace),
        ("verification", app.spatial_workspace),
        ("evidence", app.proofgraph_viewer),
        ("reporting", app.reporting_workspace),
    )
    for profile, expected_widget in expectations:
        app.start_center._open_workspace(profile)
        app.root.update()
        assert app.workspace_profile_var.get() == profile
        assert app.notebook.select() == str(expected_widget)

    assert app.project.to_dict() == project_before


def test_start_center_health_semantics_distinguish_error_warning_and_missing_state(app):
    center = app.start_center
    center.set_active_project(
        {
            "name": "Health Test",
            "path": "/tmp/health.cleanroomx.json",
            "dirty": False,
            "analysis_count": 3,
            "room_count": 4,
            "device_count": 5,
            "diagnostics_available": True,
            "error_count": 2,
            "warning_count": 1,
            "verification_available": True,
            "configured_analysis_count": 2,
            "current_count": 1,
            "stale_count": 1,
            "dependency_freshness_unverifiable_count": 0,
            "not_verified_count": 0,
            "evidence_record_count": 2,
            "recovery_count": 1,
            "recovery_issue_count": 0,
        }
    )
    app.root.update()

    assert center.project_state_var.get() == "2 open errors"
    assert center.project_state_label.cget("style") == "CX.Status.Fail.TLabel"
    assert "2 errors" in center.project_diagnostics_var.get()
    assert center.project_diagnostics_label.cget("style") == "CX.Status.Fail.TLabel"
    assert "1 stale" in center.project_verification_var.get()
    assert center.project_verification_label.cget("style") == "CX.Status.Warning.TLabel"
    assert "1 saved candidate" in center.project_recovery_var.get()

    center.set_active_project(
        {
            "name": "No Data",
            "path": "",
            "dirty": False,
            "diagnostics_available": False,
            "verification_available": False,
        }
    )
    app.root.update()
    assert center.project_state_var.get() == "Unsaved project"
    assert center.project_diagnostics_var.get() == "Problems: unavailable"
    assert center.project_verification_var.get() == "Verification: unavailable"

def test_recent_projects_show_active_available_and_missing_state(app, tmp_path):
    active = bundled_demo_project_path()
    available = tmp_path / "Available.cleanroomx.json"
    missing = tmp_path / "Missing.cleanroomx.json"
    available.write_text("{}\n", encoding="utf-8")

    app.load_project_path(active)
    app._remember_recent_project(available)
    app._remember_recent_project(missing)
    app._activate_start_workspace()
    app.root.update()

    rows = {
        app.start_center._recent_paths[iid]: app.start_center.recent_tree.item(
            iid, "values"
        )
        for iid in app.start_center.recent_tree.get_children()
    }
    assert rows[str(active.resolve(strict=False))][1] == "Active"
    assert rows[str(available.resolve(strict=False))][1] == "Available"
    assert rows[str(missing.resolve(strict=False))][1] == "Missing"
    assert rows[str(missing.resolve(strict=False))][2] == "Unavailable"


def test_start_center_primary_controls_fit_supported_minimum_window(app):
    app.root.geometry("1050x680")
    app._activate_start_workspace()
    app.root.update_idletasks()
    app.root.update()

    center = app.start_center
    assert center.winfo_ismapped()
    controls = [
        *center.workspace_buttons.values(),
        center.problems_button,
        center.recovery_button,
        center.recent_search_entry,
        center.remove_recent_button,
    ]
    for control in controls:
        assert control.winfo_ismapped(), control
        assert control.winfo_rootx() >= center.winfo_rootx()
        assert control.winfo_rooty() >= center.winfo_rooty()
        assert (
            control.winfo_rootx() + control.winfo_width()
            <= center.winfo_rootx() + center.winfo_width()
        ), control
        assert (
            control.winfo_rooty() + control.winfo_height()
            <= center.winfo_rooty() + center.winfo_height()
        ), control

def test_start_center_keyboard_focus_tracks_recent_project_state(app):
    app._activate_start_workspace()
    app.root.update_idletasks()
    app.root.update()
    assert app.root.focus_get() == app.start_center.new_project_button

    app.load_project_path(bundled_demo_project_path())
    app._activate_start_workspace()
    app.root.update_idletasks()
    app.root.update()
    assert app.root.focus_get() == app.start_center.recent_search_entry

def test_spatial_focus_from_non_design_workspace_enters_design_profile(app):
    app.load_project_path(bundled_demo_project_path())
    app.activate_workspace_profile("evidence", persist=False)
    app.root.update()
    assert app.workspace_profile_var.get() == "evidence"

    app._activate_spatial_workspace()
    app.root.update()

    assert app.workspace_profile_var.get() == "design"
    assert app.workspace_status_var.get() == "Workspace: Design"
    assert app.notebook.select() == str(app.spatial_workspace)

