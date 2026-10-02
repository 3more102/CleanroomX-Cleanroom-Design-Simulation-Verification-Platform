from __future__ import annotations

import argparse
import sys

from .strict_json import StrictJSONError
from .cli_output import dumps_strict_json, publish_cli_output
from .fan_variable_friction_loop import solve_fan_variable_friction_loop
from .fan_variable_friction_loop_io import (
    load_fan_variable_friction_loop_study,
)
from .fan_variable_friction_loop_report import (
    markdown_fan_variable_friction_loop_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-fan-loop-friction",
        description=(
            "Bounded fan operating-point solver with variable Darcy-friction "
            "loop-network re-solving"
        ),
    )
    parser.add_argument(
        "study", help="Path to fan/variable-friction loop study JSON"
    )
    parser.add_argument(
        "--format", choices=("json", "markdown"), default="markdown"
    )
    parser.add_argument("--output", help="Optional output file")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = solve_fan_variable_friction_loop(
        load_fan_variable_friction_loop_study(args.study)
    )
    try:
        text = (
            dumps_strict_json(result)
            if args.format == "json"
            else markdown_fan_variable_friction_loop_report(result)
        )
    except StrictJSONError as exc:
        print(
            f"cleanroomx-fan-loop-friction: error: analysis result is not strict JSON: {exc}",
            file=sys.stderr,
        )
        return 1
    if args.output:
        if not publish_cli_output(
            "cleanroomx-fan-loop-friction",
            args.output,
            text,
            protected_inputs=(args.study,),
        ):
            return 1
    else:
        print(text)
    return 0 if result["status"] == "solved" else 2


if __name__ == "__main__":
    raise SystemExit(main())
