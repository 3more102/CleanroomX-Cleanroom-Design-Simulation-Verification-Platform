from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .application import ExternalDependencyChangedError, run_analysis
from .project import atomic_write_text


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
    manifest_path = Path(args.manifest)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    try:
        run = run_analysis(
            "dossier",
            payload,
            base_dir=manifest_path.resolve().parent,
        )
    except ExternalDependencyChangedError as exc:
        print(f"cleanroomx-dossier: {exc}", file=sys.stderr)
        return 3

    result = run.result
    text = json.dumps(result, indent=2) if args.format == "json" else run.markdown
    if args.output:
        atomic_write_text(args.output, text)
    else:
        print(text)
    return 2 if result["executive_summary"]["state"] == "attention_required" else 0


if __name__ == "__main__":
    raise SystemExit(main())
