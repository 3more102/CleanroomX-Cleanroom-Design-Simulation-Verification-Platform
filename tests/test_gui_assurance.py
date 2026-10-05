from __future__ import annotations

import os
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.gui_assurance import (
    EvidenceWorkspace,
    VerificationWorkspace,
    evidence_record_matches_filters,
    evidence_record_projection,
    verification_summary_projection,
)
from cleanroomx.gui_theme import configure_ttk_theme


def test_verification_summary_projection_never_invents_current_state():
    missing = verification_summary_projection({})
    assert missing["state"] == "not configured"
    assert missing["current"] == 0

    stale = verification_summary_projection(
        {
            "summary": {
                "configured_analysis_count": 3,
                "current_count": 2,
                "stale_count": 1,
                "dependency_freshness_unverifiable_count": 0,
                "not_verified_count": 0,
            }
        }
    )
    assert stale["state"] == "stale"
    assert stale["current"] == 2

    current = verification_summary_projection(
        {
            "summary": {
                "configured_analysis_count": 2,
                "current_count": 2,
                "stale_count": 0,
                "dependency_freshness_unverifiable_count": 0,
                "not_verified_count": 0,
            }
        }
    )
    assert current["state"] == "current"


def test_evidence_record_projection_separates_historical_verdict_from_currency():
    record = {
        "sequence": 7,
        "completed_at_utc": "2026-10-05T06:00:00Z",
        "analysis_id": "a1",
        "analysis_name": "Pressure",
        "analysis_kind": "project_verification",
        "verification": {
            "status": "pass",
            "verified": True,
            "complete": True,
            "findings": [{}, {}],
        },
        "evidence": [{}, {}, {}],
        "record_sha256": "abc",
        "project_source_revision": "def",
    }
    latest = evidence_record_projection(
        record,
        {"analysis_id": "a1", "state": "stale", "latest_record": {"sequence": 7}},
    )
    assert latest["verification_status"] == "pass"
    assert latest["currency_state"] == "stale"
    assert latest["evidence_count"] == 3
    assert latest["finding_count"] == 2

    historical = evidence_record_projection(
        record,
        {"analysis_id": "a1", "state": "current", "latest_record": {"sequence": 8}},
    )
    assert historical["currency_state"] == "historical"


def test_evidence_record_filters_match_only_explicit_ledger_fields():
    row = {
        "sequence": 12,
        "completed_at_utc": "2026-10-05T08:00:00Z",
        "analysis_id": "pressure-a",
        "analysis_name": "Pressure cascade",
        "analysis_kind": "pressure_verification",
        "verification_status": "pass",
        "currency_state": "stale",
        "record_sha256": "abc123",
        "source_revision": "rev456",
    }

    assert evidence_record_matches_filters(row)
    assert evidence_record_matches_filters(row, verdict="PASS")
    assert evidence_record_matches_filters(row, currency="STALE")
    assert evidence_record_matches_filters(row, query="pressure abc123")
    assert not evidence_record_matches_filters(row, verdict="fail")
    assert not evidence_record_matches_filters(row, currency="current")
    assert not evidence_record_matches_filters(row, query="airflow")


def test_evidence_workspace_filters_retained_records_without_changing_total_count():
    root = _root()
    workspace = EvidenceWorkspace(
        root,
        on_history=lambda: None,
        on_proofgraph=lambda: None,
        on_report=lambda: None,
    )
    try:
        records = [
            {
                "sequence": 1,
                "completed_at_utc": "2026-10-05T07:00:00Z",
                "analysis_id": "a1",
                "analysis_name": "Pressure",
                "analysis_kind": "pressure_verification",
                "verification": {"status": "pass", "verified": True, "complete": True},
                "evidence": [{}],
            },
            {
                "sequence": 2,
                "completed_at_utc": "2026-10-05T08:00:00Z",
                "analysis_id": "a2",
                "analysis_name": "Airflow",
                "analysis_kind": "airflow_verification",
                "verification": {"status": "fail", "verified": False, "complete": True},
                "evidence": [{}, {}],
            },
        ]
        currency = {
            "analyses": [
                {"analysis_id": "a1", "state": "stale", "latest_record": {"sequence": 1}},
                {"analysis_id": "a2", "state": "current", "latest_record": {"sequence": 2}},
            ]
        }
        workspace.refresh(records, proofgraph_count=1, currency=currency)
        root.update_idletasks()

        assert workspace.record_count_var.get() == "2"
        assert workspace.visible_var.get() == "2 / 2 visible"

        workspace.verdict_filter_var.set("fail")
        root.update_idletasks()
        assert workspace.record_count_var.get() == "2"
        assert workspace.visible_var.get() == "1 / 2 visible"
        assert len(workspace.tree.get_children()) == 1
        assert "Airflow" in workspace.detail.get("1.0", "end")

        workspace.verdict_filter_var.set("All")
        workspace.currency_filter_var.set("stale")
        root.update_idletasks()
        assert workspace.visible_var.get() == "1 / 2 visible"
        assert "Pressure" in workspace.detail.get("1.0", "end")

        workspace.search_var.set("does-not-exist")
        root.update_idletasks()
        assert workspace.visible_var.get() == "0 / 2 visible"
        assert "match the current evidence filters" in workspace.detail.get("1.0", "end")
    finally:
        root.destroy()


