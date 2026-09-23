from __future__ import annotations

import argparse
import json
from pathlib import Path

from .duct import analyze_duct_network
from .duct_io import load_duct_network
from .duct_report import markdown_duct_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-duct",
        description="Analyze explicit cleanroom duct paths and critical-path pressure loss.",
    )
    parser.add_argument("file")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = analyze_duct_network(load_duct_network(args.file))
    rendered = (
        json.dumps(result, indent=2)
        if args.format == "json"
        else markdown_duct_report(result)
    )
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
