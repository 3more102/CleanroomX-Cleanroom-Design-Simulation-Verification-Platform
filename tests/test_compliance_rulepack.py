from __future__ import annotations

import copy
import json

import pytest

from cleanroomx.compliance_rulepack import (
    RULE_PACK_SCHEMA,
    RULE_PACK_SCHEMA_VERSION,
    analyze_compliance_check,
    compliance_check_from_dict,
    markdown_compliance_report,
)


def _payload() -> dict:
    return {
        "name": "Process suite project criteria",
        "rule_pack": {
            "schema": RULE_PACK_SCHEMA,
            "schema_version": RULE_PACK_SCHEMA_VERSION,
            "id": "project-urs-demo",
            "version": "1.0",
            "title": "Project URS demonstration criteria",
            "source": "Example project criteria only; not a regulatory standard",
            "rules": [
                {
                    "id": "temperature",
                    "title": "Room temperature",
                    "evidence_path": "/rooms/Process/temperature_c",
                    "operator": "range",
                    "expected": {"min": 20, "max": 22},
                    "unit": "degC",
                    "reference": "URS-ENV-001",
                },
                {
                    "id": "ach",
                    "title": "Minimum air changes",
                    "evidence_path": "/rooms/Process/ach",
                    "operator": "min",
                    "expected": 20,
                    "unit": "1/h",
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
                    "temperature_c": 21.0,
                    "ach": 22.0,
                    "mode": "operational",
                }
            }
        },
    }


def test_reference_case_passes_and_preserves_rule_pack_digest() -> None:
    result = analyze_compliance_check(compliance_check_from_dict(_payload()))

    assert result["status"] == "pass"
    assert result["complete"] is True
    assert result["verified"] is True
    assert result["no_failures_detected"] is True
    assert result["passed"] is True
    assert result["summary"] == {
        "rule_count": 3,
        "pass_count": 3,
        "fail_count": 0,
        "not_checked_count": 0,
    }
    assert len(result["rule_pack"]["sha256"]) == 64
    assert len(result["evidence_sha256"]) == 64
    json.dumps(result, sort_keys=True, allow_nan=False)


def test_evidence_digest_binds_the_exact_supplied_evidence_revision() -> None:
    payload = _payload()
    baseline = analyze_compliance_check(compliance_check_from_dict(payload))

    changed = copy.deepcopy(payload)
    changed["evidence"]["source_revision"] = "B"
    revised = analyze_compliance_check(compliance_check_from_dict(changed))

    assert baseline["status"] == revised["status"] == "pass"
    assert baseline["rule_pack"]["sha256"] == revised["rule_pack"]["sha256"]
    assert baseline["evidence_sha256"] != revised["evidence_sha256"]


def test_missing_evidence_is_not_promoted_to_pass() -> None:
    payload = _payload()
    del payload["evidence"]["rooms"]["Process"]["ach"]

    result = analyze_compliance_check(compliance_check_from_dict(payload))

    assert result["status"] == "pass_with_unchecked"
    assert result["complete"] is False
    assert result["verified"] is False
    assert result["no_failures_detected"] is True
    assert result["passed"] is True
    finding = next(item for item in result["findings"] if item["id"] == "ach")
    assert finding["status"] == "not_checked"
    assert finding["evidence_present"] is False


def test_numeric_failure_retains_delta() -> None:
    payload = _payload()
    payload["evidence"]["rooms"]["Process"]["temperature_c"] = 24.5

    result = analyze_compliance_check(compliance_check_from_dict(payload))

    finding = next(item for item in result["findings"] if item["id"] == "temperature")
    assert result["status"] == "fail"
    assert result["verified"] is False
    assert result["no_failures_detected"] is False
    assert result["passed"] is False
    assert finding["status"] == "fail"
    assert finding["delta"] == 2.5


def test_tolerance_is_explicit_and_can_accept_boundary_difference() -> None:
    payload = _payload()
    rule = payload["rule_pack"]["rules"][0]
    rule["tolerance"] = 0.5
    payload["evidence"]["rooms"]["Process"]["temperature_c"] = 22.5

    result = analyze_compliance_check(compliance_check_from_dict(payload))

    finding = next(item for item in result["findings"] if item["id"] == "temperature")
    assert finding["status"] == "pass"
    assert finding["tolerance"] == 0.5


def test_exists_operator_requires_path_but_not_expected_value() -> None:
    payload = _payload()
    payload["rule_pack"]["rules"] = [
        {
            "id": "sensor-id",
            "title": "Sensor identity recorded",
            "evidence_path": "/instrument/id",
            "operator": "exists",
        }
    ]
    payload["evidence"] = {"instrument": {"id": None}}

    result = analyze_compliance_check(compliance_check_from_dict(payload))

    assert result["status"] == "pass"
    assert result["findings"][0]["actual"] is None
    assert result["findings"][0]["evidence_present"] is True


def test_json_pointer_escaping_is_supported() -> None:
    payload = _payload()
    payload["rule_pack"]["rules"] = [
        {
            "id": "escaped",
            "title": "Escaped key",
            "evidence_path": "/a~1b/c~0d",
            "operator": "equals",
            "expected": 7,
        }
    ]
    payload["evidence"] = {"a/b": {"c~d": 7}}

    result = analyze_compliance_check(compliance_check_from_dict(payload))
    assert result["status"] == "pass"


