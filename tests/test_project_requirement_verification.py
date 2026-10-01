from __future__ import annotations

import copy

import pytest

from cleanroomx.project_requirement_verification import (
    RequirementEvidence,
    verify_project_requirements,
)
from cleanroomx.project_requirements import (
    PROJECT_REQUIREMENTS_SCHEMA,
    PROJECT_REQUIREMENTS_SCHEMA_VERSION,
    project_requirements_from_dict,
)


def _requirement(
    requirement_id: str = "REQ-ACH",
    *,
    applicability: str = "applicable",
    status: str = "approved",
    target=None,
    minimum: float | None = 20.0,
    maximum: float | None = None,
    tolerance: float | None = 0.0,
    unit: str | None = "1/h",
    required_evidence: list[str] | None = None,
    scope: list[str] | None = None,
) -> dict:
    return {
        "id": requirement_id,
        "title": f"Requirement {requirement_id}",
        "description": "Explicit project-owned engineering criterion.",
        "discipline": "HVAC",
        "category": "air_change_rate",
        "source": "Project URS",
        "source_revision": "Rev C",
        "reference": "7.2",
        "unit": unit,
        "target": target,
        "minimum": minimum,
        "maximum": maximum,
        "tolerance": tolerance,
        "applicability": applicability,
        "scope": ["ROOM-A"] if scope is None else scope,
        "verification_method": "calculation",
        "required_evidence": (
            ["calculation"] if required_evidence is None else required_evidence
        ),
        "status": status,
        "assumptions": [],
        "notes": None,
    }


def _registry(*requirements: dict):
    return project_requirements_from_dict(
        {
            "schema": PROJECT_REQUIREMENTS_SCHEMA,
            "schema_version": PROJECT_REQUIREMENTS_SCHEMA_VERSION,
            "sets": [
                {
                    "id": "urs-main",
                    "title": "Approved project URS",
                    "description": "Project criteria.",
                    "source": "URS.pdf",
                    "source_revision": "Rev C",
                    "requirements": list(requirements),
                }
            ],
        }
    )


def _evidence(
    *,
    evidence_id: str = "E-ACH",
    requirement_id: str = "REQ-ACH",
    subject_ref: str | None = "ROOM-A",
    value=20.0,
    unit: str | None = "1/h",
    kinds: tuple[str, ...] = ("calculation",),
    freshness: str = "current",
) -> RequirementEvidence:
    return RequirementEvidence(
        id=evidence_id,
        requirement_id=requirement_id,
        subject_ref=subject_ref,
        property_name="air_change_rate",
        value=value,
        unit=unit,
        source="CleanroomX air-system analysis",
        source_revision="analysis-sha-1",
        calculation_source="cleanroomx.air_system_design",
        project_revision="project-rev-7",
        evidence_kinds=kinds,
        freshness=freshness,
    )


def test_minimum_requirement_uses_explicit_tolerance_and_verifies() -> None:
    requirements = _registry(_requirement(tolerance=0.1))

    result = verify_project_requirements(
        requirements,
        [_evidence(value=19.95)],
    )

    assert result["status"] == "pass"
    assert result["complete"] is True
    assert result["verified"] is True
    assert result["no_failures_detected"] is True
    finding = result["findings"][0]
    assert finding["status"] == "pass"
    assert finding["state"] == "pass"
    assert finding["criterion"] == {
        "operator": "minimum",
        "expected": 20.0,
        "tolerance": 0.1,
    }
    assert finding["delta"] == pytest.approx(-0.05)
    assert finding["project_revision"] == "project-rev-7"


def test_requirement_failure_is_not_hidden_by_tolerance() -> None:
    requirements = _registry(_requirement(tolerance=0.1))

    result = verify_project_requirements(
        requirements,
        [_evidence(value=19.8)],
    )

    assert result["status"] == "fail"
    assert result["complete"] is True
    assert result["verified"] is False
    assert result["no_failures_detected"] is False
    assert result["summary"]["fail_count"] == 1


def test_missing_evidence_is_not_checked_not_pass() -> None:
    result = verify_project_requirements(
        _registry(_requirement()),
        [],
    )

    assert result["status"] == "not_checked"
    assert result["complete"] is False
    assert result["verified"] is False
    assert result["no_failures_detected"] is True
    assert result["findings"][0]["state"] == "not_checked"


def test_missing_bound_evidence_value_is_incomplete_not_fail() -> None:
    requirement = _requirement(
        target="HEPA",
        minimum=None,
        tolerance=0.0,
        unit=None,
        required_evidence=[],
    )

    result = verify_project_requirements(
        _registry(requirement),
        [
            _evidence(
                value=None,
                unit=None,
                kinds=(),
            )
        ],
    )

    assert result["status"] == "not_checked"
    assert result["findings"][0]["state"] == "incomplete"
    assert result["findings"][0]["actual"] is None
    assert result["verified"] is False


