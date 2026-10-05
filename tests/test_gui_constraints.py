from __future__ import annotations

import copy

import pytest

import cleanroomx.gui_constraints as gui_constraints_module

from cleanroomx.project import ProjectDocument, project_from_dict
from cleanroomx.gui_constraints import (
    ConstraintManagerDialog,
    add_constraint_rule,
    constraint_sets_snapshot,
    create_constraint_set,
    remove_constraint_rule,
    update_constraint_rule,
    update_constraint_set,
)


def _rule(rule_id: str = "ach") -> dict:
    return {
        "id": rule_id,
        "title": "Minimum air changes",
        "evidence_path": "/rooms/Process/ach",
        "operator": "min",
        "expected": 20,
        "unit": "1/h",
        "tolerance": 0.5,
        "reference": "URS-HVAC-004",
    }


def _project_with_constraints() -> tuple[ProjectDocument, str]:
    project = ProjectDocument(name="Constraint project")
    analysis_id = create_constraint_set(
        project,
        analysis_name="Process room criteria",
        pack_id="process-room",
        version="1.0",
        title="Process room constraints",
        source="Owner-approved URS",
        first_rule=_rule(),
    )
    return project, analysis_id


def test_constraint_set_is_canonical_project_analysis_and_round_trips() -> None:
    project, analysis_id = _project_with_constraints()

    snapshot = constraint_sets_snapshot(project)

    assert len(snapshot) == 1
    assert snapshot[0]["analysis_id"] == analysis_id
    assert snapshot[0]["valid"] is True
    assert snapshot[0]["pack"] == {
        "id": "process-room",
        "version": "1.0",
        "title": "Process room constraints",
        "source": "Owner-approved URS",
    }
    assert snapshot[0]["rules"][0]["id"] == "ach"
    assert snapshot[0]["rules"][0]["tolerance"] == 0.5

    document = project.to_dict()
    restored = project_from_dict(copy.deepcopy(document))
    assert restored.to_dict() == document
    assert constraint_sets_snapshot(restored) == snapshot


def test_constraint_set_and_rule_edits_are_validated_before_mutation() -> None:
    project, analysis_id = _project_with_constraints()
    before = copy.deepcopy(project.to_dict())

    with pytest.raises(ValueError, match="operator must be one of"):
        add_constraint_rule(
            project,
            analysis_id,
            {
                **_rule("bad"),
                "operator": "approximately",
            },
        )

    assert project.to_dict() == before

    add_constraint_rule(
        project,
        analysis_id,
        {
            "id": "temperature",
            "title": "Room temperature",
            "evidence_path": "/rooms/Process/temperature_c",
            "operator": "range",
            "expected": {"min": 20, "max": 22},
            "unit": "degC",
            "tolerance": 0.25,
        },
    )
    update_constraint_rule(
        project,
        analysis_id,
        "ach",
        {
            **_rule(),
            "expected": 25,
            "tolerance": 1.0,
        },
    )
    update_constraint_set(
        project,
        analysis_id,
        analysis_name="Approved process criteria",
        pack_id="process-room",
        version="2.0",
        title="Approved process room constraints",
        source="URS Rev D",
    )

    snapshot = constraint_sets_snapshot(project)[0]
    assert snapshot["analysis_name"] == "Approved process criteria"
    assert snapshot["pack"]["version"] == "2.0"
    by_id = {rule["id"]: rule for rule in snapshot["rules"]}
    assert by_id["ach"]["expected"] == 25.0
    assert by_id["ach"]["tolerance"] == 1.0
    assert by_id["temperature"]["expected"] == {"min": 20.0, "max": 22.0}


def test_constraint_rule_delete_refuses_to_leave_invalid_empty_pack() -> None:
    project, analysis_id = _project_with_constraints()
    before = copy.deepcopy(project.to_dict())

    with pytest.raises(ValueError, match="retain at least one rule"):
        remove_constraint_rule(project, analysis_id, "ach")

    assert project.to_dict() == before


def test_constraint_rule_delete_preserves_remaining_valid_pack() -> None:
    project, analysis_id = _project_with_constraints()
    add_constraint_rule(
        project,
        analysis_id,
        {
            "id": "mode",
            "title": "Operating mode",
            "evidence_path": "/rooms/Process/mode",
            "operator": "one_of",
            "expected": ["at_rest", "operational"],
        },
    )

    remove_constraint_rule(project, analysis_id, "ach")

    snapshot = constraint_sets_snapshot(project)[0]
    assert [rule["id"] for rule in snapshot["rules"]] == ["mode"]


def test_constraint_snapshot_surfaces_invalid_existing_input_without_crashing() -> None:
    project = ProjectDocument(name="Legacy invalid constraint")
    analysis = project.create_analysis(
        kind="compliance_check",
        name="Broken criteria",
        payload={
            "name": "Broken criteria",
            "rule_pack": {
                "schema": "cleanroomx.compliance-rule-pack",
                "schema_version": 1,
                "id": "broken",
                "version": "1",
                "title": "Broken",
                "source": "Test",
                "rules": [],
            },
            "evidence": {},
        },
    )

    snapshot = constraint_sets_snapshot(project)

    assert snapshot[0]["analysis_id"] == analysis.id
    assert snapshot[0]["valid"] is False
    assert snapshot[0]["rules"] == []
    assert "non-empty array" in snapshot[0]["error"]

def test_constraint_editor_records_unexpected_apply_failures(monkeypatch) -> None:
    dialog = ConstraintManagerDialog.__new__(ConstraintManagerDialog)

    def fail_apply(_description, _mutation):
        raise RuntimeError("synthetic constraint editor failure")

    dialog._apply_project_edit = fail_apply
    incidents = []
    messages = []

    class Report:
        def user_message(self):
            return "Constraint editor failed.\n\nError reference: CX-CONSTRAINT"

    def record(operation, exc):
        incidents.append((operation, type(exc).__name__, str(exc)))
        return Report()

    monkeypatch.setattr(gui_constraints_module, "record_gui_exception", record)
    monkeypatch.setattr(
        gui_constraints_module.messagebox,
        "showerror",
        lambda title, message, **kwargs: messages.append((title, message)),
    )

    assert dialog._apply("Update rule", lambda _project: None) is False
    assert incidents == [
        (
            "Constraint editor: Update rule",
            "RuntimeError",
            "synthetic constraint editor failure",
        )
    ]
    assert messages == [
        (
            "Constraint update failed",
            "Constraint editor failed.\n\nError reference: CX-CONSTRAINT",
        )
    ]


def test_constraint_editor_keeps_validation_failures_user_facing(monkeypatch) -> None:
    dialog = ConstraintManagerDialog.__new__(ConstraintManagerDialog)

    def fail_apply(_description, _mutation):
        raise ValueError("minimum must be positive")

    dialog._apply_project_edit = fail_apply
    messages = []
    monkeypatch.setattr(
        gui_constraints_module,
        "record_gui_exception",
        lambda *_args, **_kwargs: pytest.fail("validation error must not become incident"),
    )
    monkeypatch.setattr(
        gui_constraints_module.messagebox,
        "showerror",
        lambda title, message, **kwargs: messages.append((title, message)),
    )

    assert dialog._apply("Update rule", lambda _project: None) is False
    assert messages == [("Constraint update failed", "minimum must be positive")]
