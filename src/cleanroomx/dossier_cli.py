from __future__ import annotations

import argparse
import json
from pathlib import Path

from .project import atomic_write_text
from .dossier import build_dossier
from .dossier_report import markdown_dossier_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-dossier",
        description="Build a traceable CleanroomX engineering dossier from analysis inputs",
    )
    parser.add_argument("manifest", help="Path to dossier manifest JSON")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", help="Optional output file")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = build_dossier(args.manifest)
    text = (
        json.dumps(result, indent=2)
        if args.format == "json"
        else markdown_dossier_report(result)
    )
    if args.output:
        atomic_write_text(args.output, text)
    else:
        print(text)
    return 2 if result["executive_summary"]["state"] == "attention_required" else 0


if __name__ == "__main__":
    raise SystemExit(main())
