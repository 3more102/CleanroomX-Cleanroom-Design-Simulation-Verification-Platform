from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .parameter_sweep import (
    ParameterSweepDependencyChangedError,
    ParameterSweepFormatError,
    load_parameter_sweep,
    parameter_sweep_markdown,
    run_parameter_sweep,
)
from .project import atomic_write_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-sweep",
        description=(
            "Run a deterministic Cartesian parameter sweep through the shared "
            "CleanroomX application analysis boundary."
        ),
    )
    parser.add_argument("study", help="Path to a cleanroomx.parameter-sweep JSON file")
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument("--output", help="Optional output file")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    study_path = Path(args.study)
    try:
        spec = load_parameter_sweep(study_path)
        result = run_parameter_sweep(spec, base_dir=study_path.resolve().parent)
        text = (
            json.dumps(
                result,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
            if args.format == "json"
            else parameter_sweep_markdown(result)
        )
        if args.output:
            atomic_write_text(args.output, text)
        else:
            print(text, end="")
    except Exception as exc:
        print(f"cleanroomx-sweep: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    return 0 if result["error_case_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
