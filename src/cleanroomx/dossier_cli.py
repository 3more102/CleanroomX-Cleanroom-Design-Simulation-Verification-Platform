from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .cli_output import (
    CLI_OUTPUT_ERROR_EXIT_CODE,
    dumps_strict_json,
    publish_cli_output,
)
from .strict_json import StrictJSONError, load_strict_json
from .application import (
    ExternalDependencyChangedError,
    ExternalDependencySnapshotError,
    analysis_external_dependency_references,
    run_analysis,
)


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
    payload = load_strict_json(manifest_path)
    try:
        run = run_analysis(
            "dossier",
            payload,
            base_dir=manifest_path.resolve().parent,
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
        base_dir = manifest_path.resolve().parent
        protected_inputs = [manifest_path]
        for _field, declared_path in analysis_external_dependency_references(
            "dossier", payload
        ):
            dependency = Path(declared_path).expanduser()
            if not dependency.is_absolute():
                dependency = base_dir / dependency
            protected_inputs.append(dependency)
        if not publish_cli_output(
            args.output,
            text,
            protected_inputs=protected_inputs,
            program="cleanroomx-dossier",
        ):
            return CLI_OUTPUT_ERROR_EXIT_CODE
    else:
        print(text)
    return 2 if result["executive_summary"]["state"] == "attention_required" else 0


if __name__ == "__main__":
    raise SystemExit(main())
