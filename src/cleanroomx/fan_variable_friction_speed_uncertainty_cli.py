from __future__ import annotations

import argparse
import json
from pathlib import Path

from .fan_variable_friction_speed_uncertainty import (
    analyze_fan_variable_friction_speed_uncertainty,
)
from .fan_variable_friction_speed_uncertainty_io import (
    load_fan_variable_friction_speed_uncertainty,
)
from .fan_variable_friction_speed_uncertainty_report import (
    markdown_fan_variable_friction_speed_uncertainty_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-fan-loop-friction-speed-uncertainty",
        description=(
            "Fan-speed sweeps with bounded nonlinear fan/loop uncertainty"
        ),
    )
    parser.add_argument(
        "study",
        help="Path to fan-speed/variable-friction uncertainty JSON",
    )
    parser.add_argument(
        "--format", choices=("json", "markdown"), default="markdown"
    )
    parser.add_argument("--output", help="Optional output file")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = analyze_fan_variable_friction_speed_uncertainty(
        load_fan_variable_friction_speed_uncertainty(args.study)
    )
    text = (
        json.dumps(result, indent=2)
        if args.format == "json"
        else markdown_fan_variable_friction_speed_uncertainty_report(result)
    )
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0 if result["status"] == "screening_complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
