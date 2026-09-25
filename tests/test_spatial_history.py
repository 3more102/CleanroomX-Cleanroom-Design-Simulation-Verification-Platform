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
