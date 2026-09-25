from __future__ import annotations

import argparse
import json

from .project import atomic_write_text
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
    text = (
        json.dumps(result, indent=2)
        if args.format == "json"
        else markdown_psychrometric_uncertainty_report(result)
    )

    if args.output:
        atomic_write_text(args.output, text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
