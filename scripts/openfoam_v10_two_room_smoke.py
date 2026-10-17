#!/usr/bin/env python3
"""Generate and execute the receipt-bound two-room Foundation v10 case."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from cleanroomx.cfd_two_room import (
    execute_two_room_case,
    export_two_room_case,
    verify_two_room_receipt,
)
from cleanroomx.cli_output import load_cli_input
from cleanroomx.strict_json import load_strict_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args(argv)
    if args.spec.is_symlink():
        raise ValueError("two-room spec must be a bounded, regular, non-symlink file")
    spec_path = args.spec.resolve(strict=True)
    if not spec_path.is_file() or spec_path.stat().st_size > 128 * 1024:
        raise ValueError("two-room spec must be a bounded, regular, non-symlink file")
    output = args.output_directory
    if output.exists() or output.is_symlink():
        raise ValueError("refusing to overwrite the two-room evidence directory")
    output.mkdir(parents=True, exist_ok=False)
    spec = load_cli_input(load_strict_json, spec_path)
    case = output / "case"
    export_two_room_case(spec, case)
    receipt_directory = output / "receipt"
    receipt = execute_two_room_case(
        case,
        receipt_directory,
        timeout_seconds=args.timeout_seconds,
    )
    verified_receipt = verify_two_room_receipt(receipt_directory / "two_room_run_receipt.json")
    if receipt.get("status") == "executed_requires_engineering_review":
        if verified_receipt.get("scientific_validation") != "BLOCKED":
            raise ValueError("two-room smoke receipt promoted scientific validation")
        screens = receipt.get("engineering_screens")
        if (
            not isinstance(screens, dict)
            or screens.get("flow_balance_status") != "MEASURED_DIAGNOSTIC_ONLY"
            or screens.get("flow_balance_acceptance_criterion") != "NOT_SET"
            or screens.get("solver_convergence_status") != "NOT_ASSESSED"
            or not isinstance(receipt.get("pressure_probe"), dict)
            or receipt.get("solver_flux", {}).get("status") != "MEASURED_DIAGNOSTIC_ONLY"
            or len(receipt.get("stages", [])) != 4
        ):
            raise ValueError("two-room smoke output is missing solver-backed pressure/flux evidence")
    print(json.dumps({"receipt": receipt, "receipt_integrity": verified_receipt}, indent=2, sort_keys=True, allow_nan=False))
    return 0 if receipt.get("status") == "executed_requires_engineering_review" else 2


if __name__ == "__main__":
    sys.exit(main())
