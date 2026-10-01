from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from .project import (
    atomic_write_text,
    capture_project_file_revision,
    load_project_document_with_revision,
    project_file_revision_matches,
)
from .project_diagnostics_cli import (
    _assert_project_output_is_safe,
    _assert_project_publication_safe,
)
from .project_requirements_workflow import (
    ProjectRequirementsWorkflowRun,
    run_project_requirements_workflow,
)
from .project_verification_persistence import (
    persist_project_requirements_workflow_run,
)
from .verification_currency import assess_project_verification_currency


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-project-verify",
        description=(
            "Run canonical project requirements verification for one saved analysis "
            "and optionally persist the resulting engineering evidence."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser(
        "run",
        help="Run canonical requirements verification without mutating the project.",
    )
    run_parser.add_argument("project", help="CleanroomX project file")
    run_parser.add_argument("analysis_id", help="Stable project analysis id")
    run_parser.add_argument(
        "--output",
        help="Write the full strict-JSON workflow artifact atomically instead of stdout",
    )

    persist_parser = sub.add_parser(
        "persist",
        help=(
            "Run canonical requirements verification and append it to the project's "
            "tamper-evident verification history."
        ),
    )
    persist_parser.add_argument("project", help="CleanroomX project file")
    persist_parser.add_argument("analysis_id", help="Stable project analysis id")


    status_parser = sub.add_parser(
        "status",
        help=(
            "Gate on the latest persisted verification being both current and a "
            "verified PASS without re-running engineering analysis."
        ),
    )
    status_parser.add_argument("project", help="CleanroomX project file")
    status_parser.add_argument("analysis_id", help="Stable project analysis id")
    return parser


def _strict_json_text(value: Any) -> str:
    return (
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def _verification_exit_code(workflow: ProjectRequirementsWorkflowRun) -> int:
    verification = workflow.verification
    return 0 if verification.get("verified") is True else 1


def _status_exit_code(assessment: dict[str, Any]) -> int:
    latest_record = assessment.get("latest_record")
    verified_pass = (
        isinstance(latest_record, dict)
        and latest_record.get("verified") is True
    )
    return 0 if assessment.get("state") == "current" and verified_pass else 1


def _status_payload(
    source: Path,
    project,
    revision,
    assessment: dict[str, Any],
) -> dict[str, Any]:
    latest_record = assessment.get("latest_record")
    verified_pass = (
        isinstance(latest_record, dict)
        and latest_record.get("verified") is True
    )
    current = assessment.get("state") == "current"
    return {
        "schema": "cleanroomx.project-verification-status",
        "schema_version": 1,
        "source": {
            "path": str(source),
            "size_bytes": revision.size,
            "sha256": revision.sha256,
            "stable_during_inspection": True,
        },
        "project": {
            "name": project.name,
            "analysis_id": assessment["analysis_id"],
        },
        "currency": assessment,
        "gate": {
            "current": current,
            "verified_pass": verified_pass,
            "accepted": current and verified_pass,
        },
    }


def _write_run_output(
    source: Path,
    workflow: ProjectRequirementsWorkflowRun,
    output: str | Path,
) -> None:
    """Publish a workflow artifact only while its exact project revision remains current."""
    project, revision_before = load_project_document_with_revision(source)
    if revision_before.sha256 != workflow.source_revision:
        raise RuntimeError(
            "project changed after requirements verification; workflow output was discarded"
        )
    _assert_project_output_is_safe(
        project,
        source=source,
        output=output,
    )
    text = _strict_json_text(workflow.to_dict())
    revision_after = capture_project_file_revision(source)
    if not project_file_revision_matches(revision_before, revision_after):
        raise RuntimeError(
            "project changed during verification artifact publication; output was discarded"
        )
    _assert_project_publication_safe(
        project,
        source=source,
        revision=revision_before,
        output=output,
    )
    atomic_write_text(
        output,
        text,
        before_replace=lambda: _assert_project_publication_safe(
            project,
            source=source,
            revision=revision_before,
            output=output,
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = Path(args.project).expanduser().resolve(strict=False)
    try:
        if args.command == "status":
            project, revision_before = load_project_document_with_revision(source)
            currency = assess_project_verification_currency(
                project,
                base_dir=source.parent,
            )
            assessment = next(
                (
                    item
                    for item in currency["analyses"]
                    if item["analysis_id"] == args.analysis_id
                ),
                None,
            )
            if assessment is None:
                raise ValueError(
                    f"analysis {args.analysis_id!r} is not present in the current project"
                )
            revision_after = capture_project_file_revision(source)
            if not project_file_revision_matches(revision_before, revision_after):
                raise RuntimeError(
                    "project changed during verification-status inspection; "
                    "status result was discarded"
                )
            sys.stdout.write(
                _strict_json_text(
                    _status_payload(
                        source,
                        project,
                        revision_after,
                        assessment,
                    )
                )
            )
            return _status_exit_code(assessment)

        workflow = run_project_requirements_workflow(
            source,
            args.analysis_id,
        )
        exit_code = _verification_exit_code(workflow)

        if args.command == "run":
            if args.output:
                _write_run_output(source, workflow, args.output)
            else:
                sys.stdout.write(_strict_json_text(workflow.to_dict()))
            return exit_code

        persisted = persist_project_requirements_workflow_run(
            source,
            workflow,
        )
        sys.stdout.write(
            _strict_json_text(
                {
                    "workflow": {
                        "source_project_revision": workflow.source_revision,
                        "analysis_id": workflow.analysis_id,
                        "verification_status": workflow.verification["status"],
                        "verification_complete": workflow.verification["complete"],
                        "verified": workflow.verification["verified"],
                        "verification_sha256": workflow.verification[
                            "verification_sha256"
                        ],
                        "workflow_sha256": workflow.workflow_sha256,
                    },
                    "persistence": persisted.to_dict(),
                }
            )
        )
        return exit_code
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"cleanroomx-project-verify: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
