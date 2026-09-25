from __future__ import annotations

import json
from pathlib import Path

import cleanroomx.gui as gui_module
from cleanroomx.gui import CleanroomXApp
from cleanroomx.project import PROJECT_SCHEMA, PROJECT_SCHEMA_VERSION, ProjectDocument


class Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Root:
    def __init__(self):
        self.last_title = ""

    def title(self, value):
        self.last_title = value


def _write_legacy_project(path: Path) -> bytes:
    payload = {
        "schema": PROJECT_SCHEMA,
        "schema_version": 0,
        "name": "Legacy Project",
        "description": "pre-v1 source",
        "analysis": {
            "id": "room-legacy",
            "name": "Room",
            "kind": "room_verification",
            "input": {},
        },
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path.read_bytes()


def _app() -> CleanroomXApp:
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = Root()
    app.project = ProjectDocument(name="Before")
    app.project_path = None
    app._project_file_revision = None
    app._recovery_source_path = None
    app._restored_recovery_artifact = None
    app._migration_source_path = None
    app._project_migration_info = None
    app._editor_analysis_id = None
    app._baseline_state = ""
    app._autosave_interval_ms = 0
    app.name_var = Value("Before")
    app.description_var = Value("")
    app.status_var = Value("")
    app._discard_current_autosave = lambda: None
    app._begin_autosave_project = lambda path: None
    app._clear_run_cache = lambda: None
    app._refresh_analysis_list = lambda: None
    app._notify_explicit_save = lambda path: None
    return app


def test_legacy_project_opens_as_protected_unsaved_migration(tmp_path):
    source = tmp_path / "legacy.cleanroomx.json"
    source_before = _write_legacy_project(source)
    app = _app()

    app.load_project_path(source)

    assert source.read_bytes() == source_before
    assert app.project.name == "Legacy Project"
    assert app.project_path == source
    assert app._migration_source_path == source.resolve()
    assert app._project_migration_info.migrated is True
    assert app._project_migration_info.source_schema_version == 0
    assert app._has_unsaved_changes() is True
    assert "Save Project As" in app.status_var.value
    assert "Migrated copy" in app.root.last_title
    assert app.root.last_title.endswith("*")


def test_save_routes_migrated_project_to_save_as_without_touching_source(
    tmp_path, monkeypatch
):
    source = tmp_path / "legacy.cleanroomx.json"
    source_before = _write_legacy_project(source)
    app = _app()
    app.load_project_path(source)
    calls = []

    app.save_project_as = lambda: calls.append("save-as")
    monkeypatch.setattr(
        gui_module,
        "save_project_document_guarded",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("migrated Save must not overwrite the legacy source")
        ),
    )

    app.save_project()

    assert calls == ["save-as"]
    assert source.read_bytes() == source_before


def test_migrated_first_save_as_refuses_legacy_source_path(tmp_path, monkeypatch):
    source = tmp_path / "legacy.cleanroomx.json"
    source_before = _write_legacy_project(source)
    app = _app()
    app.load_project_path(source)
    warnings = []

    monkeypatch.setattr(
        gui_module.filedialog,
        "asksaveasfilename",
        lambda **kwargs: str(source),
    )
    monkeypatch.setattr(
        gui_module.messagebox,
        "showwarning",
        lambda title, message, parent=None: warnings.append((title, message)),
    )

    app.save_project_as()

    assert source.read_bytes() == source_before
    assert app._migration_source_path == source.resolve()
    assert app._has_unsaved_changes() is True
    assert warnings
    assert warnings[0][0] == "Preserve legacy project"
    assert "different file" in warnings[0][1]
    assert "rollback" in warnings[0][1]


def test_migrated_save_as_preserves_original_and_writes_current_schema(
    tmp_path, monkeypatch
):
    source = tmp_path / "legacy.cleanroomx.json"
    source_before = _write_legacy_project(source)
    destination = tmp_path / "migrated.cleanroomx.json"
    app = _app()
    app.load_project_path(source)

    monkeypatch.setattr(
        gui_module.filedialog,
        "asksaveasfilename",
        lambda **kwargs: str(destination),
    )

    app.save_project_as()

    assert source.read_bytes() == source_before
    saved = json.loads(destination.read_text(encoding="utf-8"))
    assert saved["schema"] == PROJECT_SCHEMA
    assert saved["schema_version"] == PROJECT_SCHEMA_VERSION
    assert saved["project"]["name"] == "Legacy Project"
    assert app.project_path == destination
    assert app._migration_source_path is None
    assert app._project_migration_info is None
    assert app._has_unsaved_changes() is False
