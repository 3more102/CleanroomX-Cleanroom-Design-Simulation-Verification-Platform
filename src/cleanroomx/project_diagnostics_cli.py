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
from .project_diagnostics import (
    analyze_project_diagnostics,
    markdown_project_diagnostics_report,
    project_diagnostics_exit_code,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-project-check",
        description=(
            "Run deterministic project-wide CleanroomX model, spatial, "
            "synchronization, input, and provenance diagnostics."
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
        help="Write the report atomically to this path instead of stdout",
    )
    return parser


def _attach_source_evidence(result: dict, path: Path, revision) -> dict:
    output = copy.deepcopy(result)
    output["source"] = {
        "path": str(path),
        "size_bytes": revision.size,
        "sha256": revision.sha256,
        "stable_during_check": True,
    }
    return output


def _assert_output_is_distinct_from_source(
    source: Path,
    output: str | Path,
) -> None:
    """Reject report destinations that could replace the checked project file."""
    destination = Path(output)
    if destination.resolve(strict=False) == source:
        raise ValueError(
            "diagnostics output path must be different from the project source"
        )
    try:
        aliases_source = destination.exists() and destination.samefile(source)
    except OSError as exc:
        raise OSError(
            f"could not verify diagnostics output path against project source: {destination}"
        ) from exc
    if aliases_source:
        raise ValueError(
            "diagnostics output path must be different from the project source"
        )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = Path(args.project).expanduser().resolve(strict=False)
    try:
        project, revision_before = load_project_document_with_revision(source)
        if args.output:
            _assert_output_is_distinct_from_source(source, args.output)
        result = analyze_project_diagnostics(project, base_dir=source.parent)
        revision_after = capture_project_file_revision(source)
        if not project_file_revision_matches(revision_before, revision_after):
            raise RuntimeError(
                "project file changed during diagnostics; report was discarded"
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
            else markdown_project_diagnostics_report(result)
        )
        if args.output:
            atomic_write_text(args.output, text)
        else:
            sys.stdout.write(text)
        return project_diagnostics_exit_code(result)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"cleanroomx-project-check: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
