from __future__ import annotations

import argparse
from pathlib import Path

from .jsonio import strict_json_dumps
from .recovery_io import load_recovery_test
from .recovery_report import markdown_recovery_report
from .recovery_test import analyze_recovery_test


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
    text = (
        strict_json_dumps(result, indent=2)
        if args.format == "json"
        else markdown_recovery_report(result)
    )
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
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
