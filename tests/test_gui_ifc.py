from __future__ import annotations

import copy
from pathlib import Path

import cleanroomx.gui as gui_module
from cleanroomx.bim_ifc import (
    IFC_LINK_METADATA_KEY,
    apply_ifc_semantics_to_project,
    layout_from_ifc_semantics,
    normalize_ifc_semantic_records,
)
from cleanroomx.gui import CleanroomXApp
from cleanroomx.project import new_project


def _records():
    return [
        {
            "global_id": "SPACE-001",
            "ifc_class": "IfcSpace",
            "name": "ISO 7 Process",
            "x_m": 1.0,
            "y_m": 2.0,
            "z_m": 0.0,
            "length_m": 6.0,
            "width_m": 5.0,
            "height_m": 3.0,
        },
        {
            "global_id": "AT-001",
            "ifc_class": "IfcAirTerminal",
            "name": "Supply 01",
            "room_global_id": "SPACE-001",
            "predefined_type": "SUPPLYAIR",
            "x_m": 2.0,
            "y_m": 3.0,
            "z_m": 2.8,
        },
    ]


class _Status:
    def __init__(self):
        self.value = ""

    def set(self, value):
        self.value = value


class _Workspace:
    def __init__(self):
        self.refresh_count = 0

    def refresh(self):
        self.refresh_count += 1


def _app(project):
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.project = project
    app.root = object()
    app._running = False
    app.status_var = _Status()
    app.spatial_workspace = _Workspace()
    app._prepare_project_history_action = lambda _action: True
    app._perform_project_edit = lambda _description, mutation: mutation()
    app._update_title = lambda: None
    app._select_ifc_source = lambda **_kwargs: Path("facility.ifc")
    app._show_ifc_plan = lambda _report: None
    return app


def _install_source(monkeypatch, records, digest):
    semantics = normalize_ifc_semantic_records(records)
    provenance = {"source_name": "facility.ifc", "source_sha256": digest}
    monkeypatch.setattr(
        gui_module,
        "extract_ifc_semantics",
        lambda _path: (copy.deepcopy(semantics), dict(provenance)),
    )
    return semantics


def _silence_messages(monkeypatch, *, confirm=True):
    monkeypatch.setattr(gui_module.messagebox, "showinfo", lambda *a, **k: None)
    monkeypatch.setattr(gui_module.messagebox, "showwarning", lambda *a, **k: None)
    monkeypatch.setattr(gui_module.messagebox, "showerror", lambda *a, **k: None)
    monkeypatch.setattr(
        gui_module.messagebox,
        "askyesno",
        lambda *a, **k: confirm,
    )


def test_gui_ifc_initial_import_establishes_identity_without_touching_analyses(
    monkeypatch,
):
    project = new_project("IFC GUI")
    app = _app(project)
    _install_source(monkeypatch, _records(), "a" * 64)
    _silence_messages(monkeypatch)
    analyses_before = copy.deepcopy(project.analyses)

    assert app.import_ifc_spatial_layout() is True

    link = project.metadata[IFC_LINK_METADATA_KEY]
    assert link["schema_version"] == 2
    assert len(link["bindings"]) == 2
    assert project.analyses == analyses_before
    assert app.spatial_workspace.refresh_count == 1
    assert "save the project" in app.status_var.value.lower()


def test_gui_ifc_initial_import_previews_provenance_before_mutation(monkeypatch):
    project = new_project("IFC GUI preview")
    app = _app(project)
    _install_source(monkeypatch, _records(), "a" * 64)

    confirmations = []
    monkeypatch.setattr(gui_module.messagebox, "showinfo", lambda *a, **k: None)
    monkeypatch.setattr(gui_module.messagebox, "showwarning", lambda *a, **k: None)
    monkeypatch.setattr(gui_module.messagebox, "showerror", lambda *a, **k: None)
    monkeypatch.setattr(
        gui_module.messagebox,
        "askyesno",
        lambda title, message, **kwargs: confirmations.append((title, message)) or True,
    )

    def perform(_description, mutation):
        assert confirmations, "IFC provenance preview must precede project mutation"
        return mutation()

    app._perform_project_edit = perform

    assert app.import_ifc_spatial_layout() is True

    assert len(confirmations) == 1
    title, message = confirmations[0]
    assert title == "Import IFC spatial layout?"
    assert "Source: facility.ifc" in message
    assert "Rooms: 1" in message
    assert "Devices: 1" in message
    assert f"Source SHA-256: {'a' * 64}" in message


def test_gui_ifc_initial_import_rejects_review_to_apply_source_drift(monkeypatch):
    project = new_project("IFC GUI source drift")
    app = _app(project)

    reviewed = normalize_ifc_semantic_records(_records())
    changed_records = _records()
    changed_records[0]["length_m"] = 7.0
    changed = normalize_ifc_semantic_records(changed_records)
    candidates = [
        (copy.deepcopy(reviewed), {"source_name": "facility.ifc", "source_sha256": "a" * 64}),
        (copy.deepcopy(changed), {"source_name": "facility.ifc", "source_sha256": "b" * 64}),
    ]
    monkeypatch.setattr(
        gui_module,
        "extract_ifc_semantics",
        lambda _path: candidates.pop(0),
    )
    monkeypatch.setattr(gui_module.messagebox, "showinfo", lambda *a, **k: None)
    monkeypatch.setattr(gui_module.messagebox, "showwarning", lambda *a, **k: None)
    monkeypatch.setattr(gui_module.messagebox, "askyesno", lambda *a, **k: True)
    errors = []
    monkeypatch.setattr(
        gui_module.messagebox,
        "showerror",
        lambda title, message, **kwargs: errors.append((title, message)),
    )
    app._perform_project_edit = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("source drift must be rejected before project mutation")
    )

    before = copy.deepcopy(project.to_dict())
    assert app.import_ifc_spatial_layout() is False

    assert project.to_dict() == before
    assert errors
    assert "changed after it was reviewed" in errors[0][1]


