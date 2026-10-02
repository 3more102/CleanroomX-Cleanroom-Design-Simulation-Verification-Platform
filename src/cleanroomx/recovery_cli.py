from __future__ import annotations

import argparse
import sys

from .cli_output import write_cli_output_or_report_error, dumps_strict_json
from .recovery_io import load_recovery_test
from .recovery_report import markdown_recovery_report
from .recovery_test import analyze_recovery_test
from .strict_json import StrictJSONError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-recovery-test",
        description="CleanroomX measured particle-recovery test analysis",
    )
    parser.add_argument("test", help="Path to recovery-test JSON")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", help="Optional output file")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = analyze_recovery_test(load_recovery_test(args.test))
    try:
        text = (
            dumps_strict_json(result)
            if args.format == "json"
            else markdown_recovery_report(result)
        )
    except StrictJSONError as exc:
        print(
            "cleanroomx-recovery-test: error: "
            f"analysis result is not strict JSON: {exc}",
            file=sys.stderr,
        )
        return 1

    if args.output:
        if not write_cli_output_or_report_error(
            "cleanroomx-recovery-test",
            args.output,
            text,
            protected_inputs=(args.test,),
        ):
            return 1
    else:
        print(text)

    status = result["criterion_status"]
    if status == "fail":
        return 2
    if status == "incomplete":
        return 3
    if status == "indeterminate":
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
