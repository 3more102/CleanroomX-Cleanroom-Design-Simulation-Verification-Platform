import json
import os
from pathlib import Path
import tkinter as tk
import time

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
    instance = CleanroomXApp(root, autosave_interval_seconds=0, ui_state_path=tmp_path / "ui.json")
    instance.load_project_path(bundled_demo_project_path())
    root.update()
    yield instance
    instance._autosave_manager.shutdown(wait=False)
    root.destroy()


def test_studio_room_prepares_real_case_inputs_and_top_run_routes_to_solver(app, tmp_path, monkeypatch):
    app.open_design_studio()
    app.spatial_workspace.select_item("device", "supply-process", notify=True)
    app.open_room_solver()
    workspace = app.openfoam_workspace
    assert workspace.supply_var.get() == "2700"
    assert "6 × 5 × 3" in workspace.room_info_var.get()
    commands = []
    monkeypatch.setattr(workspace, "_start_command", lambda label, command: commands.append(command))
    workspace.runtime_mode_var.set("native")
    workspace.bashrc_var.set("")
    workspace.runs_folder_var.set(str(tmp_path / "runs"))
    workspace.mesh_var.set("6 6 6")
    app.run_current()
    assert len(commands) == 1 and commands[0][3] == "run"
    root = Path(workspace.case_directory_var.get()).parent
    spec = json.loads((root / "specification.json").read_text())
    assert spec["supply_flow_m3_s"] == .75
    assert spec["room_m"] == [6, 5, 3]
    assert "--sync-results" in commands[0]
    assert (root / "project-input.json").is_file()
    assert workspace.verify_native_fields_var.get()



def test_changed_room_geometry_requires_review_before_run(app, tmp_path, monkeypatch):
    import copy

    app.open_design_studio()
    app.spatial_workspace.select_item("device", "supply-process", notify=True)
    app.open_room_solver()
    workspace = app.openfoam_workspace
    reviewed, room_id = workspace._room_context_getter()
    modified = copy.deepcopy(reviewed)
    modified["project"]["metadata"]["spatial_layout"]["rooms"][0]["length_m"] = 9
    monkeypatch.setattr(workspace, "_room_context_getter", lambda: (modified, room_id))
    commands = []
    monkeypatch.setattr(workspace, "_start_command", lambda label, command: commands.append(command))
    workspace.runtime_mode_var.set("native")
    workspace.bashrc_var.set("")
    workspace.runs_folder_var.set(str(tmp_path / "runs"))
    workspace.mesh_var.set("6 6 6")

    workspace.run_room_study()
    assert commands == []
    assert not (tmp_path / "runs").exists()
    assert "9 × 5 × 3" in workspace.room_info_var.get()
    assert "review" in app.status_var.get().lower()

    workspace.run_room_study()
    assert len(commands) == 1
    spec = json.loads((Path(workspace.case_directory_var.get()).parent / "specification.json").read_text())
    assert spec["room_m"] == [9, 5, 3]


def test_changed_auto_supply_clears_outdated_value_before_run(app, tmp_path, monkeypatch):
    import copy

    app.open_design_studio()
    app.spatial_workspace.select_item("device", "supply-process", notify=True)
    app.open_room_solver()
    workspace = app.openfoam_workspace
    assert workspace.supply_var.get() == "2700"
    reviewed, room_id = workspace._room_context_getter()
    modified = copy.deepcopy(reviewed)
    modified["analyses"][0]["input"]["rooms"][0]["supply_airflow_m3_h"] = 3000
    monkeypatch.setattr(workspace, "_room_context_getter", lambda: (modified, room_id))
    commands = []
    monkeypatch.setattr(workspace, "_start_command", lambda label, command: commands.append(command))
    workspace.runtime_mode_var.set("native")
    workspace.bashrc_var.set("")
    workspace.runs_folder_var.set(str(tmp_path / "runs"))
    workspace.mesh_var.set("6 6 6")

    workspace.run_room_study()
    assert commands == []
    assert not (tmp_path / "runs").exists()
    assert workspace.supply_var.get() == "3000"
    assert "review" in app.status_var.get().lower()

    workspace.run_room_study()
    assert len(commands) == 1
    spec = json.loads((Path(workspace.case_directory_var.get()).parent / "specification.json").read_text())
    assert spec["supply_flow_m3_s"] == pytest.approx(3000 / 3600)


def test_failed_child_process_sets_failure_and_unlocks_controls(app):
    import sys
    workspace = app.openfoam_workspace
    workspace._start_command("Failing process", [sys.executable, "-c", "raise SystemExit(7)"])
    deadline = time.monotonic() + 10
    while workspace._busy and time.monotonic() < deadline:
        app.root.update()
        time.sleep(.01)
    assert not workspace._busy
    assert "Failed (exit 7)" in workspace.progress_var.get()
    assert "disabled" not in workspace.runtime_button.state()


def test_stop_terminates_a_real_background_process_and_unlocks_the_desktop(app):
    import sys
    workspace = app.openfoam_workspace
    workspace._start_command("Long running process", [sys.executable, "-c", "import time; time.sleep(60)"])
    process = workspace._process
    assert process is not None and workspace._busy
    assert app.cancel_button.cget("text") == "Stop"
    app.cancel_run()
    deadline = time.monotonic() + 10
    while workspace._busy and time.monotonic() < deadline:
        app.root.update()
        time.sleep(.01)
    assert process.poll() is not None
    assert not workspace._busy
    assert "Stopped" in workspace.progress_var.get()
    assert app.cancel_button.cget("text") == "Abandon"
    assert "disabled" not in app.run_button.state()
