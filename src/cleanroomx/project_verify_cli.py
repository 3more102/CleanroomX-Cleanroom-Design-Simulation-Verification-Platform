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
    _assert_output_is_distinct_from_dependencies,
    _assert_output_is_distinct_from_source,
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
    status_parser.add_argument(
        "analysis_id",
        nargs="?",
        help="Stable project analysis id (omit when using --all)",
    )
    status_parser.add_argument(
        "--all",
        action="store_true",
        dest="all_analyses",
        help=(
            "Gate the complete project verification set instead of one analysis. "
            "The gate passes only when at least one analysis is configured and "
            "every configured/currently retained verification is current and a "
            "verified PASS."
        ),
    )
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


def _project_status_gate(currency: dict[str, Any]) -> dict[str, Any]:
    configured = [
        item
        for item in currency["analyses"]
        if item["state"] != "not_configured"
    ]
    accepted_analysis_ids: list[str] = []
    rejected_analysis_ids: list[str] = []
    for item in configured:
        verified_pass = (
            isinstance(item.get("latest_record"), dict)
            and item["latest_record"].get("verified") is True
        )
        accepted = item["state"] == "current" and verified_pass
        target = accepted_analysis_ids if accepted else rejected_analysis_ids
        target.append(item["analysis_id"])

    all_current = bool(configured) and all(
        item["state"] == "current" for item in configured
    )
    all_verified_pass = bool(configured) and all(
        isinstance(item.get("latest_record"), dict)
        and item["latest_record"].get("verified") is True
        for item in configured
    )
    return {
        "configured_analysis_count": len(configured),
        "accepted_analysis_count": len(accepted_analysis_ids),
        "rejected_analysis_count": len(rejected_analysis_ids),
        "accepted_analysis_ids": accepted_analysis_ids,
        "rejected_analysis_ids": rejected_analysis_ids,
        "all_current": all_current,
        "all_verified_pass": all_verified_pass,
        "accepted": all_current and all_verified_pass,
    }

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


def _project_status_payload(
    source: Path,
    project,
    revision,
    currency: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "cleanroomx.project-verification-status-set",
        "schema_version": 1,
        "source": {
            "path": str(source),
            "size_bytes": revision.size,
            "sha256": revision.sha256,
            "stable_during_inspection": True,
        },
        "project": {
            "name": project.name,
        },
        "currency": currency,
        "gate": _project_status_gate(currency),
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
    _assert_output_is_distinct_from_source(source, output)
    _assert_output_is_distinct_from_dependencies(
        project,
        base_dir=source.parent,
        output=output,
    )
    text = _strict_json_text(workflow.to_dict())
    revision_after = capture_project_file_revision(source)
    if not project_file_revision_matches(revision_before, revision_after):
        raise RuntimeError(
            "project changed during verification artifact publication; output was discarded"
        )
    atomic_write_text(output, text)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = Path(args.project).expanduser().resolve(strict=False)
    try:
        if args.command == "status":
            if args.all_analyses and args.analysis_id is not None:
                raise ValueError("status accepts either an analysis_id or --all, not both")
            if not args.all_analyses and args.analysis_id is None:
                raise ValueError("status requires an analysis_id or --all")

            project, revision_before = load_project_document_with_revision(source)
            currency = assess_project_verification_currency(
                project,
                base_dir=source.parent,
            )

            if args.all_analyses:
                payload = _project_status_payload(
                    source,
                    project,
                    revision_before,
                    currency,
                )
                exit_code = 0 if payload["gate"]["accepted"] else 1
            else:
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
                payload = _status_payload(
                    source,
                    project,
                    revision_before,
                    assessment,
                )
                exit_code = _status_exit_code(assessment)

            revision_after = capture_project_file_revision(source)
            if not project_file_revision_matches(revision_before, revision_after):
                raise RuntimeError(
                    "project changed during verification-status inspection; "
                    "status result was discarded"
                )
            payload["source"]["size_bytes"] = revision_after.size
            payload["source"]["sha256"] = revision_after.sha256
            sys.stdout.write(_strict_json_text(payload))
            return exit_code

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
