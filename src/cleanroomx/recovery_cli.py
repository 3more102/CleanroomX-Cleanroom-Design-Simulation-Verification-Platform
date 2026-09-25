from __future__ import annotations

import argparse
import json
from pathlib import Path

from .project import atomic_write_text
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
        json.dumps(result, indent=2)
        if args.format == "json"
        else markdown_recovery_report(result)
    )
    if args.output:
        atomic_write_text(args.output, text)
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
