from __future__ import annotations

import os
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.gui_notifications import (
    NotificationCenter,
    default_notification_timeout_ms,
    normalize_notification_level,
    notification_style_name,
)
from cleanroomx.gui_theme import configure_ttk_theme
from cleanroomx.run_history import RUN_HISTORY_METADATA_KEY


def test_notification_projection_is_semantic_and_deterministic():
    assert normalize_notification_level("pass") == "success"
    assert normalize_notification_level("informational") == "info"
    assert normalize_notification_level("warn") == "warning"
    assert normalize_notification_level("failed") == "error"
    assert normalize_notification_level("unexpected") == "info"

    assert notification_style_name("success") == "CX.Status.Pass.TLabel"
    assert notification_style_name("warning") == "CX.Status.Warning.TLabel"
    assert notification_style_name("error") == "CX.Status.Fail.TLabel"
    assert default_notification_timeout_ms("success") == 4500
    assert default_notification_timeout_ms("info") == 6000
    assert default_notification_timeout_ms("warning") is None
    assert default_notification_timeout_ms("error") is None


def test_notification_center_is_non_modal_and_keeps_explicit_level_text():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    configure_ttk_theme(root, "dark")
    anchor = tk.Frame(root)
    anchor.pack()
    center = NotificationCenter(root, anchor=anchor)
    try:
        record = center.notify(
            "Project dossier exported",
            level="success",
            detail="Created demo.dossier.json",
            persistent=False,
            timeout_ms=0,
        )
        root.update_idletasks()

        assert record.level == "success"
        assert center.visible is True
        assert center.level_var.get() == "SUCCESS"
        assert center.message_var.get() == "Project dossier exported"
        assert center.detail_var.get() == "Created demo.dossier.json"
        assert center.level_label.cget("style") == "CX.Status.Pass.TLabel"
        assert center.history[-1] == record

        warning = center.notify(
            "Verification evidence is stale",
            level="warning",
        )
        root.update_idletasks()
        assert warning.persistent is True
        assert center.level_var.get() == "WARNING"
        assert center._dismiss_after_id is None

        center.dismiss()
        root.update_idletasks()
        assert center.visible is False
    finally:
        root.destroy()


@pytest.fixture
def app(tmp_path):
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    callback_errors = []
    root.report_callback_exception = lambda *args: callback_errors.append(args)
    application = CleanroomXApp(
        root,
        autosave_interval_seconds=0,
        ui_state_path=tmp_path / "gui-layout.json",
    )
    application.load_project_path(bundled_demo_project_path())
    root.update()
    try:
        yield application
        assert callback_errors == []
    finally:
        root.destroy()


def test_successful_validation_uses_non_modal_notification(app, monkeypatch):
    modal_calls = []
    monkeypatch.setattr(
        "cleanroomx.gui.messagebox.showinfo",
        lambda *args, **kwargs: modal_calls.append((args, kwargs)),
    )

    app.validate_current()
    app.root.update_idletasks()

    assert modal_calls == []
    assert app.notification_center.visible is True
    assert app.notification_center.history[-1].level == "success"
    assert "Input valid" in app.notification_center.history[-1].message
    assert "Input valid" in app.status_var.get()


def test_empty_run_history_is_informational_notification(app, monkeypatch):
    app.project.metadata.pop(RUN_HISTORY_METADATA_KEY, None)
    modal_calls = []
    monkeypatch.setattr(
        "cleanroomx.gui.messagebox.showinfo",
        lambda *args, **kwargs: modal_calls.append((args, kwargs)),
    )

    assert app.show_run_history() is False
    app.root.update_idletasks()

    assert modal_calls == []
    assert app.notification_center.history[-1].level == "info"
    assert "No completed analysis runs" in app.notification_center.history[-1].message
