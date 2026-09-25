from __future__ import annotations

import json
from pathlib import Path
import tempfile
from time import perf_counter

from cleanroomx.project import (
    ProjectDocument,
    capture_project_file_revision,
    save_project_document,
    save_project_document_guarded,
    scan_project_revisions,
)


def _project(label: str, payload_bytes: int) -> ProjectDocument:
    return ProjectDocument(
        name=f"Benchmark {label}",
        description=label,
        metadata={"payload": "x" * payload_bytes},
    )


def _milliseconds(start: float, end: float) -> float:
    return round((end - start) * 1000.0, 3)


def main() -> int:
    sizes = (
        ("small", 10_000),
        ("medium", 250_000),
        ("large", 1_000_000),
        ("stress", 4_000_000),
    )
    with tempfile.TemporaryDirectory(prefix="cleanroomx-revision-bench-") as raw:
        root = Path(raw)
        for label, size in sizes:
            baseline_path = root / f"{label}-baseline.cleanroomx.json"
            guarded_path = root / f"{label}-guarded.cleanroomx.json"
            initial = _project(f"{label}-initial", size)
            updated = _project(f"{label}-updated", size)

            save_project_document(baseline_path, initial)
            start = perf_counter()
            save_project_document(baseline_path, updated)
            baseline_ms = _milliseconds(start, perf_counter())

            save_project_document(guarded_path, initial)
            expected = capture_project_file_revision(guarded_path)
            start = perf_counter()
            save_project_document_guarded(
                guarded_path,
                updated,
                expected_revision=expected,
            )
            guarded_ms = _milliseconds(start, perf_counter())
            scan = scan_project_revisions(guarded_path)

            record = {
                "case": label,
                "project_bytes": guarded_path.stat().st_size,
                "unguarded_atomic_save_ms": baseline_ms,
                "guarded_revision_save_ms": guarded_ms,
                "overhead_ratio": (
                    round(guarded_ms / baseline_ms, 3)
                    if baseline_ms > 0.0
                    else None
                ),
                "revision_count": len(scan.revisions),
                "revision_issues": len(scan.issues),
                "revision_bytes": (
                    scan.revisions[0].path.stat().st_size
                    if scan.revisions
                    else 0
                ),
            }
            print(json.dumps(record, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
