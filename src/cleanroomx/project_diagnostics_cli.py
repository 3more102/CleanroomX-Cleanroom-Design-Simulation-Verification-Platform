from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
from typing import Sequence

from .cli_output import CliStateError
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
    """Return whether output refers to a protected input path."""
    protected = protected.expanduser().resolve(strict=False)
    destination = Path(output).expanduser()
    try:
        if destination.resolve(strict=False) == protected:
            return True
    except (OSError, RuntimeError) as exc:
        raise OSError(
            f"could not verify diagnostics output path: {destination}"
        ) from exc
    try:
        if not destination.exists() or not protected.exists():
            return False
        return destination.samefile(protected)
    except FileNotFoundError:
        # A path disappearing between the existence and identity checks cannot
        # still be the existing file that would be overwritten. Lexical aliases
        # were already caught by the resolved-path equality check above.
        return False
    except OSError as exc:
        raise OSError(
            f"could not verify diagnostics output path against protected input: {destination}"
        ) from exc


def _assert_output_is_distinct_from_source(
    source: Path,
    output: str | Path,
) -> None:
    """Reject report destinations that could replace the checked project file."""
    if _paths_alias(source, output):
        raise ValueError(
            "diagnostics output path must be different from the project source"
        )


def _assert_output_is_distinct_from_dependencies(
    project,
    *,
    base_dir: Path,
    output: str | Path,
) -> None:
    """Reject report destinations that could replace declared engineering inputs."""
    for analysis in project.analyses:
        for field, declared_path in _external_dependency_references(
            analysis.kind,
            analysis.input,
        ):
            dependency = _resolve_relative(base_dir, declared_path)
            if _paths_alias(dependency, output):
                raise ValueError(
                    "diagnostics output path must be different from external dependency "
                    f"{field!r} for analysis {analysis.id!r}: "
                    f"{dependency.expanduser().resolve(strict=False)}"
                )


def _assert_project_output_is_safe(
    project,
    *,
    source: Path,
    output: str | Path,
) -> None:
    """Reject a report destination that aliases project engineering inputs.

    Call immediately before publication as well as before expensive work so a
    pathname identity change cannot bypass the protected-output boundary.
    """
    _assert_output_is_distinct_from_source(source, output)
    _assert_output_is_distinct_from_dependencies(
        project,
        base_dir=source.parent,
        output=output,
    )


def _assert_project_publication_safe(
    project,
    *,
    source: Path,
    revision,
    output: str | Path,
    output_guard=None,
) -> None:
    """Revalidate exact source revision and protected output identity before commit."""
    current = capture_project_file_revision(source)
    if not project_file_revision_matches(revision, current):
        raise CliStateError(
            "project source changed before report publication; output was discarded"
        )
    guard = _assert_project_output_is_safe if output_guard is None else output_guard
    guard(
        project,
        source=source,
        output=output,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = Path(args.project).expanduser().resolve(strict=False)
    try:
        project, revision_before = load_project_document_with_revision(source)
        if args.output:
            _assert_project_output_is_safe(
                project,
                source=source,
                output=args.output,
            )
        result = analyze_project_diagnostics(project, base_dir=source.parent)
        revision_after = capture_project_file_revision(source)
        if not project_file_revision_matches(revision_before, revision_after):
            raise CliStateError(
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
            _assert_project_publication_safe(
                project,
                source=source,
                revision=revision_before,
                output=args.output,
            )
            atomic_write_text(
                args.output,
                text,
                before_replace=lambda: _assert_project_publication_safe(
                    project,
                    source=source,
                    revision=revision_before,
                    output=args.output,
                ),
            )
        else:
            sys.stdout.write(text)
        return project_diagnostics_exit_code(result)
    except (OSError, CliStateError, ValueError) as exc:
        print(f"cleanroomx-project-check: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
