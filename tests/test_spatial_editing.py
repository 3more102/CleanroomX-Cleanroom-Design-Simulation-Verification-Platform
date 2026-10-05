from __future__ import annotations

import copy

import pytest

from cleanroomx.project import ProjectDocument, load_project_document, save_project_document
from cleanroomx.spatial import SpatialDesignWorkspace, _Hit, empty_layout, normalize_layout
from cleanroomx.spatial_editing import duplicate_spatial_item, update_spatial_properties
from cleanroomx.spatial_integrity import validate_spatial_layout_document


@pytest.fixture
def layout():
    return normalize_layout({
        **empty_layout(),
        "rooms": [{
            "id": "process", "name": "Process", "x_m": 2, "y_m": 3,
            "length_m": 6, "width_m": 5, "height_m": 3,
            "floor_elevation_m": 1, "pressure_pa": 30,
            "classification": "Project class", "analysis_room_name": "Process analysis",
        }],
        "devices": [
            {"id": "ffu", "name": "FFU", "type": "ffu", "room_id": "process",
             "x_m": 4, "y_m": 5, "z_m": 3},
            {"id": "door", "name": "Door", "type": "door", "room_id": "process",
             "x_m": 4, "y_m": 3, "z_m": 0, "wall_side": "south", "swing": "left",
             "width_m": 0.9, "height_m": 2.1},
            {"id": "unassigned", "name": "Monitor", "type": "sensor", "room_id": None,
             "x_m": 0, "y_m": 0, "z_m": 1},
        ],
        "engineering_sync": {
            "analysis_id": "verification",
            "rooms": [{"room_id": "process", "analysis_room_name": "Process analysis",
                       "length_m": 6, "width_m": 5, "height_m": 3}],
        },
    })


@pytest.mark.parametrize("field,value", [
    ("name", " "), ("x_m", "abc"), ("y_m", ""), ("length_m", "0"),
    ("width_m", "-1"), ("height_m", "NaN"), ("height_m", "1e999"),
    ("floor_elevation_m", "Infinity"), ("pressure_pa", "unknown"),
    ("pressure_pa", "NaN"),
])
def test_invalid_room_properties_are_rejected_without_partial_changes(layout, field, value):
    before = copy.deepcopy(layout)
    with pytest.raises(ValueError):
        update_spatial_properties(layout, "room", "process", {
            "name": "Edited name", "x_m": "10", field: value,
        })
    assert layout == before


def test_room_property_move_keeps_device_offsets_and_elevations(layout):
    before = copy.deepcopy(layout)
    result = update_spatial_properties(layout, "room", "process", {
        "x_m": "-1.25", "y_m": "8.5", "height_m": "4", "floor_elevation_m": "2",
    })
    assert layout == before
    room = result["rooms"][0]
    assert (room["x_m"], room["y_m"], room["height_m"], room["floor_elevation_m"]) == (-1.25, 8.5, 4, 2)
    for old, moved in zip(layout["devices"][:2], result["devices"][:2]):
        assert moved["x_m"] - room["x_m"] == pytest.approx(old["x_m"] - 2)
        assert moved["y_m"] - room["y_m"] == pytest.approx(old["y_m"] - 3)
        assert moved["z_m"] == old["z_m"]
    assert result["devices"][2] == layout["devices"][2]
    assert result["engineering_sync"] == layout["engineering_sync"]


def test_blank_pressure_and_optional_metadata_clear_without_inventing_zero(layout):
    result = update_spatial_properties(layout, "room", "process", {
        "pressure_pa": "", "classification": " ", "analysis_room_name": "",
    })
    room = result["rooms"][0]
    assert all(key not in room for key in ("pressure_pa", "classification", "analysis_room_name"))
    assert layout["rooms"][0]["pressure_pa"] == 30


@pytest.mark.parametrize("values", [
    {"room_id": "missing"}, {"wall_side": "diagonal"}, {"z_m": "NaN"},
    {"width_m": "0"}, {"height_m": "-1"}, {"orientation_deg": "Infinity"},
])
def test_invalid_device_edit_is_atomic(layout, values):
    before = copy.deepcopy(layout)
    with pytest.raises(ValueError):
        update_spatial_properties(layout, "device", "door", {"x_m": "5", **values})
    assert layout == before


def test_device_can_be_unassigned_and_optional_opening_metadata_cleared(layout):
    result = update_spatial_properties(layout, "device", "door", {
        "room_id": "", "wall_side": "", "swing": "", "orientation_deg": "90",
    })
    device = result["devices"][1]
    assert device["room_id"] is None
    assert "wall_side" not in device and "swing" not in device
    assert device["orientation_deg"] == 90
    assert result["rooms"] == layout["rooms"]


def test_duplicate_room_copies_geometry_and_children_without_engineering_evidence(layout):
    before = copy.deepcopy(layout)
    result, room_id = duplicate_spatial_item(layout, "room", "process")
    assert layout == before
    room = result["rooms"][-1]
    assert room["id"] == room_id != "process"
    assert room["name"] == "Process copy"
    assert room["x_m"] > 8
    for field in ("length_m", "width_m", "height_m", "floor_elevation_m", "classification", "y_m"):
        assert room[field] == layout["rooms"][0][field]
    assert "pressure_pa" not in room and "analysis_room_name" not in room
    assert result["engineering_sync"] == layout["engineering_sync"]
    assert result["view"] == layout["view"]
    children = [device for device in result["devices"] if device["room_id"] == room_id]
    assert len(children) == 2
    for original, child in zip(layout["devices"][:2], children):
        assert child["id"] != original["id"]
        assert child["x_m"] - room["x_m"] == original["x_m"] - 2
        assert child["y_m"] == original["y_m"]
        assert child["z_m"] == original["z_m"]
        assert child["type"] == original["type"]
    assert children[1]["swing"] == "left" and children[1]["wall_side"] == "south"
    ids = [item["id"] for item in result["rooms"] + result["devices"]]
    assert len(ids) == len(set(ids))
    children[0]["name"] = "Renamed copy"
    assert layout == before
    validate_spatial_layout_document(result)


