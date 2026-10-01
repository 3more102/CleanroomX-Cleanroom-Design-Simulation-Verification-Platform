from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .application import (
    ExternalDependencyChangedError,
    ExternalDependencySnapshotError,
    _resolve_relative,
    analysis_external_dependency_references,
    run_analysis,
)
from .cli_output import assert_output_is_distinct_from_paths
from .persistence import atomic_write_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-consistency",
        description=(
            "Check duplicated room-airflow inputs across CleanroomX "
            "verification and HVAC projects"
        ),
    )
    parser.add_argument(
        "verification_project",
        help="Path to a CleanroomX multi-room verification project JSON",
    )
    parser.add_argument(
        "hvac_project",
        help="Path to a CleanroomX HVAC project JSON",
    )
    parser.add_argument(
        "--airflow-tolerance-m3-h",
        type=float,
        default=0.0,
        help=(
            "User-supplied absolute room-airflow consistency tolerance in m3/h "
            "(default: exact agreement)"
        ),
    )
    parser.add_argument(
        "--require-same-room-set",
        action="store_true",
        help="Fail when the two files do not contain identical room-name sets",
    )
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
    )
    parser.add_argument("--output", help="Optional output file")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    payload = {
        "verification_project": args.verification_project,
        "hvac_project": args.hvac_project,
        "room_airflow_abs_tolerance_m3_h": args.airflow_tolerance_m3_h,
        "require_same_room_set": args.require_same_room_set,
    }
    base_dir = Path.cwd()
    protected_output_paths = tuple(
        (
            f"consistency input {field!r}",
            _resolve_relative(base_dir, declared_path),
        )
        for field, declared_path in analysis_external_dependency_references(
            "consistency",
            payload,
        )
    )
    if args.output:
        try:
            assert_output_is_distinct_from_paths(
                args.output,
                protected_output_paths,
            )
        except (OSError, ValueError) as exc:
            print(f"cleanroomx-consistency: output safety error: {exc}", file=sys.stderr)
            return 3

    try:
        run = run_analysis("consistency", payload, base_dir=base_dir)
    except (ExternalDependencyChangedError, ExternalDependencySnapshotError) as exc:
        print(f"cleanroomx-consistency: {exc}", file=sys.stderr)
        return 3

    result = run.result
    text = json.dumps(result, indent=2) if args.format == "json" else run.markdown
    if args.output:
        try:
            atomic_write_text(
                args.output,
                text,
                before_replace=lambda: assert_output_is_distinct_from_paths(
                    args.output,
                    protected_output_paths,
                ),
            )
        except (OSError, ValueError) as exc:
            print(f"cleanroomx-consistency: output safety error: {exc}", file=sys.stderr)
            return 3
    else:
        print(text)
    return 2 if result["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
