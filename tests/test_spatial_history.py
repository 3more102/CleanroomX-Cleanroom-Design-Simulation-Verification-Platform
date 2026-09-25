from __future__ import annotations

import pytest

from cleanroomx.project import ProjectDocument
from cleanroomx.spatial import (
    SpatialDesignWorkspace,
    _Hit,
    _drag_target_coordinate,
    empty_layout,
    normalize_layout,
)


def _workspace_project() -> ProjectDocument:
    project = ProjectDocument(name="History integration")
    layout = normalize_layout(
        {
            **empty_layout(),
            "rooms": [
                {
                    "id": "room-a",
                    "name": "Room A",
                    "x_m": 2.0,
                    "y_m": 0.0,
                    "length_m": 4.0,
                    "width_m": 4.0,
                    "height_m": 3.0,
                }
            ],
        }
    )
    project.metadata["spatial_layout"] = layout
    return project


def _workspace(project: ProjectDocument) -> SpatialDesignWorkspace:
    workspace = object.__new__(SpatialDesignWorkspace)
    workspace.layout = project.metadata["spatial_layout"]
    workspace.selected = _Hit("room", "room-a")
    workspace._project_getter = lambda: project
    workspace._on_change = lambda: None
    workspace._status_setter = lambda value: None
    workspace._load_property_panel = lambda: None
    workspace._update_history_controls = lambda: None
    workspace.redraw = lambda: None
    workspace._on_history_record = None
    workspace._on_undo_requested = None
    workspace._on_redo_requested = None
    workspace._drag_anchor = None
    workspace._drag_item_origin = None
    workspace._drag_history_before = None
    workspace._resize_room_id = None
    return workspace


def test_spatial_workspace_delegates_design_mutation_to_global_history():
    project = _workspace_project()
    workspace = _workspace(project)
    captured = []
    changes = []
    statuses = []
    workspace._on_history_record = lambda *args: captured.append(args) or True
    workspace._on_change = lambda: changes.append("changed")
    workspace._status_setter = statuses.append

    before = workspace._history_layout()
    workspace.layout["rooms"][0]["x_m"] = 5.0
    workspace._persist(
        "Spatial item moved",
        history_before=before,
        selection_before=("room", "room-a"),
    )

    assert not hasattr(workspace, "_history")
    assert project.metadata["spatial_layout"]["rooms"][0]["x_m"] == 5.0
    assert len(captured) == 1
    before_layout, before_selection, after_layout, after_selection, description = captured[0]
    assert before_layout["rooms"][0]["x_m"] == 2.0
    assert before_selection == ("room", "room-a")
    assert after_layout["rooms"][0]["x_m"] == 5.0
    assert after_selection == ("room", "room-a")
    assert description == "Spatial item moved"
    assert changes == ["changed"]
    assert statuses[-1] == "Spatial item moved"


def test_spatial_toolbar_undo_redo_use_application_wide_callbacks():
    project = _workspace_project()
    workspace = _workspace(project)
    calls = []
    workspace._on_undo_requested = lambda: calls.append("undo") or True
    workspace._on_redo_requested = lambda: calls.append("redo") or True

    assert workspace.undo_edit() is True
    assert workspace.redo_edit() is True
    assert calls == ["undo", "redo"]


def test_history_selection_restore_is_view_neutral_and_validates_target():
    project = _workspace_project()
    workspace = _workspace(project)
    workspace.layout["view"]["azimuth_deg"] = 123.0

    workspace.restore_history_selection(("room", "room-a"))
    assert workspace.selected == _Hit("room", "room-a")
    assert workspace.layout["view"]["azimuth_deg"] == 123.0

    workspace.restore_history_selection(("device", "missing-device"))
    assert workspace.selected is None
    assert workspace.layout["view"]["azimuth_deg"] == 123.0



class _Flag:
    def __init__(self, value: bool):
        self.value = value

    def get(self) -> bool:
        return self.value


class _Event:
    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y


def test_room_drag_uses_snap_and_translates_assigned_devices():
    project = _workspace_project()
    workspace = _workspace(project)
    workspace.layout["devices"].append(
        {
            "id": "device-a",
            "type": "sensor",
            "name": "Sensor",
            "room_id": "room-a",
            "x_m": 3.0,
            "y_m": 1.0,
            "z_m": 1.0,
        }
    )
    workspace._snap_to_grid = _Flag(True)
    workspace._resize_room_id = None
    workspace._drag_anchor = (2.0, 0.0)
    workspace._drag_item_origin = (2.0, 0.0)
    workspace._canvas_to_world = lambda x, y: (float(x), float(y))

    workspace._on_left_drag(_Event(2.6, 0.6))

    room = workspace.layout["rooms"][0]
    device = workspace.layout["devices"][0]
    assert (room["x_m"], room["y_m"]) == (2.5, 0.5)
    assert (device["x_m"], device["y_m"]) == (3.5, 1.5)


