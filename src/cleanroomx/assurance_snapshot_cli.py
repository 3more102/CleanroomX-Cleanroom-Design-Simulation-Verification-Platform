from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .assurance_snapshot import (
    AssuranceSnapshotError,
    verify_assurance_snapshot_file,
    write_assurance_snapshot,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-assurance-snapshot",
        description=(
            "Create or verify deterministic, self-contained CleanroomX "
            "design-assurance snapshots."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    create_parser = sub.add_parser(
        "create",
        help=(
            "Freeze a design-assurance input and result into a tamper-evident "
            "snapshot."
        ),
    )
    create_parser.add_argument(
        "input",
        help="Design-assurance input JSON file",
    )
    create_parser.add_argument(
        "output",
        help="Output assurance snapshot JSON file",
    )

    verify_parser = sub.add_parser(
        "verify",
        help=(
            "Verify snapshot integrity and replay its embedded "
            "design-assurance input."
        ),
    )
    verify_parser.add_argument(
        "snapshot",
        help="Assurance snapshot JSON file",
    )
    return parser


def _print_json(payload: dict) -> None:
    sys.stdout.write(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "create":
            snapshot = write_assurance_snapshot(args.input, args.output)
            _print_json(
                {
                    "status": "created",
                    "schema": snapshot["schema"],
                    "schema_version": snapshot["schema_version"],
                    "output": args.output,
                    "snapshot_sha256": snapshot["snapshot_sha256"],
                    "source_sha256": snapshot["source"]["sha256"],
                    "result_sha256": snapshot["analysis"]["result_sha256"],
                    "traceability_sha256": (
                        snapshot["analysis"]["traceability_sha256"]
                    ),
                }
            )
            return 0

        report = verify_assurance_snapshot_file(args.snapshot)
        _print_json(report)
        return 0 if report["valid"] else 2
    except (OSError, AssuranceSnapshotError) as exc:
        print(
            f"cleanroomx-assurance-snapshot: error: {exc}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
