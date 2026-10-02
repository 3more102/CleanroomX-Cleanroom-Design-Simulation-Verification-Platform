from __future__ import annotations

import argparse
import sys

from .strict_json import StrictJSONError
from .cli_output import atomic_write_cli_output, dumps_strict_json
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
    try:
        text = (
            dumps_strict_json(result)
            if args.format == "json"
            else markdown_uncertainty_report(result)
        )
    except StrictJSONError as exc:
        print(
            f"cleanroomx-uncertainty: error: analysis result is not strict JSON: {exc}",
            file=sys.stderr,
        )
        return 1
    if args.output:
        atomic_write_cli_output(
            args.output,
            text,
            protected_inputs=(args.room,),
        )
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
