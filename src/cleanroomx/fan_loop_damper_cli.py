from __future__ import annotations

import argparse
import json
from pathlib import Path

from .fan_loop_damper import solve_fan_loop_damper_study
from .fan_loop_damper_io import load_fan_loop_damper_study
from .fan_loop_damper_report import markdown_fan_loop_damper_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-fan-damper",
        description="Discrete explicit-resistance damper study for a fan-driven loop network",
    )
    parser.add_argument("study", help="Path to fan/loop damper study JSON")
    parser.add_argument(
        "--format", choices=("json", "markdown"), default="markdown"
    )
    parser.add_argument("--output", help="Optional output file")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = solve_fan_loop_damper_study(
        load_fan_loop_damper_study(args.study)
    )
    text = (
        json.dumps(result, indent=2)
        if args.format == "json"
        else markdown_fan_loop_damper_report(result)
    )
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0 if result["status"] == "solved" else 2


if __name__ == "__main__":
    raise SystemExit(main())
