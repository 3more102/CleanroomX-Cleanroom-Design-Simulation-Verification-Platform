from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import tempfile
import time

from cleanroomx.project import (
    ProjectDocument,
    load_project_document_with_revision,
    save_project_document,
)


DEFAULT_CASES = (
    ("small", 16 * 1024, 3),
    ("medium", 1 * 1024 * 1024, 3),
    ("large", 8 * 1024 * 1024, 2),
    ("stress", 16 * 1024 * 1024, 1),
)


def _measure_case(root: Path, label: str, payload_bytes: int, repetitions: int) -> dict:
    project = ProjectDocument(
        name=f"Project I/O benchmark {label}",
        metadata={"benchmark_payload": "x" * payload_bytes},
    )
    path = root / f"{label}.cleanroomx.json"
    save_seconds: list[float] = []
    load_seconds: list[float] = []

    for _ in range(repetitions):
        started = time.perf_counter()
        save_project_document(path, project)
        save_seconds.append(time.perf_counter() - started)

        started = time.perf_counter()
        loaded, revision = load_project_document_with_revision(path)
        load_seconds.append(time.perf_counter() - started)

        assert len(loaded.metadata["benchmark_payload"]) == payload_bytes
        assert revision.exists
        assert revision.size == path.stat().st_size
        assert revision.sha256

    file_size = path.stat().st_size
    save_median = statistics.median(save_seconds)
    load_median = statistics.median(load_seconds)
    return {
        "case": label,
        "payload_bytes": payload_bytes,
        "file_bytes": file_size,
        "repetitions": repetitions,
        "save_median_seconds": save_median,
        "load_median_seconds": load_median,
        "save_mib_per_second": (file_size / (1024 * 1024)) / save_median,
        "load_mib_per_second": (file_size / (1024 * 1024)) / load_median,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark CleanroomX revision-stable durable project I/O."
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON output path in addition to stdout.",
    )
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="cleanroomx-project-io-benchmark-") as tmp:
        root = Path(tmp)
        cases = [
            _measure_case(root, label, payload_bytes, repetitions)
            for label, payload_bytes, repetitions in DEFAULT_CASES
        ]

    report = {
        "benchmark": "cleanroomx.project-io",
        "schema_version": 1,
        "cases": cases,
    }
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    print(encoded, end="")
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
