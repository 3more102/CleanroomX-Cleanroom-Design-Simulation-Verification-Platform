"""Reference demo model metrics and interactive Design Studio regression tests.

Run GUI tests on a real Tk display or under xvfb-run; a missing display is a skip,
not evidence of visual/interaction parity.
"""
from __future__ import annotations

from types import SimpleNamespace
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.project import load_project_document
from cleanroomx.spatial import _Hit, layout_metrics


def test_demo_geometry_and_device_count_are_derived_from_model():
    document = load_project_document(bundled_demo_project_path())
    layout = document.metadata["spatial_layout"]
    metrics = layout_metrics(layout)

    assert metrics["room_count"] == 3
    assert metrics["total_floor_area_m2"] == pytest.approx(62.0)
    assert metrics["total_volume_m3"] == pytest.approx(186.0)
    assert sum(metrics["device_counts"].values()) == 10


@pytest.fixture
def studio(tmp_path):
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        import os

        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")

    callback_errors = []
    root.report_callback_exception = lambda *args: callback_errors.append(args)
    app = CleanroomXApp(
        root,
        autosave_interval_seconds=0,
        ui_state_path=tmp_path / "gui-layout.json",
    )
    app.load_project_path(bundled_demo_project_path())
    app.notebook.select(app.spatial_workspace)
    root.geometry("1600x900")
    root.update()
    try:
        yield app
        assert callback_errors == []
    finally:
        root.destroy()


def test_live_reference_cards_and_device_categories(studio):
    work = studio.spatial_workspace
    assert work._studio_summary_vars["rooms"].get() == "3"
    assert work._studio_summary_vars["area"].get() == "62.0 m²"
    assert work._studio_summary_vars["volume"].get() == "186.0 m³"
    assert work._studio_summary_vars["devices"].get() == "10"
    assert "FFU: 1" in work._placed_devices_summary_var.get()
    assert "Other / Openings: 5" in work._placed_devices_summary_var.get()


def test_navigator_click_updates_2d_3d_and_inspector(studio):
    work = studio.spatial_workspace
    room = work.layout["rooms"][0]
    tag = f"room:{room['id']}"
    assert work.room_navigator_canvas.find_withtag(tag)
    bounds = work.room_navigator_canvas.bbox(tag)
    assert bounds is not None
    event = SimpleNamespace(
        x=(bounds[0] + bounds[2]) // 2,
        y=(bounds[1] + bounds[3]) // 2,
    )
    work._on_room_navigator_click(event)
    studio.root.update()

    assert work.selected == _Hit("room", room["id"])
    assert work.canvas_2d.find_withtag(tag)
    assert work.canvas_3d.find_withtag(tag)
    assert room["name"] in work._selected_room_summary_var.get()
    assert "Configured pressure:" in work._selected_room_summary_var.get()


def test_real_room_duplicate_updates_cards_and_undo(studio):
    work = studio.spatial_workspace
    room_id = work.layout["rooms"][0]["id"]
    work.select_item("room", room_id)
    before = layout_metrics(work.layout)
    work.duplicate_selected()
    studio.root.update()
    after = layout_metrics(work.layout)

    assert after["room_count"] == before["room_count"] + 1
    assert work._studio_summary_vars["rooms"].get() == str(after["room_count"])
    assert work._studio_summary_vars["area"].get() == (
        f"{after['total_floor_area_m2']:.1f} m²"
    )
    assert work._studio_summary_vars["devices"].get() == str(
        sum(after["device_counts"].values())
    )

    assert studio.undo_project_edit()
    studio.root.update()
    assert work._studio_summary_vars["rooms"].get() == str(before["room_count"])


def test_focus_and_studio_restore_visibility(studio):
    work = studio.spatial_workspace
    work.select_item("room", work.layout["rooms"][0]["id"])
    assert work.focus_selected_room()
    studio.root.update()
    assert work._workspace_mode.get() == "3d"
    assert work._isolated_item is None

    work.isolate_selected()
    assert work._isolated_item is not None
    work.studio_view()
    studio.root.update()
    assert work._isolated_item is None
    assert work.inspector_visible()
    assert work._workspace_mode.get() == "3d"


def test_bundled_demo_enters_dark_integrated_studio_without_project_edits(studio):
    before = studio.project.to_dict()
    studio.activate_reference_demo_studio()
    studio.root.update()

    work = studio.spatial_workspace
    assert studio.theme_var.get() == "dark"
    assert work._workspace_mode.get() == "3d"
    assert not studio.navigator_panel_visible_var.get()
    assert not studio.output_panel_visible_var.get()
    assert not studio._paned_contains(studio.main_panes, studio.navigator_panel)
    assert not studio._paned_contains(studio.workspace_panes, studio.output_panel)
    assert work.inspector_visible()
    assert work.selected == _Hit("room", work.layout["rooms"][0]["id"])
    assert work.layout["rooms"][0]["name"] in work._selected_room_summary_var.get()
    after = studio.project.to_dict()
    # Camera fit is intentionally stored as view presentation metadata.
    # Room and device geometry plus engineering analyses must remain unchanged.
    assert after["project"]["metadata"]["spatial_layout"]["rooms"] == (
        before["project"]["metadata"]["spatial_layout"]["rooms"]
    )
    assert after["project"]["metadata"]["spatial_layout"]["devices"] == (
        before["project"]["metadata"]["spatial_layout"]["devices"]
    )
    assert after["analyses"] == before["analyses"]
