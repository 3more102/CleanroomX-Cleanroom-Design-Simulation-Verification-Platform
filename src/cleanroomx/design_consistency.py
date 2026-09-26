from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Any

from .air_system_design import (
    AirSystemDesign,
    air_system_design_from_dict,
    analyze_air_system_design,
)
from .design_requirements import (
    DesignRequirementsProject,
    analyze_design_requirements,
    design_requirements_from_dict,
)
from .input_contracts import reject_unknown_fields
from .markdown import markdown_text
from .verification import aggregate_verification_status


_ALLOWED_INPUT_KEYS = frozenset(
    {
        "name",
        "requirements",
        "air_system",
        "require_same_room_set",
        "dimension_abs_tolerance_m",
        "ach_abs_tolerance_1_h",
        "airflow_abs_tolerance_m3_h",
        "sensible_load_abs_tolerance_w",
        "temperature_abs_tolerance_c",
    }
)

_NOT_EVALUATED_FIELDS = (
    {
        "field": "relative_humidity_percent",
        "reason": "The preliminary air-system workflow does not carry a room relative-humidity design condition.",
    },
    {
        "field": "pressure_target_pa",
        "reason": "Room pressure is evaluated by the separate pressure/leakage-network workflow, not by preliminary air-system sizing.",
    },
    {
        "field": "recovery_target_minutes",
        "reason": "Recovery performance is not calculated by the preliminary air-system workflow.",
    },
    {
        "field": "filtration_requirement",
        "reason": "Free-text filtration requirements are not implicitly mapped to user-entered equipment capacities.",
    },
    {
        "field": "supply_return_strategy",
        "reason": "Requirements strategy text is intentionally not mapped implicitly to controlled air-system strategy labels.",
    },
    {
        "field": "contamination_assumptions",
        "reason": "Contamination assumptions require a dedicated particle/contamination analysis rather than a textual equality check.",
    },
    {
        "field": "operating_mode",
        "reason": "The preliminary air-system workflow does not currently expose an operating-mode field.",
    },
)


def _nonnegative_finite(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite number >= 0")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{field_name} must be a finite number >= 0")
    return number


@dataclass(frozen=True)
class DesignConsistencyStudy:
    name: str
    requirements: DesignRequirementsProject
    air_system: AirSystemDesign
    require_same_room_set: bool = True
    dimension_abs_tolerance_m: float = 0.0
    ach_abs_tolerance_1_h: float = 0.0
    airflow_abs_tolerance_m3_h: float = 0.0
    sensible_load_abs_tolerance_w: float = 0.0
    temperature_abs_tolerance_c: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("design-consistency study name cannot be empty")
        if not isinstance(self.require_same_room_set, bool):
            raise ValueError("require_same_room_set must be a boolean")
        for field_name in (
            "dimension_abs_tolerance_m",
            "ach_abs_tolerance_1_h",
            "airflow_abs_tolerance_m3_h",
            "sensible_load_abs_tolerance_w",
            "temperature_abs_tolerance_c",
        ):
            object.__setattr__(
                self,
                field_name,
                _nonnegative_finite(getattr(self, field_name), field_name),
            )


def design_consistency_from_dict(data: dict) -> DesignConsistencyStudy:
    if not isinstance(data, dict):
        raise ValueError("design consistency input must be an object")
    reject_unknown_fields(
        data,
        _ALLOWED_INPUT_KEYS,
        context="design consistency input",
    )

    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name must be a non-empty string")

    requirements_data = data.get("requirements")
    if not isinstance(requirements_data, dict):
        raise ValueError("requirements must be a design-requirements object")
    air_system_data = data.get("air_system")
    if not isinstance(air_system_data, dict):
        raise ValueError("air_system must be an air-system-design object")

    require_same_room_set = data.get("require_same_room_set", True)
    if not isinstance(require_same_room_set, bool):
        raise ValueError("require_same_room_set must be a boolean")

    return DesignConsistencyStudy(
        name=name,
        requirements=design_requirements_from_dict(requirements_data),
        air_system=air_system_design_from_dict(air_system_data),
        require_same_room_set=require_same_room_set,
        dimension_abs_tolerance_m=data.get("dimension_abs_tolerance_m", 0.0),
        ach_abs_tolerance_1_h=data.get("ach_abs_tolerance_1_h", 0.0),
        airflow_abs_tolerance_m3_h=data.get("airflow_abs_tolerance_m3_h", 0.0),
        sensible_load_abs_tolerance_w=data.get(
            "sensible_load_abs_tolerance_w", 0.0
        ),
        temperature_abs_tolerance_c=data.get(
            "temperature_abs_tolerance_c", 0.0
        ),
    )


