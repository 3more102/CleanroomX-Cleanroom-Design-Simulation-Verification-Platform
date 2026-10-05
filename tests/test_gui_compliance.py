from __future__ import annotations

import copy
import os
import tkinter as tk

import pytest

from cleanroomx.compliance_rulepack import compliance_check_from_dict
from cleanroomx.gui import CleanroomXApp
from cleanroomx.gui_compliance import ComplianceRulePackPanel


def _payload() -> dict:
    return {
        "name": "Process suite criteria",
        "rule_pack": {
            "schema": "cleanroomx.compliance-rule-pack",
            "schema_version": 1,
            "id": "project-criteria",
            "version": "1.0",
            "title": "Project criteria",
            "source": "Project URS",
            "rules": [
                {
                    "id": "temperature",
                    "title": "Room temperature",
                    "evidence_path": "/room/temperature_c",
                    "operator": "range",
                    "expected": {"min": 20, "max": 22},
                    "unit": "degC",
                    "reference": "URS-001",
                },
                {
                    "id": "ach",
                    "title": "Minimum air changes",
                    "evidence_path": "/room/ach",
                    "operator": "min",
                    "expected": 20,
                    "unit": "1/h",
                    "reference": "URS-002",
                },
                {
                    "id": "pressure",
                    "title": "Pressure evidence exists",
                    "evidence_path": "/room/pressure_pa",
                    "operator": "exists",
                },
            ],
        },
        "evidence": {
            "room": {
                "temperature_c": 21.0,
                "ach": 18.0,
            }
        },
    }


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


def _panel(root, payload):
    state = {"payload": copy.deepcopy(payload), "edits": []}
    messages = []

    def get_input():
        return copy.deepcopy(state["payload"])

    def set_input(value, description):
        compliance_check_from_dict(copy.deepcopy(value))
        state["payload"] = copy.deepcopy(value)
        state["edits"].append(description)
        return True

    panel = ComplianceRulePackPanel(
        root,
        input_getter=get_input,
        input_setter=set_input,
        status_setter=messages.append,
        confirm_delete=lambda _rule_id: True,
    )
    panel.pack(fill="both", expand=True)
    root.update()
    return panel, state, messages


def test_compliance_panel_uses_backend_findings_and_filters(root):
    panel, _state, _messages = _panel(root, _payload())

    result = panel.refresh()
    root.update()

    assert result is not None
    assert result["summary"] == {
        "rule_count": 3,
        "pass_count": 1,
        "fail_count": 1,
        "not_checked_count": 1,
    }
    assert len(panel.tree.get_children()) == 3
    assert panel.validation_var.get() == "FAIL"
    identity = panel.identity_var.get()
    assert "Pack project-criteria v1.0" in identity
    assert "criteria SHA-256" in identity
    assert "evidence SHA-256" in identity

    panel.status_filter_var.set("Fail")
    root.update()
    children = panel.tree.get_children()
    assert len(children) == 1
    assert panel.tree.set(children[0], "id") == "ach"

    panel.clear_filters()
    panel.search_var.set("pressure")
    root.update()
    children = panel.tree.get_children()
    assert len(children) == 1
    assert panel.tree.set(children[0], "id") == "pressure"


def test_compliance_panel_edits_rule_through_validated_input_setter(root):
    panel, state, _messages = _panel(root, _payload())
    panel.refresh()
    root.update()

    panel._select_rule_id("ach")
    panel.expected_var.set("17")
    assert panel.apply_selected() is True
    root.update()

    rule = next(
        item
        for item in state["payload"]["rule_pack"]["rules"]
        if item["id"] == "ach"
    )
    assert rule["expected"] == 17
    assert state["edits"][-1] == "Edit compliance rule ach"
    assert panel.validation_var.get() == "PASS_WITH_UNCHECKED"


def test_compliance_panel_rejects_invalid_expected_without_committing(root):
    panel, state, messages = _panel(root, _payload())
    panel.refresh()
    root.update()

    panel._select_rule_id("ach")
    panel.expected_var.set("NaN")
    before = copy.deepcopy(state["payload"])

    assert panel.apply_selected() is False
    assert state["payload"] == before
    assert state["edits"] == []
    assert panel.validation_var.get() == "EDIT INVALID"
    assert any("strict JSON" in message for message in messages)


