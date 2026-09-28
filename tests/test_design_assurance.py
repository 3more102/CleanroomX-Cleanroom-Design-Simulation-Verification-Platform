from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from cleanroomx.design_assurance import (
    analyze_design_assurance,
    design_assurance_from_dict,
    markdown_design_assurance_report,
)


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def _payload() -> dict:
    return json.loads(
        (EXAMPLES / "design_assurance_demo.json").read_text(encoding="utf-8")
    )


def test_reference_case_passes_and_preserves_component_traceability() -> None:
    result = analyze_design_assurance(design_assurance_from_dict(_payload()))

    assert result["status"] == "pass"
    assert result["complete"] is True
    assert result["passed"] is True
    assert result["summary"]["component_count"] == 2
    assert result["summary"]["compliance_check_count"] == 1
    assert result["summary"]["fail_count"] == 0
    pack = result["traceability"][1]["rule_pack"]
    assert pack["id"] == "project-urs-demo"
    assert len(pack["sha256"]) == 64
    json.dumps(result, sort_keys=True, allow_nan=False)


def test_missing_compliance_evidence_remains_visible_as_unchecked() -> None:
    payload = _payload()
    del payload["compliance_checks"][0]["evidence"]["rooms"]["Process"]["ach"]

    result = analyze_design_assurance(design_assurance_from_dict(payload))

    assert result["status"] == "pass_with_unchecked"
    assert result["complete"] is False
    assert result["passed"] is True
    assert result["summary"]["not_checked_count"] >= 1


def test_design_consistency_failure_dominates_aggregate_status() -> None:
    payload = _payload()
    payload["design_consistency"]["air_system"]["rooms"][0]["min_ach"] = 25

    result = analyze_design_assurance(design_assurance_from_dict(payload))

    assert result["status"] == "fail"
    assert result["passed"] is False
    assert result["summary"]["fail_count"] >= 1


def test_requires_at_least_one_compliance_check() -> None:
    payload = _payload()
    payload["compliance_checks"] = []

    with pytest.raises(ValueError, match="non-empty array"):
        design_assurance_from_dict(payload)


def test_unknown_top_level_field_fails_closed() -> None:
    payload = _payload()
    payload["implicit_standard"] = "not allowed"

    with pytest.raises(ValueError, match="unsupported design assurance input field"):
        design_assurance_from_dict(payload)


def test_engine_is_deterministic_and_does_not_mutate_input() -> None:
    payload = _payload()
    before = copy.deepcopy(payload)

    first = analyze_design_assurance(design_assurance_from_dict(payload))
    second = analyze_design_assurance(design_assurance_from_dict(payload))

    assert first == second
    assert payload == before


def test_markdown_escapes_user_controlled_content() -> None:
    payload = _payload()
    payload["name"] = "Assurance | <A>"

    report = markdown_design_assurance_report(
        analyze_design_assurance(design_assurance_from_dict(payload))
    )

    assert "Assurance \\| &lt;A&gt;" in report
    assert "not regulatory approval" in report
