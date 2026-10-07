from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

import cleanroomx.gui_constraints as constraints
import cleanroomx.gui_requirements as requirements
from cleanroomx.gui_compliance import ComplianceRulePackPanel


class Variable:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


INVALID_JSON = [
    '{"x": 1, "x": 2}',
    '[{"x": 1, "x": 2}]',
    'NaN', 'Infinity', '-Infinity', '1e999',
    '"\\ud800"', '[' * 2000 + '0' + ']' * 2000, '{',
]


def _dialog(surface, text="7", tolerance="0"):
    destroyed = []
    if surface == "constraint":
        fields = {key: "" for key in ("unit", "source", "reference")}
        fields.update(id="rule", title="Rule", evidence_path="/value", expected=text, tolerance=tolerance)
        dialog = SimpleNamespace(vars={key: Variable(value) for key, value in fields.items()},
                                 operator_var=Variable("equals"), result=None,
                                 destroy=lambda: destroyed.append(True))
        accept = constraints._RuleDialog._accept
    else:
        fields = {key: "" for key in ("reference", "unit", "scope", "verification_method",
                                       "required_evidence", "assumptions", "notes")}
        fields.update({key: key for key in ("id", "title", "description", "discipline", "category",
                                            "source", "source_revision")})
        dialog = SimpleNamespace(vars={key: Variable(value) for key, value in fields.items()},
                                 criterion_mode=Variable("target"), target_var=Variable(text),
                                 minimum_var=Variable(), maximum_var=Variable(),
                                 tolerance_var=Variable(tolerance), applicability_var=Variable("applicable"),
                                 status_var=Variable("draft"), result=None,
                                 destroy=lambda: destroyed.append(True))
        accept = requirements._RequirementDialog._accept
    return dialog, accept, destroyed


@pytest.mark.parametrize("surface", ["constraint", "requirement"])
@pytest.mark.parametrize("text", INVALID_JSON)
def test_edit_dialog_rejects_ambiguous_or_non_strict_json_without_closing(monkeypatch, surface, text):
    errors = []
    monkeypatch.setattr(constraints.messagebox, "showerror", lambda title, message, **kwargs: errors.append(message))
    dialog, accept, destroyed = _dialog(surface, text)
    accept(dialog)
    assert dialog.result is None
    assert destroyed == []
    assert len(errors) == 1
    assert ("Expected" if surface == "constraint" else "Target") in errors[0]


@pytest.mark.parametrize("surface", ["constraint", "requirement"])
@pytest.mark.parametrize("text", ["nan", "inf", "-inf", "1e999"])
def test_edit_dialog_rejects_non_finite_tolerance_before_closing(monkeypatch, surface, text):
    errors = []
    monkeypatch.setattr(constraints.messagebox, "showerror", lambda title, message, **kwargs: errors.append(message))
    dialog, accept, destroyed = _dialog(surface, tolerance=text)
    accept(dialog)
    assert dialog.result is None
    assert destroyed == []
    assert "finite" in errors[0]


@pytest.mark.parametrize("surface", ["constraint", "requirement"])
def test_edit_dialog_accepts_valid_nested_json_and_closes(monkeypatch, surface):
    monkeypatch.setattr(constraints.messagebox, "showerror", lambda *args, **kwargs: pytest.fail("unexpected rejection"))
    dialog, accept, destroyed = _dialog(surface, '{"x": [1, true, null, "é"]}', "0.25")
    accept(dialog)
    assert dialog.result["expected" if surface == "constraint" else "target"] == {"x": [1, True, None, "é"]}
    assert dialog.result["tolerance"] == 0.25
    assert destroyed == [True]


@pytest.mark.parametrize("field", ["minimum_var", "maximum_var"])
def test_requirement_bounds_reject_non_finite_numbers(monkeypatch, field):
    errors = []
    monkeypatch.setattr(requirements.messagebox, "showerror", lambda title, message, **kwargs: errors.append(message))
    dialog, accept, destroyed = _dialog("requirement")
    dialog.criterion_mode.set("bounds")
    getattr(dialog, field).set("1e999")
    accept(dialog)
    assert dialog.result is None
    assert not destroyed
    assert "finite" in errors[0]


@pytest.mark.parametrize("text", INVALID_JSON)
def test_compliance_panel_rejection_preserves_inputs_and_does_not_publish(text):
    payload = {"rule_pack": {"rules": [{"id": "rule", "expected": 7}]}, "evidence": {"value": 7}}
    before = copy.deepcopy(payload)
    published, statuses = [], []
    panel = SimpleNamespace(_payload=payload, selected_finding=lambda: {"id": "rule"},
                            _input_setter=lambda *args: published.append(args),
                            _status_setter=statuses.append, validation_var=Variable(),
                            title_var=Variable("Rule"), path_var=Variable("/value"),
                            operator_var=Variable("equals"), tolerance_var=Variable("0"),
                            expected_var=Variable(text), unit_var=Variable(), source_var=Variable(),
                            reference_var=Variable())
    panel._candidate_from_editor = lambda: ComplianceRulePackPanel._candidate_from_editor(panel)
    assert ComplianceRulePackPanel.apply_selected(panel) is False
    assert payload == before
    assert published == []
    assert panel.validation_var.get() == "EDIT INVALID"
    assert "expected" in statuses[0]
