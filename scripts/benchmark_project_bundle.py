from __future__ import annotations

import json
from pathlib import Path
import tempfile
import time
import tracemalloc

from cleanroomx.project import AnalysisDocument, ProjectDocument
from cleanroomx.project_bundle import (
    export_project_bundle,
    extract_project_bundle,
    inspect_project_bundle,
)


CASES = (
    ("small", 64 * 1024),
    ("medium", 1024 * 1024),
    ("large", 8 * 1024 * 1024),
    ("stress", 32 * 1024 * 1024),
)


def _write_json_payload(path: Path, target_bytes: int) -> None:
    prefix = b'{"padding":"'
    suffix = b'"}\n'
    payload_bytes = max(0, target_bytes - len(prefix) - len(suffix))
    chunk = b"x" * min(1024 * 1024, max(1, payload_bytes))
    with path.open("wb") as handle:
        handle.write(prefix)
        remaining = payload_bytes
        while remaining:
            piece = chunk[: min(len(chunk), remaining)]
            handle.write(piece)
            remaining -= len(piece)
        handle.write(suffix)


def _project(dependency_name: str) -> ProjectDocument:
    return ProjectDocument(
        name="Portable bundle benchmark",
        analyses=[
            AnalysisDocument(
                id="consistency-benchmark",
                name="Bundle benchmark",
                kind="consistency",
                input={
                    "verification_project": dependency_name,
                    "hvac_project": dependency_name,
                },
            )
        ],
        active_analysis_id="consistency-benchmark",
    )


def main() -> int:
    results = []
    with tempfile.TemporaryDirectory(prefix="cleanroomx-bundle-benchmark-") as raw:
        root = Path(raw)
        for label, target_size in CASES:
            case = root / label
            case.mkdir()
            dependency = case / "engineering-input.json"
            _write_json_payload(dependency, target_size)
            bundle = case / "project.cleanroomx.zip"
            extracted = case / "extracted"

            tracemalloc.start()
            start = time.perf_counter()
            export_report = export_project_bundle(
                bundle,
                _project(dependency.name),
                source_base=case,
            )
            export_seconds = time.perf_counter() - start

            start = time.perf_counter()
            verify_report = inspect_project_bundle(bundle)
            verify_seconds = time.perf_counter() - start

            start = time.perf_counter()
            extract_project_bundle(bundle, extracted)
            extract_seconds = time.perf_counter() - start
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            results.append(
                {
                    "case": label,
                    "dependency_bytes": dependency.stat().st_size,
                    "bundle_bytes": export_report["bundle_size_bytes"],
                    "export_seconds": round(export_seconds, 6),
                    "verify_seconds": round(verify_seconds, 6),
                    "extract_seconds": round(extract_seconds, 6),
                    "peak_python_bytes": peak,
                    "verified_dependency_count": verify_report["dependency_count"],
                }
            )

    print(json.dumps({"project_bundle_benchmark": results}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
