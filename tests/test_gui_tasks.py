from __future__ import annotations

import os
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.gui_tasks import (
    TaskCenter,
    execution_progress_label,
    format_task_duration,
    normalize_task_state,
    task_state_style,
)
from cleanroomx.gui_theme import configure_ttk_theme


def test_task_projection_never_invents_numeric_progress():
    assert normalize_task_state("success") == "completed"
    assert normalize_task_state("cancel requested") == "abandon requested"
    assert execution_progress_label("running") == "Indeterminate"
    assert execution_progress_label("finalizing") == "Indeterminate"
    assert execution_progress_label("completed") == "Complete"
    assert execution_progress_label("failed") == "Stopped"
    assert task_state_style("completed") == "CX.Status.Pass.TLabel"
    assert task_state_style("failed") == "CX.Status.Fail.TLabel"
    assert format_task_duration(3.24) == "3.2 s"
    assert format_task_duration(65.2) == "1m 05.2s"


def test_task_center_separates_execution_state_from_engineering_result():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    configure_ttk_theme(root, "dark")
    center = TaskCenter(root)
    try:
        center.start_task(
            "analysis:1",
            "Pressure Cascade",
            category="Analysis",
            stage="Executing pressure solver",
            started_at="10:15:00",
        )
        center.update_task(
            "analysis:1",
            state="finalizing",
            stage="Finalizing run-history evidence",
            duration_seconds=2.3,
        )
        center.update_task(
            "analysis:1",
            state="completed",
            stage="Result accepted into current session",
            duration_seconds=2.8,
            result="FAIL",
            detail="Execution completed; the engineering result failed its own criteria.",
        )
        root.update_idletasks()

        record = center.records[0]
        assert record.state == "completed"
        assert record.result == "FAIL"
        assert record.progress == "Complete"
        assert center.tree.set("analysis:1", "state") == "COMPLETED"
        assert center.tree.set("analysis:1", "result") == "FAIL"
        center.tree.selection_set("analysis:1")
        center._sync_detail()
        assert "Execution state: COMPLETED" in center.detail_var.get()
        assert "Engineering/result status: FAIL" in center.detail_var.get()
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


def test_application_exposes_task_center_and_controller_lifecycle(app):
    assert "Tasks" in [
        app.output_notebook.tab(tab_id, "text")
        for tab_id in app.output_notebook.tabs()
    ]

    app.task_center.start_task(
        "analysis:test",
        "Test analysis",
        category="Analysis",
        stage="Executing backend",
        started_at="10:00:00",
    )
    app._active_run_task_id = "analysis:test"
    app._run_started_monotonic = None
    app._update_active_run_task(
        state="finalizing",
        stage="Finalizing evidence",
        duration_seconds=1.25,
    )
    app._finish_active_run_task(
        state="completed",
        stage="Result accepted",
        result="PASS",
        detail="Controller accepted the current result.",
    )

    record = app.task_center.records[0]
    assert record.state == "completed"
    assert record.stage == "Result accepted"
    assert record.result == "PASS"
    assert app._active_run_task_id is None

    app.show_task_center()
    app.root.update_idletasks()
    assert app.output_notebook.select() == str(app.task_center)
    assert app.output_panel_visible_var.get() is True
