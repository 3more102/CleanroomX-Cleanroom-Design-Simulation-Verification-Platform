from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .cli_output import assert_output_is_distinct_from_paths, dumps_strict_json
from .strict_json import StrictJSONError, load_strict_json
from .application import (
    ExternalDependencyChangedError,
    ExternalDependencySnapshotError,
    _resolve_relative,
    analysis_external_dependency_references,
    run_analysis,
)
from .persistence import atomic_write_text


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
    manifest_path = Path(args.manifest).expanduser().resolve(strict=False)
    payload = load_strict_json(manifest_path)
    base_dir = manifest_path.parent
    protected_output_paths = (
        ("dossier manifest", manifest_path),
        *(
            (
                f"dossier external dependency {field!r}",
                _resolve_relative(base_dir, declared_path),
            )
            for field, declared_path in analysis_external_dependency_references(
                "dossier",
                payload,
            )
        ),
    )
    if args.output:
        try:
            assert_output_is_distinct_from_paths(
                args.output,
                protected_output_paths,
            )
        except (OSError, ValueError) as exc:
            print(f"cleanroomx-dossier: output safety error: {exc}", file=sys.stderr)
            return 3

    try:
        run = run_analysis(
            "dossier",
            payload,
            base_dir=base_dir,
        )
    except (ExternalDependencyChangedError, ExternalDependencySnapshotError) as exc:
        print(f"cleanroomx-dossier: {exc}", file=sys.stderr)
        return 3

    result = run.result
    try:
        text = dumps_strict_json(result) if args.format == "json" else run.markdown
    except StrictJSONError as exc:
        print(
            f"cleanroomx-dossier: error: analysis result is not strict JSON: {exc}",
            file=sys.stderr,
        )
        return 1

    if args.output:
        try:
            atomic_write_text(
                args.output,
                text,
                before_replace=lambda: assert_output_is_distinct_from_paths(
                    args.output,
                    protected_output_paths,
                ),
            )
        except (OSError, ValueError) as exc:
            print(f"cleanroomx-dossier: output safety error: {exc}", file=sys.stderr)
            return 3
    else:
        print(text)
    return 2 if result["executive_summary"]["state"] == "attention_required" else 0


if __name__ == "__main__":
    raise SystemExit(main())
