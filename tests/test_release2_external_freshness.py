from __future__ import annotations

from hashlib import sha256
import json
import os

from cleanroomx.application import AnalysisRun, analysis_run_is_current


def _canonical_sha256(payload: dict) -> str:
    return sha256(
        json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _run_for_file(payload: dict, filename: str, data: bytes) -> AnalysisRun:
    digest = sha256(data).hexdigest()
    provenance = {
        "schema": "cleanroomx.application-execution-provenance",
        "schema_version": 1,
        "analysis_kind": "consistency",
        "input_sha256": _canonical_sha256(payload),
        "external_dependency_count": 1,
        "external_dependencies_stable": True,
        "external_dependencies": [
            {
                "field": "verification_project",
                "declared_path": filename,
                "sha256_after": digest,
                "size_bytes_after": len(data),
                "stable_during_run": True,
            }
        ],
    }
    return AnalysisRun(
        kind="consistency",
        title="Consistency",
        status="PASS",
        result={},
        markdown="",
        diagnostics={"application_execution_provenance": provenance},
        plot=None,
        input_snapshot=payload,
    )


def test_file_backed_cached_run_becomes_stale_when_dependency_changes(tmp_path):
    payload = {"verification_project": "verification.json"}
    source = tmp_path / "verification.json"
    original = b'{"revision":1}'
    source.write_bytes(original)
    run = _run_for_file(payload, source.name, original)

    assert analysis_run_is_current(run, "consistency", payload, base_dir=tmp_path)

    source.write_bytes(b'{"revision":2}')
    assert not analysis_run_is_current(run, "consistency", payload, base_dir=tmp_path)


def test_file_backed_cached_run_becomes_unusable_when_dependency_disappears(tmp_path):
    payload = {"verification_project": "verification.json"}
    source = tmp_path / "verification.json"
    original = b'{"revision":1}'
    source.write_bytes(original)
    run = _run_for_file(payload, source.name, original)

    source.unlink()
    assert not analysis_run_is_current(run, "consistency", payload, base_dir=tmp_path)


def test_metadata_only_timestamp_change_keeps_content_revision_current(tmp_path):
    payload = {"verification_project": "verification.json"}
    source = tmp_path / "verification.json"
    original = b'{"revision":1}'
    source.write_bytes(original)
    run = _run_for_file(payload, source.name, original)

    before = source.stat()
    os.utime(
        source,
        ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000),
    )
    assert analysis_run_is_current(run, "consistency", payload, base_dir=tmp_path)


def test_inline_run_has_no_external_freshness_dependency(tmp_path):
    payload = {"value": 7}
    provenance = {
        "schema": "cleanroomx.application-execution-provenance",
        "schema_version": 1,
        "analysis_kind": "room_verification",
        "input_sha256": _canonical_sha256(payload),
        "external_dependency_count": 0,
        "external_dependencies_stable": True,
        "external_dependencies": [],
    }
    run = AnalysisRun(
        kind="room_verification",
        title="Room",
        status="PASS",
        result={},
        markdown="",
        diagnostics={"application_execution_provenance": provenance},
        plot=None,
        input_snapshot=payload,
    )
    assert analysis_run_is_current(
        run, "room_verification", payload, base_dir=tmp_path
    )
