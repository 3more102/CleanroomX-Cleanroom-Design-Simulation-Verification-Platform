from __future__ import annotations

import argparse
import json

from .persistence import atomic_write_text
from .fan_speed import analyze_fan_speed_study
from .fan_speed_io import load_fan_speed_study
from .fan_speed_report import markdown_fan_speed_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-fan-speed",
        description="Bounded fan-speed affinity-law operating-point sweep",
    )
    parser.add_argument("study", help="Path to fan-speed study JSON")
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
    )
    parser.add_argument("--output", help="Optional output file")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = analyze_fan_speed_study(load_fan_speed_study(args.study))
    text = (
        json.dumps(result, indent=2)
        if args.format == "json"
        else markdown_fan_speed_report(result)
    )
    if args.output:
        atomic_write_text(args.output, text)
    else:
        print(text)
    return 0 if result["status"] == "screening_complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
