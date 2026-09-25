from __future__ import annotations

import argparse
import json

from .project import atomic_write_text

from .damper_study import solve_loop_damper_study
from .damper_study_io import load_loop_damper_study
from .damper_study_report import markdown_loop_damper_study_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-damper-study",
        description="CleanroomX explicit loop damper-resistance scenario study",
    )
    parser.add_argument("study", help="Path to damper-study JSON")
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
    )
    parser.add_argument("--output", help="Optional output file")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = solve_loop_damper_study(
        load_loop_damper_study(args.study)
    )
    text = (
        json.dumps(result, indent=2)
        if args.format == "json"
        else markdown_loop_damper_study_report(result)
    )
    if args.output:
        atomic_write_text(args.output, text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
