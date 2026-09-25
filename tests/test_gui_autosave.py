from __future__ import annotations

from pathlib import Path

import pytest

import cleanroomx.gui as gui_module
from cleanroomx.autosave import AutosaveStatus
from cleanroomx.gui import CleanroomXApp
from cleanroomx.persistence import PersistenceDurabilityError
from cleanroomx.project import AnalysisDocument, ProjectDocument


class Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Text:
    def __init__(self, value):
        self.value = value

    def get(self, *args):
        return self.value


class Root:
    def __init__(self):
        self.calls = []

    def after(self, delay, callback):
        self.calls.append((delay, callback))


def test_recovery_snapshot_preserves_invalid_editor_draft_without_mutating_model():
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.project = ProjectDocument(
        name="Saved Name",
        analyses=[
            AnalysisDocument(
                id="a",
                name="A",
                kind="room_verification",
                input={"value": 1},
            )
        ],
        active_analysis_id="a",
    )
    app._editor_analysis_id = "a"
    app.name_var = Value("Draft Name")
    app.description_var = Value("Unsaved description")
    app.input_text = Text("{broken")

    snapshot = app._build_recovery_snapshot()

    assert snapshot["project"]["project"]["name"] == "Draft Name"
    assert snapshot["project"]["project"]["description"] == "Unsaved description"
    assert snapshot["project"]["analyses"][0]["input"] == {"value": 1}
    assert snapshot["ui_state"]["editor_text"] == "{broken"
    assert snapshot["ui_state"]["editor_json_valid"] is False
    assert app.project.name == "Saved Name"
    assert app.project.analysis_by_id("a").input == {"value": 1}


def test_recovery_snapshot_promotes_valid_editor_draft_into_recoverable_project():
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.project = ProjectDocument(
        name="Demo",
        analyses=[
            AnalysisDocument(
                id="a",
                name="A",
                kind="room_verification",
                input={"value": 1},
            )
        ],
        active_analysis_id="a",
    )
    app._editor_analysis_id = "a"
    app.name_var = Value("Demo")
    app.description_var = Value("")
    app.input_text = Text('{"value": 2}')

    snapshot = app._build_recovery_snapshot()

    assert snapshot["project"]["analyses"][0]["input"] == {"value": 2}
    assert snapshot["ui_state"]["editor_json_valid"] is True


def test_autosave_tick_queues_only_dirty_state_and_reschedules():
    class Manager:
        def __init__(self):
            self.calls = []

        def request_autosave(self, snapshot, *, source_path):
            self.calls.append((snapshot, source_path))
            return True

        def status(self):
            return AutosaveStatus(state="idle", message="ready")

    app = CleanroomXApp.__new__(CleanroomXApp)
    app._autosave_interval_ms = 2500
    app._autosave_manager = Manager()
    app._has_unsaved_changes = lambda: True
    app._build_recovery_snapshot = lambda: {"project": {}, "ui_state": {}}
    app.project_path = Path("/tmp/demo.cleanroomx.json")
    app.autosave_status_var = Value("")
    app.status_var = Value("")
    app.root = Root()

    app._autosave_tick()

    assert app._autosave_manager.calls == [
        ({"project": {}, "ui_state": {}}, app.project_path)
    ]
    assert app.autosave_status_var.value == "Autosave: saving…"
    assert app.root.calls == [(2500, app._autosave_tick)]


def test_autosave_tick_does_not_write_clean_project():
    class Manager:
        def __init__(self):
            self.requests = 0
            self.discards = 0

        def request_autosave(self, snapshot, *, source_path):
            self.requests += 1
            return True

        def status(self):
            return AutosaveStatus(state="saved", message="saved")

        def discard_current_recoveries(self):
            self.discards += 1

    app = CleanroomXApp.__new__(CleanroomXApp)
    app._autosave_interval_ms = 1000
    app._autosave_manager = Manager()
    app._has_unsaved_changes = lambda: False
    app.project_path = None
    app.autosave_status_var = Value("")
    app.status_var = Value("")
    app.root = Root()

    app._autosave_tick()

    assert app._autosave_manager.requests == 0
    assert app._autosave_manager.discards == 1
    assert app.autosave_status_var.value == "Autosave: clean"


def test_gui_parser_exposes_configurable_autosave_interval():
    args = gui_module.build_parser().parse_args(
        ["--autosave-interval-seconds", "12.5", "--check"]
    )
    assert args.autosave_interval_seconds == 12.5


def test_gui_rejects_negative_autosave_interval_before_tk_startup():
    with pytest.raises(SystemExit) as exc:
        gui_module.main(["--autosave-interval-seconds", "-1", "--check"])
    assert exc.value.code == 2


def test_explicit_save_surfaces_recovery_cleanup_failure_in_status():
    class Manager:
        def notify_explicit_save(self, path):
            self.path = path

        def status(self):
            return AutosaveStatus(
                state="failed",
                message="Project saved; recovery cleanup failed",
            )

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = object()
    app._recovery_checkpoint_after_id = None
    app._autosave_manager = Manager()
    app.autosave_status_var = Value("")

    target = Path("/tmp/demo.cleanroomx.json")
    app._notify_explicit_save(target)

    assert app._autosave_manager.path == target
    assert app.autosave_status_var.value == "Autosave: recovery cleanup failed"


def test_clean_checkpoint_keeps_cleanup_failure_visible():
    class Manager:
        def __init__(self):
            self.failed = False

        def status(self):
            return AutosaveStatus(
                state="failed" if self.failed else "saved",
                message=(
                    "Autosave recovery cleanup failed: simulated"
                    if self.failed
                    else "saved"
                ),
            )

        def discard_current_recoveries(self):
            self.failed = True

    app = CleanroomXApp.__new__(CleanroomXApp)
    app._autosave_manager = Manager()
    app._has_unsaved_changes = lambda: False
    app.autosave_status_var = Value("")
    app.status_var = Value("")

    app._checkpoint_recovery()

    assert app.autosave_status_var.value == "Autosave: recovery cleanup failed"
    assert "cleanup failed" in app.status_var.value


def test_persistence_durability_warning_is_actionable(tmp_path, monkeypatch):
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = object()
    app.status_var = Value("")
    warnings = []
    monkeypatch.setattr(
        gui_module.messagebox,
        "showwarning",
        lambda title, message, **kwargs: warnings.append((title, message)),
    )
    target = tmp_path / "project.cleanroomx.json"
    exc = PersistenceDurabilityError(
        target,
        "atomic replacement",
        OSError("simulated directory fsync failure"),
    )

    app._report_persistence_durability_failure(target, exc)

    assert "durability was not confirmed" in app.status_var.value
    assert warnings
    assert "Save Project As" in warnings[0][1]
    assert "power loss" in warnings[0][1]
