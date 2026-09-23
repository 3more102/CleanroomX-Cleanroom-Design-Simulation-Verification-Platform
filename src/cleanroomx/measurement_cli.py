from __future__ import annotations

import argparse
import json
from pathlib import Path

from .measurement import analyze_measurement
from .measurement_io import load_measurement
from .measurement_report import markdown_measurement_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-measurement",
        description="CleanroomX measurement uncertainty and provenance analysis",
    )
    parser.add_argument("measurement", help="Path to measurement JSON")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", help="Optional output file")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = analyze_measurement(load_measurement(args.measurement))
    text = (
        json.dumps(result, indent=2)
        if args.format == "json"
        else markdown_measurement_report(result)
    )
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)

    status = result["criterion_status"]
    if status == "fail":
        return 2
    if status == "indeterminate":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
