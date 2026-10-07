from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
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

# These are intentionally conservative CI regression ceilings. The validated
# 2026-10-05 Python 3.13 stress baseline was ~0.18 s export, ~0.10 s verify,
# ~0.18 s extract, and ~68 MiB peak traced Python memory. The ceilings below
# retain broad hosted-runner margin while still detecting catastrophic
# recomputation or memory-growth regressions.
STRESS_MAX_PHASE_SECONDS = 3.0
STRESS_MAX_PEAK_PYTHON_BYTES = 256 * 1024 * 1024


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


def _validate_extracted_dependency(
    label: str,
    extracted_root: Path,
    verify_report: dict,
    *,
    source_size: int,
) -> Path:
    """Verify the extracted dependency at its manifest-defined portable path."""
    dependencies = verify_report.get("dependencies")
    if verify_report.get("dependency_count") != 1 or not isinstance(dependencies, list):
        raise RuntimeError(
            f"{label} bundle verification expected exactly one dependency"
        )
    if len(dependencies) != 1 or not isinstance(dependencies[0], dict):
        raise RuntimeError(
            f"{label} bundle verification returned inconsistent dependency metadata"
        )

    record = dependencies[0]
    archive_path = record.get("path")
    expected_size = record.get("size_bytes")
    if not isinstance(archive_path, str) or not archive_path:
        raise RuntimeError(
            f"{label} bundle verification returned an invalid dependency path"
        )
    if (
        isinstance(expected_size, bool)
        or not isinstance(expected_size, int)
        or expected_size < 0
    ):
        raise RuntimeError(
            f"{label} bundle verification returned an invalid dependency size"
        )
    if expected_size != source_size:
        raise RuntimeError(
            f"{label} bundle dependency size changed across export/verification: "
            f"{expected_size} != {source_size}"
        )

    portable_path = PurePosixPath(archive_path)
    if portable_path.is_absolute() or ".." in portable_path.parts:
        raise RuntimeError(
            f"{label} bundle verification returned an unsafe dependency path"
        )
    extracted_dependency = extracted_root.joinpath(*portable_path.parts)
    if (
        not extracted_dependency.is_file()
        or extracted_dependency.stat().st_size != expected_size
    ):
        raise RuntimeError(
            f"{label} bundle extraction did not reproduce the verified dependency"
        )
    return extracted_dependency


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

            _validate_extracted_dependency(
                label,
                extracted,
                verify_report,
                source_size=dependency.stat().st_size,
            )
            if label == "stress":
                phase_times = {
                    "export": export_seconds,
                    "verify": verify_seconds,
                    "extract": extract_seconds,
                }
                for phase, seconds in phase_times.items():
                    if seconds > STRESS_MAX_PHASE_SECONDS:
                        raise RuntimeError(
                            f"stress bundle {phase} exceeded CI regression budget: "
                            f"{seconds:.6f}s > {STRESS_MAX_PHASE_SECONDS:.6f}s"
                        )
                if peak > STRESS_MAX_PEAK_PYTHON_BYTES:
                    raise RuntimeError(
                        "stress bundle exceeded CI traced-memory regression budget: "
                        f"{peak} > {STRESS_MAX_PEAK_PYTHON_BYTES} bytes"
                    )

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