def _finding(
    *,
    code: str,
    room: str | None,
    status: str,
    message: str,
    expected: Any = None,
    actual: Any = None,
    tolerance: float | None = None,
    unit: str | None = None,
    delta: float | None = None,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if status not in {"pass", "fail", "not_checked"}:
        raise ValueError(f"unsupported design-consistency status: {status!r}")
    return {
        "code": code,
        "room": room,
        "status": status,
        "message": message,
        "expected": expected,
        "actual": actual,
        "delta": delta,
        "tolerance": tolerance,
        "unit": unit,
        "provenance": dict(provenance or {}),
    }


def _numeric_finding(
    *,
    code: str,
    room: str,
    expected: float | None,
    actual: float | None,
    tolerance: float,
    unit: str,
    label: str,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if expected is None:
        return _finding(
            code=code,
            room=room,
            status="not_checked",
            message=(
                f"No {label} requirement is configured; the air-system value "
                "is retained as evidence but is not judged."
            ),
            expected=None,
            actual=actual,
            tolerance=tolerance,
            unit=unit,
            provenance=provenance,
        )
    if actual is None:
        return _finding(
            code=code,
            room=room,
            status="fail",
            message=f"The requirements define {label}, but the air-system input does not.",
            expected=expected,
            actual=None,
            tolerance=tolerance,
            unit=unit,
            provenance=provenance,
        )

    delta = actual - expected
    passed = abs(delta) <= tolerance
    return _finding(
        code=code,
        room=room,
        status="pass" if passed else "fail",
        message=(
            f"{label} is consistent within the configured absolute tolerance."
            if passed
            else f"{label} differs by more than the configured absolute tolerance."
        ),
        expected=expected,
        actual=actual,
        delta=delta,
        tolerance=tolerance,
        unit=unit,
        provenance=provenance,
    )


def _temperature_finding(
    *,
    room: str,
    expected_range: tuple[float, float] | None,
    actual: float | None,
    tolerance: float,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if expected_range is None:
        return _finding(
            code="requirements.room_air_temperature",
            room=room,
            status="not_checked",
            message=(
                "No room-air temperature requirement range is configured; "
                "the air-system condition is not judged."
            ),
            expected=None,
            actual=actual,
            tolerance=tolerance,
            unit="degC",
            provenance=provenance,
        )

    expected = {"min": expected_range[0], "max": expected_range[1]}
    if actual is None:
        return _finding(
            code="requirements.room_air_temperature",
            room=room,
            status="fail",
            message=(
                "A room-air temperature requirement range is configured, but "
                "the air-system room temperature is not configured."
            ),
            expected=expected,
            actual=None,
            tolerance=tolerance,
            unit="degC",
            provenance=provenance,
        )

    lower = expected_range[0] - tolerance
    upper = expected_range[1] + tolerance
    passed = lower <= actual <= upper
    delta = 0.0
    if actual < expected_range[0]:
        delta = actual - expected_range[0]
    elif actual > expected_range[1]:
        delta = actual - expected_range[1]

    return _finding(
        code="requirements.room_air_temperature",
        room=room,
        status="pass" if passed else "fail",
        message=(
            "The air-system room temperature is inside the configured requirement range."
            if passed
            else "The air-system room temperature is outside the configured requirement range."
        ),
        expected=expected,
        actual=actual,
        delta=delta,
        tolerance=tolerance,
        unit="degC",
        provenance=provenance,
    )


def _target(room_result: dict[str, Any], target_name: str) -> dict[str, Any]:
    for target in room_result["targets"]:
        if target["name"] == target_name:
            return target
    raise RuntimeError(
        f"design requirements result omitted expected target {target_name!r}"
    )


def analyze_design_consistency(study: DesignConsistencyStudy) -> dict:
    requirements_result = analyze_design_requirements(study.requirements)
    air_system_result = analyze_air_system_design(study.air_system)

    requirement_models = {room.name: room for room in study.requirements.rooms}
    air_models = {room.name: room for room in study.air_system.rooms}
    requirement_results = {
        room["name"]: room for room in requirements_result["rooms"]
    }
    air_results = {room["name"]: room for room in air_system_result["rooms"]}

    requirement_names = sorted(requirement_models)
    air_names = sorted(air_models)
    same_room_set = requirement_names == air_names
    findings: list[dict[str, Any]] = []

    if same_room_set:
        room_set_status = "pass"
        room_set_message = (
            "The design-requirements and air-system room sets are identical."
        )
    elif study.require_same_room_set:
        room_set_status = "fail"
        room_set_message = (
            "The design-requirements and air-system room sets differ while "
            "require_same_room_set is enabled."
        )
    else:
        room_set_status = "not_checked"
        room_set_message = (
            "The room sets differ, but exact room-set equality is not required; "
            "only rooms present in both inputs are compared."
        )

    findings.append(
        _finding(
            code="room_set",
            room=None,
            status=room_set_status,
            message=room_set_message,
            expected=requirement_names,
            actual=air_names,
            provenance={
                "require_same_room_set": study.require_same_room_set,
                "requirements_only": sorted(
                    set(requirement_names) - set(air_names)
                ),
                "air_system_only": sorted(
                    set(air_names) - set(requirement_names)
                ),
            },
        )
    )

    for room_name in sorted(set(requirement_names) & set(air_names)):
        requirement_room = requirement_models[room_name]
        air_room = air_models[room_name]
        requirement_result = requirement_results[room_name]
        air_result = air_results[room_name]

        for field_name, code in (
            ("length_m", "geometry.length_m"),
            ("width_m", "geometry.width_m"),
            ("height_m", "geometry.height_m"),
        ):
            findings.append(
                _numeric_finding(
                    code=code,
                    room=room_name,
                    expected=getattr(requirement_room, field_name),
                    actual=getattr(air_room, field_name),
                    tolerance=study.dimension_abs_tolerance_m,
                    unit="m",
                    label=field_name,
                    provenance={"source": "design requirements room geometry"},
                )
            )

        minimum_ach_target = _target(requirement_result, "minimum_ach")
        findings.append(
            _numeric_finding(
                code="requirements.minimum_ach",
                room=room_name,
                expected=requirement_room.min_ach,
                actual=air_room.min_ach,
                tolerance=study.ach_abs_tolerance_1_h,
                unit="1/h",
                label="minimum ACH",
                provenance=minimum_ach_target.get("provenance"),
            )
        )

        ach_airflow_target = _target(
            requirement_result, "ach_based_supply_airflow"
        )
        findings.append(
            _numeric_finding(
                code="requirements.ach_based_supply_airflow",
                room=room_name,
                expected=ach_airflow_target["value"],
                actual=air_result["airflow_drivers"]["minimum_ach"][
                    "airflow_m3_h"
                ],
                tolerance=study.airflow_abs_tolerance_m3_h,
                unit="m^3/h",
                label="ACH-based supply airflow",
                provenance=ach_airflow_target.get("provenance"),
            )
        )

        sensible_target = _target(
            requirement_result, "provided_sensible_load"
        )
        findings.append(
            _numeric_finding(
                code="requirements.provided_sensible_load",
                room=room_name,
                expected=sensible_target["value"],
                actual=air_room.sensible_load_w,
                tolerance=study.sensible_load_abs_tolerance_w,
                unit="W",
                label="provided sensible load",
                provenance=sensible_target.get("provenance"),
            )
        )

        findings.append(
            _temperature_finding(
                room=room_name,
                expected_range=requirement_room.temperature_c,
                actual=air_room.room_air_temp_c,
                tolerance=study.temperature_abs_tolerance_c,
                provenance=requirement_room.origins.get("temperature_c"),
            )
        )

    counts = {
        status: sum(1 for finding in findings if finding["status"] == status)
        for status in ("pass", "fail", "not_checked")
    }
    aggregate_status = aggregate_verification_status(
        finding["status"] for finding in findings
    )
    complete = bool(findings) and counts["not_checked"] == 0
    passed = counts["fail"] == 0

    return {
        "study": study.name,
        "status": aggregate_status,
        "complete": complete,
        "passed": passed,
        "summary": {
            "finding_count": len(findings),
            "pass_count": counts["pass"],
            "fail_count": counts["fail"],
            "not_checked_count": counts["not_checked"],
            "matched_room_count": len(set(requirement_names) & set(air_names)),
            "requirements_room_count": len(requirement_names),
            "air_system_room_count": len(air_names),
        },
        "tolerances": {
            "dimension_abs_tolerance_m": study.dimension_abs_tolerance_m,
            "ach_abs_tolerance_1_h": study.ach_abs_tolerance_1_h,
            "airflow_abs_tolerance_m3_h": study.airflow_abs_tolerance_m3_h,
            "sensible_load_abs_tolerance_w": study.sensible_load_abs_tolerance_w,
            "temperature_abs_tolerance_c": study.temperature_abs_tolerance_c,
        },
        "findings": findings,
        "source_analyses": {
            "design_requirements": {
                "name": requirements_result["project"],
                "status": requirements_result["status"],
                "warning_count": requirements_result["warning_count"],
                "warnings": list(requirements_result["warnings"]),
            },
            "air_system_design": {
                "name": air_system_result["design"],
                "status": air_system_result["status"],
                "warning_count": air_system_result["warning_count"],
                "warnings": list(air_system_result["warnings"]),
            },
        },
        "not_evaluated_fields": [
            dict(item) for item in _NOT_EVALUATED_FIELDS
        ],
        "engineering_note": (
            "This read-only cross-check compares only quantities represented "
            "explicitly in both canonical Phase 1 workflows. A complete pass "
            "means those defined comparisons are consistent within the configured "
            "tolerances; it does not validate pressure-network performance, "
            "filtration selection, contamination control, CFD, commissioning/TAB, "
            "certification, or regulatory compliance."
        ),
    }


def _report_value(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, (dict, list)):
        rendered = json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
    else:
        rendered = str(value)
    return markdown_text(rendered)


def markdown_design_consistency_report(result: dict) -> str:
    summary = result["summary"]
    lines = [
        f"# CleanroomX Design Consistency — {markdown_text(result['study'])}",
        "",
        f"Status: **{markdown_text(result['status']).upper()}**",
        f"Complete defined comparisons: **{'YES' if result['complete'] else 'NO'}**",
        (
            "Findings: "
            f"**{summary['pass_count']} pass**, "
            f"**{summary['fail_count']} fail**, "
            f"**{summary['not_checked_count']} not checked**."
        ),
        "",
        "## Cross-workflow findings",
        "",
        "| Room | Check | Status | Expected | Actual | Delta | Tolerance | Unit | Finding |",
        "|---|---|---|---|---|---:|---:|---|---|",
    ]
    for finding in result["findings"]:
        lines.append(
            "| {room} | {code} | {status} | {expected} | {actual} | {delta} | "
            "{tolerance} | {unit} | {message} |".format(
                room=markdown_text(finding["room"] or "project"),
                code=markdown_text(finding["code"]),
                status=markdown_text(finding["status"]),
                expected=_report_value(finding["expected"]),
                actual=_report_value(finding["actual"]),
                delta=_report_value(finding["delta"]),
                tolerance=_report_value(finding["tolerance"]),
                unit=markdown_text(finding["unit"] or ""),
                message=markdown_text(finding["message"]),
            )
        )

    lines.extend(["", "## Source workflow warnings", ""])
    for key in ("design_requirements", "air_system_design"):
        source = result["source_analyses"][key]
        lines.append(
            f"- **{markdown_text(key)}:** "
            f"{markdown_text(source['status'])}; "
            f"{source['warning_count']} warning(s)."
        )
        lines.extend(
            f"  - {markdown_text(warning)}" for warning in source["warnings"]
        )

    lines.extend(["", "## Deliberately not evaluated", ""])
    for item in result["not_evaluated_fields"]:
        lines.append(
            f"- **{markdown_text(item['field'])}:** "
            f"{markdown_text(item['reason'])}"
        )

    lines.extend(
        ["", "## Engineering boundary", "", markdown_text(result["engineering_note"]), ""]
    )
    return "\n".join(lines)
