"""Read-only, evidence-grounded CleanroomX project assistant.

This is a deterministic engineering review adapter, not an LLM or CFD solver.
It reuses the canonical project diagnostics and multi-chat agent boundaries.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .markdown import markdown_text
from .multi_agent import (
    AgentReply,
    AgentRequest,
    AgentSpec,
    MultiAgentCoordinator,
)
from .project import (
    capture_project_file_revision,
    load_project_document_with_revision,
    project_file_revision_matches,
)
from .project_diagnostics import (
    PROJECT_DIAGNOSTICS_SCHEMA,
    analyze_project_diagnostics,
)

ASSISTANT_REVIEW_SCHEMA = "cleanroomx.assistant-project-review"
ASSISTANT_REVIEW_SCHEMA_VERSION = 1
_PRIORITY = {"error": 0, "warning": 1, "info": 2}
_DEFAULT_QUESTION = "Review the project and prioritize supported corrective actions."


class AssistantSourceChangedError(RuntimeError):
    """Project revision changed; no assistant answer can be trusted."""


def _validated_limit(max_findings: int) -> int:
    if type(max_findings) is not int or not 1 <= max_findings <= 50:
        raise ValueError("max_findings must be a JSON integer from 1 to 50")
    return max_findings


def _validated_question(question: str) -> str:
    if not isinstance(question, str) or len(question) > 2000:
        raise ValueError("question must be a string of at most 2000 characters")
    return question.strip() or _DEFAULT_QUESTION


def prioritize_project_diagnostics(
    diagnostics: dict[str, Any],
    *,
    source_sha256: str,
    source_size_bytes: int,
    question: str = "",
    max_findings: int = 12,
) -> dict[str, Any]:
    """Transform canonical diagnostics into a bounded, traceable review.

    This function creates no new scientific claims and never modifies input.
    """
    max_findings = _validated_limit(max_findings)
    question = _validated_question(question)
    if not isinstance(diagnostics, dict) or diagnostics.get("schema") != PROJECT_DIAGNOSTICS_SCHEMA:
        raise ValueError("canonical CleanroomX project diagnostics are required")
    if not isinstance(source_sha256, str) or len(source_sha256) != 64 or any(
        ch not in "0123456789abcdef" for ch in source_sha256
    ):
        raise ValueError("source_sha256 must be a lowercase SHA-256 digest")
    if type(source_size_bytes) is not int or source_size_bytes < 0:
        raise ValueError("source_size_bytes must be a non-negative integer")

    issues = diagnostics.get("issues")
    summary = diagnostics.get("summary")
    if not isinstance(issues, list) or not isinstance(summary, dict):
        raise ValueError("canonical diagnostics have an invalid structure")
    if any(
        not isinstance(issue, dict)
        or issue.get("severity") not in _PRIORITY
        or type(issue.get("sequence")) is not int
        or issue["sequence"] < 1
        for issue in issues
    ):
        raise ValueError("canonical diagnostics contain malformed findings")
    counts = {
        key: summary.get(key)
        for key in ("error_count", "warning_count", "info_count", "issue_count")
    }
    if any(type(value) is not int or value < 0 for value in counts.values()):
        raise ValueError("canonical diagnostics have invalid summary counts")
    if (
        counts["issue_count"] != len(issues)
        or counts["error_count"] != sum(item["severity"] == "error" for item in issues)
        or counts["warning_count"] != sum(item["severity"] == "warning" for item in issues)
        or counts["info_count"] != sum(item["severity"] == "info" for item in issues)
    ):
        raise ValueError("canonical diagnostic counts do not match findings")

    ordered = sorted(issues, key=lambda issue: (_PRIORITY[issue["severity"]], issue["sequence"]))
    findings = [
        {
            "diagnostic_sequence": issue["sequence"],
            "evidence_ref": f"diagnostics.issue.{issue['sequence']}",
            "severity": issue["severity"],
            "rule": issue["rule"],
            "category": issue["category"],
            "element": issue.get("element", {}),
            "finding": issue["message"],
            "suggested_action": issue["suggested_action"],
        }
        for issue in ordered[:max_findings]
    ]
    currency = diagnostics.get("verification_currency", {})
    if not isinstance(currency, dict):
        raise ValueError("canonical verification currency is invalid")
    currency_summary = currency.get("summary", {})
    if not isinstance(currency_summary, dict):
        raise ValueError("canonical verification currency summary is invalid")
    decision = "review_required" if (
        counts["error_count"] or counts["warning_count"]
    ) else "no_blocking_diagnostic_findings"
    return {
        "schema": ASSISTANT_REVIEW_SCHEMA,
        "schema_version": ASSISTANT_REVIEW_SCHEMA_VERSION,
        "mode": "deterministic-read-only",
        "question": question,
        "source": {
            "size_bytes": source_size_bytes,
            "sha256": source_sha256,
            "stable_during_review": True,
        },
        "project": diagnostics.get("project", {}),
        "decision": decision,
        "summary": dict(counts),
        "findings": findings,
        "shown_findings": len(findings),
        "omitted_findings": len(issues) - len(findings),
        "verification_currency": currency_summary,
        "limitations": [
            *diagnostics.get("limitations", []),
            "This assistant provides deterministic project diagnostics, not a generative AI model.",
            "Absence of findings never demonstrates converged CFD, cleanroom compliance, or certification.",
            "Suggested actions originate from canonical diagnostic rules; no design changes are applied.",
        ],
    }


def markdown_assistant_review(review: dict[str, Any]) -> str:
    if not isinstance(review, dict) or review.get("schema") != ASSISTANT_REVIEW_SCHEMA:
        raise ValueError("invalid assistant project review")
    summary = review["summary"]
    source = review["source"]
    lines = [
        "# CleanroomX Project Assistant",
        "",
        f"Project: **{markdown_text(review['project'].get('name', ''))}**",
        f"Review state: **{markdown_text(review['decision'])}**",
        f"Errors: **{summary['error_count']}**; warnings: **{summary['warning_count']}**; "
        f"informational: **{summary['info_count']}**",
        f"Project SHA-256: \`{source['sha256']}\`",
        "",
        "## Prioritized evidence-backed findings",
        "",
    ]
    if not review["findings"]:
        lines.extend(["No findings were produced by the configured project diagnostics.", ""])
    for finding in review["findings"]:
        lines.extend([
            f"### {finding['diagnostic_sequence']}. {markdown_text(finding['severity'])} "
            f"— {markdown_text(finding['rule'])}",
            "",
            f"- Evidence: \`{finding['evidence_ref']}\`",
            f"- Finding: {markdown_text(finding['finding'])}",
            f"- Suggested action: {markdown_text(finding['suggested_action'])}",
            "",
        ])
    if review["omitted_findings"]:
        lines.extend([
            f"**{review['omitted_findings']} additional findings omitted** by output limit.",
            "",
        ])
    lines.extend(["## Limits", ""])
    for limitation in review["limitations"]:
        lines.append(f"- {markdown_text(limitation)}")
    return "\n".join(lines) + "\n"


def build_assistant_review(
    project_path: str | Path,
    *,
    question: str = "",
    max_findings: int = 12,
) -> dict[str, Any]:
    """Load one exact project revision and refuse output if its bytes change."""
    _validated_question(question)
    _validated_limit(max_findings)
    source = Path(project_path).expanduser().resolve(strict=False)
    project, revision = load_project_document_with_revision(source)
    if not revision.exists or revision.size is None or revision.sha256 is None:
        raise OSError("project is not a readable regular file")
    before = capture_project_file_revision(source)
    if not project_file_revision_matches(revision, before):
        raise AssistantSourceChangedError("project changed before assistant diagnostics")
    diagnostics = analyze_project_diagnostics(project, base_dir=source.parent)
    after = capture_project_file_revision(source)
    if not project_file_revision_matches(revision, after):
        raise AssistantSourceChangedError("project changed during assistant diagnostics")
    return prioritize_project_diagnostics(
        diagnostics,
        source_sha256=revision.sha256,
        source_size_bytes=revision.size,
        question=question,
        max_findings=max_findings,
    )


@dataclass(frozen=True)
class ProjectReviewAgent:
    """Chat specialist pinned to canonical read-only project diagnostics."""

    project_path: Path
    max_findings: int = 12

    def __init__(self, project_path: str | Path, max_findings: int = 12) -> None:
        object.__setattr__(self, "project_path", Path(project_path).expanduser().resolve(strict=False))
        object.__setattr__(self, "max_findings", _validated_limit(max_findings))

    def __call__(self, request: AgentRequest) -> AgentReply:
        review = build_assistant_review(
            self.project_path,
            question=request.prompt,
            max_findings=self.max_findings,
        )
        return AgentReply(content=markdown_assistant_review(review), data=review)


def register_project_review_agent(
    coordinator: MultiAgentCoordinator,
    agent_id: str,
    *,
    project_path: str | Path,
    max_findings: int = 12,
) -> AgentSpec:
    return coordinator.register_agent(
        agent_id,
        ProjectReviewAgent(project_path, max_findings),
        title="Project evidence reviewer",
        capabilities=(
            "cleanroomx.project-diagnostics",
            "engineering-evidence-review",
            "read-only",
        ),
    )
