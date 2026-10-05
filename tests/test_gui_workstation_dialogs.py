"""Real Tk coverage for high-density workstation dialogs."""
from __future__ import annotations

import os
import tkinter as tk

import pytest

from cleanroomx.gui import (
    AnalysisPicker,
    CleanroomXApp,
    RunHistoryDialog,
    bundled_demo_project_path,
)


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


def test_analysis_picker_filters_canonical_workflows_without_mock_entries(app):
    picker = AnalysisPicker(app.root)
    app.root.update()

    assert picker._catalog
    item = picker._catalog[0]
    picker.search_var.set(str(item["title"]))
    app.root.update()

    children = picker.tree.get_children()
    assert children
    assert item["key"] in children
    assert picker.count_var.get().endswith(
        f"of {len(picker._catalog)} workflows"
    )

    picker.category_var.set(str(item["category"]))
    app.root.update()
    for iid in picker.tree.get_children():
        assert picker.tree.set(iid, "category") == item["category"]

    picker.search_var.set("workflow-name-that-does-not-exist")
    app.root.update()
    assert picker.tree.get_children() == ()
    assert str(picker.add_button.cget("state")) == "disabled"

    picker._clear_filters()
    app.root.update()
    assert len(picker.tree.get_children()) == len(picker._catalog)
    picker.destroy()


def test_run_history_dialog_filters_retained_canonical_records_and_empty_state(app):
    app.smoke_run_active()
    app.root.update()

    dialog = RunHistoryDialog(app.root, app.project.metadata)
    app.root.update()

    assert dialog.records
    latest = dialog.records[-1]
    total = len(dialog.records)

    dialog.search_var.set(str(latest["analysis_name"]))
    dialog.status_filter_var.set(str(latest["status"]))
    app.root.update()

    children = dialog.tree.get_children()
    assert children
    for iid in children:
        record = next(
            item for item in dialog.records
            if str(item["sequence"]) == iid
        )
        assert record["status"] == latest["status"]
        assert latest["analysis_name"].casefold() in (
            str(record["analysis_name"]).casefold()
        )
    assert dialog.count_var.get().endswith(f"of {total} records")

    dialog.search_var.set("retained-record-that-does-not-exist")
    app.root.update()
    assert dialog.tree.get_children() == ()
    assert "match the active filters" in dialog.detail.get(
        "1.0", "end"
    ).casefold()

    dialog._clear_filters()
    app.root.update()
    assert len(dialog.tree.get_children()) == total
    dialog.destroy()
