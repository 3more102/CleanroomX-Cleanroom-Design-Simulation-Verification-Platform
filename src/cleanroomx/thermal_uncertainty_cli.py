from __future__ import annotations

import argparse
import json
from pathlib import Path

from .thermal_uncertainty import analyze_thermal_uncertainty
from .thermal_uncertainty_io import load_thermal_uncertainty_case
from .thermal_uncertainty_report import markdown_thermal_uncertainty_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-thermal-uncertainty",
        description=(
            "CleanroomX endpoint-scenario screening for bounded thermal/HVAC inputs"
        ),
    )
    parser.add_argument("case", help="Path to thermal-uncertainty JSON")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", help="Optional output file")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = analyze_thermal_uncertainty(
        load_thermal_uncertainty_case(args.case)
    )
    text = (
        json.dumps(result, indent=2)
        if args.format == "json"
        else markdown_thermal_uncertainty_report(result)
    )
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
