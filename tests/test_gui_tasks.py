from __future__ import annotations

import os
import tkinter as tk

import pytest

from cleanroomx.gui_tasks import TaskCenter, format_duration


def test_format_duration_is_compact_and_deterministic():
    assert format_duration(0) == "00:00"
    assert format_duration(65) == "01:05"
    assert format_duration(3661) == "1:01:01"


@pytest.fixture
def root():
    try:
        window = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    window.withdraw()
    try:
        yield window
    finally:
        window.destroy()


def test_task_center_tracks_real_states_without_fake_progress(root):
    panel = TaskCenter(root)
    panel.pack(fill="both", expand=True)
    root.update()

    record = panel.start_task(
        "analysis:1",
        "Analysis · Demo",
        message="Backend workflow: room_verification",
    )
    root.update()

    assert record.state == "running"
    assert record.progress == "Indeterminate"
    assert panel.running_count() == 1
    assert panel.tree.set("analysis:1", "state") == "Running"
    assert panel.tree.set("analysis:1", "progress") == "Indeterminate"

    panel.mark_abandon_requested("analysis:1", "Waiting for worker exit.")
    root.update()
    assert record.state == "running"
    assert record.progress == "Abandon requested"
    assert "Waiting for worker exit." in panel.detail.get("1.0", "end")

    panel.finish_task(
        "analysis:1",
        "abandoned",
        result="Worker exited after abandon request",
    )
    root.update()
    assert record.state == "abandoned"
    assert record.progress == "Complete"
    assert panel.running_count() == 0
    assert "none running" in panel.summary_var.get()


def test_task_center_clear_finished_preserves_running_work(root):
    panel = TaskCenter(root)
    panel.start_task("running", "Running task")
    panel.start_task("done", "Finished task")
    panel.finish_task("done", "completed", result="PASS")
    root.update()

    panel.clear_finished()
    root.update()

    assert panel.record("running") is not None
    assert panel.record("done") is None
    assert panel.tree.exists("running")
    assert not panel.tree.exists("done")
