from __future__ import annotations

import argparse
import sys

from .strict_json import StrictJSONError
from .cli_output import dumps_strict_json, publish_cli_output
from .psychrometric_uncertainty import analyze_psychrometric_uncertainty
from .psychrometric_uncertainty_io import load_psychrometric_uncertainty
from .psychrometric_uncertainty_report import (
    markdown_psychrometric_uncertainty_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-psychrometric-uncertainty",
        description=(
            "Deterministic psychrometric-state uncertainty envelope screening"
        ),
    )
    parser.add_argument("file", help="Path to psychrometric uncertainty JSON")
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
    )
    parser.add_argument("--output", help="Optional output file")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = analyze_psychrometric_uncertainty(
        load_psychrometric_uncertainty(args.file)
    )
    try:
        text = (
            dumps_strict_json(result)
            if args.format == "json"
            else markdown_psychrometric_uncertainty_report(result)
        )
    except StrictJSONError as exc:
        print(
            f"cleanroomx-psychrometric-uncertainty: error: analysis result is not strict JSON: {exc}",
            file=sys.stderr,
        )
        return 1

    if args.output:
        if not publish_cli_output(
            "cleanroomx-psychrometric-uncertainty",
            args.output,
            text,
            protected_inputs=(args.file,),
        ):
            return 1
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