def test_rule_pack_rejects_unknown_fields() -> None:
    payload = _payload()
    payload["rule_pack"]["rules"][0]["limit_typo"] = 22

    with pytest.raises(ValueError, match="unknown field"):
        compliance_check_from_dict(payload)


@pytest.mark.parametrize("token", ["00", "01", "١", "１", "²", "+1", "-1", " 1", "-", "9" * 5000, "2"])
def test_invalid_or_out_of_range_array_reference_cannot_verify_evidence(token: str) -> None:
    payload = _payload()
    payload["rule_pack"]["rules"] = [{"id": "array", "title": "Array value", "operator": "equals",
                                    "expected": 7, "evidence_path": f"/values/{token}"}]
    payload["evidence"] = {"values": [7, 7]}
    result = analyze_compliance_check(compliance_check_from_dict(payload))
    assert result["status"] == "not_checked"
    assert result["verified"] is False
    assert result["findings"][0]["evidence_present"] is False
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("token", ["0", "1", "01", "١", "²"])
def test_pointer_object_keys_are_exact_and_canonical_array_indices_work(token: str) -> None:
    payload = _payload()
    payload["rule_pack"]["rules"] = [{"id": "value", "title": "Value", "operator": "equals",
                                    "expected": 7, "evidence_path": f"/values/{token}"}]
    payload["evidence"] = {"values": {token: 7}}
    assert analyze_compliance_check(compliance_check_from_dict(payload))["verified"] is True
    if token in ("0", "1"):
        payload["evidence"] = {"values": [7, 7]}
        assert analyze_compliance_check(compliance_check_from_dict(payload))["verified"] is True


def test_duplicate_rule_ids_fail_closed() -> None:
    payload = _payload()
    payload["rule_pack"]["rules"][1]["id"] = "temperature"

    with pytest.raises(ValueError, match="duplicate compliance rule id"):
        compliance_check_from_dict(payload)


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan"), True])
def test_numeric_rule_expected_must_be_finite_json_number(value: object) -> None:
    payload = _payload()
    payload["rule_pack"]["rules"][1]["expected"] = value

    with pytest.raises(ValueError, match="finite JSON number"):
        compliance_check_from_dict(payload)


def test_invalid_json_pointer_escape_fails_closed() -> None:
    payload = _payload()
    payload["rule_pack"]["rules"][0]["evidence_path"] = "/room/~2bad"

    with pytest.raises(ValueError, match="invalid JSON Pointer escape"):
        compliance_check_from_dict(payload)


@pytest.mark.parametrize(
    ("expected", "actual"),
    [
        (True, 1),
        (False, 0),
        ({"enabled": True}, {"enabled": 1}),
        ([False], [0]),
    ],
)
def test_equals_uses_json_type_semantics(expected: object, actual: object) -> None:
    payload = _payload()
    payload["rule_pack"]["rules"] = [
        {
            "id": "typed-equality",
            "title": "Typed equality",
            "evidence_path": "/value",
            "operator": "equals",
            "expected": expected,
        }
    ]
    payload["evidence"] = {"value": actual}

    result = analyze_compliance_check(compliance_check_from_dict(payload))

    assert result["status"] == "fail"
    assert result["findings"][0]["status"] == "fail"


@pytest.mark.parametrize(
    ("expected", "actual"),
    [
        ([1, 2], True),
        ([0, 2], False),
        ([{"enabled": 1}], {"enabled": True}),
    ],
)
def test_one_of_does_not_conflate_json_booleans_and_numbers(
    expected: object, actual: object
) -> None:
    payload = _payload()
    payload["rule_pack"]["rules"] = [
        {
            "id": "typed-membership",
            "title": "Typed membership",
            "evidence_path": "/value",
            "operator": "one_of",
            "expected": expected,
        }
    ]
    payload["evidence"] = {"value": actual}

    result = analyze_compliance_check(compliance_check_from_dict(payload))

    assert result["status"] == "fail"
    assert result["findings"][0]["status"] == "fail"


def test_json_numeric_int_and_float_remain_equivalent() -> None:
    payload = _payload()
    payload["rule_pack"]["rules"] = [
        {
            "id": "numeric-equivalence",
            "title": "JSON numeric equivalence",
            "evidence_path": "/value",
            "operator": "one_of",
            "expected": [1.0],
        }
    ]
    payload["evidence"] = {"value": 1}

    result = analyze_compliance_check(compliance_check_from_dict(payload))

    assert result["status"] == "pass"


def test_engine_is_deterministic_and_does_not_mutate_input() -> None:
    payload = _payload()
    before = copy.deepcopy(payload)

    first = analyze_compliance_check(compliance_check_from_dict(payload))
    second = analyze_compliance_check(compliance_check_from_dict(payload))

    assert first == second
    assert payload == before


def test_markdown_escapes_user_controlled_content() -> None:
    payload = _payload()
    payload["name"] = "Study | <A>"

    report = markdown_compliance_report(
        analyze_compliance_check(compliance_check_from_dict(payload))
    )

    assert "Study \\| &lt;A&gt;" in report
    assert "Evidence SHA-256:" in report
    assert "not a regulatory approval" in report


def test_non_numeric_evidence_fails_numeric_rule_instead_of_crashing() -> None:
    payload = _payload()
    payload["evidence"]["rooms"]["Process"]["ach"] = "twenty"

    result = analyze_compliance_check(compliance_check_from_dict(payload))

    finding = next(item for item in result["findings"] if item["id"] == "ach")
    assert finding["status"] == "fail"
    assert finding["delta"] is None
