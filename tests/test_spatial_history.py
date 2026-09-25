from __future__ import annotations

from cleanroomx.project import ProjectDocument
from cleanroomx.spatial import SpatialDesignWorkspace, _Hit, empty_layout, normalize_layout


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
    workspace._canvas_to_world = lambda x, y: (float(x), float(y))

    workspace._on_left_drag(_Event(2.6, 0.6))

    room = workspace.layout["rooms"][0]
    device = workspace.layout["devices"][0]
    assert (room["x_m"], room["y_m"]) == (2.5, 0.5)
    assert (device["x_m"], device["y_m"]) == (3.5, 1.5)


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
