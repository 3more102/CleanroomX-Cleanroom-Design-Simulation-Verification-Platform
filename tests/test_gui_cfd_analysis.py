"""Real Tk explorer smoke tests (skip only when a display is unavailable)."""
import time
import tkinter as tk
import shutil

import pytest

from cleanroomx.gui_cfd_analysis import CFDAnalysisExplorer
from cleanroomx.cfd_result_analysis import analyze_synced_results
from cfd_analysis_fixtures import write_sync_store


def _wait(root, condition, seconds=8):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        root.update()
        if condition():
            return
        time.sleep(0.01)
    pytest.fail("Timed out waiting for the real Tk analysis worker")


def test_real_explorer_loads_async_draws_filters_and_shows_missing_data(tmp_path):
    pytest.importorskip("vtk")
    pytest.importorskip("matplotlib")
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    write_sync_store(tmp_path / "store", thermal=False)
    explorer = CFDAnalysisExplorer(root, lambda: analyze_synced_results(tmp_path/"store", "SYNTHETIC-run-a"))
    try:
        _wait(root, lambda: explorer.current_graph is not None and not explorer._busy)
        assert explorer.current_graph["kind"] == "field_history"
        assert len(explorer.figure.axes[0].lines) == 1
        explorer.view_var.set("2D cell slab")
        explorer.case_var.set("configuration_1")
        explorer.position_var.set("0.5")
        explorer.thickness_var.set("0.1")
        explorer.draw_graph()
        _wait(root, lambda: not explorer._busy)
        assert explorer.current_graph["kind"] == "cell_slab"
        assert explorer.current_graph["displayed_cell_count"] == 2
        explorer._pin()
        assert len(explorer.pinned_graphs) == 1
        explorer.view_var.set("Field history (mean and range)")
        explorer.field_var.set("T")
        explorer.draw_graph()
        _wait(root, lambda: not explorer._busy)
        assert explorer.current_graph["status"] == "not_available"
        assert "Not available" in explorer.status_var.get()
        assert "scientific_validation" in explorer.details.get("1.0", "end")
    finally:
        explorer._close()
        root.destroy()


def test_workspace_analysis_actions_use_existing_result_and_receipt_inputs(tmp_path, monkeypatch):
    from cleanroomx.gui_openfoam import OpenFOAMWorkspace
    import cleanroomx.gui_cfd_analysis as module
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk display unavailable: {exc}")
    opened = []
    monkeypatch.setattr(module,"open_analysis_explorer",lambda *args, **kwargs: opened.append((args,kwargs)))
    workspace = OpenFOAMWorkspace(root)
    try:
        workspace.result_directory_var.set(str(tmp_path/"store"))
        workspace.simulation_id_var.set("run-a")
        workspace.two_room_case_directory_var.set(str(tmp_path/"case"))
        workspace.two_room_receipt_directory_var.set(str(tmp_path/"receipt"))
        workspace._analyze_results()
        workspace._analyze_two_room()
        assert len(opened) == 2
        assert workspace.analysis_button in workspace._action_buttons
        assert workspace.two_room_analysis_button in workspace._action_buttons
    finally:
        workspace.destroy()
        root.destroy()


