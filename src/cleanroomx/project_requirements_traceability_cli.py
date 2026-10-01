from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
from typing import Sequence

from .project import (
    atomic_write_text,
    capture_project_file_revision,
    load_project_document_with_revision,
    project_file_revision_matches,
)
from .project_diagnostics_cli import _assert_project_output_is_safe
from .project_requirements_traceability import (
    build_project_requirements_traceability,
    markdown_project_requirements_traceability,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-project-traceability",
        description=(
            "Inspect canonical persisted project requirements and requirement-to-analysis "
            "evidence mappings without running engineering analysis."
        ),
    )
    parser.add_argument("project", help="CleanroomX project file")
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        dest="output_format",
        help="Output format (default: json)",
    )
    parser.add_argument(
        "--output",
        help="Write the traceability report atomically instead of stdout",
    )
    return parser


def _attach_source_evidence(result: dict, source: Path, revision) -> dict:
    output = copy.deepcopy(result)
    output["source"] = {
        "path": str(source),
        "size_bytes": revision.size,
        "sha256": revision.sha256,
        "stable_during_inspection": True,
    }
    return output


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        source = Path(args.project).expanduser().resolve(strict=False)
        project, revision_before = load_project_document_with_revision(source)
        if args.output:
            _assert_project_output_is_safe(
                project,
                source=source,
                output=args.output,
            )

        result = build_project_requirements_traceability(project)
        revision_after = capture_project_file_revision(source)
        if not project_file_revision_matches(revision_before, revision_after):
            raise RuntimeError(
                "project file changed during requirements-traceability inspection; "
                "report was discarded"
            )

        result = _attach_source_evidence(result, source, revision_after)
        text = (
            json.dumps(
                result,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
            if args.output_format == "json"
            else markdown_project_requirements_traceability(result)
        )
        if args.output:
            _assert_project_output_is_safe(
                project,
                source=source,
                output=args.output,
            )
            atomic_write_text(
                args.output,
                text,
                before_replace=lambda: _assert_project_output_is_safe(
                    project,
                    source=source,
                    output=args.output,
                ),
            )
        else:
            sys.stdout.write(text)
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"cleanroomx-project-traceability: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
