from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from cleanroomx.application import run_analysis
from cleanroomx.project import (
    AnalysisDocument,
    PROJECT_SCHEMA_VERSION,
    ProjectDocument,
    load_project_document,
    save_project_document,
)
from cleanroomx.run_history import (
    RUN_HISTORY_METADATA_KEY,
    RunHistoryIntegrityError,
    append_run_history_record,
    run_history_records,
    validate_run_history,
)


ROOT = Path(__file__).resolve().parents[1]


def _room_payload() -> dict:
    return json.loads(
        (ROOT / "examples" / "basic_room.json").read_text(encoding="utf-8")
    )


def test_run_history_preserves_exact_input_and_execution_evidence():
    payload = _room_payload()
    run = run_analysis("room_verification", payload)
    metadata: dict = {}

    record = append_run_history_record(
        metadata,
        analysis_id="room-1",
        analysis_name="Room verification",
        analysis_kind="room_verification",
        input_payload=payload,
        run=run,
        completed_at_utc="2026-09-25T11:00:00Z",
    )

    payload["name"] = "mutated after append"
    records = run_history_records(metadata)
    assert records == [record]
    assert records[0]["input_snapshot"]["name"] != payload["name"]
    provenance = records[0]["execution_provenance"]
    assert records[0]["input_sha256"] == provenance["input_sha256"]
    assert records[0]["analysis_kind"] == provenance["analysis_kind"]
    assert validate_run_history(metadata)["head_record_sha256"] == record["record_sha256"]


def test_run_history_detects_record_tampering():
    payload = _room_payload()
    run = run_analysis("room_verification", payload)
    metadata: dict = {}
    append_run_history_record(
        metadata,
        analysis_id="room-1",
        analysis_name="Room verification",
        analysis_kind="room_verification",
        input_payload=payload,
        run=run,
        completed_at_utc="2026-09-25T11:00:00Z",
    )

    metadata[RUN_HISTORY_METADATA_KEY]["records"][0]["status"] = "tampered"

    with pytest.raises(RunHistoryIntegrityError, match="integrity digest"):
        validate_run_history(metadata)


def test_run_history_pruning_preserves_anchor_and_contiguous_chain():
    payload = _room_payload()
    run = run_analysis("room_verification", payload)
    metadata: dict = {}

    append_run_history_record(
        metadata,
        analysis_id="room-1",
        analysis_name="Room verification",
        analysis_kind="room_verification",
        input_payload=payload,
        run=run,
        completed_at_utc="2026-09-25T11:00:01Z",
        limit=3,
    )
    second = append_run_history_record(
        metadata,
        analysis_id="room-1",
        analysis_name="Room verification",
        analysis_kind="room_verification",
        input_payload=payload,
        run=run,
        completed_at_utc="2026-09-25T11:00:02Z",
        limit=3,
    )
    for index in (3, 4, 5):
        append_run_history_record(
            metadata,
            analysis_id="room-1",
            analysis_name="Room verification",
            analysis_kind="room_verification",
            input_payload=payload,
            run=run,
            completed_at_utc=f"2026-09-25T11:00:0{index}Z",
            limit=3,
        )

    history = metadata[RUN_HISTORY_METADATA_KEY]
    assert history["anchor_record_sha256"] == second["record_sha256"]
    assert [record["sequence"] for record in history["records"]] == [3, 4, 5]
    assert (
        history["records"][0]["previous_record_sha256"]
        == history["anchor_record_sha256"]
    )
    summary = validate_run_history(metadata)
    assert summary["record_count"] == 3
    assert summary["first_sequence"] == 3
    assert summary["last_sequence"] == 5


def test_append_refuses_corrupt_existing_history_without_overwriting_it():
    payload = _room_payload()
    run = run_analysis("room_verification", payload)
    metadata: dict = {}
    append_run_history_record(
        metadata,
        analysis_id="room-1",
        analysis_name="Room verification",
        analysis_kind="room_verification",
        input_payload=payload,
        run=run,
        completed_at_utc="2026-09-25T11:00:00Z",
    )
    metadata[RUN_HISTORY_METADATA_KEY]["records"][0]["status"] = "corrupt"
    corrupt_snapshot = copy.deepcopy(metadata)

    with pytest.raises(RunHistoryIntegrityError):
        append_run_history_record(
            metadata,
            analysis_id="room-1",
            analysis_name="Room verification",
            analysis_kind="room_verification",
            input_payload=payload,
            run=run,
            completed_at_utc="2026-09-25T11:01:00Z",
        )

    assert metadata == corrupt_snapshot


def test_append_rejects_run_that_does_not_match_input_snapshot():
    payload = _room_payload()
    run = run_analysis("room_verification", payload)
    changed = copy.deepcopy(payload)
    changed["name"] = "Different input"

    with pytest.raises(RunHistoryIntegrityError, match="input digest"):
        append_run_history_record(
            {},
            analysis_id="room-1",
            analysis_name="Room verification",
            analysis_kind="room_verification",
            input_payload=changed,
            run=run,
        )


def test_run_history_round_trips_in_project_metadata_without_schema_change(tmp_path):
    payload = _room_payload()
    run = run_analysis("room_verification", payload)
    project = ProjectDocument(
        name="Audited project",
        analyses=[
            AnalysisDocument(
                id="room-1",
                name="Room verification",
                kind="room_verification",
                input=payload,
            )
        ],
        active_analysis_id="room-1",
    )
    append_run_history_record(
        project.metadata,
        analysis_id="room-1",
        analysis_name="Room verification",
        analysis_kind="room_verification",
        input_payload=payload,
        run=run,
        completed_at_utc="2026-09-25T11:00:00Z",
    )

    path = save_project_document(tmp_path / "audited.cleanroomx.json", project)
    loaded = load_project_document(path)
    raw = json.loads(path.read_text(encoding="utf-8"))

    assert raw["schema_version"] == PROJECT_SCHEMA_VERSION == 1
    assert loaded.metadata == project.metadata
    assert validate_run_history(loaded.metadata)["record_count"] == 1


def test_file_backed_run_history_preserves_dependency_revision_evidence(tmp_path):
    for name in ("facility_project.json", "consistency_hvac_demo.json"):
        (tmp_path / name).write_bytes((ROOT / "examples" / name).read_bytes())
    payload = {
        "verification_project": "facility_project.json",
        "hvac_project": "consistency_hvac_demo.json",
        "room_airflow_abs_tolerance_m3_h": 0.0,
        "require_same_room_set": True,
    }
    run = run_analysis("consistency", payload, base_dir=tmp_path)
    metadata: dict = {}

    append_run_history_record(
        metadata,
        analysis_id="consistency-1",
        analysis_name="Cross-module consistency",
        analysis_kind="consistency",
        input_payload=payload,
        run=run,
        completed_at_utc="2026-09-25T11:00:00Z",
    )

    record = run_history_records(metadata)[0]
    provenance = record["execution_provenance"]
    assert provenance["external_dependency_count"] == 2
    assert provenance["external_dependencies_stable"] is True
    assert [item["field"] for item in provenance["external_dependencies"]] == [
        "verification_project",
        "hvac_project",
    ]
    for dependency in provenance["external_dependencies"]:
        assert dependency["sha256_before"] == dependency["sha256_after"]
        assert dependency["size_bytes_before"] == dependency["size_bytes_after"]
        assert dependency["mtime_ns_before"] == dependency["mtime_ns_after"]