def test_stale_and_unknown_freshness_fail_closed() -> None:
    requirements = _registry(_requirement())

    stale = verify_project_requirements(
        requirements,
        [_evidence(freshness="stale")],
    )
    unknown = verify_project_requirements(
        requirements,
        [_evidence(freshness="unknown")],
    )

    assert stale["findings"][0]["state"] == "stale"
    assert stale["summary"]["stale_count"] == 1
    assert stale["verified"] is False
    assert unknown["findings"][0]["state"] == "incomplete"
    assert unknown["summary"]["incomplete_count"] == 1
    assert unknown["verified"] is False


def test_unsupported_unit_mismatch_is_invalid_fail_closed() -> None:
    result = verify_project_requirements(
        _registry(_requirement(unit="1/h")),
        [_evidence(unit="Hz")],
    )

    assert result["status"] == "not_checked"
    assert result["findings"][0]["state"] == "invalid"
    assert result["summary"]["invalid_count"] == 1
    assert "unsupported source engineering unit 'Hz'" in result["findings"][0]["explanation"]


def test_missing_value_remains_incomplete_before_unit_conversion() -> None:
    result = verify_project_requirements(
        _registry(_requirement(minimum=1000.0, unit="Pa")),
        [_evidence(value=None, unit="kPa")],
    )

    finding = result["findings"][0]
    assert result["verified"] is False
    assert finding["state"] == "incomplete"
    assert finding["actual"] is None
    assert "does not contain an engineering value" in finding["explanation"]


def test_compatible_pressure_units_are_converted_before_comparison() -> None:
    result = verify_project_requirements(
        _registry(_requirement(minimum=1000.0, unit="Pa")),
        [_evidence(value=1.0, unit="kPa")],
    )

    finding = result["findings"][0]
    assert result["verified"] is True
    assert finding["status"] == "pass"
    assert finding["actual"] == pytest.approx(1000.0)
    assert finding["evidence_actual"] == 1.0
    assert finding["evidence_unit"] == "kPa"
    assert finding["unit"] == "Pa"
    assert finding["unit_conversion"]["dimension"] == "pressure"
    assert finding["unit_conversion"]["scale"] == pytest.approx(1000.0)
    assert finding["delta"] == pytest.approx(0.0)


def test_airflow_units_are_converted_with_explicit_trace() -> None:
    result = verify_project_requirements(
        _registry(_requirement(minimum=1.0, unit="m3/s")),
        [_evidence(value=3600.0, unit="m3/h")],
    )

    finding = result["findings"][0]
    assert result["verified"] is True
    assert finding["actual"] == pytest.approx(1.0)
    assert finding["unit_conversion"]["source_canonical_unit"] == "m3/h"
    assert finding["unit_conversion"]["target_canonical_unit"] == "m3/s"


def test_temperature_units_apply_affine_conversion_before_tolerance() -> None:
    result = verify_project_requirements(
        _registry(
            _requirement(
                target=20.0,
                minimum=None,
                tolerance=0.01,
                unit="degC",
            )
        ),
        [_evidence(value=68.0, unit="degF")],
    )

    finding = result["findings"][0]
    assert result["verified"] is True
    assert finding["actual"] == pytest.approx(20.0, abs=1e-12)
    assert finding["delta"] == pytest.approx(0.0, abs=1e-12)
    assert finding["unit_conversion"]["offset"] != 0.0


def test_equivalent_air_change_rate_aliases_are_explicitly_supported() -> None:
    result = verify_project_requirements(
        _registry(_requirement(minimum=20.0, unit="1/h")),
        [_evidence(value=20.0, unit="ACH")],
    )

    finding = result["findings"][0]
    assert result["verified"] is True
    assert finding["actual"] == pytest.approx(20.0)
    assert finding["unit_conversion"]["dimension"] == "air_change_rate"


def test_incompatible_named_and_unitless_values_fail_closed() -> None:
    requirement = _requirement(
        target=20.0,
        minimum=None,
        unit=None,
    )
    result = verify_project_requirements(
        _registry(requirement),
        [_evidence(value=20.0, unit="Pa")],
    )

    finding = result["findings"][0]
    assert result["verified"] is False
    assert finding["state"] == "invalid"
    assert "unset unit" in finding["explanation"]


def test_exact_unit_comparison_keeps_legacy_finding_shape() -> None:
    result = verify_project_requirements(
        _registry(_requirement(unit="Pa", minimum=1000.0)),
        [_evidence(value=1000.0, unit="Pa")],
    )

    finding = result["findings"][0]
    assert result["verified"] is True
    assert "unit_conversion" not in finding
    assert "evidence_actual" not in finding
    assert "evidence_unit" not in finding


def test_missing_required_evidence_kind_is_incomplete() -> None:
    result = verify_project_requirements(
        _registry(
            _requirement(required_evidence=["design", "calculation"])
        ),
        [_evidence(kinds=("calculation",))],
    )

    assert result["findings"][0]["state"] == "incomplete"
    assert result["findings"][0]["evidence_kinds"] == ["calculation"]
    assert result["verified"] is False