def test_gui_ifc_initial_import_requires_explicit_layout_replacement(monkeypatch):
    project = new_project("IFC GUI")
    original = normalize_ifc_semantic_records(_records())
    project.metadata["spatial_layout"] = layout_from_ifc_semantics(original)
    before = copy.deepcopy(project.to_dict())
    app = _app(project)
    _install_source(monkeypatch, _records(), "a" * 64)
    _silence_messages(monkeypatch, confirm=False)

    assert app.import_ifc_spatial_layout() is False
    assert project.to_dict() == before
    assert IFC_LINK_METADATA_KEY not in project.metadata


def test_gui_ifc_review_is_read_only_and_surfaces_two_sided_conflict(monkeypatch):
    project = new_project("IFC GUI")
    original = normalize_ifc_semantic_records(_records())
    apply_ifc_semantics_to_project(
        project,
        original,
        source_name="facility.ifc",
        source_sha256="a" * 64,
    )
    project.metadata["spatial_layout"]["rooms"][0]["length_m"] = 6.5
    before = copy.deepcopy(project.to_dict())

    revised = _records()
    revised[0]["length_m"] = 7.0
    app = _app(project)
    _install_source(monkeypatch, revised, "b" * 64)
    _silence_messages(monkeypatch)
    plans = []
    app._show_ifc_plan = lambda report: plans.append(copy.deepcopy(report))

    report = app.review_ifc_reimport()

    assert report is not None
    assert report["can_apply"] is False
    assert report["conflict_count"] == 1
    assert plans[0] == report
    assert project.to_dict() == before
    assert "blocked" in app.status_var.value.lower()


def test_gui_ifc_apply_preserves_global_id_spatial_identity(monkeypatch):
    project = new_project("IFC GUI")
    original = normalize_ifc_semantic_records(_records())
    apply_ifc_semantics_to_project(
        project,
        original,
        source_name="facility.ifc",
        source_sha256="a" * 64,
    )
    original_room_id = project.metadata["spatial_layout"]["rooms"][0]["id"]

    revised = _records()
    revised[0]["name"] = "Renamed Process"
    revised[0]["length_m"] = 7.0
    app = _app(project)
    _install_source(monkeypatch, revised, "b" * 64)
    _silence_messages(monkeypatch, confirm=True)
    reviewed = []
    app._show_ifc_plan = lambda report: reviewed.append(copy.deepcopy(report))

    assert app.apply_ifc_reimport() is True

    room = project.metadata["spatial_layout"]["rooms"][0]
    assert room["id"] == original_room_id
    assert room["name"] == "Renamed Process"
    assert room["length_m"] == 7.0
    assert reviewed[0]["can_apply"] is True
    assert app.spatial_workspace.refresh_count == 1


def test_gui_ifc_apply_rejects_review_to_apply_source_drift(monkeypatch):
    project = new_project("IFC GUI re-import drift")
    original = normalize_ifc_semantic_records(_records())
    apply_ifc_semantics_to_project(
        project,
        original,
        source_name="facility.ifc",
        source_sha256="a" * 64,
    )

    reviewed_records = _records()
    reviewed_records[0]["length_m"] = 7.0
    reviewed = normalize_ifc_semantic_records(reviewed_records)
    changed_records = _records()
    changed_records[0]["length_m"] = 8.0
    changed = normalize_ifc_semantic_records(changed_records)

    app = _app(project)
    candidates = [
        (copy.deepcopy(reviewed), {"source_name": "facility.ifc", "source_sha256": "b" * 64}),
        (copy.deepcopy(changed), {"source_name": "facility.ifc", "source_sha256": "c" * 64}),
    ]
    monkeypatch.setattr(
        gui_module,
        "extract_ifc_semantics",
        lambda _path: candidates.pop(0),
    )
    monkeypatch.setattr(gui_module.messagebox, "showinfo", lambda *a, **k: None)
    monkeypatch.setattr(gui_module.messagebox, "showwarning", lambda *a, **k: None)
    monkeypatch.setattr(gui_module.messagebox, "askyesno", lambda *a, **k: True)
    errors = []
    monkeypatch.setattr(
        gui_module.messagebox,
        "showerror",
        lambda title, message, **kwargs: errors.append((title, message)),
    )
    app._perform_project_edit = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("source drift must be rejected before project mutation")
    )

    before = copy.deepcopy(project.to_dict())
    assert app.apply_ifc_reimport() is False

    assert project.to_dict() == before
    assert app.spatial_workspace.refresh_count == 0
    assert errors
    assert "changed after it was reviewed" in errors[0][1]


def test_gui_ifc_apply_blocks_conflict_without_mutating_project(monkeypatch):
    project = new_project("IFC GUI")
    original = normalize_ifc_semantic_records(_records())
    apply_ifc_semantics_to_project(
        project,
        original,
        source_name="facility.ifc",
        source_sha256="a" * 64,
    )
    project.metadata["spatial_layout"]["rooms"][0]["length_m"] = 6.5
    before = copy.deepcopy(project.to_dict())

    revised = _records()
    revised[0]["length_m"] = 7.0
    app = _app(project)
    _install_source(monkeypatch, revised, "b" * 64)
    _silence_messages(monkeypatch, confirm=True)

    assert app.apply_ifc_reimport() is False
    assert project.to_dict() == before
    assert app.spatial_workspace.refresh_count == 0