def test_real_explorer_compares_standalone_store_without_renaming_case(tmp_path, monkeypatch):
    pytest.importorskip("vtk")
    pytest.importorskip("matplotlib")
    import cleanroomx.gui_cfd_analysis as module
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    write_sync_store(tmp_path / "store")
    case_id = "Lab West/supply-region"
    native = write_sync_store(tmp_path / "comparison", run="SYNTHETIC-standalone", case_id=case_id)
    standalone = tmp_path / "native-output"
    shutil.move(native, standalone)
    monkeypatch.setattr(module.filedialog, "askdirectory", lambda **kwargs: str(standalone))
    explorer = CFDAnalysisExplorer(root, lambda: analyze_synced_results(tmp_path / "store", "SYNTHETIC-run-a"))
    try:
        _wait(root, lambda: explorer.current_graph is not None and not explorer._busy)
        explorer._add_comparison()
        _wait(root, lambda: len(explorer.sessions) == 2 and not explorer._busy)
        assert case_id in explorer.case_combo["values"]
        assert explorer.sessions[1].report["mode"] == "native_case_sync"
        explorer.view_var.set("Compare cases / runs at selected time")
        explorer.time_var.set("10")
        explorer.draw_graph()
        _wait(root, lambda: not explorer._busy)
        assert explorer.current_graph["kind"] == "comparison"
        assert {s["case_id"] for s in explorer.current_graph["series"]} == {"configuration_1", case_id}
        assert all(p["time_name"] == "10" for s in explorer.current_graph["series"] for p in s["points"])
        assert explorer.current_graph["scientific_validation"] == "BLOCKED"
    finally:
        explorer._close()
        root.destroy()


def test_refresh_rechecks_sources_and_invalidates_stale_figures(tmp_path):
    pytest.importorskip("vtk")
    pytest.importorskip("matplotlib")
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    write_sync_store(tmp_path / "store")
    loaded = []
    def loader():
        loaded.append(True)
        return analyze_synced_results(tmp_path / "store", "SYNTHETIC-run-a")
    explorer = CFDAnalysisExplorer(root, loader)
    try:
        _wait(root, lambda: explorer.current_graph is not None and not explorer._busy)
        explorer._pin()
        assert len(explorer.pinned_graphs) == 1
        explorer.refresh_button.invoke()
        _wait(root, lambda: len(loaded) >= 2 and not explorer._busy)
        assert explorer.current_graph is None
        assert explorer.pinned_graphs == []
        assert len(explorer.sessions) == 1
        assert "reverified" in explorer.status_var.get()
        explorer.draw_graph()
        _wait(root, lambda: explorer.current_graph is not None and not explorer._busy)
    finally:
        explorer._close()
        root.destroy()


def test_3d_orbit_controls_reorient_existing_solver_samples(tmp_path):
    pytest.importorskip("vtk")
    pytest.importorskip("matplotlib")
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    write_sync_store(tmp_path / "store")
    explorer = CFDAnalysisExplorer(root, lambda: analyze_synced_results(tmp_path / "store", "SYNTHETIC-run-a"))
    try:
        _wait(root, lambda: explorer.current_graph is not None and not explorer._busy)
        explorer.view_var.set("3D cell samples")
        explorer.case_var.set("configuration_1")
        explorer.time_var.set("10")
        explorer.draw_graph()
        _wait(root, lambda: not explorer._busy)
        assert explorer.current_graph["kind"] == "cell_3d"
        explorer.azimuth_var.set(35)
        explorer.elevation_var.set(42)
        explorer._rotate_3d()
        assert explorer.figure.axes[0].azim == pytest.approx(35)
        assert explorer.figure.axes[0].elev == pytest.approx(42)
    finally:
        explorer._close()
        root.destroy()


def test_solver_time_navigation_uses_only_recorded_steps(tmp_path, monkeypatch):
    pytest.importorskip("vtk")
    pytest.importorskip("matplotlib")
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    write_sync_store(tmp_path / "store")
    explorer = CFDAnalysisExplorer(root, lambda: analyze_synced_results(tmp_path / "store", "SYNTHETIC-run-a"))
    try:
        _wait(root, lambda: explorer.current_graph is not None and not explorer._busy)
        explorer.time_combo.configure(values=("1", "2.5", "10"))
        explorer.time_var.set("1")
        calls = []
        monkeypatch.setattr(explorer, "draw_graph", lambda: calls.append(explorer.time_var.get()))
        explorer._step_time(1)
        assert explorer.time_var.get() == "2.5"
        explorer._step_time(1)
        assert explorer.time_var.get() == "10"
        explorer._step_time(1)
        assert calls == ["2.5", "10"]
        explorer._step_time(-1)
        assert explorer.time_var.get() == "2.5"
    finally:
        explorer._close()
        root.destroy()