def _root():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    configure_ttk_theme(root, "dark")
    return root


def test_assurance_widgets_present_explicit_currency_and_evidence():
    root = _root()
    verification = VerificationWorkspace(
        root,
        on_verify=lambda: None,
        on_persist=lambda: None,
        on_traceability=lambda: None,
        on_history=lambda: None,
        on_problems=lambda: None,
        on_proofgraph=lambda: None,
    )
    evidence = EvidenceWorkspace(
        root,
        on_history=lambda: None,
        on_proofgraph=lambda: None,
        on_report=lambda: None,
    )
    try:
        currency = {
            "summary": {
                "configured_analysis_count": 1,
                "current_count": 0,
                "stale_count": 1,
                "dependency_freshness_unverifiable_count": 0,
                "not_verified_count": 0,
                "not_configured_count": 0,
            },
            "analyses": [
                {
                    "analysis_id": "a1",
                    "analysis_name": "Room verification",
                    "analysis_kind": "room_verification",
                    "state": "stale",
                    "external_dependency_count": 0,
                    "active_mapping_ids": ["m1"],
                    "mismatch_reasons": ["analysis_input_changed"],
                    "explanation": "Latest evidence does not match current input.",
                    "current_identity": {
                        "analysis_input_sha256": "input",
                        "requirements_sha256": "req",
                        "mappings_sha256": "map",
                    },
                    "latest_record": {
                        "sequence": 4,
                        "completed_at_utc": "2026-10-05T06:00:00Z",
                        "verification_status": "pass",
                        "verification_complete": True,
                        "record_sha256": "record",
                    },
                }
            ],
        }
        verification.refresh(currency)
        evidence.refresh(
            [
                {
                    "sequence": 4,
                    "completed_at_utc": "2026-10-05T06:00:00Z",
                    "analysis_id": "a1",
                    "analysis_name": "Room verification",
                    "analysis_kind": "room_verification",
                    "verification": {
                        "status": "pass",
                        "verified": True,
                        "complete": True,
                        "findings": [{}],
                    },
                    "evidence": [{}, {}],
                    "record_sha256": "record",
                    "project_source_revision": "project",
                }
            ],
            proofgraph_count=2,
            currency=currency,
        )
        root.update_idletasks()

        assert verification.state_var.get() == "STALE"
        assert verification.tree.get_children()
        assert "analysis_input_changed" in verification.detail.get("1.0", "end")
        assert evidence.record_count_var.get() == "1"
        assert evidence.proofgraph_count_var.get() == "2"
        assert evidence.currency_var.get() == "STALE"
        assert "historical verdict" in evidence.detail.get("1.0", "end").lower()
    finally:
        root.destroy()


@pytest.fixture
def app(tmp_path):
    root = _root()
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


def test_navigator_routes_verification_and_evidence_to_first_class_workspaces(app):
    app.analysis_tree.selection_set("nav-verification")
    app.analysis_tree.focus("nav-verification")
    app._on_navigator_selected()
    app.root.update_idletasks()
    assert app.notebook.select() == str(app.verification_workspace)

    app.analysis_tree.selection_set("nav-evidence")
    app.analysis_tree.focus("nav-evidence")
    app._on_navigator_selected()
    app.root.update_idletasks()
    assert app.notebook.select() == str(app.evidence_workspace)
