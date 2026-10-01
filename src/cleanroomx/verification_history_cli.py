from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from .project import (
    capture_project_file_revision,
    load_project_document_with_revision,
    project_file_revision_matches,
)
from .verification_run_history import (
    validate_project_verification_run_history,
    verification_run_history_records,
)
from .verification_currency import (
    assess_project_verification_currency,
    verification_history_record_currency_context,
)


VERIFICATION_HISTORY_INSPECTION_SCHEMA = "cleanroomx.verification-history-inspection"
VERIFICATION_HISTORY_INSPECTION_SCHEMA_VERSION = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-verification-history",
        description=(
            "Inspect persisted canonical project-requirements verification evidence "
            "without mutating the project."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser(
        "list",
        help="List compact summaries of retained verification records.",
    )
    list_parser.add_argument("project", help="CleanroomX project file")
    list_parser.add_argument(
        "--analysis-id",
        help="Return only records for this stable analysis id.",
    )

    show_parser = sub.add_parser(
        "show",
        help="Show one full persisted verification record by ledger sequence.",
    )
    show_parser.add_argument("project", help="CleanroomX project file")
    show_parser.add_argument(
        "--sequence",
        type=int,
        required=True,
        help="Persisted verification ledger sequence number.",
    )
    return parser


def _strict_json_clone(value: Any) -> Any:
    return json.loads(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
    )


def _compact_record(
    record: dict[str, Any],
    current_assessment: dict[str, Any] | None,
) -> dict[str, Any]:
    verification = record["verification"]
    return {
        "sequence": record["sequence"],
        "completed_at_utc": record["completed_at_utc"],
        "analysis_id": record["analysis_id"],
        "analysis_name": record["analysis_name"],
        "analysis_kind": record["analysis_kind"],
        "verification": {
            "status": verification["status"],
            "complete": verification["complete"],
            "verified": verification["verified"],
            "summary": copy.deepcopy(verification["summary"]),
        },
        "current_currency": verification_history_record_currency_context(
            record,
            current_assessment,
        ),
        "project_source_revision": record["project_source_revision"],
        "analysis_bundle_sha256": record["analysis_bundle_sha256"],
        "requirements_sha256": record["requirements_sha256"],
        "mappings_sha256": record["mappings_sha256"],
        "verification_sha256": record["verification_sha256"],
        "workflow_sha256": record["workflow_sha256"],
        "verification_identity_sha256": record["verification_identity_sha256"],
        "record_sha256": record["record_sha256"],
    }


def _load_stable_project(path: Path):
    project, revision_before = load_project_document_with_revision(path)
    history_summary = validate_project_verification_run_history(project.metadata)
    records = verification_run_history_records(project.metadata)
    currency = assess_project_verification_currency(
        project,
        base_dir=path.parent,
    )
    revision_after = capture_project_file_revision(path)
    if not project_file_revision_matches(revision_before, revision_after):
        raise RuntimeError(
            "project file changed during verification-history inspection; "
            "inspection result was discarded"
        )
    return project, revision_after, history_summary, records, currency


def _source_payload(path: Path, revision) -> dict[str, Any]:
    return {
        "path": str(path),
        "size_bytes": revision.size,
        "sha256": revision.sha256,
        "stable_during_inspection": True,
    }


def _print_json(payload: dict[str, Any]) -> None:
    sys.stdout.write(
        json.dumps(
            _strict_json_clone(payload),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = Path(args.project).expanduser().resolve(strict=False)
    try:
        project, revision, history_summary, records, currency = _load_stable_project(source)
        currency_by_analysis = {
            item["analysis_id"]: item
            for item in currency.get("analyses", [])
        }

        if args.command == "list":
            selected = records
            if args.analysis_id is not None:
                selected = [
                    record
                    for record in records
                    if record["analysis_id"] == args.analysis_id
                ]
            _print_json(
                {
                    "schema": VERIFICATION_HISTORY_INSPECTION_SCHEMA,
                    "schema_version": VERIFICATION_HISTORY_INSPECTION_SCHEMA_VERSION,
                    "source": _source_payload(source, revision),
                    "project": {
                        "name": project.name,
                        "analysis_count": len(project.analyses),
                    },
                    "history": history_summary,
                    "currency": currency,
                    "selection": {
                        "analysis_id": args.analysis_id,
                        "record_count": len(selected),
                    },
                    "records": [
                        _compact_record(
                            record,
                            currency_by_analysis.get(record["analysis_id"]),
                        )
                        for record in selected
                    ],
                }
            )
            return 0

        if args.sequence < 1:
            raise ValueError("verification-history sequence must be a positive integer")
        record = next(
            (item for item in records if item["sequence"] == args.sequence),
            None,
        )
        if record is None:
            raise ValueError(
                f"verification-history sequence {args.sequence} is not retained"
            )
        _print_json(
            {
                "schema": VERIFICATION_HISTORY_INSPECTION_SCHEMA,
                "schema_version": VERIFICATION_HISTORY_INSPECTION_SCHEMA_VERSION,
                "source": _source_payload(source, revision),
                "project": {
                    "name": project.name,
                    "analysis_count": len(project.analyses),
                },
                "history": history_summary,
                "currency": currency,
                "record_currency": verification_history_record_currency_context(
                    record,
                    currency_by_analysis.get(record["analysis_id"]),
                ),
                "record": copy.deepcopy(record),
            }
        )
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(
            f"cleanroomx-verification-history: error: {exc}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
