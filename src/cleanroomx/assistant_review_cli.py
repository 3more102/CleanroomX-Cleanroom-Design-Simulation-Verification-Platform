"""CLI for the read-only CleanroomX evidence-grounded project assistant."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .assistant_review import (
    AssistantSourceChangedError,
    build_assistant_review,
    markdown_assistant_review,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-assistant",
        description="Review an existing project using canonical evidence-based diagnostics (no LLM).",
    )
    parser.add_argument("project", help="CleanroomX project JSON file")
    parser.add_argument(
        "--question",
        default="Review the project and prioritize supported corrective actions.",
        help="Question retained with the report; no free-form solver commands are executed.",
    )
    parser.add_argument("--max-findings", type=int, default=12, help="Show 1 to 50 findings.")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        review = build_assistant_review(
            args.project,
            question=args.question,
            max_findings=args.max_findings,
        )
        output = (
            markdown_assistant_review(review)
            if args.format == "markdown"
            else json.dumps(review, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
        )
    except (OSError, ValueError, AssistantSourceChangedError) as exc:
        print(f"cleanroomx-assistant: error: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(output)
    return 1 if (
        review["summary"]["error_count"] or review["summary"]["warning_count"]
    ) else 0


if __name__ == "__main__":
    raise SystemExit(main())
