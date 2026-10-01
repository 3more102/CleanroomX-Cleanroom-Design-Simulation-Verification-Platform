from __future__ import annotations

from dataclasses import dataclass
import copy
import hashlib
import json
from typing import Any

from .compliance_rulepack import (
    ComplianceCheck,
    analyze_compliance_check,
    compliance_check_from_dict,
)
from .design_consistency import (
    DesignConsistencyStudy,
    analyze_design_consistency,
    design_consistency_from_dict,
)
from .input_contracts import reject_unknown_fields
from .markdown import markdown_text
from .pressure_design_consistency import (
    PressureDesignConsistencyStudy,
    analyze_pressure_design_consistency,
    pressure_design_consistency_from_dict,
)


_ALLOWED_INPUT_KEYS = frozenset(
    {
        "name",
        "design_consistency",
        "pressure_design_consistency",
        "compliance_checks",
    }
)


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class DesignAssuranceStudy:
    name: str
    design_consistency: DesignConsistencyStudy
    compliance_checks: tuple[ComplianceCheck, ...]
    pressure_design_consistency: PressureDesignConsistencyStudy | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("design assurance study name cannot be empty")
        if not self.compliance_checks:
            raise ValueError("design assurance study requires at least one compliance check")


def design_assurance_from_dict(data: dict) -> DesignAssuranceStudy:
    if not isinstance(data, dict):
        raise ValueError("design assurance input must be an object")
    reject_unknown_fields(
        data,
        _ALLOWED_INPUT_KEYS,
        context="design assurance input",
    )

    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name must be a non-empty string")

    consistency_data = data.get("design_consistency")
    if not isinstance(consistency_data, dict):
        raise ValueError("design_consistency must be a design-consistency object")

    raw_checks = data.get("compliance_checks")
    if not isinstance(raw_checks, list) or not raw_checks:
        raise ValueError("compliance_checks must be a non-empty array")
    checks = []
    for index, item in enumerate(raw_checks):
        if not isinstance(item, dict):
            raise ValueError(f"compliance_checks[{index}] must be an object")
        checks.append(compliance_check_from_dict(item))

    pressure_study = None
    if "pressure_design_consistency" in data:
        pressure_data = data["pressure_design_consistency"]
        if not isinstance(pressure_data, dict):
            raise ValueError(
                "pressure_design_consistency must be a "
                "pressure-design-consistency object"
            )
        pressure_study = pressure_design_consistency_from_dict(pressure_data)

    return DesignAssuranceStudy(
        name=name,
        design_consistency=design_consistency_from_dict(consistency_data),
        compliance_checks=tuple(checks),
        pressure_design_consistency=pressure_study,
    )


def _aggregate_status(statuses: list[str], complete: bool) -> str:
    if any(status == "fail" for status in statuses):
        return "fail"
    if statuses and all(status == "not_checked" for status in statuses):
        return "not_checked"
    if not complete or any(status != "pass" for status in statuses):
        return "pass_with_unchecked"
    return "pass"


