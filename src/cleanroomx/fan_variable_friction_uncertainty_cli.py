from __future__ import annotations

import argparse
import sys

from .strict_json import StrictJSONError
from .cli_output import cli_error_boundary, dumps_strict_json, load_cli_input, publish_cli_output
from .fan_variable_friction_uncertainty import (
    analyze_fan_variable_friction_loop_uncertainty,
)
from .fan_variable_friction_uncertainty_io import (
    load_fan_variable_friction_loop_uncertainty,
)
from .fan_variable_friction_uncertainty_report import (
    markdown_fan_variable_friction_loop_uncertainty_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-fan-loop-friction-uncertainty",
        description=(
            "Deterministic bounded uncertainty over fixed pressure and "
            "automatic-friction loop-edge local-loss coefficients"
        ),
    )
    parser.add_argument(
        "study",
        help="Path to fan/variable-friction uncertainty study JSON",
    )
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
    )
    parser.add_argument("--output", help="Optional output file")
    return parser


@cli_error_boundary("cleanroomx-fan-loop-friction-uncertainty")
def main() -> int:
    args = build_parser().parse_args()
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_cli_input(load_fan_variable_friction_loop_uncertainty, args.study)
    )
    try:
        text = (
            dumps_strict_json(result)
            if args.format == "json"
            else markdown_fan_variable_friction_loop_uncertainty_report(result)
        )
    except StrictJSONError as exc:
        print(
            f"cleanroomx-fan-loop-friction-uncertainty: error: analysis result is not strict JSON: {exc}",
            file=sys.stderr,
        )
        return 1
    if args.output:
        if not publish_cli_output(
            "cleanroomx-fan-loop-friction-uncertainty",
            args.output,
            text,
            protected_inputs=(args.study,),
        ):
            return 1
    else:
        print(text)
    return 0 if result["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
