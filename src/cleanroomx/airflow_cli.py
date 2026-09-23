from __future__ import annotations

import argparse
import json
from pathlib import Path

from .airflow_balance import analyze_air_balance
from .airflow_io import load_air_balance_project
from .airflow_report import markdown_air_balance_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-balance",
        description="CleanroomX room/facility airflow-balance analysis",
    )
    parser.add_argument("project", help="Path to airflow-balance project JSON")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", help="Optional output file")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = analyze_air_balance(load_air_balance_project(args.project))
    text = (
        json.dumps(result, indent=2)
        if args.format == "json"
        else markdown_air_balance_report(result)
    )

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)

    return 0 if result["all_requirements_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
