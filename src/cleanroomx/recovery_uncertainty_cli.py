from __future__ import annotations

import argparse
import json
from pathlib import Path

from .recovery_uncertainty import (
    analyze_recovery_uncertainty,
)
from .recovery_uncertainty_io import (
    load_recovery_uncertainty,
)
from .recovery_uncertainty_report import (
    markdown_recovery_uncertainty_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-recovery-uncertainty",
        description=(
            "CleanroomX uncertainty-aware measured "
            "recovery acceptance"
        ),
    )
    parser.add_argument(
        "test",
        help="Path to recovery-uncertainty JSON",
    )
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
    )
    parser.add_argument(
        "--output",
        help="Optional output file",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = analyze_recovery_uncertainty(
        load_recovery_uncertainty(args.test)
    )
    text = (
        json.dumps(result, indent=2)
        if args.format == "json"
        else markdown_recovery_uncertainty_report(
            result
        )
    )
    if args.output:
        Path(args.output).write_text(
            text,
            encoding="utf-8",
        )
    else:
        print(text)

    return {
        "fail": 2,
        "incomplete": 3,
        "indeterminate": 4,
    }.get(result["criterion_status"], 0)


if __name__ == "__main__":
    raise SystemExit(main())
