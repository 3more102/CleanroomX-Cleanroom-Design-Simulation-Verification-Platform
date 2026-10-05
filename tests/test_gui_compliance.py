from __future__ import annotations

import os
from types import SimpleNamespace
import tkinter as tk

import pytest

from cleanroomx.compliance_rulepack import (
    RULE_PACK_SCHEMA,
    RULE_PACK_SCHEMA_VERSION,
    analyze_compliance_check,
    compliance_check_from_dict,
)
from cleanroomx.gui import CleanroomXApp
from cleanroomx.gui_compliance import (
    ComplianceWorkspace,
    compliance_input_projection,
    compliance_result_projection,
)


def _payload() -> dict:
    return {
        "name": "Project criteria",
        "rule_pack": {
            "schema": RULE_PACK_SCHEMA,
            "schema_version": RULE_PACK_SCHEMA_VERSION,
            "id": "project-criteria",
            "version": "2.1",
            "title": "Project URS criteria",
            "source": "Owner-approved project criteria",
            "rules": [
                {
                    "id": "ach",
                    "title": "Minimum air changes",
                    "evidence_path": "/rooms/Process/ach",
                    "operator": "min",
                    "expected": 20,
                    "unit": "1/h",
                    "tolerance": 0.5,
                    "reference": "URS-HVAC-004",
                },
                {
                    "id": "mode",
                    "title": "Operating mode",
                    "evidence_path": "/rooms/Process/mode",
                    "operator": "one_of",
                    "expected": ["at_rest", "operational"],
                },
            ],
        },
        "evidence": {
            "rooms": {
                "Process": {
                    "ach": 21.0,
                    "mode": "operational",
                }
            }
        },
    }


def test_compliance_input_projection_uses_canonical_parser() -> None:
    projected = compliance_input_projection(_payload())

    assert projected["valid"] is True
    assert projected["pack"] == {
        "id": "project-criteria",
        "version": "2.1",
        "title": "Project URS criteria",
        "source": "Owner-approved project criteria",
    }
    assert projected["rules"][0]["id"] == "ach"
    assert projected["rules"][0]["tolerance"] == 0.5
    assert projected["rules"][0]["unit"] == "1/h"
    assert projected["rules"][0]["reference"] == "URS-HVAC-004"


def test_compliance_input_projection_fails_closed_for_invalid_rule_pack() -> None:
    payload = _payload()
    payload["rule_pack"]["rules"][0]["operator"] = "approximately"

    projected = compliance_input_projection(payload)

    assert projected["valid"] is False
    assert projected["rules"] == []
    assert "operator" in projected["error"]


def test_compliance_result_projection_does_not_invent_a_run() -> None:
    projected = compliance_result_projection(None)

    assert projected["available"] is False
    assert projected["status"] == "not_run"
    assert projected["complete"] is None
    assert projected["verified"] is None
    assert projected["findings"] == []


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


def _workspace(root: tk.Tk) -> ComplianceWorkspace:
    workspace = ComplianceWorkspace(
        root,
        on_run=lambda: None,
        on_validate=lambda: None,
        on_open_inputs=lambda: None,
        on_open_results=lambda: None,
        on_open_history=lambda: None,
        on_open_traceability=lambda: None,
        on_select_analysis=lambda _analysis_id: None,
    )
    workspace.pack(fill="both", expand=True)
    return workspace


def test_compliance_workspace_displays_canonical_findings(root) -> None:
    payload = _payload()
    result = analyze_compliance_check(compliance_check_from_dict(payload))
    workspace = _workspace(root)

    workspace.set_analysis_options(
        (("check-1", "Process compliance"),),
        active_id="check-1",
    )
    workspace.set_context(
        analysis_name="Process compliance",
        analysis_input=payload,
        last_run=SimpleNamespace(result=result),
        running=False,
    )
    root.update_idletasks()

    assert workspace.state_var.get() == "PASS"
    assert "2 pass" in workspace.summary_var.get()
    rows = list(workspace.tree.get_children())
    assert len(rows) == 2
    assert workspace.tree.set(rows[0], "status") == "PASS"
    assert workspace.tree.set(rows[0], "actual") == "21.0"
    assert "Owner-approved project criteria" in workspace.source_var.get()
    assert result["rule_pack"]["sha256"] in workspace.digest_var.get()
    assert result["evidence_sha256"] in workspace.digest_var.get()


def test_compliance_workspace_keeps_missing_evidence_not_checked(root) -> None:
    payload = _payload()
    del payload["evidence"]["rooms"]["Process"]["mode"]
    result = analyze_compliance_check(compliance_check_from_dict(payload))
    workspace = _workspace(root)

    workspace.set_context(
        analysis_name="Process compliance",
        analysis_input=payload,
        last_run=SimpleNamespace(result=result),
        running=False,
    )
    root.update_idletasks()

    assert workspace.state_var.get() == "PASS WITH UNCHECKED"
    assert "1 not checked" in workspace.summary_var.get()
    rows = list(workspace.tree.get_children())
    states = {workspace.tree.set(iid, "id"): workspace.tree.set(iid, "status") for iid in rows}
    assert states["mode"] == "NOT CHECKED"


def test_compliance_workspace_never_derives_result_from_input_only(root) -> None:
    workspace = _workspace(root)

    workspace.set_context(
        analysis_name="Process compliance",
        analysis_input=_payload(),
        last_run=None,
        running=False,
    )
    root.update_idletasks()

    assert workspace.state_var.get() == "NOT RUN"
    assert workspace.summary_var.get() == "No current-session canonical compliance result"
    rows = list(workspace.tree.get_children())
    assert all(workspace.tree.set(iid, "status") == "NOT RUN" for iid in rows)


def test_navigator_and_command_palette_open_compliance_workspace(root, tmp_path) -> None:
    app = CleanroomXApp(
        root,
        autosave_interval_seconds=0,
        ui_state_path=tmp_path / "gui-layout.json",
    )
    root.update()

    assert app.analysis_tree.exists("nav-compliance")
    app.analysis_tree.selection_set("nav-compliance")
    app.analysis_tree.focus("nav-compliance")
    app._on_navigator_selected()
    root.update_idletasks()

    assert app.notebook.select() == str(app.compliance_workspace)
    assert app.workspace_status_var.get() == "Workspace: Compliance Rule Packs"
    assert app.selection_status_var.get() == "Selected: Compliance Rule Packs"

    commands = {item.command_id: item for item in app._command_palette_commands()}
    assert "compliance.open" in commands
