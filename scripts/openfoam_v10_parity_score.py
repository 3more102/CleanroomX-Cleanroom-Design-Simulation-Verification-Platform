#!/usr/bin/env python3
"""Validate and score the published OpenFOAM Foundation v10 capability matrix."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = ROOT / "docs" / "openfoam_foundation_v10_capabilities.csv"
DEFAULT_INVENTORY = ROOT / "docs" / "openfoam_foundation_v10_source_inventory.csv"
TRACKS = ("native_status", "integration_status", "cleanroom_status")
STATES = {"complete", "partial", "blocked", "unsupported", "na"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise ValueError(f"{path}: missing CSV header")
        return list(reader)


def validate(rows: list[dict[str, str]], inventory: list[dict[str, str]]) -> None:
    required = {
        "id",
        "category",
        "capability",
        "upstream_reference",
        *TRACKS,
        "implementation_path",
        "test_evidence",
        "remaining_gap",
    }
    if not rows:
        raise ValueError("capability matrix is empty")
    missing = required - set(rows[0])
    if missing:
        raise ValueError(f"matrix missing columns: {', '.join(sorted(missing))}")
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("matrix contains duplicate capability IDs")
    for row in rows:
        if any(not row.get(column, "").strip() for column in required):
            raise ValueError(f"{row.get('id', '<no id>')}: required field is blank")
        if not row["upstream_reference"].startswith("https://"):
            raise ValueError(f"{row['id']}: upstream reference must be an HTTPS URL")
        for track in TRACKS:
            if row[track] not in STATES:
                raise ValueError(f"{row['id']}: invalid {track}={row[track]!r}")
            if row[track] == "complete":
                evidence = row["test_evidence"].casefold()
                if row["implementation_path"].strip().casefold() in {"none", "n/a"}:
                    raise ValueError(f"{row['id']}: complete {track} requires an implementation path")
                if row["remaining_gap"].strip().casefold() not in {"none", "none identified"}:
                    raise ValueError(f"{row['id']}: complete {track} requires remaining_gap to be 'none'")
                if not evidence.startswith("pass:"):
                    raise ValueError(f"{row['id']}: complete {track} requires test_evidence beginning PASS:")
                if track == "integration_status" and not (
                    "openfoam foundation v10" in evidence and "non-synthetic" in evidence
                ):
                    raise ValueError(
                        f"{row['id']}: complete integration requires non-synthetic Foundation v10 evidence"
                    )
                if track == "cleanroom_status" and not (
                    "measured" in evidence and "uncertainty" in evidence
                ):
                    raise ValueError(
                        f"{row['id']}: complete cleanroom status requires measured evidence and uncertainty"
                    )
        if any(marker in row["test_evidence"].casefold() for marker in ("synthetic-only", "synthetic fixture")) and "complete" in (
            row["native_status"], row["integration_status"], row["cleanroom_status"]
        ):
            raise ValueError(f"{row['id']}: synthetic-only evidence cannot support complete status")

    inventory_required = {"release", "source_commit", "inventory_type", "upstream_path", "upstream_reference"}
    if not inventory or not inventory_required <= set(inventory[0]):
        raise ValueError("pinned source inventory is missing required columns or rows")
    for entry in inventory:
        if not entry["upstream_reference"].startswith("https://"):
            raise ValueError(f"source inventory reference is not HTTPS: {entry['upstream_path']}")
    commits = {entry["source_commit"] for entry in inventory}
    if len(commits) != 1 or not re.fullmatch(r"[0-9a-f]{40}", next(iter(commits), "")):
        raise ValueError("source inventory must use one pinned 40-character commit SHA")
    commit = next(iter(commits))
    for entry in inventory:
        if entry["release"] != "OpenFOAM Foundation v10" or f"/blob/{commit}/" not in entry["upstream_reference"]:
            raise ValueError(f"source inventory is not pinned to its stated release and commit: {entry['upstream_path']}")


def score(rows: list[dict[str, str]]) -> dict[str, Any]:
    result: dict[str, Any] = {"rows": len(rows), "tracks": {}}
    for track in TRACKS:
        eligible = [row for row in rows if row[track] != "na"]
        categories: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in eligible:
            categories[row["category"]].append(row)
        result["tracks"][track] = {
            "complete": sum(row[track] == "complete" for row in eligible),
            "denominator": len(eligible),
            "score": sum(row[track] == "complete" for row in eligible) / len(eligible) if eligible else 0.0,
            "states": dict(sorted(Counter(row[track] for row in eligible).items())),
            "categories": {
                name: {
                    "complete": sum(row[track] == "complete" for row in values),
                    "denominator": len(values),
                    "score": sum(row[track] == "complete" for row in values) / len(values),
                    "states": dict(sorted(Counter(row[track] for row in values).items())),
                }
                for name, values in sorted(categories.items())
            },
        }
    return result


def markdown(report: dict[str, Any]) -> str:
    labels = {
        "native_status": "Native solver capability parity",
        "integration_status": "End-to-end OpenFOAM integration coverage",
        "cleanroom_status": "Validated cleanroom engineering workflows",
    }
    lines = [f"Matrix rows: {report['rows']}", "", "| Track | Complete | Denominator | Score |", "|---|---:|---:|---:|"]
    for track in TRACKS:
        entry = report["tracks"][track]
        lines.append(f"| {labels[track]} | {entry['complete']} | {entry['denominator']} | {entry['score']:.2%} |")
    for track in TRACKS:
        lines.extend(["", f"### {labels[track]} by category", "", "| Category | Complete | Denominator | Score |", "|---|---:|---:|---:|"])
        for category, entry in report["tracks"][track]["categories"].items():
            lines.append(f"| {category} | {entry['complete']} | {entry['denominator']} | {entry['score']:.2%} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args(argv)
    try:
        rows = read_csv(args.matrix)
        inventory = read_csv(args.inventory)
        validate(rows, inventory)
        report = score(rows)
    except (OSError, ValueError, csv.Error) as error:
        print(f"matrix error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True) if args.format == "json" else markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
