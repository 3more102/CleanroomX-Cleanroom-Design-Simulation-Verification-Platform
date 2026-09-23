from __future__ import annotations

import argparse
import json
from pathlib import Path

from .uncertainty import analyze_room_uncertainty
from .uncertainty_io import load_uncertain_room
from .uncertainty_report import markdown_uncertainty_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-uncertainty",
        description="CleanroomX conservative uncertainty and input-provenance analysis",
    )
    parser.add_argument("room", help="Path to uncertain-room JSON")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", help="Optional output file")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = analyze_room_uncertainty(load_uncertain_room(args.room))
    text = (
        json.dumps(result, indent=2)
        if args.format == "json"
        else markdown_uncertainty_report(result)
    )
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)

    status = result["requirement"]["status"]
    if status == "fail":
        return 2
    if status == "indeterminate":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
