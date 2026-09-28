from __future__ import annotations

from dataclasses import dataclass
import copy
import html
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


_ALLOWED_INPUT_KEYS = frozenset({"name", "design_consistency", "compliance_checks"})


@dataclass(frozen=True)
class DesignAssuranceStudy:
    name: str
    design_consistency: DesignConsistencyStudy
    compliance_checks: tuple[ComplianceCheck, ...]

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

    return DesignAssuranceStudy(
        name=name,
        design_consistency=design_consistency_from_dict(consistency_data),
        compliance_checks=tuple(checks),
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
    compliance_results = [
        analyze_compliance_check(check) for check in study.compliance_checks
    ]

    component_statuses = [design_result["status"]] + [
        result["status"] for result in compliance_results
    ]
    complete = bool(design_result["complete"]) and all(
        result["complete"] for result in compliance_results
    )
    fail_count = int(design_result["summary"]["fail_count"]) + sum(
        int(result["summary"]["fail_count"]) for result in compliance_results
    )
    not_checked_count = int(design_result["summary"]["not_checked_count"]) + sum(
        int(result["summary"]["not_checked_count"]) for result in compliance_results
    )
    pass_count = int(design_result["summary"]["pass_count"]) + sum(
        int(result["summary"]["pass_count"]) for result in compliance_results
    )
    finding_count = int(design_result["summary"]["finding_count"]) + sum(
        int(result["summary"]["rule_count"]) for result in compliance_results
    )

    traceability = [
        {
            "component": "design_consistency",
            "name": design_result["study"],
            "status": design_result["status"],
            "complete": design_result["complete"],
            "source": "CleanroomX canonical design-consistency analysis",
        }
    ]
    for result in compliance_results:
        traceability.append(
            {
                "component": "compliance_check",
                "name": result["name"],
                "status": result["status"],
                "complete": result["complete"],
                "rule_pack": copy.deepcopy(result["rule_pack"]),
            }
        )

    status = _aggregate_status(component_statuses, complete)
    return {
        "study": study.name,
        "status": status,
        "complete": complete,
        "passed": fail_count == 0,
        "summary": {
            "component_count": 1 + len(compliance_results),
            "compliance_check_count": len(compliance_results),
            "finding_count": finding_count,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "not_checked_count": not_checked_count,
        },
        "components": {
            "design_consistency": design_result,
            "compliance_checks": compliance_results,
        },
        "traceability": traceability,
        "engineering_note": (
            "This assurance matrix composes existing CleanroomX design-consistency "
            "and user-supplied compliance rule-pack evidence without adding new "
            "engineering equations, standards limits, acceptance criteria, or hidden "
            "semantic mappings. A complete pass means only that every included "
            "component completed without a recorded failure. It is not regulatory "
            "approval, cleanroom certification, CFD validation, commissioning/TAB "
            "acceptance, or proof that the supplied rule packs are complete."
        ),
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
    return html.escape(text).replace("|", "\\|").replace("\n", " ")


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

    for check in result["components"]["compliance_checks"]:
        pack = check["rule_pack"]
        trace = f"{pack['id']} v{pack['version']} / {pack['sha256']}"
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