def test_drag_target_coordinate_uses_gesture_origin_and_validates_grid():
    assert _drag_target_coordinate(
        item_origin=2.0,
        pointer_origin=2.0,
        pointer_current=2.76,
        grid_m=0.5,
        snap_to_grid=True,
    ) == 3.0
    assert _drag_target_coordinate(
        item_origin=2.0,
        pointer_origin=2.0,
        pointer_current=2.76,
        grid_m=0.5,
        snap_to_grid=False,
    ) == pytest.approx(2.76)

    with pytest.raises(ValueError, match="positive"):
        _drag_target_coordinate(
            item_origin=2.0,
            pointer_origin=2.0,
            pointer_current=2.76,
            grid_m=0.0,
            snap_to_grid=True,
        )


def _drag_result(samples: list[tuple[float, float]]) -> tuple[float, float]:
    project = _workspace_project()
    workspace = _workspace(project)
    workspace._snap_to_grid = _Flag(True)
    workspace._drag_anchor = (2.0, 0.0)
    workspace._drag_item_origin = (2.0, 0.0)
    workspace._canvas_to_world = lambda x, y: (float(x), float(y))

    for x, y in samples:
        workspace._on_left_drag(_Event(x, y))

    room = workspace.layout["rooms"][0]
    return room["x_m"], room["y_m"]


def test_room_drag_final_geometry_is_independent_of_motion_event_count():
    single_event = _drag_result([(2.76, 0.76)])
    many_events = _drag_result(
        [
            (2.11, 0.11),
            (2.24, 0.24),
            (2.49, 0.49),
            (2.63, 0.63),
            (2.76, 0.76),
        ]
    )

    assert single_event == (3.0, 1.0)
    assert many_events == single_event


def test_noop_drag_release_does_not_dirty_project_or_record_history():
    project = _workspace_project()
    workspace = _workspace(project)
    changes: list[str] = []
    statuses: list[str] = []
    history_records: list[tuple] = []
    workspace._on_change = lambda: changes.append("changed")
    workspace._status_setter = statuses.append
    workspace._on_history_record = lambda *args: history_records.append(args) or True
    workspace._drag_anchor = (2.0, 0.0)
    workspace._drag_item_origin = (2.0, 0.0)
    workspace._drag_history_before = (
        workspace._history_layout(),
        workspace._selection_state(),
    )

    workspace._on_left_up(_Event(2.0, 0.0))

    assert changes == []
    assert history_records == []
    assert statuses[-1] == "Spatial edit unchanged"
    assert workspace._drag_anchor is None
    assert workspace._drag_item_origin is None
    assert workspace._drag_history_before is None


def test_drag_release_records_one_history_transaction():
    project = _workspace_project()
    workspace = _workspace(project)
    changes: list[str] = []
    history_records: list[tuple] = []
    workspace._on_change = lambda: changes.append("changed")
    workspace._on_history_record = lambda *args: history_records.append(args) or True
    workspace._snap_to_grid = _Flag(True)
    workspace._drag_anchor = (2.0, 0.0)
    workspace._drag_item_origin = (2.0, 0.0)
    workspace._drag_history_before = (
        workspace._history_layout(),
        workspace._selection_state(),
    )
    workspace._canvas_to_world = lambda x, y: (float(x), float(y))

    for point in ((2.24, 0.0), (2.63, 0.0), (2.76, 0.0)):
        workspace._on_left_drag(_Event(*point))
    workspace._on_left_up(_Event(2.76, 0.0))

    assert project.metadata["spatial_layout"]["rooms"][0]["x_m"] == 3.0
    assert changes == ["changed"]
    assert len(history_records) == 1
    assert history_records[0][-1] == "Spatial item moved"


def test_room_resize_handle_obeys_grid_snap():
    project = _workspace_project()
    workspace = _workspace(project)
    workspace._snap_to_grid = _Flag(True)
    workspace._resize_room_id = "room-a"
    workspace._drag_anchor = (6.0, 4.0)
    workspace._canvas_to_world = lambda x, y: (float(x), float(y))

    workspace._on_left_drag(_Event(7.4, 5.4))

    room = workspace.layout["rooms"][0]
    assert room["length_m"] == 5.5
    assert room["width_m"] == 5.5


def test_keyboard_nudge_moves_room_and_assigned_devices_one_grid_step():
    project = _workspace_project()
    workspace = _workspace(project)
    workspace.layout["devices"].append(
        {
            "id": "device-a",
            "type": "sensor",
            "name": "Sensor",
            "room_id": "room-a",
            "x_m": 3.0,
            "y_m": 1.0,
            "z_m": 1.0,
        }
    )
    workspace._snap_to_grid = _Flag(True)

    assert workspace._nudge_selected(1, 0) == "break"

    room = workspace.layout["rooms"][0]
    device = workspace.layout["devices"][0]
    assert room["x_m"] == 2.5
    assert device["x_m"] == 3.5
