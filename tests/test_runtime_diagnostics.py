import json
from types import SimpleNamespace

import pytest

from cleanroomx.runtime_diagnostics import (
    DIAGNOSTIC_BUNDLE_SCHEMA,
    DIAGNOSTIC_BUNDLE_SCHEMA_VERSION,
    RuntimeEventJournal,
    build_diagnostic_bundle,
    sanitized_run_summary,
)


def _clock():
    values = iter(
        [
            "2026-09-25T10:00:00.000Z",
            "2026-09-25T10:00:01.000Z",
            "2026-09-25T10:00:02.000Z",
            "2026-09-25T10:00:03.000Z",
        ]
    )
    return lambda: next(values)


def test_runtime_event_journal_is_bounded_ordered_and_instance_owned():
    journal = RuntimeEventJournal(capacity=2, clock=_clock())

    journal.record("one", operation=1)
    journal.record("two", level="warning", operation=2)
    journal.record("three", operation=3)

    events = journal.snapshot()
    assert [item["sequence"] for item in events] == [2, 3]
    assert [item["event"] for item in events] == ["two", "three"]
    assert events[0]["timestamp_utc"] == "2026-09-25T10:00:01.000Z"
    assert events[0]["context"] == {"operation": 2}


def test_runtime_event_journal_rejects_invalid_contracts():
    with pytest.raises(ValueError, match="positive integer"):
        RuntimeEventJournal(capacity=0)
    journal = RuntimeEventJournal(clock=lambda: "2026-09-25T10:00:00.000Z")
    with pytest.raises(ValueError, match="unsupported diagnostic level"):
        journal.record("event", level="fatal")
    with pytest.raises(ValueError, match="non-empty"):
        journal.record("   ")


def test_runtime_event_context_is_strict_json_safe_and_does_not_use_object_repr(tmp_path):
    class UnsafeRepr:
        def __repr__(self):
            raise AssertionError("arbitrary repr must not be called")

    journal = RuntimeEventJournal(clock=lambda: "2026-09-25T10:00:00.000Z")
    journal.record(
        "context",
        nan=float("nan"),
        inf=float("inf"),
        path=tmp_path / "private" / "project.cleanroomx.json",
        opaque=UnsafeRepr(),
    )

    event = journal.snapshot()[0]
    assert event["context"]["nan"] == {"non_finite_float": "nan"}
    assert event["context"]["inf"] == {"non_finite_float": "inf"}
    assert event["context"]["path"] == {
        "path_name": "project.cleanroomx.json",
        "path_is_absolute": True,
    }
    assert event["context"]["opaque"] == {"unsupported_type": "UnsafeRepr"}
    json.dumps(event, allow_nan=False)


def test_sanitized_run_summary_retains_hash_evidence_but_not_full_paths_or_results():
    run = SimpleNamespace(
        kind="consistency",
        title="Cross-module consistency",
        status="pass",
        result={"secret_engineering_result": 123},
        diagnostics={
            "application_execution_provenance": {
                "schema": "cleanroomx.application-execution-provenance",
                "schema_version": 1,
                "cleanroomx_version": "0.100.0",
                "analysis_kind": "consistency",
                "input_canonicalization": "strict-json",
                "input_sha256": "a" * 64,
                "external_dependency_count": 1,
                "external_dependencies_stable": True,
                "external_dependencies": [
                    {
                        "field": "hvac_project",
                        "declared_path": "/private/customer/project/hvac.json",
                        "sha256_before": "b" * 64,
                        "sha256_after": "b" * 64,
                        "size_bytes_before": 10,
                        "size_bytes_after": 10,
                        "stable_during_run": True,
                    }
                ],
            }
        },
    )

    summary = sanitized_run_summary(run)

    assert "result" not in summary
    dependency = summary["execution_provenance"]["external_dependencies"][0]
    assert dependency["path_name"] == "hvac.json"
    assert dependency["path_was_absolute"] is True
    assert "/private/customer/project" not in json.dumps(summary)
    assert summary["execution_provenance"]["input_sha256"] == "a" * 64


def test_build_diagnostic_bundle_is_strict_json_and_schema_versioned():
    journal = RuntimeEventJournal(clock=lambda: "2026-09-25T10:00:00.000Z")
    journal.record("application.started", autosave_enabled=True)

    bundle = build_diagnostic_bundle(
        journal,
        project={
            "name": "Demo",
            "project_file_name": "demo.cleanroomx.json",
            "analysis_count": 1,
            "analyses": [{"id": "a", "name": "Room", "kind": "room_verification"}],
        },
        runtime_state={"running": False, "dirty": True},
        generated_at_utc="2026-09-25T10:01:00.000Z",
    )

    assert bundle["schema"] == DIAGNOSTIC_BUNDLE_SCHEMA
    assert bundle["schema_version"] == DIAGNOSTIC_BUNDLE_SCHEMA_VERSION
    assert bundle["generated_at_utc"] == "2026-09-25T10:01:00.000Z"
    assert bundle["events"][0]["event"] == "application.started"
    assert bundle["environment"]["cleanroomx_version"] == "0.100.0"
    encoded = json.dumps(bundle, allow_nan=False, sort_keys=True)
    assert json.loads(encoded) == bundle
