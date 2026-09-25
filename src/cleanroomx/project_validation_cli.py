from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .project import (
    ProjectFormatError,
    atomic_write_text,
    load_project_document_with_revision,
)
from .project_validation import (
    markdown_project_validation_report,
    validate_project,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-project-validate",
        description=(
            "Validate every analysis and project-wide spatial state in a "
            "CleanroomX desktop project without running analyses"
        ),
    )
    parser.add_argument("project", help="Path to a .cleanroomx.json project")
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
        help="Validation report format (default: markdown)",
    )
    parser.add_argument("--output", help="Optional output file")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_path = Path(args.project)
    try:
        project, _revision = load_project_document_with_revision(project_path)
        report = validate_project(project, base_dir=project_path.parent)
    except (OSError, ProjectFormatError, TypeError, ValueError) as exc:
        print(f"cleanroomx-project-validate: {exc}", file=sys.stderr)
        return 2

    text = (
        json.dumps(
            report.to_dict(),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
        if args.format == "json"
        else markdown_project_validation_report(report)
    )
    if args.output:
        try:
            atomic_write_text(args.output, text)
        except OSError as exc:
            print(f"cleanroomx-project-validate: cannot write report: {exc}", file=sys.stderr)
            return 2
    else:
        print(text, end="")

    return 2 if report.status == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