def test_compliance_panel_duplicate_and_delete_preserve_valid_pack(root):
    panel, state, _messages = _panel(root, _payload())
    panel.refresh()
    root.update()

    panel._select_rule_id("temperature")
    assert panel.duplicate_selected() is True
    root.update()

    ids = [item["id"] for item in state["payload"]["rule_pack"]["rules"]]
    assert "temperature-copy" in ids
    assert len(ids) == 4

    panel._select_rule_id("temperature-copy")
    assert panel.delete_selected() is True
    root.update()

    ids = [item["id"] for item in state["payload"]["rule_pack"]["rules"]]
    assert ids == ["temperature", "ach", "pressure"]
    compliance_check_from_dict(copy.deepcopy(state["payload"]))


def test_compliance_panel_sorts_findings_and_preserves_selected_rule(root):
    panel, _state, _messages = _panel(root, _payload())
    panel.refresh()
    root.update()

    panel._select_rule_id("temperature")
    panel._sort_by("state")
    root.update()

    children = panel.tree.get_children()
    assert [panel.tree.set(iid, "state") for iid in children] == [
        "FAIL",
        "NOT CHECKED",
        "PASS",
    ]
    selected = panel.selected_finding()
    assert selected is not None
    assert selected["id"] == "temperature"


def test_compliance_panel_cancelled_delete_does_not_mutate_input(root):
    payload = _payload()
    state = {"payload": copy.deepcopy(payload), "edits": []}
    messages = []

    panel = ComplianceRulePackPanel(
        root,
        input_getter=lambda: copy.deepcopy(state["payload"]),
        input_setter=lambda value, description: state["edits"].append(description) or True,
        status_setter=messages.append,
        confirm_delete=lambda _rule_id: False,
    )
    panel.pack(fill="both", expand=True)
    panel.refresh()
    root.update()
    panel._select_rule_id("temperature")

    assert panel.delete_selected() is False
    assert state["payload"] == payload
    assert state["edits"] == []
    assert messages[-1] == "Delete cancelled for compliance rule temperature"


def test_compliance_panel_apply_does_not_request_delete_confirmation(root):
    payload = _payload()
    state = {"payload": copy.deepcopy(payload), "edits": []}
    confirmations = []

    def set_input(value, description):
        compliance_check_from_dict(copy.deepcopy(value))
        state["payload"] = copy.deepcopy(value)
        state["edits"].append(description)
        return True

    panel = ComplianceRulePackPanel(
        root,
        input_getter=lambda: copy.deepcopy(state["payload"]),
        input_setter=set_input,
        confirm_delete=lambda rule_id: confirmations.append(rule_id) or False,
    )
    panel.pack(fill="both", expand=True)
    panel.refresh()
    root.update()

    panel._select_rule_id("ach")
    panel.expected_var.set("17")
    assert panel.apply_selected() is True
    assert confirmations == []
    assert state["edits"][-1] == "Edit compliance rule ach"


def test_opening_compliance_workspace_commits_current_editor_before_switch(root, tmp_path):
    app = CleanroomXApp(
        root,
        autosave_interval_seconds=0,
        ui_state_path=tmp_path / "gui-layout.json",
    )
    source = app.project.create_analysis(
        kind="room_verification",
        name="Source analysis",
        payload={},
    )
    target = app.project.create_analysis(
        kind="compliance_check",
        name="Project criteria",
        payload=_payload(),
    )
    app.project.active_analysis_id = source.id
    app._refresh_analysis_list(select_id=source.id)
    root.update()
    app.input_text.delete("1.0", "end")
    app.input_text.insert("1.0", '{"preserved": true}')

    app._activate_compliance_workspace()
    root.update()

    assert source.input == {"preserved": True}
    assert app.project.active_analysis_id == target.id
    assert app._editor_analysis_id == target.id
    assert app.notebook.select() == str(app.compliance_panel)


def test_opening_compliance_workspace_blocks_switch_on_invalid_current_json(root, tmp_path):
    app = CleanroomXApp(
        root,
        autosave_interval_seconds=0,
        ui_state_path=tmp_path / "gui-layout.json",
    )
    source = app.project.create_analysis(
        kind="room_verification",
        name="Source analysis",
        payload={},
    )
    app.project.create_analysis(
        kind="compliance_check",
        name="Project criteria",
        payload=_payload(),
    )
    app.project.active_analysis_id = source.id
    app._refresh_analysis_list(select_id=source.id)
    root.update()
    app.input_text.delete("1.0", "end")
    app.input_text.insert("1.0", "{broken")

    app._activate_compliance_workspace()
    root.update()

    assert app.project.active_analysis_id == source.id
    assert app._editor_analysis_id == source.id
    assert app.input_text.get("1.0", "end-1c") == "{broken"
    assert app.status_var.get().startswith(
        "Cannot open compliance manager until current input is valid:"
    )
