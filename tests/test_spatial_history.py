from __future__ import annotations

import copy
from types import SimpleNamespace

from cleanroomx.project import ProjectDocument
from cleanroomx.spatial import (
    SpatialDesignWorkspace,
    _Hit,
    _drag_target_coordinate,
    empty_layout,
    normalize_layout,
)
from cleanroomx.spatial_history import SpatialEditHistory


def _design(x_m: float) -> dict:
    layout = empty_layout()
    layout["rooms"] = [
        {
            "id": "room-a",
            "name": "Room A",
            "x_m": x_m,
            "y_m": 0.0,
            "length_m": 4.0,
            "width_m": 4.0,
            "height_m": 3.0,
        }
    ]
    layout.pop("view")
    return layout


def test_spatial_history_round_trip_is_bounded_and_snapshot_isolated():
    history = SpatialEditHistory(limit=2)
    before = _design(0.0)
    after = _design(1.0)

    assert history.record(
        before_layout=before,
        before_selection=("room", "room-a"),
        after_layout=after,
        after_selection=("room", "room-a"),
        description="Move room",
    )

    before["rooms"][0]["x_m"] = 99.0
    after["rooms"][0]["x_m"] = 88.0

    restored, description = history.undo()
    assert description == "Move room"
    assert restored.layout["rooms"][0]["x_m"] == 0.0
    restored.layout["rooms"][0]["x_m"] = 77.0

    replayed, description = history.redo()
    assert description == "Move room"
    assert replayed.layout["rooms"][0]["x_m"] == 1.0
    assert replayed.selection == ("room", "room-a")

    assert history.undo() is not None
    assert history.record(
        before_layout=_design(0.0),
        before_selection=None,
        after_layout=_design(2.0),
        after_selection=("room", "room-a"),
        description="Move again",
    )
    assert history.can_redo is False

    assert history.record(
        before_layout=_design(2.0),
        before_selection=("room", "room-a"),
        after_layout=_design(3.0),
        after_selection=("room", "room-a"),
        description="Move third",
    )
    assert history.record(
        before_layout=_design(3.0),
        before_selection=("room", "room-a"),
        after_layout=_design(4.0),
        after_selection=("room", "room-a"),
        description="Move fourth",
    )
    assert history.undo_description == "Move fourth"
    assert history.undo() is not None
    oldest_retained, _ = history.undo()
    assert oldest_retained.layout["rooms"][0]["x_m"] == 2.0
    assert history.undo() is None


def test_spatial_history_ignores_selection_only_noop():
    history = SpatialEditHistory()
    layout = _design(0.0)
    assert history.record(
        before_layout=layout,
        before_selection=None,
        after_layout=copy.deepcopy(layout),
        after_selection=("room", "room-a"),
        description="Select room",
    ) is False
    assert history.can_undo is False
    assert history.can_redo is False


def test_workspace_undo_redo_restores_model_and_selection_without_rewinding_view():
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

    workspace = object.__new__(SpatialDesignWorkspace)
    workspace.layout = project.metadata["spatial_layout"]
    workspace.selected = _Hit("room", "room-a")
    workspace._history = SpatialEditHistory()
    workspace._project_getter = lambda: project
    changes: list[str] = []
    statuses: list[str] = []
    workspace._on_change = lambda: changes.append("changed")
    workspace._status_setter = statuses.append
    workspace._load_property_panel = lambda: None
    workspace._update_history_controls = lambda: None
    workspace.redraw = lambda: None

    before = workspace._history_layout()
    workspace.layout["rooms"][0]["x_m"] = 5.0
    workspace._persist(
        "Spatial item moved",
        history_before=before,
        selection_before=("room", "room-a"),
    )
    workspace.layout["view"]["azimuth_deg"] = 123.0

    assert workspace.undo_edit() is True
    assert project.metadata["spatial_layout"]["rooms"][0]["x_m"] == 2.0
    assert workspace.selected == _Hit("room", "room-a")
    assert workspace.layout["view"]["azimuth_deg"] == 123.0
    assert statuses[-1] == "Undo: Spatial item moved"

    assert workspace.redo_edit() is True
    assert project.metadata["spatial_layout"]["rooms"][0]["x_m"] == 5.0
    assert workspace.layout["view"]["azimuth_deg"] == 123.0
    assert statuses[-1] == "Redo: Spatial item moved"
    assert len(changes) == 3



