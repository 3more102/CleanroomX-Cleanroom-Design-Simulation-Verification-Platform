from __future__ import annotations

from types import SimpleNamespace

import cleanroomx.gui as gui_module
from cleanroomx.gui import CleanroomXApp
from cleanroomx.project import ProjectFileRevision, ProjectSaveDurabilityError


class _RecordingLogger:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def exception(self, message: str, *args: object) -> None:
        self.calls.append((message, args))


class _Value:
    def __init__(self) -> None:
        self.value = None

    def set(self, value) -> None:
        self.value = value


def test_ui_layout_save_failure_is_recorded(monkeypatch, tmp_path) -> None:
    app = CleanroomXApp.__new__(CleanroomXApp)
    app._ui_state_path = tmp_path / "layout.json"
    app._capture_ui_layout_state = lambda: {"theme": "light"}
    logger = _RecordingLogger()
    monkeypatch.setattr(gui_module, "GUI_RUNTIME_LOGGER", logger)

    def fail_save(*_args, **_kwargs):
        raise OSError("layout destination is unavailable")

    monkeypatch.setattr(gui_module, "save_gui_layout_state", fail_save)

    app._save_ui_layout_state()

    assert logger.calls == [
        (
            "Failed to persist GUI layout state path=%s",
            (app._ui_state_path,),
        )
    ]


def test_dirty_state_signature_failure_is_recorded_and_fails_safe(monkeypatch) -> None:
    app = CleanroomXApp.__new__(CleanroomXApp)
    app._baseline_state = "saved"
    logger = _RecordingLogger()
    monkeypatch.setattr(gui_module, "GUI_RUNTIME_LOGGER", logger)

    def fail_signature() -> str:
        raise ValueError("editor state cannot be serialized")

    app._project_state_signature = fail_signature

    assert app._has_unsaved_changes() is True
    assert logger.calls == [
        (
            "Failed to compute project dirty-state signature; treating project as modified",
            (),
        )
    ]


def test_durability_recovery_reload_failure_is_recorded(monkeypatch, tmp_path) -> None:
    project_path = tmp_path / "project.cleanroomx.json"
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = object()
    app.status_var = _Value()
    analysis = SimpleNamespace(id="requirements", name="Requirements")
    app._project_verification_target = lambda: (project_path, analysis)

    workflow = object()
    monkeypatch.setattr(
        gui_module,
        "run_project_requirements_workflow",
        lambda *_args, **_kwargs: workflow,
    )
    committed = ProjectFileRevision(
        path=str(project_path),
        exists=True,
        size=128,
        mtime_ns=1,
        sha256="a" * 64,
    )
    durability_error = ProjectSaveDurabilityError(project_path, committed)

    def fail_persist(*_args, **_kwargs):
        raise durability_error

    monkeypatch.setattr(
        gui_module,
        "persist_project_requirements_workflow_run",
        fail_persist,
    )

    def fail_reload(_path):
        raise OSError("reload failed")

    app.load_project_path = fail_reload
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        gui_module.messagebox,
        "showwarning",
        lambda title, message, **_kwargs: warnings.append((title, message)),
    )
    logger = _RecordingLogger()
    monkeypatch.setattr(gui_module, "GUI_RUNTIME_LOGGER", logger)

    assert app.persist_project_requirements_verification() is False
    assert app.status_var.value == (
        "Verification bytes committed; save durability not confirmed"
    )
    assert warnings
    assert logger.calls == [
        (
            "Failed to reload project after durability warning path=%s",
            (project_path,),
        )
    ]

def test_engineering_panel_failures_are_recorded_without_hiding_operator_state(
    monkeypatch,
) -> None:
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.project = SimpleNamespace(
        name="Engineering panel failure",
        analyses=[],
        metadata={},
    )
    app.project_path = None
    app.last_run = None
    app.verification_text = "verification"
    app.evidence_text = "evidence"
    app.console_text = "console"
    app._base_dir = lambda: None

    class ProblemsPanel:
        @staticmethod
        def refresh():
            return {"summary": {"status": "ok"}}

    app.problems_panel = ProblemsPanel()
    displayed: dict[str, str] = {}
    app._set_text = lambda target, value: displayed.__setitem__(target, value)

    def fail_currency(*_args, **_kwargs):
        raise RuntimeError("currency backend failed")

    def fail_history(*_args, **_kwargs):
        raise ValueError("verification history failed")

    monkeypatch.setattr(
        gui_module,
        "assess_project_verification_currency",
        fail_currency,
    )
    monkeypatch.setattr(
        gui_module,
        "verification_run_history_records",
        fail_history,
    )
    logger = _RecordingLogger()
    monkeypatch.setattr(gui_module, "GUI_RUNTIME_LOGGER", logger)

    diagnostics = app._refresh_engineering_panels()

    assert diagnostics == {"summary": {"status": "ok"}}
    assert displayed["verification"] == (
        "Verification currency unavailable: currency backend failed\n"
    )
    assert displayed["evidence"] == (
        "Verification evidence unavailable: verification history failed\n"
    )
    assert logger.calls == [
        (
            "Failed to assess project verification currency path=%s",
            (None,),
        ),
        (
            "Failed to load persisted verification evidence path=%s",
            (None,),
        ),
    ]


def test_engineering_panel_failures_are_recorded_without_hiding_operator_state(
    monkeypatch,
) -> None:
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.project = SimpleNamespace(
        name="Engineering panel failure",
        analyses=[],
        metadata={},
    )
    app.project_path = None
    app.last_run = None
    app.verification_text = "verification"
    app.evidence_text = "evidence"
    app.console_text = "console"
    app._base_dir = lambda: None

    class ProblemsPanel:
        @staticmethod
        def refresh():
            return {"summary": {"status": "ok"}}

    app.problems_panel = ProblemsPanel()
    displayed: dict[str, str] = {}
    app._set_text = lambda target, value: displayed.__setitem__(target, value)

    def fail_currency(*_args, **_kwargs):
        raise RuntimeError("currency backend failed")

    def fail_history(*_args, **_kwargs):
        raise ValueError("verification history failed")

    monkeypatch.setattr(
        gui_module,
        "assess_project_verification_currency",
        fail_currency,
    )
    monkeypatch.setattr(
        gui_module,
        "verification_run_history_records",
        fail_history,
    )
    logger = _RecordingLogger()
    monkeypatch.setattr(gui_module, "GUI_RUNTIME_LOGGER", logger)

    diagnostics = app._refresh_engineering_panels()

    assert diagnostics == {"summary": {"status": "ok"}}
    assert displayed["verification"] == (
        "Verification currency unavailable: currency backend failed\n"
    )
    assert displayed["evidence"] == (
        "Verification evidence unavailable: verification history failed\n"
    )
    assert logger.calls == [
        (
            "Failed to assess project verification currency path=%s",
            (None,),
        ),
        (
            "Failed to load persisted verification evidence path=%s",
            (None,),
        ),
    ]

