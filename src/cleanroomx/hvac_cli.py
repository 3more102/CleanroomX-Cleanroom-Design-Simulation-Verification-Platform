from __future__ import annotations

import argparse
import sys

from .cli_output import dumps_strict_json
from .project import atomic_write_text
from .hvac import analyze_hvac_project
from .hvac_io import load_hvac_project
from .hvac_report import markdown_hvac_report
from .strict_json import StrictJSONError


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
    try:
        text = (
            dumps_strict_json(result)
            if args.format == "json"
            else markdown_hvac_report(result)
        )
    except StrictJSONError as exc:
        print(
            f"cleanroomx-hvac: error: analysis result is not strict JSON: {exc}",
            file=sys.stderr,
        )
        return 1

    if args.output:
        atomic_write_text(args.output, text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
