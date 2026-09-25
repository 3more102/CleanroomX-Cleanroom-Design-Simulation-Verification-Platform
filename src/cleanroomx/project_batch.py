from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Sequence

from . import __version__
from .application import run_analysis
from .markdown import markdown_text
from .project import (
    AnalysisDocument,
    ProjectDocument,
    ProjectFileRevision,
    atomic_write_text,
    capture_project_file_revision,
    load_project_document_with_revision,
    project_file_revision_matches,
)

PROJECT_BATCH_SCHEMA = "cleanroomx.project-batch-run"
PROJECT_BATCH_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ProjectAnalysisOutcome:
    analysis_id: str
    analysis_name: str
    kind: str
    execution_state: str
    run: dict | None = None
    error_type: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict:
        return {
            "analysis_id": self.analysis_id,
            "analysis_name": self.analysis_name,
            "kind": self.kind,
            "execution_state": self.execution_state,
            "run": self.run,
            "error": (
                None
                if self.error_type is None
                else {
                    "type": self.error_type,
                    "message": self.error_message or "",
                }
            ),
        }


@dataclass(frozen=True)
class ProjectBatchRun:
    project_name: str
    source_path: str
    source_size_bytes: int
    source_sha256: str
    selected_analysis_ids: tuple[str, ...]
    outcomes: tuple[ProjectAnalysisOutcome, ...]
    source_stable_during_run: bool
    source_change_stage: str | None = None
    source_change_analysis_id: str | None = None
    source_check_error: str | None = None

    @property
    def completed_count(self) -> int:
        return sum(item.execution_state == "completed" for item in self.outcomes)

    @property
    def error_count(self) -> int:
        return sum(item.execution_state == "error" for item in self.outcomes)

    @property
    def attempted_count(self) -> int:
        return len(self.outcomes)

    def to_dict(self) -> dict:
        payload = {
            "schema": PROJECT_BATCH_SCHEMA,
            "schema_version": PROJECT_BATCH_SCHEMA_VERSION,
            "cleanroomx_version": __version__,
            "project": {
                "name": self.project_name,
                "source_path": self.source_path,
                "source_revision": {
                    "size_bytes": self.source_size_bytes,
                    "sha256": self.source_sha256,
                },
            },
            "selection": {
                "analysis_ids": list(self.selected_analysis_ids),
                "requested_count": len(self.selected_analysis_ids),
            },
            "execution": {
                "attempted_count": self.attempted_count,
                "completed_count": self.completed_count,
                "error_count": self.error_count,
                "source_stable_during_run": self.source_stable_during_run,
                "source_change_stage": self.source_change_stage,
                "source_change_analysis_id": self.source_change_analysis_id,
                "source_check_error": self.source_check_error,
            },
            "analyses": [item.to_dict() for item in self.outcomes],
        }
        # Enforce the same finite, strict-JSON boundary as application results.
        json.dumps(payload, sort_keys=True, allow_nan=False)
        return payload


def _select_analyses(
    project: ProjectDocument,
    analysis_ids: Sequence[str] | None,
) -> tuple[AnalysisDocument, ...]:
    if analysis_ids is None:
        return tuple(project.analyses)

    requested = tuple(analysis_ids)
    if any(not isinstance(value, str) or not value.strip() for value in requested):
        raise ValueError("analysis ids must be non-empty strings")
    if len(requested) != len(set(requested)):
        raise ValueError("analysis ids must not contain duplicates")

    available = {analysis.id for analysis in project.analyses}
    unknown = sorted(set(requested) - available)
    if unknown:
        raise ValueError("unknown project analysis id(s): " + ", ".join(unknown))

    selected = set(requested)
    # Project order is authoritative so the same project and selection always
    # schedule analyses in the same deterministic order.
    return tuple(analysis for analysis in project.analyses if analysis.id in selected)


def _source_revision_state(
    path: Path,
    expected: ProjectFileRevision,
) -> tuple[bool, str | None]:
    try:
        current = capture_project_file_revision(path)
    except OSError as exc:
        return False, str(exc)
    return project_file_revision_matches(expected, current), None


