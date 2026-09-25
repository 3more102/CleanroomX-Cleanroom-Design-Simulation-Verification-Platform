from __future__ import annotations

import argparse
import json
from pathlib import Path

from .project import atomic_write_text
from .qualification import analyze_qualification_uncertainty
from .qualification_io import load_qualification_uncertainty
from .qualification_report import markdown_qualification_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-qualification",
        description="Uncertainty-aware cleanroom qualification screening",
    )
    parser.add_argument("file", help="Path to qualification uncertainty JSON")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", help="Optional output file")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = analyze_qualification_uncertainty(load_qualification_uncertainty(args.file))
    text = (
        json.dumps(result, indent=2)
        if args.format == "json"
        else markdown_qualification_report(result)
    )

    if args.output:
        atomic_write_text(args.output, text)
    else:
        print(text)

    if result["overall_status"] == "fail":
        return 2
    if result["overall_status"] == "indeterminate":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
