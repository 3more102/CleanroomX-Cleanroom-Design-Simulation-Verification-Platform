"""Deterministic, read-only project-diagnostics regression comparison.

This evaluates changes in configured software/model findings, not compliance.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from .markdown import markdown_text
from .project_diagnostics import (
    PROJECT_DIAGNOSTICS_SCHEMA,
    PROJECT_DIAGNOSTICS_SCHEMA_VERSION,
)


def _validated_report(report: Any, label: str) -> tuple[str, Counter]:
    if not isinstance(report, dict):
        raise ValueError(f"{label} diagnostics must be a JSON object")
    if (
        report.get("schema") != PROJECT_DIAGNOSTICS_SCHEMA
        or report.get("schema_version") != PROJECT_DIAGNOSTICS_SCHEMA_VERSION
    ):
        raise ValueError(f"{label} must be a compatible CleanroomX project diagnostics report")
    project = report.get("project")
    if not isinstance(project, dict) or not isinstance(project.get("name"), str):
        raise ValueError(f"{label} diagnostics lack a valid project name")
    issues = report.get("issues")
    summary = report.get("summary")
    if not isinstance(issues, list) or not isinstance(summary, dict):
        raise ValueError(f"{label} diagnostics lack issues or summary")
    if type(summary.get("issue_count")) is not int or summary["issue_count"] != len(issues):
        raise ValueError(f"{label} issue summary does not match its findings")
    counts: Counter = Counter()
    for index, item in enumerate(issues):
        if not isinstance(item, dict) or not isinstance(item.get("element"), dict):
            raise ValueError(f"{label} issue {index} is malformed")
        fields = [item.get("rule"), item.get("category"), item.get("severity")]
        if any(not isinstance(value, str) or not value for value in fields):
            raise ValueError(f"{label} issue {index} is missing identity fields")
        if fields[2] not in {"error", "warning", "info"}:
            raise ValueError(f"{label} issue {index} has an unknown severity")
        element = item["element"]
        typ = element.get("type")
        element_id = element.get("id")
        name = element.get("name")
        if not isinstance(typ, str) or not typ:
            raise ValueError(f"{label} issue {index} lacks an element type")
        if element_id is not None and not isinstance(element_id, str):
            raise ValueError(f"{label} issue {index} has an invalid element id")
        if name is not None and not isinstance(name, str):
            raise ValueError(f"{label} issue {index} has an invalid element name")
        # Stable IDs take precedence over display names and diagnostic prose.
        key = (fields[0], fields[1], typ, element_id or "",
               (name or "") if not element_id else "", fields[2])
        counts[key] += 1
    return project["name"], counts


def _entries(counts: Counter) -> list[dict[str, Any]]:
    severity_rank = {"error": 0, "warning": 1, "info": 2}
    items = []
    for key, count in sorted(
        counts.items(),
        key=lambda pair: (severity_rank[pair[0][5]], pair[0]),
    ):
        rule, category, typ, element_id, name, severity = key
        items.append({
            "rule": rule, "category": category, "severity": severity,
            "element": {"type": typ, "id": element_id or None,
                        "name": name or None},
            "count": count,
        })
    return items


def compare_project_diagnostics(
    baseline: dict[str, Any], current: dict[str, Any],
) -> dict[str, Any]:
    """Compare stable rule/element identities with multiset semantics.

    Severity is part of identity: escalation is a new actionable finding,
    while duplicate findings remain counted rather than silently collapsed.
    """
    baseline_name, old = _validated_report(baseline, "baseline")
    current_name, new = _validated_report(current, "current")
    if baseline_name != current_name:
        raise ValueError("diagnostics baseline is for a different project name")
    added = new - old
    resolved = old - new
    persistent = new & old
    actionable = sum(
        count for key, count in added.items() if key[-1] in {"error", "warning"}
    )
    return {
        "schema": "cleanroomx.project-diagnostics-comparison",
        "schema_version": 1,
        "project_name": current_name,
        "state": "regression" if actionable else (
            "changed" if added or resolved else "unchanged"
        ),
        "regressed": bool(actionable),
        "summary": {
            "new_issue_count": sum(added.values()),
            "new_actionable_count": actionable,
            "resolved_issue_count": sum(resolved.values()),
            "persistent_issue_count": sum(persistent.values()),
        },
        "new_issues": _entries(added),
        "resolved_issues": _entries(resolved),
    }


def markdown_project_diagnostics_comparison(comparison: dict[str, Any]) -> str:
    """Render an escaped, count-aware baseline delta for human operators."""
    s = comparison["summary"]
    lines = [
        "## Baseline diagnostics comparison", "",
        f"- State: **{markdown_text(comparison['state'])}**",
        f"- New actionable findings: **{s['new_actionable_count']}**",
        f"- New findings (including info): **{s['new_issue_count']}**",
        f"- Resolved findings: **{s['resolved_issue_count']}**",
        f"- Persisting findings: **{s['persistent_issue_count']}**", "",
    ]
    for title, key in (("New findings", "new_issues"), ("Resolved findings", "resolved_issues")):
        lines.extend([f"### {title}", "",
                      "| Severity | Rule | Element | Count |",
                      "|---|---|---|---:|"])
        for issue in comparison[key]:
            element = issue["element"]
            label = element["id"] or element["name"] or element["type"]
            lines.append("| {} | {} | {} | {} |".format(
                markdown_text(issue["severity"]),
                markdown_text(issue["rule"]),
                markdown_text(label),
                issue["count"],
            ))
        if not comparison[key]:
            lines.append("| — | None | — | 0 |")
        lines.append("")
    return "\n".join(lines)
