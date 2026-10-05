from __future__ import annotations

from datetime import datetime, timezone
import os
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.gui_tasks import (
    EngineeringTaskCenter,
    EngineeringTaskModel,
    _progress_text,
)


def test_engineering_task_model_records_real_elapsed_and_terminal_state():
    tick = [10.0]
    model = EngineeringTaskModel(
        monotonic=lambda: tick[0],
        utc_now=lambda: datetime(2026, 10, 5, 7, 30, tzinfo=timezone.utc),
    )

    started = model.start(
        "analysis:1",
        "Run analysis — pressure study",
        detail="Backend pressure solver",
        cancellable=True,
    )
    assert started.state == "running"
    assert started.started_at_utc == "2026-10-05T07:30:00Z"
    assert started.elapsed_seconds == 0.0
    assert started.cancellable is True
    assert model.active_count() == 1

    tick[0] = 13.25
    active = model.snapshot("analysis:1")
    assert active.elapsed_seconds == pytest.approx(3.25)

    model.mark_abandon_requested("analysis:1")
    requested = model.snapshot("analysis:1")
    assert requested.state == "abandon_requested"
    assert requested.cancellable is False
    assert model.active_count() == 1

    tick[0] = 16.5
    finished = model.abandon(
        "analysis:1",
        "Backend worker finished; result ignored by operator request.",
    )
    assert finished.state == "abandoned"
    assert finished.finished is True
    assert finished.elapsed_seconds == pytest.approx(6.5)
    assert model.active_count() == 0


def test_engineering_task_model_never_invents_progress_and_clears_only_finished():
    tick = [1.0]
    model = EngineeringTaskModel(monotonic=lambda: tick[0])

    model.start("run:a", "Analysis A")
    tick[0] = 2.0
    model.start("run:b", "Analysis B")
    tick[0] = 4.0
    model.complete("run:a", "PASS")

    snapshots = {item.id: item for item in model.snapshots()}
    assert set(snapshots) == {"run:a", "run:b"}
    assert snapshots["run:a"].result == "PASS"
    assert snapshots["run:b"].result == ""
    assert not hasattr(snapshots["run:b"], "progress_percent")

    assert model.remove_finished() == 1
    assert len(model) == 1
    assert model.snapshot("run:b").state == "running"


def test_task_progress_labels_never_invent_a_percentage():
    assert _progress_text("running") == "Indeterminate"
    assert _progress_text("abandon_requested") == "Waiting for worker"
    assert _progress_text("completed") == "Complete"
    assert "%" not in _progress_text("running")


def test_engineering_task_model_rejects_duplicate_active_identifier():
    model = EngineeringTaskModel()
    model.start("same", "First")

    with pytest.raises(ValueError, match="already active"):
        model.start("same", "Second")


@pytest.mark.skipif(
    not os.environ.get("DISPLAY"),
    reason="real Tk display required",
)
def test_task_center_exposes_truthful_abandon_lifecycle():
    root = tk.Tk()
    callback_calls = []
    updates = []
    try:
        panel = EngineeringTaskCenter(
            root,
            on_change=lambda active, total: updates.append((active, total)),
        )
        panel.pack(fill="both", expand=True)
        panel.start_task(
            "analysis:7",
            "Run analysis — ACH",
            detail="ACH solver",
            cancel_callback=lambda: callback_calls.append("cancel"),
        )
        root.update()

        panel.tree.selection_set("analysis:7")
        panel._on_selected()
        assert str(panel.abandon_button["state"]) == "normal"

        panel._abandon_selected()
        root.update()
        assert callback_calls == ["cancel"]
        assert panel.model.snapshot("analysis:7").state == "abandon_requested"
        assert panel.active_count() == 1

        panel.abandon_task(
            "analysis:7",
            "Backend worker finished; result ignored by operator request.",
        )
        root.update()
        snapshot = panel.model.snapshot("analysis:7")
        assert snapshot.state == "abandoned"
        assert snapshot.finished is True
        assert updates[-1] == (0, 1)
    finally:
        root.destroy()


@pytest.mark.skipif(
    not os.environ.get("DISPLAY"),
    reason="real Tk display required",
)
def test_cleanroomx_shell_tracks_analysis_task_without_faking_backend_cancellation(tmp_path):
    root = tk.Tk()
    callback_errors = []
    root.report_callback_exception = lambda *args: callback_errors.append(args)
    app = CleanroomXApp(
        root,
        autosave_interval_seconds=0,
        ui_state_path=tmp_path / "gui-layout.json",
    )
    try:
        app.load_project_path(bundled_demo_project_path())
        root.update()
        analysis = app._editor_analysis()
        assert analysis is not None

        app._start_run_task(42, analysis)
        root.update()
        assert app.task_center.active_count() == 1
        assert app.output_notebook.tab(app.task_center, "text") == "Tasks 1"
        assert app.task_status_var.get().startswith("Tasks: 1 active")
        task = app.task_center.model.snapshot("analysis-run:42")
        assert task.state == "running"
        assert "backend solver" in task.detail

        app._mark_run_task_abandon_requested()
        root.update()
        assert app.task_center.model.snapshot("analysis-run:42").state == "abandon_requested"

        app._finish_run_task(
            "abandoned",
            "Backend worker finished; result ignored by operator request.",
        )
        root.update()
        finished = app.task_center.model.snapshot("analysis-run:42")
        assert finished.state == "abandoned"
        assert app.task_center.active_count() == 0
        assert app.output_notebook.tab(app.task_center, "text") == "Tasks"

        commands = {command.command_id for command in app._command_palette_commands()}
        assert "workspace.tasks" in commands
        assert app.analysis_tree.exists("nav-tasks")
        app.analysis_tree.selection_set("nav-tasks")
        app.analysis_tree.focus("nav-tasks")
        app.analysis_tree.event_generate("<<TreeviewSelect>>")
        root.update()
        assert app.output_notebook.select() == str(app.task_center)
        assert callback_errors == []
    finally:
        root.destroy()