def test_repeated_duplicates_have_unique_names_and_nonoverlapping_placement(layout):
    first, first_id = duplicate_spatial_item(layout, "room", "process")
    first["rooms"][-1]["name"] = "PROCESS COPY"
    second, second_id = duplicate_spatial_item(first, "room", "process")
    assert first_id != second_id
    assert second["rooms"][-1]["name"] == "Process copy 2"
    assert second["rooms"][-1]["x_m"] > first["rooms"][-1]["x_m"] + 6


@pytest.mark.parametrize("device_id", ["ffu", "door", "unassigned"])
def test_duplicate_device_keeps_parent_and_offsets_without_copying_room(layout, device_id):
    result, device_copy_id = duplicate_spatial_item(layout, "device", device_id)
    original = next(item for item in layout["devices"] if item["id"] == device_id)
    duplicate = result["devices"][-1]
    assert duplicate["id"] == device_copy_id != device_id
    assert duplicate["room_id"] == original["room_id"]
    assert duplicate["z_m"] == original["z_m"]
    assert duplicate["x_m"] == original["x_m"] + layout["grid_m"]
    if device_id == "door":
        assert duplicate["y_m"] == original["y_m"]
    assert result["rooms"] == layout["rooms"]


def test_device_at_room_boundary_is_offset_inward(layout):
    layout["devices"][0].update(x_m=8, y_m=8)
    result, _ = duplicate_spatial_item(layout, "device", "ffu")
    assert (result["devices"][-1]["x_m"], result["devices"][-1]["y_m"]) == (7.5, 7.5)


def test_invalid_selection_and_unrepresentable_room_copy_do_not_mutate(layout):
    before = copy.deepcopy(layout)
    for kind, item_id in (("other", "process"), ("room", "missing")):
        with pytest.raises(ValueError):
            duplicate_spatial_item(layout, kind, item_id)
    assert layout == before
    layout["rooms"][0]["x_m"] = 1e308
    layout["rooms"][0]["length_m"] = 1e308
    before = copy.deepcopy(layout)
    with pytest.raises(ValueError):
        duplicate_spatial_item(layout, "room", "process")
    assert layout == before


def test_edited_duplicate_round_trips_through_project_persistence(layout, tmp_path):
    duplicate, room_id = duplicate_spatial_item(layout, "room", "process")
    edited = update_spatial_properties(duplicate, "room", room_id, {"height_m": "4", "pressure_pa": "15"})
    project = ProjectDocument(name="Copies", metadata={"spatial_layout": edited})
    path = tmp_path / "copies.cleanroomx.json"
    save_project_document(path, project)
    reopened = load_project_document(path)
    assert reopened.metadata["spatial_layout"] == edited
    save_project_document(path, reopened)
    assert load_project_document(path).metadata["spatial_layout"] == edited


def _workspace(layout):
    project = ProjectDocument(name="Editor", metadata={"spatial_layout": layout})
    workspace = object.__new__(SpatialDesignWorkspace)
    workspace.layout = project.metadata["spatial_layout"]
    workspace.selected = _Hit("room", "process")
    workspace._project_getter = lambda: project
    workspace._load_property_panel = lambda: None
    workspace._update_history_controls = lambda: None
    workspace.redraw = lambda: None
    events = {"changes": [], "history": [], "statuses": []}
    workspace._on_change = lambda: events["changes"].append(True)
    workspace._on_history_record = lambda *args: events["history"].append(args)
    workspace._status_setter = events["statuses"].append
    return workspace, project, events


def test_workspace_duplicate_is_one_history_transaction_with_selection(layout):
    workspace, project, events = _workspace(layout)
    assert workspace._on_duplicate_shortcut() == "break"
    assert len(events["changes"]) == len(events["history"]) == 1
    before, old_selection, after, new_selection, _ = events["history"][0]
    assert len(before["rooms"]) == 1 and len(after["rooms"]) == 2
    assert old_selection == ("room", "process")
    assert new_selection == ("room", workspace.layout["rooms"][-1]["id"])
    assert project.metadata["spatial_layout"] is workspace.layout


def test_workspace_rejected_properties_keep_model_history_and_editor_text(layout, monkeypatch):
    workspace, project, events = _workspace(layout)
    before = project.metadata["spatial_layout"]
    class Value:
        def get(self):
            return "not a number"
    workspace._property_vars = {"height_m": Value()}
    modal_errors = []
    monkeypatch.setattr(
        "cleanroomx.spatial.messagebox.showerror",
        lambda *args, **kwargs: modal_errors.append(args),
    )
    workspace.apply_properties()
    assert modal_errors == []
    assert events["changes"] == events["history"] == []
    assert project.metadata["spatial_layout"] is before
    assert workspace.layout is before
    assert before == layout
    assert workspace._property_vars["height_m"].get() == "not a number"
    assert events["statuses"][-1] == (
        "Properties not applied: Height (m) must be a finite number"
    )


def test_workspace_unchanged_properties_do_not_create_history(layout):
    workspace, project, events = _workspace(layout)
    workspace._property_vars = {}
    workspace.apply_properties()
    assert events["changes"] == events["history"] == []
    assert workspace.layout is project.metadata["spatial_layout"]
