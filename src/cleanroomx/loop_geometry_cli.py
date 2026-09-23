from __future__ import annotations

import argparse
import json
from pathlib import Path

from .loop_geometry import analyze_reference_geometry_loop
from .loop_geometry_io import load_reference_geometry_loop
from .loop_geometry_report import markdown_reference_geometry_loop_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-loop-geometry",
        description="Derive fixed loop resistances from reference duct geometry and solve the mesh",
    )
    parser.add_argument("network", help="Path to reference-geometry loop JSON")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", help="Optional output file")
    parser.add_argument(
        "--mass-balance-tolerance-m3-h",
        type=float,
        default=1e-6,
        help="Absolute node continuity tolerance in m3/h",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=100,
        help="Maximum damped-Newton iterations",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = analyze_reference_geometry_loop(
        load_reference_geometry_loop(args.network),
        mass_balance_tolerance_m3_h=args.mass_balance_tolerance_m3_h,
        max_iterations=args.max_iterations,
    )
    text = (
        json.dumps(result, indent=2)
        if args.format == "json"
        else markdown_reference_geometry_loop_report(result)
    )
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