def analyze_design_assurance(study: DesignAssuranceStudy) -> dict:
    design_result = analyze_design_consistency(study.design_consistency)
    pressure_result = (
        analyze_pressure_design_consistency(study.pressure_design_consistency)
        if study.pressure_design_consistency is not None
        else None
    )
    compliance_results = [
        analyze_compliance_check(check) for check in study.compliance_checks
    ]

    component_statuses = [design_result["status"]]
    component_complete = [bool(design_result["complete"])]
    if pressure_result is not None:
        component_statuses.append(pressure_result["status"])
        component_complete.append(bool(pressure_result["complete"]))
    component_statuses.extend(
        result["status"] for result in compliance_results
    )
    component_complete.extend(
        bool(result["complete"]) for result in compliance_results
    )
    complete = all(component_complete)

    pressure_fail_count = (
        int(pressure_result["summary"]["fail_count"])
        if pressure_result is not None
        else 0
    )
    pressure_not_checked_count = (
        int(pressure_result["summary"]["not_checked_count"])
        if pressure_result is not None
        else 0
    )
    pressure_pass_count = (
        int(pressure_result["summary"]["pass_count"])
        if pressure_result is not None
        else 0
    )
    pressure_finding_count = (
        int(pressure_result["summary"]["finding_count"])
        if pressure_result is not None
        else 0
    )

    fail_count = (
        int(design_result["summary"]["fail_count"])
        + pressure_fail_count
        + sum(
            int(result["summary"]["fail_count"])
            for result in compliance_results
        )
    )
    not_checked_count = (
        int(design_result["summary"]["not_checked_count"])
        + pressure_not_checked_count
        + sum(
            int(result["summary"]["not_checked_count"])
            for result in compliance_results
        )
    )
    pass_count = (
        int(design_result["summary"]["pass_count"])
        + pressure_pass_count
        + sum(
            int(result["summary"]["pass_count"])
            for result in compliance_results
        )
    )
    finding_count = (
        int(design_result["summary"]["finding_count"])
        + pressure_finding_count
        + sum(
            int(result["summary"]["rule_count"])
            for result in compliance_results
        )
    )

    traceability = [
        {
            "component": "design_consistency",
            "name": design_result["study"],
            "status": design_result["status"],
            "complete": design_result["complete"],
            "source": "CleanroomX canonical design-consistency analysis",
            "result_sha256": _canonical_sha256(design_result),
        }
    ]
    if pressure_result is not None:
        traceability.append(
            {
                "component": "pressure_design_consistency",
                "name": pressure_result["study"],
                "status": pressure_result["status"],
                "complete": pressure_result["complete"],
                "source": (
                    "CleanroomX canonical pressure-design-consistency analysis"
                ),
                "result_sha256": _canonical_sha256(pressure_result),
            }
        )
    for result in compliance_results:
        traceability.append(
            {
                "component": "compliance_check",
                "name": result["name"],
                "status": result["status"],
                "complete": result["complete"],
                "rule_pack": copy.deepcopy(result["rule_pack"]),
                "evidence_sha256": result["evidence_sha256"],
                "result_sha256": _canonical_sha256(result),
            }
        )

    status = _aggregate_status(component_statuses, complete)
    traceability_sha256 = _canonical_sha256(traceability)

    components = {
        "design_consistency": design_result,
        "compliance_checks": compliance_results,
    }
    if pressure_result is not None:
        components["pressure_design_consistency"] = pressure_result

    engineering_note = (
        "This assurance matrix composes existing CleanroomX design-consistency "
        "and user-supplied compliance rule-pack evidence without adding new "
        "engineering equations, standards limits, acceptance criteria, or hidden "
        "semantic mappings. A complete pass means only that every included "
        "component completed without a recorded failure. It is not regulatory "
        "approval, cleanroom certification, CFD validation, commissioning/TAB "
        "acceptance, or proof that the supplied rule packs are complete."
    )
    if pressure_result is not None:
        engineering_note = (
            "This assurance matrix composes existing CleanroomX design-consistency, "
            "explicit pressure-design-consistency, and user-supplied compliance "
            "rule-pack evidence without adding new engineering equations, standards "
            "limits, acceptance criteria, or hidden semantic mappings. A complete "
            "pass means only that every included component completed without a "
            "recorded failure. It is not regulatory approval, cleanroom certification, "
            "CFD validation, commissioning/TAB acceptance, or proof that the supplied "
            "rule packs are complete."
        )

    no_failures_detected = fail_count == 0
    verified = complete and status == "pass"

    return {
        "study": study.name,
        "status": status,
        "complete": complete,
        "verified": verified,
        "no_failures_detected": no_failures_detected,
        "passed": no_failures_detected,
        "summary": {
            "component_count": (
                1
                + len(compliance_results)
                + (1 if pressure_result is not None else 0)
            ),
            "compliance_check_count": len(compliance_results),
            "finding_count": finding_count,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "not_checked_count": not_checked_count,
        },
        "components": components,
        "traceability": traceability,
        "traceability_sha256": traceability_sha256,
        "engineering_note": engineering_note,
    }