def run_project_file(
    path: str | Path,
    *,
    analysis_ids: Sequence[str] | None = None,
    fail_fast: bool = False,
) -> ProjectBatchRun:
    """Execute project analyses against one stable in-memory project revision.

    The project file is never modified. The source revision is checked before
    every scheduled analysis and again after each completed/failed analysis.
    If the source changes, no further analyses are scheduled.
    """

    source = Path(path).expanduser().resolve(strict=False)
    project, revision = load_project_document_with_revision(source)
    if not revision.exists or revision.size is None or revision.sha256 is None:
        raise OSError(f"project source is not a readable regular file: {source}")

    selected = _select_analyses(project, analysis_ids)
    outcomes: list[ProjectAnalysisOutcome] = []
    source_stable = True
    change_stage: str | None = None
    change_analysis_id: str | None = None
    source_check_error: str | None = None

    for analysis in selected:
        matches, check_error = _source_revision_state(source, revision)
        if not matches:
            source_stable = False
            change_stage = "before-analysis"
            change_analysis_id = analysis.id
            source_check_error = check_error
            break

        failed = False
        try:
            run = run_analysis(
                analysis.kind,
                copy.deepcopy(analysis.input),
                base_dir=source.parent,
            )
        except Exception as exc:  # per-analysis execution boundary
            failed = True
            outcomes.append(
                ProjectAnalysisOutcome(
                    analysis_id=analysis.id,
                    analysis_name=analysis.name,
                    kind=analysis.kind,
                    execution_state="error",
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
            )
        else:
            outcomes.append(
                ProjectAnalysisOutcome(
                    analysis_id=analysis.id,
                    analysis_name=analysis.name,
                    kind=analysis.kind,
                    execution_state="completed",
                    run=run.to_dict(),
                )
            )

        matches, check_error = _source_revision_state(source, revision)
        if not matches:
            source_stable = False
            change_stage = "after-analysis"
            change_analysis_id = analysis.id
            source_check_error = check_error
            break

        if failed and fail_fast:
            break

    return ProjectBatchRun(
        project_name=project.name,
        source_path=str(source),
        source_size_bytes=revision.size,
        source_sha256=revision.sha256,
        selected_analysis_ids=tuple(analysis.id for analysis in selected),
        outcomes=tuple(outcomes),
        source_stable_during_run=source_stable,
        source_change_stage=change_stage,
        source_change_analysis_id=change_analysis_id,
        source_check_error=source_check_error,
    )


def render_project_batch_markdown(batch: ProjectBatchRun) -> str:
    lines = [
        f"# CleanroomX project batch — {markdown_text(batch.project_name)}",
        "",
        f"- Source: {markdown_text(batch.source_path)}",
        f"- Source SHA-256: `{batch.source_sha256}`",
        f"- Requested analyses: {len(batch.selected_analysis_ids)}",
        f"- Attempted: {batch.attempted_count}",
        f"- Completed: {batch.completed_count}",
        f"- Execution errors: {batch.error_count}",
        "- Source stable during run: "
        + ("yes" if batch.source_stable_during_run else "no"),
    ]
    if not batch.source_stable_during_run:
        lines.append(
            "- Source-change boundary: "
            f"{batch.source_change_stage or 'unknown'}"
            + (
                f" at analysis {markdown_text(batch.source_change_analysis_id)}"
                if batch.source_change_analysis_id
                else ""
            )
        )
        if batch.source_check_error:
            lines.append(f"- Source-check error: {markdown_text(batch.source_check_error)}")

    lines.extend(["", "## Analysis outcomes", ""])
    if not batch.outcomes:
        lines.append("No analyses were executed.")
    for outcome in batch.outcomes:
        lines.append(
            f"### {markdown_text(outcome.analysis_name)} "
            f"({markdown_text(outcome.analysis_id)}, {markdown_text(outcome.kind)})"
        )
        lines.append("")
        if outcome.execution_state == "completed":
            assert outcome.run is not None
            lines.append(f"- Execution: completed")
            lines.append(f"- Analysis status: {outcome.run.get('status', 'complete')}")
            diagnostics = outcome.run.get("diagnostics")
            provenance = (
                diagnostics.get("application_execution_provenance")
                if isinstance(diagnostics, dict)
                else None
            )
            if isinstance(provenance, dict) and provenance.get("input_sha256"):
                lines.append(f"- Input SHA-256: `{provenance['input_sha256']}`")
        else:
            lines.append("- Execution: error")
            lines.append(
                f"- Error: {markdown_text(outcome.error_type or 'Error')}: "
                f"{markdown_text(outcome.error_message or '')}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def project_batch_exit_code(batch: ProjectBatchRun) -> int:
    if not batch.source_stable_during_run:
        return 3
    if batch.error_count:
        return 2
    return 0


def _serialize_output(batch: ProjectBatchRun, output_format: str) -> str:
    if output_format == "markdown":
        return render_project_batch_markdown(batch)
    return (
        json.dumps(
            batch.to_dict(),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-project-run",
        description=(
            "Execute analyses from a CleanroomX project in deterministic project order "
            "without modifying the project file."
        ),
    )
    parser.add_argument("project", help="Path to a .cleanroomx.json project")
    parser.add_argument(
        "--analysis",
        action="append",
        dest="analysis_ids",
        metavar="ID",
        help="Run only this analysis id; repeat to select multiple analyses",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop scheduling analyses after the first execution error",
    )
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


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        batch = run_project_file(
            args.project,
            analysis_ids=args.analysis_ids,
            fail_fast=args.fail_fast,
        )
        text = _serialize_output(batch, args.output_format)
        if args.output:
            atomic_write_text(args.output, text)
        else:
            sys.stdout.write(text)
        return project_batch_exit_code(batch)
    except (OSError, ValueError) as exc:
        print(f"cleanroomx-project-run: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
