from __future__ import annotations

import argparse
import json
from pathlib import Path

from .project import atomic_write_text
from .hvac import analyze_hvac_project
from .hvac_io import load_hvac_project
from .hvac_report import markdown_hvac_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-hvac",
        description="CleanroomX preliminary HVAC and psychrometric analysis",
    )
    parser.add_argument("project", help="Path to HVAC project JSON")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", help="Optional output file")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = analyze_hvac_project(load_hvac_project(args.project))
    text = (
        json.dumps(result, indent=2)
        if args.format == "json"
        else markdown_hvac_report(result)
    )
    if args.output:
        atomic_write_text(args.output, text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