def _md(value: Any) -> str:
    if value is None:
        text = "—"
    elif isinstance(value, str):
        text = value
    else:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
            separators=(",", ":"),
        )
    return markdown_text(text)


def markdown_design_assurance_report(result: dict) -> str:
    summary = result["summary"]
    lines = [
        "# CleanroomX Design Assurance Matrix",
        "",
        f"- Study: {_md(result['study'])}",
        f"- Status: **{_md(result['status'])}**",
        f"- Complete: **{_md(result['complete'])}**",
        f"- Findings: {summary['finding_count']}",
        f"- Pass / Fail / Not checked: {summary['pass_count']} / {summary['fail_count']} / {summary['not_checked_count']}",
        f"- Traceability SHA-256: `{_md(result['traceability_sha256'])}`",
        f"- Design-consistency result SHA-256: `{_md(result['traceability'][0]['result_sha256'])}`",
        "",
        "| Component | Status | Complete | Pass | Fail | Not checked | Traceability |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ]

    design = result["components"]["design_consistency"]
    lines.append(
        "| "
        + " | ".join(
            [
                "Design consistency",
                _md(design["status"]),
                _md(design["complete"]),
                _md(design["summary"]["pass_count"]),
                _md(design["summary"]["fail_count"]),
                _md(design["summary"]["not_checked_count"]),
                _md(design["study"]),
            ]
        )
        + " |"
    )

    pressure = result["components"].get("pressure_design_consistency")
    if pressure is not None:
        pressure_traceability = next(
            entry
            for entry in result["traceability"]
            if entry["component"] == "pressure_design_consistency"
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    "Pressure design consistency",
                    _md(pressure["status"]),
                    _md(pressure["complete"]),
                    _md(pressure["summary"]["pass_count"]),
                    _md(pressure["summary"]["fail_count"]),
                    _md(pressure["summary"]["not_checked_count"]),
                    _md(
                        f"{pressure['study']} / result "
                        f"{pressure_traceability['result_sha256']}"
                    ),
                ]
            )
            + " |"
        )

    compliance_traceability = [
        entry
        for entry in result["traceability"]
        if entry["component"] == "compliance_check"
    ]
    for check, traceability in zip(
        result["components"]["compliance_checks"],
        compliance_traceability,
    ):
        pack = check["rule_pack"]
        trace = (
            f"{pack['id']} v{pack['version']} / pack {pack['sha256']} / "
            f"evidence {check['evidence_sha256']} / result {traceability['result_sha256']}"
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    _md(f"Compliance: {check['name']}"),
                    _md(check["status"]),
                    _md(check["complete"]),
                    _md(check["summary"]["pass_count"]),
                    _md(check["summary"]["fail_count"]),
                    _md(check["summary"]["not_checked_count"]),
                    _md(trace),
                ]
            )
            + " |"
        )

    unresolved: list[str] = []
    for finding in design["findings"]:
        if finding["status"] != "pass":
            location = finding.get("room") or "project"
            unresolved.append(
                f"- Design consistency / {_md(location)} / {_md(finding['code'])}: "
                f"**{_md(finding['status'])}** — {_md(finding['message'])}"
            )
    if pressure is not None:
        for finding in pressure["findings"]:
            if finding["status"] != "pass":
                unresolved.append(
                    f"- Pressure design consistency / {_md(finding['room'])}: "
                    f"**{_md(finding['status'])}** — {_md(finding['message'])}"
                )
    for check in result["components"]["compliance_checks"]:
        for finding in check["findings"]:
            if finding["status"] != "pass":
                reference = finding.get("reference") or finding["id"]
                unresolved.append(
                    f"- Compliance / {_md(check['name'])} / {_md(reference)}: "
                    f"**{_md(finding['status'])}** — {_md(finding['title'])}"
                )

    lines.extend(["", "## Non-pass evidence", ""])
    if unresolved:
        lines.extend(unresolved)
    else:
        lines.append("No failed or unresolved findings are present in the included components.")

    lines.extend(["", _md(result["engineering_note"])])
    return "\n".join(lines) + "\n"