def test_unresolved_applicability_and_no_criterion_never_pass() -> None:
    unknown = verify_project_requirements(
        _registry(_requirement(applicability="unknown")),
        [_evidence()],
    )
    no_criterion = _requirement()
    no_criterion["minimum"] = None
    unchecked = verify_project_requirements(
        _registry(no_criterion),
        [_evidence()],
    )

    assert unknown["findings"][0]["state"] == "incomplete"
    assert unknown["verified"] is False
    assert unchecked["findings"][0]["state"] == "not_checked"
    assert unchecked["findings"][0]["criterion"] is None
    assert unchecked["verified"] is False


def test_draft_requirement_blocks_verified_outcome() -> None:
    result = verify_project_requirements(
        _registry(_requirement(status="draft")),
        [_evidence()],
    )

    finding = result["findings"][0]
    assert finding["state"] == "incomplete"
    assert finding["requirement_status"] == "draft"
    assert result["status"] == "not_checked"
    assert result["verified"] is False


def test_superseded_and_withdrawn_requirements_are_explicitly_inactive() -> None:
    requirements = _registry(
        _requirement("REQ-SUPERSEDED", status="superseded", scope=["ROOM-A"]),
        _requirement("REQ-WITHDRAWN", status="withdrawn", scope=["ROOM-B"]),
    )

    result = verify_project_requirements(requirements, [])

    assert [item["state"] for item in result["findings"]] == [
        "inactive",
        "inactive",
    ]
    assert all(item["included"] is False for item in result["findings"])
    assert result["summary"]["inactive_count"] == 2
    assert result["status"] == "not_checked"
    assert result["verified"] is False


def test_duplicate_evidence_ids_are_rejected_graph_wide() -> None:
    requirements = _registry(
        _requirement("REQ-ACH", scope=["ROOM-A"]),
        _requirement("REQ-ACH-B", scope=["ROOM-B"]),
    )
    first = _evidence(evidence_id="E-DUP")
    second = _evidence(
        evidence_id="E-DUP",
        requirement_id="REQ-ACH-B",
        subject_ref="ROOM-B",
    )

    with pytest.raises(ValueError, match="duplicate ids"):
        verify_project_requirements(requirements, [first, second])


def test_not_applicable_requirement_is_explicitly_excluded() -> None:
    result = verify_project_requirements(
        _registry(_requirement(applicability="not_applicable")),
        [],
    )

    finding = result["findings"][0]
    assert finding["state"] == "not_applicable"
    assert finding["included"] is False
    assert result["summary"]["not_applicable_count"] == 1
    assert result["status"] == "not_checked"
    assert result["verified"] is False


def test_duplicate_evidence_binding_is_invalid_and_deterministic() -> None:
    requirements = _registry(_requirement())
    left = _evidence(evidence_id="E-2")
    right = _evidence(evidence_id="E-1")

    forward = verify_project_requirements(requirements, [left, right])
    reverse = verify_project_requirements(requirements, [right, left])

    assert forward == reverse
    finding = forward["findings"][0]
    assert finding["state"] == "invalid"
    assert finding["evidence_ids"] == ["E-1", "E-2"]


def test_evidence_order_does_not_change_verification_digest() -> None:
    requirements = _registry(
        _requirement("REQ-ACH", scope=["ROOM-A"]),
        _requirement("REQ-ACH-B", scope=["ROOM-B"]),
    )
    first = _evidence()
    second = _evidence(
        evidence_id="E-ACH-B",
        requirement_id="REQ-ACH-B",
        subject_ref="ROOM-B",
        value=21.0,
    )

    forward = verify_project_requirements(requirements, [first, second])
    reverse = verify_project_requirements(requirements, [second, first])

    assert forward == reverse
    assert forward["verified"] is True
    assert len(forward["verification_sha256"]) == 64


def test_project_scope_requirement_requires_project_scope_evidence() -> None:
    requirements = _registry(_requirement(scope=[]))

    with pytest.raises(ValueError, match="project-scope requirement"):
        verify_project_requirements(
            requirements,
            [_evidence(subject_ref="ROOM-A")],
        )


def test_unknown_requirement_evidence_is_rejected() -> None:
    requirements = _registry(_requirement())

    with pytest.raises(ValueError, match="unknown requirement"):
        verify_project_requirements(
            requirements,
            [_evidence(requirement_id="REQ-UNKNOWN")],
        )


def test_non_numeric_target_with_tolerance_is_invalid() -> None:
    requirement = _requirement(
        target="HEPA",
        minimum=None,
        tolerance=0.1,
        unit=None,
        required_evidence=[],
    )
    result = verify_project_requirements(
        _registry(requirement),
        [
            _evidence(
                value="HEPA",
                unit=None,
                kinds=(),
            )
        ],
    )

    assert result["findings"][0]["state"] == "invalid"
    assert result["verified"] is False


def test_equivalent_numeric_evidence_spelling_has_same_digest() -> None:
    requirements = _registry(_requirement())
    integer = _evidence(value=20)
    floating = _evidence(value=20.0)

    integer_result = verify_project_requirements(requirements, [integer])
    float_result = verify_project_requirements(requirements, [floating])

    assert integer_result == float_result