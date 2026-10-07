from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence

from .cli_output import cli_error_boundary, dumps_strict_json
from .persistence import atomic_write_text
from .strict_json import load_strict_json
from .system_health import build_system_health_report, compare_system_health_reports


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
        "--require-desktop",
        action="store_true",
        help="Require a hidden Tk desktop root to initialize, settle idle work, and close cleanly",
    )
    parser.add_argument(
        "--deep",
        action="store_true",
        help="Execute the packaged demo active analysis through the real application runner",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        help="Compare the current health report with a prior cleanroomx-doctor JSON report",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Return exit code 3 when baseline comparison detects health regression",
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
    comparison = report.get("comparison")
    if comparison:
        comparison_summary = comparison["summary"]
        lines.extend(
            [
                f"Baseline drift: {comparison['state'].upper()}",
                (
                    "Drift changes: "
                    f"{comparison_summary['regression_count']} regression(s), "
                    f"{comparison_summary['improvement_count']} improvement(s), "
                    f"{comparison_summary['added_check_count']} added check(s), "
                    f"{comparison_summary['removed_check_count']} removed check(s)"
                ),
                "",
            ]
        )
    for item in report["checks"]:
        requirement = "required" if item["required"] else "advisory"
        lines.append(
            f"[{item['status'].upper()}] {item['label']} ({requirement}) - {item['summary']}"
        )
        remediation = item.get("remediation")
        if remediation and item.get("status") != "pass":
            lines.append(f"  Action: {remediation}")
    return "\n".join(lines).rstrip() + "\n"


@cli_error_boundary("cleanroomx-doctor")
def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.fail_on_regression and args.baseline is None:
        raise ValueError("--fail-on-regression requires --baseline")
    if args.output is not None and args.baseline is not None:
        output_path = args.output.expanduser().resolve(strict=False)
        baseline_path = args.baseline.expanduser().resolve(strict=False)
        if output_path == baseline_path:
            raise ValueError("--output must not overwrite the health baseline")

    report = build_system_health_report(
        require_bim=args.require_bim,
        require_desktop=args.require_desktop,
        deep=args.deep,
    )
    comparison = None
    if args.baseline is not None:
        baseline = load_strict_json(args.baseline, max_bytes=2 * 1024 * 1024)
        comparison = compare_system_health_reports(baseline, report)
        report = {**report, "comparison": comparison}

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
    if not report["required_ready"]:
        return 2
    if args.fail_on_regression and comparison is not None and comparison["regressed"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
