"""Headless, read-only CleanroomX AI evidence review.

This command never contacts a model, runs a solver, or modifies a project.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from .ai_assistant import build_assistant_context, format_offline_review
from .ai_assistant_plan import build_assistant_action_plan, render_assistant_action_plan
from .ai_assistant_specialist import (
    SPECIALIST_FOCUSES, build_specialist_review, render_specialist_review,
)
from .ai_cfd_evidence import bound_cfd_evidence, format_cfd_evidence
from .ai_cfd_followup import build_cfd_followup_plan, render_cfd_followup_plan
from .project import (
    capture_project_file_revision,
    load_project_document_with_revision,
    project_file_revision_matches,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-ai-review",
        description=(
            "Create an offline, read-only AI-assistant evidence review "
            "from canonical CleanroomX project diagnostics."
        ),
    )
    parser.add_argument("project", help="Existing CleanroomX project JSON file")
    parser.add_argument(
        "--actions", action="store_true",
        help="Include proposed, non-executed corrective actions.",
    )
    parser.add_argument(
        "--format", choices=("text", "json"), default="text",
        dest="output_format", help="Report format (default: text).",
    )
    parser.add_argument(
        "--max-findings", type=int, default=15,
        help="Maximum number of diagnostic findings (1-50).",
    )
    parser.add_argument(
        "--specialist", choices=SPECIALIST_FOCUSES,
        help="Include an offline, evidence-bound specialist review.",
    )
    parser.add_argument(
        "--cfd-export",
        help=(
            "Existing multiroom CFD export directory containing report.json; "
            "requires an exact matching saved project source revision."
        ),
    )
    parser.add_argument(
        "--cfd-actions", action="store_true",
        help="Include source-bound, non-executed CFD follow-up checks; requires --cfd-export.",
    )
    return parser


def build_offline_review(
    project_path: str | Path, *,
    actions: bool = False,
    max_findings: int = 15,
    cfd_export: str | Path | None = None,
    cfd_actions: bool = False,
    specialist: str | None = None,
) -> dict:
    """Return a revision-checked, side-effect-free review envelope."""
    if type(max_findings) is not int or not 1 <= max_findings <= 50:
        raise ValueError("max_findings must be an integer between 1 and 50")
    if cfd_actions and cfd_export is None:
        raise ValueError("--cfd-actions requires --cfd-export")
    source = Path(project_path).expanduser().resolve(strict=False)
    project, before = load_project_document_with_revision(source)
    if not before.exists or not before.sha256:
        raise OSError("A saved CleanroomX project is required.")
    context = build_assistant_context(
        project, base_dir=source.parent, max_findings=max_findings
    )
    if cfd_export is not None:
        context["cfd_evidence"] = bound_cfd_evidence(
            cfd_export, project=project, project_path=source,
        )
    plan = build_assistant_action_plan(context) if actions else None
    cfd_plan = (
        build_cfd_followup_plan(context["cfd_evidence"])
        if cfd_actions else None
    )
    specialist_review = (
        build_specialist_review(context, focus=specialist)
        if specialist is not None else None
    )
    after = capture_project_file_revision(source)
    if not project_file_revision_matches(before, after):
        raise RuntimeError(
            "The project changed during AI review; evidence was discarded."
        )
    return {
        "schema": "cleanroomx.ai-offline-review",
        "schema_version": 1,
        "source_revision_sha256": before.sha256,
        "source_stable_during_review": True,
        "model_used": False,
        "network_used": False,
        "context": context,
        "action_plan": plan,
        "cfd_followup_plan": cfd_plan,
        "specialist_review": specialist_review,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = build_offline_review(
            args.project, actions=args.actions, max_findings=args.max_findings,
            cfd_export=args.cfd_export, cfd_actions=args.cfd_actions, specialist=args.specialist,
        )
        if args.output_format == "json":
            output = json.dumps(
                result, ensure_ascii=False, sort_keys=True,
                indent=2, allow_nan=False,
            )
        else:
            output = format_offline_review(result["context"])
            if "cfd_evidence" in result["context"]:
                output += "\n\n" + format_cfd_evidence(result["context"]["cfd_evidence"])
            if result["action_plan"] is not None:
                output += "\n\n" + render_assistant_action_plan(result["action_plan"])
            if result["cfd_followup_plan"] is not None:
                output += "\n\n" + render_cfd_followup_plan(result["cfd_followup_plan"])
            if result["specialist_review"] is not None:
                output += "\n\n" + render_specialist_review(result["specialist_review"])
            output += "\n\nSource revision: " + result["source_revision_sha256"]
            output += "\nNo model request or solver execution was performed."
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        print("cleanroomx-ai-review: " + str(exc), file=sys.stderr)
        return 2
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
