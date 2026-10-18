"""Design Studio data contracts and real Tk selection/card synchronization."""
from __future__ import annotations

import os
import tkinter as tk

import pytest

from cleanroomx.gui_design_studio import design_studio_snapshot


def _reference_layout():
    return {
        "rooms": [
            {"id": "p", "name": "Process", "x_m": 0, "y_m": 0,
             "length_m": 6, "width_m": 5, "height_m": 3, "pressure_pa": 15},
            {"id": "q", "name": "Preparation", "x_m": 6, "y_m": 0,
             "length_m": 5, "width_m": 4, "height_m": 3},
            {"id": "a", "name": "Ante / Airlock", "x_m": 11, "y_m": 0,
             "length_m": 4, "width_m": 3, "height_m": 3},
        ],
        "devices": (
            [{"type": "ffu", "room_id": "p"}] * 3
            + [{"type": "supply", "room_id": "q"}] * 2
            + [{"type": "return", "room_id": "p"},
               {"type": "exhaust", "room_id": "q"}]
            + [{"type": "door", "room_id": "a"}] * 3
        ),
    }


def test_reference_demo_geometry_is_derived_not_hardcoded():
    result = design_studio_snapshot(_reference_layout(), selected_room_id="p")
    assert (
        result["room_count"],
        result["floor_area_m2"],
        result["volume_m3"],
        result["placed_device_count"],
    ) == (3, 62, 186, 10)
    assert result["selected_room"]["configured_pressure_pa"] == 15
    assert result["selected_room"]["device_count"] == 4
    assert result["device_categories"] == {
        "FFU": 3, "Supply": 2, "Return / exhaust": 2, "Other": 3,
    }


def test_dashboard_snapshot_recomputes_after_changes():
    layout = _reference_layout()
    layout["rooms"][0]["length_m"] = 7
    layout["devices"].append({"type": "opening", "room_id": "p"})
    result = design_studio_snapshot(layout, selected_room_id="p")
    assert result["floor_area_m2"] == 67
    assert result["volume_m3"] == 201
    assert result["placed_device_count"] == 11
    assert result["selected_room"]["device_count"] == 5
    layout["rooms"].clear()
    assert design_studio_snapshot(layout, selected_room_id="p")["selected_room"] is None


def test_invalid_configured_pressure_is_not_displayed_as_solver_output():
    layout = {
        "rooms": [{"id": "p", "length_m": "nan", "width_m": 3,
                   "height_m": 3, "pressure_pa": "nan"}],
        "devices": [],
    }
    result = design_studio_snapshot(layout, selected_room_id="p")
    assert result["volume_m3"] == 0
    assert result["selected_room"]["configured_pressure_pa"] is None


@pytest.fixture
def studio_app(tmp_path):
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path

    callback_errors = []
    root.report_callback_exception = lambda *args: callback_errors.append(args)
    app = CleanroomXApp(
        root,
        autosave_interval_seconds=0,
        ui_state_path=tmp_path / "layout.json",
    )
    app.load_project_path(bundled_demo_project_path())
    app.notebook.select(app.spatial_workspace)
    root.update()
    try:
        yield app
        assert callback_errors == []
    finally:
        root.destroy()


def test_real_studio_cards_selection_navigator_and_isolation(studio_app):
    workspace = studio_app.spatial_workspace
    room = workspace.layout["rooms"][0]
    workspace.redraw()
    expected = design_studio_snapshot(workspace.layout)
    assert workspace._studio_metric_vars["rooms"].get() == str(expected["room_count"])
    assert workspace._studio_metric_vars["devices"].get() == str(expected["placed_device_count"])
    assert workspace._studio_room_canvas.find_withtag(f'studio-room:{room["id"]}')
    assert workspace.select_item("room", room["id"], notify=True)
    assert room["name"] in workspace._studio_selected_text.get()
    assert workspace._studio_focus_button.instate(["!disabled"])
    workspace.isolate_selected()
    assert workspace._isolated_item.item_id == room["id"]
    workspace.show_all()
    assert workspace._isolated_item is None
    workspace.set_workspace_mode("3d")
    assert workspace._workspace_mode.get() == "3d"


def test_studio_live_cards_follow_geometry_mutation(studio_app):
    workspace = studio_app.spatial_workspace
    baseline = design_studio_snapshot(workspace.layout)
    room = workspace.layout["rooms"][0]
    room["length_m"] += 1
    workspace.redraw()
    updated = design_studio_snapshot(workspace.layout)
    assert updated["floor_area_m2"] > baseline["floor_area_m2"]
    assert workspace._studio_metric_vars["floor_area"].get() == (
        f'{updated["floor_area_m2"]:,.1f} m²'
    )
