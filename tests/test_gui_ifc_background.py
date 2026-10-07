from __future__ import annotations

import os
import threading
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp


class _Status:
    def __init__(self) -> None:
        self.value = ""

    def set(self, value: str) -> None:
        self.value = value


@pytest.fixture
def tk_root():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    try:
        yield root
    finally:
        root.destroy()


def test_ifc_background_task_runs_operation_off_tk_thread(tk_root) -> None:
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = tk_root
    app.status_var = _Status()
    tk_thread = threading.get_ident()
    worker_threads: list[int] = []

    def operation() -> str:
        worker_threads.append(threading.get_ident())
        return "complete"

    result = app._run_ifc_background_task("Reading IFC test model…", operation)

    assert result == "complete"
    assert worker_threads
    assert worker_threads[0] != tk_thread


def test_ifc_background_task_surfaces_worker_exception(tk_root) -> None:
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = tk_root
    app.status_var = _Status()

    def operation():
        raise ValueError("synthetic IFC parser failure")

    with pytest.raises(ValueError, match="synthetic IFC parser failure"):
        app._run_ifc_background_task("Reading broken IFC test model…", operation)
