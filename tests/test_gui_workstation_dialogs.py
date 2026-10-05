"""Real Tk coverage for high-density workstation dialogs."""
from __future__ import annotations

import os
import tkinter as tk

import pytest

from cleanroomx.gui import (
    AnalysisPicker,
    CleanroomXApp,
    RequirementsTraceabilityDialog,
    RunHistoryDialog,
    VerificationHistoryDialog,
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



def test_verification_history_filters_retained_status_and_currency_without_recomputing():
    class Value:
        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value

    dialog = VerificationHistoryDialog.__new__(VerificationHistoryDialog)
    dialog.records = [
        {
            "sequence": 1,
            "completed_at_utc": "2026-10-01T10:00:00Z",
            "analysis_id": "room-a",
            "analysis_name": "Room A",
            "analysis_kind": "room_verification",
            "verification": {"status": "pass", "verified": True},
            "verification_identity_sha256": "a" * 64,
        },
        {
            "sequence": 2,
            "completed_at_utc": "2026-10-02T10:00:00Z",
            "analysis_id": "room-b",
            "analysis_name": "Room B",
            "analysis_kind": "room_verification",
            "verification": {"status": "fail", "verified": False},
            "verification_identity_sha256": "b" * 64,
        },
    ]
    dialog._context_by_sequence = {
        1: {"state": "current", "mismatch_reasons": []},
        2: {
            "state": "stale",
            "mismatch_reasons": ["analysis_input_changed"],
        },
    }
    dialog.search_var = Value("room a")
    dialog.status_filter_var = Value("pass")
    dialog.currency_filter_var = Value("current")

    visible = dialog._filtered_records()

    assert [item["sequence"] for item in visible] == [1]
    assert dialog._currency_text(dialog._context_by_sequence[2]) == (
        "stale (analysis_input_changed)"
    )

    dialog.search_var = Value("")
    dialog.status_filter_var = Value("All")
    dialog.currency_filter_var = Value("stale")
    assert [item["sequence"] for item in dialog._filtered_records()] == [2]



def test_requirements_traceability_filters_canonical_requirements_and_mappings(app):
    snapshot = {
        "requirement_set_count": 1,
        "requirement_count": 1,
        "mapping_count": 1,
        "active_mapping_count": 1,
        "active_mapped_requirement_count": 1,
        "requirements_sha256": "a" * 64,
        "mappings_sha256": "b" * 64,
        "requirements": [
            {
                "id": "REQ-ACH",
                "title": "Minimum air changes",
                "status": "approved",
                "applicability": "applicable",
                "scope": ["ROOM-A"],
                "criterion": "minimum=20, unit=1/h",
                "detail": {
                    "discipline": "HVAC",
                    "source": "Project Design Basis",
                },
            }
        ],
        "mappings": [
            {
                "id": "MAP-ACH",
                "requirement_title": "Minimum air changes",
                "property_name": "air_change_rate",
                "status": "active",
                "reference_state": "resolved",
                "subject_ref": "ROOM-A",
                "analysis_name": "Room A verification",
                "analysis_id": "analysis-room-a",
                "result_path": ["metrics", "air_changes_per_hour"],
                "detail": {
                    "requirement_id": "REQ-ACH",
                    "analysis_reference_state": "resolved",
                },
            }
        ],
    }

    dialog = RequirementsTraceabilityDialog(app.root, snapshot)
    app.root.update()

    assert dialog.count_var.get() == "2 of 2 traceability rows"

    dialog.type_filter_var.set("Requirement")
    app.root.update()
    assert dialog.tree.get_children(dialog.requirements_root) == (
        "requirement:REQ-ACH",
    )
    assert dialog.tree.get_children(dialog.mappings_root) == ()

    dialog.type_filter_var.set("All")
    dialog.search_var.set("room a")
    app.root.update()
    visible = (
        len(dialog.tree.get_children(dialog.requirements_root))
        + len(dialog.tree.get_children(dialog.mappings_root))
    )
    assert visible >= 1

    dialog.search_var.set("traceability-item-that-does-not-exist")
    app.root.update()
    assert dialog.count_var.get() == "0 of 2 traceability rows"
    assert dialog.tree.get_children(dialog.requirements_root) == ()
    assert dialog.tree.get_children(dialog.mappings_root) == ()

    dialog._clear_filters()
    app.root.update()
    assert dialog.count_var.get() == "2 of 2 traceability rows"
    dialog.destroy()
