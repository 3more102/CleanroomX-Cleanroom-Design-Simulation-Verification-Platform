from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
from typing import Sequence

from .cli_output import CliStateError, resolve_cli_path
from .application import _external_dependency_references, _resolve_relative
from .project import (
    atomic_write_text,
    capture_project_file_revision,
    load_project_document_with_revision,
    project_file_revision_matches,
)
from .strict_json import load_strict_json_snapshot
from .project_diagnostics_baseline import (
    compare_project_diagnostics,
    markdown_project_diagnostics_comparison,
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
    parser.add_argument(
        "--baseline", help="Compare with a prior project-diagnostics JSON report",
    )
    parser.add_argument(
        "--fail-on-regression", action="store_true",
        help="With --baseline, fail only for new errors/warnings (exit 3)",
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
    destination = Path(output)
    try:
        protected_path = protected.expanduser()
        destination = destination.expanduser()
        protected_resolved = protected_path.resolve(strict=False)
        if destination.resolve(strict=False) == protected_resolved:
            return True
    except (OSError, RuntimeError) as exc:
        raise OSError(
            f"could not verify diagnostics output path: {destination}"
        ) from exc
    try:
        if not destination.exists() or not protected_resolved.exists():
            return False
        return destination.samefile(protected_resolved)
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
                    f"{dependency}"
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
    try:
        if args.fail_on_regression and not args.baseline:
            raise ValueError("--fail-on-regression requires --baseline")
        source = resolve_cli_path(args.project, label="project")
        baseline_path = (
            resolve_cli_path(args.baseline, label="baseline")
            if args.baseline else None
        )
        if baseline_path is not None and _paths_alias(source, baseline_path):
            raise ValueError("diagnostics baseline must not alias project source")
        if baseline_path is not None and args.output and _paths_alias(
            baseline_path, args.output
        ):
            raise ValueError("diagnostics output must not overwrite baseline")
        baseline_revision = None
        baseline_report = None
        baseline_bytes = None
        if baseline_path is not None:
            baseline_revision = capture_project_file_revision(baseline_path)
            baseline_snapshot = load_strict_json_snapshot(
                baseline_path, max_bytes=2 * 1024 * 1024
            )
            baseline_report = baseline_snapshot.value
            baseline_bytes = baseline_snapshot.raw_bytes
            if not project_file_revision_matches(
                baseline_revision, capture_project_file_revision(baseline_path)
            ):
                raise CliStateError("diagnostics baseline changed during input read")
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
        comparison = None
        if baseline_report is not None:
            provenance = baseline_report.get("source") if isinstance(baseline_report, dict) else None
            if not isinstance(provenance, dict) or provenance.get("path") != str(source):
                raise ValueError("diagnostics baseline source path does not match project source")
            comparison = compare_project_diagnostics(baseline_report, result)
            comparison["baseline_report_sha256"] = hashlib.sha256(baseline_bytes).hexdigest()
            result["comparison"] = comparison
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
            else (
                markdown_project_diagnostics_report(result)
                + (markdown_project_diagnostics_comparison(comparison) if comparison else "")
            )
        )
        def check_baseline_unchanged():
            if baseline_path is not None and not project_file_revision_matches(
                baseline_revision, capture_project_file_revision(baseline_path)
            ):
                raise CliStateError(
                    "diagnostics baseline changed before report publication"
                )
        check_baseline_unchanged()
        if args.output:
            def guard_publication():
                _assert_project_publication_safe(
                    project,
                    source=source,
                    revision=revision_before,
                    output=args.output,
                )
                check_baseline_unchanged()
                if baseline_path is not None and _paths_alias(
                    baseline_path, args.output
                ):
                    raise ValueError("diagnostics output must not overwrite baseline")
            guard_publication()
            atomic_write_text(args.output, text, before_replace=guard_publication)
        else:
            sys.stdout.write(text)
        if args.fail_on_regression:
            return 3 if comparison["regressed"] else 0
        return project_diagnostics_exit_code(result)
    except (OSError, CliStateError, ValueError) as exc:
        print(f"cleanroomx-project-check: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
