from __future__ import annotations

import argparse
import json
from pathlib import Path

from .fan_control import analyze_fan_speed_control
from .fan_control_io import load_fan_speed_control_study
from .fan_control_report import markdown_fan_speed_control_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-fan-control",
        description="CleanroomX bounded fan-speed control scenario study",
    )
    parser.add_argument("study", help="Path to fan-speed control study JSON")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", help="Optional output file")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = analyze_fan_speed_control(load_fan_speed_control_study(args.study))
    text = (
        json.dumps(result, indent=2)
        if args.format == "json"
        else markdown_fan_speed_control_report(result)
    )
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)

    return 2 if result["status"] == "target_not_met_in_tested_scenarios" else 0


if __name__ == "__main__":
    raise SystemExit(main())
