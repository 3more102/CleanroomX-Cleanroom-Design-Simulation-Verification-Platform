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
    return parser


def build_offline_review(
    project_path: str | Path, *, actions: bool = False, max_findings: int = 15,
) -> dict:
    """Return a revision-checked, side-effect-free review envelope."""
    if type(max_findings) is not int or not 1 <= max_findings <= 50:
        raise ValueError("max_findings must be an integer between 1 and 50")
    source = Path(project_path).expanduser().resolve(strict=False)
    project, before = load_project_document_with_revision(source)
    if not before.exists or not before.sha256:
        raise OSError("A saved CleanroomX project is required.")
    context = build_assistant_context(
        project, base_dir=source.parent, max_findings=max_findings
    )
    plan = build_assistant_action_plan(context) if actions else None
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
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = build_offline_review(
            args.project, actions=args.actions, max_findings=args.max_findings
        )
        if args.output_format == "json":
            output = json.dumps(
                result, ensure_ascii=False, sort_keys=True,
                indent=2, allow_nan=False,
            )
        else:
            output = format_offline_review(result["context"])
            if result["action_plan"] is not None:
                output += "\n\n" + render_assistant_action_plan(result["action_plan"])
            output += "\n\nSource revision: " + result["source_revision_sha256"]
            output += "\nNo model request or solver execution was performed."
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        print("cleanroomx-ai-review: " + str(exc), file=sys.stderr)
        return 2
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
