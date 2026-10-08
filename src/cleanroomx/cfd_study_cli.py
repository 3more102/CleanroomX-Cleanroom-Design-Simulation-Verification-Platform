"""CLI for evidence-gated cleanroom CFD post-processing."""
from __future__ import annotations

import argparse
import sys

from .cfd_study import analyze_cfd_study
from .cli_output import cli_error_boundary, dumps_strict_json, load_cli_input, publish_cli_output
from .strict_json import load_strict_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cleanroomx-cfd-study", description="Compare external CFD cleanroom ventilation runs")
    parser.add_argument("study", help="Strict JSON CFD study specification and optional solver field samples")
    parser.add_argument("--output", help="Optional destination (input file cannot be overwritten)")
    return parser


@cli_error_boundary("cleanroomx-cfd-study")
def main() -> int:
    args = build_parser().parse_args()
    report = analyze_cfd_study(load_cli_input(load_strict_json, args.study))
    text = dumps_strict_json(report)
    if args.output:
        if not publish_cli_output("cleanroomx-cfd-study", args.output, text, protected_inputs=(args.study,)):
            return 1
    else:
        print(text)
    return 0 if report["comparison_status"] == "comparable" else 3


if __name__ == "__main__":
    sys.exit(main())
