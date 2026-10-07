from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence

from .cli_output import cli_error_boundary, dumps_strict_json
from .persistence import atomic_write_text
from .system_health import build_system_health_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-doctor",
        description=(
            "Check CleanroomX workstation/runtime readiness and emit "
            "machine-readable diagnostics."
        ),
    )
    parser.add_argument(
        "--require-bim",
        action="store_true",
        help="Treat missing or unloadable native IfcOpenShell support as a required failure",
    )
    parser.add_argument(
        "--deep",
        action="store_true",
        help="Execute the packaged demo active analysis through the real application runner",
    )
    parser.add_argument(
        "--format",
        choices=("json", "text"),
        default="json",
        help="Output format; JSON is the deterministic default for CI and support evidence",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the selected report format atomically to this path instead of stdout",
    )
    return parser


def _doctor_output_guard() -> None:
    """Publication hook retained for the shared atomic-output contract."""
    return None


def _render_text(report: dict) -> str:
    summary = report["summary"]
    lines = [
        (
            f"CleanroomX {report['application']['version']} system health: "
            f"{report['status']}"
        ),
        f"Required readiness: {'PASS' if report['required_ready'] else 'FAIL'}",
        (
            "Checks: "
            f"{summary['pass']} pass, {summary['warn']} warn, {summary['fail']} fail"
        ),
        "",
    ]
    for item in report["checks"]:
        requirement = "required" if item["required"] else "advisory"
        lines.append(
            f"[{item['status'].upper()}] {item['label']} ({requirement}) - {item['summary']}"
        )
    return "\n".join(lines).rstrip() + "\n"


@cli_error_boundary("cleanroomx-doctor")
def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_system_health_report(require_bim=args.require_bim, deep=args.deep)
    text = (
        _render_text(report)
        if args.format == "text"
        else dumps_strict_json(report, indent=2, sort_keys=True) + "\n"
    )
    if args.output is None:
        sys.stdout.write(text)
    else:
        atomic_write_text(
            args.output,
            text,
            before_replace=_doctor_output_guard,
        )
    return 0 if report["required_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
