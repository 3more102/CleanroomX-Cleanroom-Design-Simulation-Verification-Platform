from __future__ import annotations

import copy
import os
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.spatial import engineering_overlay_state, normalize_layout


def _layout() -> dict:
    return normalize_layout(
        {
            "rooms": [
                {
                    "id": "room-a",
                    "name": "Room A",
                    "analysis_room_name": "Room A",
                    "x_m": 0.0,
                    "y_m": 0.0,
                    "length_m": 5.0,
                    "width_m": 4.0,
                    "height_m": 3.0,
                    "pressure_pa": 15.0,
                },
                {
                    "id": "room-b",
                    "name": "Room B",
                    "analysis_room_name": "Room B",
                    "x_m": 5.0,
                    "y_m": 0.0,
                    "length_m": 4.0,
                    "width_m": 4.0,
                    "height_m": 3.0,
                    "pressure_pa": 5.0,
                },
            ]
        }
    )


def test_ach_overlay_projects_canonical_verification_results_without_mutation():
    layout = _layout()
    result = {
        "rooms": [
            {
                "room": "Room A",
                "ach": 34.2,
                "status": "pass",
                "findings": [
                    {"code": "ACH", "status": "pass", "actual": 34.2, "unit": "1/h"}
                ],
            },
            {
                "room": "Room B",
                "ach": 18.5,
                "status": "fail",
                "findings": [
                    {"code": "ACH", "status": "fail", "actual": 18.5, "unit": "1/h"}
                ],
            },
        ]
    }
    before_layout = copy.deepcopy(layout)
    before_result = copy.deepcopy(result)

    overlay = engineering_overlay_state(layout, result=result, mode="ach")

    assert layout == before_layout
    assert result == before_result
    assert overlay["minimum"] == 18.5
    assert overlay["maximum"] == 34.2
    by_room = {item["room_id"]: item for item in overlay["rooms"]}
    assert by_room["room-a"]["value"] == 34.2
    assert by_room["room-a"]["status"] == "pass"
    assert "ACH: 34.20" in by_room["room-a"]["label"]
    assert by_room["room-b"]["status"] == "fail"


def test_airflow_overlay_uses_existing_hvac_air_balance_values_and_status():
    layout = _layout()
    result = {
        "rooms": [
            {
                "name": "Room A",
                "governing_airflow_m3_h": 1500.0,
                "air_balance": {
                    "supply_airflow_m3_h": 1500.0,
                    "return_airflow_m3_h": 1200.0,
                    "exhaust_airflow_m3_h": 100.0,
                    "passes_minimum_surplus": True,
                },
            },
            {
                "name": "Room B",
                "governing_airflow_m3_h": 900.0,
                "air_balance": {
                    "supply_airflow_m3_h": 900.0,
                    "return_airflow_m3_h": 950.0,
                    "exhaust_airflow_m3_h": 50.0,
                    "passes_minimum_surplus": False,
                },
            },
        ]
    }

    overlay = engineering_overlay_state(layout, result=result, mode="airflow")
    by_room = {item["room_id"]: item for item in overlay["rooms"]}

    assert by_room["room-a"]["details"] == {
        "supply_m3_h": 1500.0,
        "return_m3_h": 1200.0,
        "exhaust_m3_h": 100.0,
    }
    assert by_room["room-a"]["status"] == "pass"
    assert by_room["room-b"]["status"] == "fail"
    assert overlay["minimum"] == 900.0
    assert overlay["maximum"] == 1500.0


def test_status_overlay_uses_result_status_and_never_derives_new_verdicts():
    layout = _layout()
    result = {
        "rooms": [
            {"room": "Room A", "status": "pass", "findings": []},
            {"room": "Room B", "status": "fail", "findings": []},
        ]
    }

    overlay = engineering_overlay_state(layout, result=result, mode="status")
    by_room = {item["room_id"]: item for item in overlay["rooms"]}

    assert by_room["room-a"]["status"] == "pass"
    assert by_room["room-a"]["fill"] == "#dcfce7"
    assert by_room["room-b"]["status"] == "fail"
    assert by_room["room-b"]["fill"] == "#fee2e2"


def test_none_overlay_has_neutral_fill_and_pressure_overlay_preserves_spatial_evidence():
    layout = _layout()

    none_overlay = engineering_overlay_state(layout, result={}, mode="none")
    assert all(item["fill"] == "#dfe7ef" for item in none_overlay["rooms"])

    pressure = engineering_overlay_state(layout, result={}, mode="pressure")
    by_room = {item["room_id"]: item for item in pressure["rooms"]}
    assert by_room["room-a"]["pressure_pa"] == 15.0
    assert by_room["room-b"]["pressure_pa"] == 5.0
    assert pressure["minimum"] == 5.0
    assert pressure["maximum"] == 15.0


@pytest.fixture
def gui_app():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    callback_errors = []
    root.report_callback_exception = lambda *args: callback_errors.append(args)
    application = CleanroomXApp(root, autosave_interval_seconds=0)
    application.load_project_path(bundled_demo_project_path())
    root.update()
    try:
        yield application
        assert callback_errors == []
    finally:
        root.destroy()


def test_overlay_selector_renders_fresh_ach_values_in_2d_and_3d_split(gui_app):
    workspace = gui_app.spatial_workspace
    workspace.set_workspace_mode("split")
    rooms = workspace.layout["rooms"]
    assert rooms

    result_rooms = [
        {
            "room": str(room.get("analysis_room_name") or room["name"]),
            "ach": 24.0 + index,
            "status": "pass",
            "findings": [
                {
                    "code": "ACH",
                    "status": "pass",
                    "actual": 24.0 + index,
                    "unit": "1/h",
                }
            ],
        }
        for index, room in enumerate(rooms)
    ]
    workspace._result_getter = lambda: {"rooms": result_rooms}
    workspace._set_overlay_mode("ACH")
    workspace.redraw()
    gui_app.root.update()

    assert workspace.layout["view"]["overlay_mode"] == "ach"
    assert workspace.canvas_2d.find_withtag("overlay_legend")
    assert workspace.canvas_3d.find_withtag("overlay_legend")

    first_tag = f"room:{rooms[0]['id']}"
    texts_2d = [
        workspace.canvas_2d.itemcget(item, "text")
        for item in workspace.canvas_2d.find_withtag(first_tag)
        if workspace.canvas_2d.type(item) == "text"
    ]
    texts_3d = [
        workspace.canvas_3d.itemcget(item, "text")
        for item in workspace.canvas_3d.find_withtag(first_tag)
        if workspace.canvas_3d.type(item) == "text"
    ]
    assert any("ACH: 24.00" in text for text in texts_2d)
    assert any("ACH: 24.00" in text for text in texts_3d)


def test_overlay_mode_normalization_preserves_backward_pressure_setting():
    legacy = {
        "view": {"show_pressure": False},
        "rooms": [],
        "devices": [],
        "relationships": [],
    }

    normalized = normalize_layout(legacy)

    assert normalized["view"]["overlay_mode"] == "none"
    assert normalized["view"]["show_pressure"] is False
