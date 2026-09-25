from __future__ import annotations

import copy

from cleanroomx.project import ProjectDocument
from cleanroomx.spatial import SpatialDesignWorkspace, _Hit, empty_layout, normalize_layout
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
