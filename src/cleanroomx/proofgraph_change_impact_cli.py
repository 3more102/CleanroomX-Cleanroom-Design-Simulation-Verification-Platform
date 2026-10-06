from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .cli_output import (
    cli_error_boundary,
    dumps_strict_json,
    load_cli_input,
    publish_cli_output,
    resolve_cli_path,
)
from .proofgraph_change_impact import compare_proofgraphs
from .proofgraph_io import proofgraph_from_dict
from .strict_json import load_strict_json


_COMMAND = "cleanroomx-proofgraph-diff"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=_COMMAND,
        description=(
            "Compare two revisions of the same CleanroomX ProofGraph and report "
            "direct changes, downstream impact, and potentially stale candidate evidence."
        ),
    )
    parser.add_argument("baseline", help="baseline ProofGraph JSON file")
    parser.add_argument("candidate", help="candidate ProofGraph JSON file")
    parser.add_argument(
        "--output",
        help="write strict JSON output atomically instead of stdout",
    )
    parser.add_argument(
        "--require-identical",
        action="store_true",
        help="return exit code 2 when the graph revisions differ",
    )
    parser.add_argument(
        "--require-no-stale",
        action="store_true",
        help=(
            "return exit code 2 when unchanged candidate records are potentially "
            "stale because an upstream dependency changed"
        ),
    )
    return parser


def _load_graph(path: Path):
    document = load_strict_json(path)
    if not isinstance(document, dict):
        raise ValueError(f"ProofGraph file must contain one JSON object: {path}")
    return proofgraph_from_dict(document)


def _has_potentially_stale_records(report: dict) -> bool:
    stale = report["potentially_stale_candidate"]
    return any(bool(ids) for ids in stale.values())


@cli_error_boundary(_COMMAND)
def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    baseline_path = resolve_cli_path(args.baseline, label="baseline ProofGraph")
    candidate_path = resolve_cli_path(args.candidate, label="candidate ProofGraph")

    baseline = load_cli_input(_load_graph, baseline_path)
    candidate = load_cli_input(_load_graph, candidate_path)
    report = compare_proofgraphs(baseline, candidate)
    text = dumps_strict_json(report, indent=2, sort_keys=True) + "\n"

    if args.output:
        if not publish_cli_output(
            _COMMAND,
            args.output,
            text,
            protected_inputs=(baseline_path, candidate_path),
        ):
            return 1
    else:
        sys.stdout.write(text)

    if args.require_identical and report["changed"]:
        return 2
    if args.require_no_stale and _has_potentially_stale_records(report):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
