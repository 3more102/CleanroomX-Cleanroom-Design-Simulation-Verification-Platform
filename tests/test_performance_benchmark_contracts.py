from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_project_bundle.py"
_SPEC = importlib.util.spec_from_file_location("cleanroomx_benchmark_project_bundle", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
benchmark = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(benchmark)


def test_extracted_dependency_validation_uses_manifest_portable_path(tmp_path):
    extracted = tmp_path / "extracted"
    payload = extracted / "dependencies" / "0001-engineering-input.json"
    payload.parent.mkdir(parents=True)
    payload.write_bytes(b"verified-payload")
    report = {
        "dependency_count": 1,
        "dependencies": [
            {
                "path": "dependencies/0001-engineering-input.json",
                "size_bytes": payload.stat().st_size,
            }
        ],
    }

    resolved = benchmark._validate_extracted_dependency(
        "small", extracted, report, source_size=payload.stat().st_size
    )

    assert resolved == payload


def test_extracted_dependency_validation_rejects_source_size_drift(tmp_path):
    extracted = tmp_path / "extracted"
    payload = extracted / "dependencies" / "0001-engineering-input.json"
    payload.parent.mkdir(parents=True)
    payload.write_bytes(b"verified-payload")
    report = {
        "dependency_count": 1,
        "dependencies": [
            {
                "path": "dependencies/0001-engineering-input.json",
                "size_bytes": payload.stat().st_size,
            }
        ],
    }

    with pytest.raises(RuntimeError, match="size changed"):
        benchmark._validate_extracted_dependency(
            "stress",
            extracted,
            report,
            source_size=payload.stat().st_size + 1,
        )
