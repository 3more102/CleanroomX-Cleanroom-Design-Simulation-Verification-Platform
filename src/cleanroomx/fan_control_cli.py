from __future__ import annotations

import argparse
import json
from pathlib import Path

from .fan_control import analyze_fan_control_study
from .fan_control_io import load_fan_control_study
from .fan_control_report import markdown_fan_control_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-fan-control",
        description="CleanroomX explicit fan-control state study",
    )
    parser.add_argument("study", help="Path to fan-control study JSON")
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
    )
    parser.add_argument("--output", help="Optional output file")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = analyze_fan_control_study(
        load_fan_control_study(args.study)
    )
    output = (
        json.dumps(result, indent=2)
        if args.format == "json"
        else markdown_fan_control_report(result)
    )
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
    else:
        print(output)

    if result["analysis_status"] != "screening_complete":
        return 2
    if result["target_status"] == "target_not_met":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