def _drag_workspace() -> tuple[SpatialDesignWorkspace, ProjectDocument]:
    project = ProjectDocument(name="Drag integration")
    layout = normalize_layout(
        {
            **empty_layout(),
            "grid_m": 1.0,
            "rooms": [
                {
                    "id": "room-a",
                    "name": "Room A",
                    "x_m": 0.0,
                    "y_m": 0.0,
                    "length_m": 4.0,
                    "width_m": 4.0,
                    "height_m": 3.0,
                }
            ],
        }
    )
    project.metadata["spatial_layout"] = layout

    workspace = object.__new__(SpatialDesignWorkspace)
    workspace.layout = project.metadata["spatial_layout"]
    workspace.selected = _Hit("room", "room-a")
    workspace._history = SpatialEditHistory()
    workspace._project_getter = lambda: project
    workspace._on_change = lambda: None
    workspace._status_setter = lambda message: None
    workspace._load_property_panel = lambda: None
    workspace._update_history_controls = lambda: None
    workspace.redraw = lambda: None
    workspace._canvas_to_world = lambda x, y: (float(x), float(y))
    workspace._drag_anchor = (0.0, 0.0)
    workspace._drag_item_origin = (0.0, 0.0)
    workspace._drag_history_before = (
        workspace._history_layout(),
        workspace._selection_state(),
    )
    return workspace, project


def test_drag_target_coordinate_is_event_rate_independent_and_validates_grid():
    one_event = _drag_target_coordinate(
        item_origin=0.0,
        pointer_origin=0.0,
        pointer_current=0.76,
        grid_m=0.5,
    )
    many_events = [
        _drag_target_coordinate(
            item_origin=0.0,
            pointer_origin=0.0,
            pointer_current=current,
            grid_m=0.5,
        )
        for current in (0.11, 0.24, 0.49, 0.63, 0.76)
    ]

    assert one_event == 1.0
    assert many_events[-1] == one_event

    import pytest

    with pytest.raises(ValueError, match="positive"):
        _drag_target_coordinate(
            item_origin=0.0,
            pointer_origin=0.0,
            pointer_current=1.0,
            grid_m=0.0,
        )


def test_workspace_drag_final_geometry_does_not_depend_on_motion_event_count():
    single, _ = _drag_workspace()
    single._on_left_drag(SimpleNamespace(x=0.76, y=1.24))
    single_position = (
        single.layout["rooms"][0]["x_m"],
        single.layout["rooms"][0]["y_m"],
    )

    sampled, _ = _drag_workspace()
    for x, y in ((0.11, 0.18), (0.24, 0.42), (0.49, 0.74), (0.63, 1.01), (0.76, 1.24)):
        sampled._on_left_drag(SimpleNamespace(x=x, y=y))
    sampled_position = (
        sampled.layout["rooms"][0]["x_m"],
        sampled.layout["rooms"][0]["y_m"],
    )

    assert single_position == (1.0, 1.0)
    assert sampled_position == single_position


def test_workspace_noop_drag_release_does_not_commit_or_mark_project_changed():
    workspace, project = _drag_workspace()
    changes: list[str] = []
    statuses: list[str] = []
    workspace._on_change = lambda: changes.append("changed")
    workspace._status_setter = statuses.append
    before = copy.deepcopy(project.metadata["spatial_layout"])

    workspace._on_left_up(SimpleNamespace(x=0, y=0))

    assert project.metadata["spatial_layout"] == before
    assert changes == []
    assert statuses[-1] == "Spatial edit unchanged"
    assert workspace._history.can_undo is False
    assert workspace._drag_anchor is None
    assert workspace._drag_item_origin is None
    assert workspace._drag_history_before is None


def test_workspace_drag_release_commits_once_and_is_undoable():
    workspace, project = _drag_workspace()
    changes: list[str] = []
    workspace._on_change = lambda: changes.append("changed")

    workspace._on_left_drag(SimpleNamespace(x=1.2, y=0.0))
    workspace._on_left_up(SimpleNamespace(x=1.2, y=0.0))

    assert project.metadata["spatial_layout"]["rooms"][0]["x_m"] == 1.0
    assert changes == ["changed"]
    assert workspace._history.can_undo is True

    state, description = workspace._history.undo()
    assert description == "Spatial item moved"
    assert state.layout["rooms"][0]["x_m"] == 0.0
