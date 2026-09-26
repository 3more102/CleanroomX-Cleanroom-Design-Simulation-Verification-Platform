from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
from typing import Sequence

from .application import _external_dependency_references, _resolve_relative
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


def _paths_alias(protected: Path, output: str | Path) -> bool:
    """Return True when an output path refers to a protected input file."""
    protected = protected.expanduser().resolve(strict=False)
    candidate = Path(output).expanduser()
    try:
        if candidate.resolve(strict=False) == protected:
            return True
    except (OSError, RuntimeError):
        pass
    try:
        return candidate.exists() and candidate.samefile(protected)
    except OSError:
        return False


def _dependency_output_alias(project, *, base_dir: Path, output: Path):
    """Return the first declared external dependency aliased by output."""
    for analysis in project.analyses:
        for field, declared_path in _external_dependency_references(
            analysis.kind,
            analysis.input,
        ):
            dependency = _resolve_relative(base_dir, declared_path)
            if _paths_alias(dependency, output):
                return analysis, field, dependency.expanduser().resolve(strict=False)
    return None


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = Path(args.project).expanduser().resolve(strict=False)
    output = Path(args.output).expanduser() if args.output else None
    try:
        if output is not None and _paths_alias(source, output):
            raise ValueError("--output must not refer to the source project file")
        project, revision_before = load_project_document_with_revision(source)
        if output is not None:
            dependency_alias = _dependency_output_alias(
                project,
                base_dir=source.parent,
                output=output,
            )
            if dependency_alias is not None:
                analysis, field, dependency = dependency_alias
                raise ValueError(
                    "--output must not overwrite external dependency "
                    f"{field!r} for analysis {analysis.id!r}: {dependency}"
                )
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
        if output is not None:
            atomic_write_text(output, text)
        else:
            sys.stdout.write(text)
        return project_diagnostics_exit_code(result)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"cleanroomx-project-check: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
