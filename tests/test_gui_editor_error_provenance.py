from __future__ import annotations

import pytest

import cleanroomx.gui_constraints as gui_constraints_module
import cleanroomx.gui_requirements as gui_requirements_module
from cleanroomx.gui_constraints import ConstraintManagerDialog
from cleanroomx.gui_requirements import RequirementsEditorDialog


class _Report:
    def __init__(self, message: str) -> None:
        self._message = message

    def user_message(self) -> str:
        return self._message


def test_constraint_editor_records_unexpected_apply_failures(monkeypatch) -> None:
    dialog = ConstraintManagerDialog.__new__(ConstraintManagerDialog)

    def fail_apply(_description, _mutation):
        raise RuntimeError("synthetic constraint editor failure")

    dialog._apply_project_edit = fail_apply
    incidents = []
    messages = []

    def record(operation, exc):
        incidents.append((operation, type(exc).__name__, str(exc)))
        return _Report("Constraint editor failed.\n\nError reference: CX-CONSTRAINT")

    monkeypatch.setattr(gui_constraints_module, "record_gui_exception", record)
    monkeypatch.setattr(
        gui_constraints_module.messagebox,
        "showerror",
        lambda title, message, **kwargs: messages.append((title, message)),
    )

    assert dialog._apply("Update rule", lambda _project: None) is False
    assert incidents == [
        (
            "Constraint editor: Update rule",
            "RuntimeError",
            "synthetic constraint editor failure",
        )
    ]
    assert messages == [
        (
            "Constraint update failed",
            "Constraint editor failed.\n\nError reference: CX-CONSTRAINT",
        )
    ]


def test_constraint_editor_keeps_validation_failures_user_facing(monkeypatch) -> None:
    dialog = ConstraintManagerDialog.__new__(ConstraintManagerDialog)

    def fail_apply(_description, _mutation):
        raise ValueError("minimum must be positive")

    dialog._apply_project_edit = fail_apply
    messages = []
    monkeypatch.setattr(
        gui_constraints_module,
        "record_gui_exception",
        lambda *_args, **_kwargs: pytest.fail("validation error must not become incident"),
    )
    monkeypatch.setattr(
        gui_constraints_module.messagebox,
        "showerror",
        lambda title, message, **kwargs: messages.append((title, message)),
    )

    assert dialog._apply("Update rule", lambda _project: None) is False
    assert messages == [("Constraint update failed", "minimum must be positive")]


def test_requirements_editor_records_unexpected_apply_failures(monkeypatch) -> None:
    dialog = RequirementsEditorDialog.__new__(RequirementsEditorDialog)

    def fail_apply(_description, _mutation):
        raise RuntimeError("synthetic requirements editor failure")

    dialog._apply_project_edit = fail_apply
    incidents = []
    messages = []

    def record(operation, exc):
        incidents.append((operation, type(exc).__name__, str(exc)))
        return _Report("Requirements editor failed.\n\nError reference: CX-REQUIREMENTS")

    monkeypatch.setattr(gui_requirements_module, "record_gui_exception", record)
    monkeypatch.setattr(
        gui_requirements_module.messagebox,
        "showerror",
        lambda title, message, **kwargs: messages.append((title, message)),
    )

    assert dialog._apply("Update requirement", lambda _project: None) is False
    assert incidents == [
        (
            "Requirements editor: Update requirement",
            "RuntimeError",
            "synthetic requirements editor failure",
        )
    ]
    assert messages[0][0] == "Requirements update failed"
    assert "Error reference: CX-REQUIREMENTS" in messages[0][1]
    assert "Existing requirement/evidence mappings are preserved." in messages[0][1]


def test_requirements_editor_keeps_validation_failures_user_facing(monkeypatch) -> None:
    dialog = RequirementsEditorDialog.__new__(RequirementsEditorDialog)

    def fail_apply(_description, _mutation):
        raise ValueError("minimum must be <= maximum")

    dialog._apply_project_edit = fail_apply
    messages = []
    monkeypatch.setattr(
        gui_requirements_module,
        "record_gui_exception",
        lambda *_args, **_kwargs: pytest.fail("validation error must not become incident"),
    )
    monkeypatch.setattr(
        gui_requirements_module.messagebox,
        "showerror",
        lambda title, message, **kwargs: messages.append((title, message)),
    )

    assert dialog._apply("Update requirement", lambda _project: None) is False
    assert messages[0][0] == "Requirements update failed"
    assert "minimum must be <= maximum" in messages[0][1]
    assert "Existing requirement/evidence mappings are preserved." in messages[0][1]
