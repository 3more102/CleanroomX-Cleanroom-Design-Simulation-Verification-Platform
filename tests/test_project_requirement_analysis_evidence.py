from __future__ import annotations

from hashlib import sha256
import json

import pytest

from cleanroomx import __version__
from cleanroomx.application import AnalysisRun
from cleanroomx.project_requirement_analysis_evidence import (
    AnalysisRequirementEvidenceError,
    AnalysisRequirementEvidenceMapping,
    bind_analysis_run_requirement_evidence,
    verify_project_requirements_from_analysis_run,
)
from cleanroomx.project_requirements import (
    PROJECT_REQUIREMENTS_SCHEMA,
    PROJECT_REQUIREMENTS_SCHEMA_VERSION,
    project_requirements_from_dict,
)
from cleanroomx.proofgraph import (
    proofgraphs_from_project_requirements_analysis_run,
)


SOURCE_PROJECT_REVISION = "a" * 64
CURRENT_PROJECT_REVISION = "a" * 64
CHANGED_PROJECT_REVISION = "b" * 64


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


def _run_bundle(
    result: dict,
    *,
    external_dependencies_stable: bool = True,
) -> dict:
    payload = {"room": "ROOM-A"}
    provenance = {
        "schema": "cleanroomx.application-execution-provenance",
        "schema_version": 1,
        "analysis_kind": "room_verification",
        "cleanroomx_version": __version__,
        "input_canonicalization": "json-sort-keys-compact-utf8-v1",
        "input_sha256": _canonical_sha256(payload),
        "external_dependency_count": 0,
        "external_dependencies_stable": external_dependencies_stable,
        "external_dependencies": [],
    }
    return AnalysisRun(
        kind="room_verification",
        title="Room verification",
        status="PASS",
        result=result,
        markdown="# Result\n",
        diagnostics={"application_execution_provenance": provenance},
        plot=None,
        input_snapshot=payload,
    ).to_dict()


def _requirements():
    return project_requirements_from_dict(
        {
            "schema": PROJECT_REQUIREMENTS_SCHEMA,
            "schema_version": PROJECT_REQUIREMENTS_SCHEMA_VERSION,
            "sets": [
                {
                    "id": "urs-main",
                    "title": "Approved URS",
                    "description": "Project criteria.",
                    "source": "URS.pdf",
                    "source_revision": "Rev C",
                    "requirements": [
                        {
                            "id": "REQ-ACH",
                            "title": "Room ACH",
                            "description": "Room air change criterion.",
                            "discipline": "HVAC",
                            "category": "air_change_rate",
                            "source": "Project URS",
                            "source_revision": "Rev C",
                            "reference": "7.2",
                            "unit": "1/h",
                            "target": None,
                            "minimum": 20.0,
                            "maximum": None,
                            "tolerance": 0.0,
                            "applicability": "applicable",
                            "scope": ["ROOM-A"],
                            "verification_method": "calculation",
                            "required_evidence": ["calculation"],
                            "status": "approved",
                            "assumptions": [],
                            "notes": None,
                        }
                    ],
                }
            ],
        }
    )


def _mapping(
    *,
    mapping_id: str = "E-REQ-ACH",
    result_path=("rooms", 0, "ach"),
) -> AnalysisRequirementEvidenceMapping:
    return AnalysisRequirementEvidenceMapping(
        id=mapping_id,
        requirement_id="REQ-ACH",
        subject_ref="ROOM-A",
        property_name="air_change_rate",
        result_path=result_path,
        unit="1/h",
        evidence_kinds=("calculation",),
    )


def test_analysis_run_binding_derives_current_evidence_and_exact_locator() -> None:
    bundle = _run_bundle(
        {"rooms": [{"name": "ROOM-A", "ach": 20.0}]}
    )

    bindings = bind_analysis_run_requirement_evidence(
        bundle,
        [_mapping()],
        source_project_revision=SOURCE_PROJECT_REVISION,
        current_project_revision=CURRENT_PROJECT_REVISION,
    )

    assert len(bindings) == 1
    evidence = bindings[0]
    assert evidence.id == "E-REQ-ACH"
    assert evidence.value == 20.0
    assert evidence.freshness == "current"
    assert evidence.project_revision == SOURCE_PROJECT_REVISION
    assert evidence.evidence_locator == "/result/rooms/0/ach"
    assert evidence.calculation_source == (
        "room_verification:/result/rooms/0/ach"
    )
    assert evidence.source_revision == bundle["integrity"]["sha256"]


def test_analysis_run_binding_marks_changed_project_revision_stale() -> None:
    bundle = _run_bundle({"rooms": [{"ach": 20.0}]})

    result = verify_project_requirements_from_analysis_run(
        _requirements(),
        bundle,
        [_mapping()],
        source_project_revision=SOURCE_PROJECT_REVISION,
        current_project_revision=CHANGED_PROJECT_REVISION,
    )

    assert result["verified"] is False
    assert result["findings"][0]["state"] == "stale"
    assert result["findings"][0]["status"] == "not_checked"


def test_analysis_run_binding_requires_current_revision_to_assert_freshness() -> None:
    bundle = _run_bundle({"rooms": [{"ach": 20.0}]})

    result = verify_project_requirements_from_analysis_run(
        _requirements(),
        bundle,
        [_mapping()],
        source_project_revision=SOURCE_PROJECT_REVISION,
        current_project_revision=None,
    )

    assert result["verified"] is False
    assert result["findings"][0]["state"] == "incomplete"
    assert result["findings"][0]["freshness"] == "unknown"


def test_unstable_external_dependency_cannot_be_current_evidence() -> None:
    bundle = _run_bundle(
        {"rooms": [{"ach": 20.0}]},
        external_dependencies_stable=False,
    )

    result = verify_project_requirements_from_analysis_run(
        _requirements(),
        bundle,
        [_mapping()],
        source_project_revision=SOURCE_PROJECT_REVISION,
        current_project_revision=CURRENT_PROJECT_REVISION,
    )

    assert result["verified"] is False
    assert result["findings"][0]["state"] == "stale"


def test_missing_result_path_becomes_incomplete_evidence_not_pass() -> None:
    bundle = _run_bundle({"rooms": [{"name": "ROOM-A"}]})

    result = verify_project_requirements_from_analysis_run(
        _requirements(),
        bundle,
        [_mapping()],
        source_project_revision=SOURCE_PROJECT_REVISION,
        current_project_revision=CURRENT_PROJECT_REVISION,
    )

    assert result["status"] == "not_checked"
    assert result["verified"] is False
    assert result["findings"][0]["state"] == "incomplete"
    assert result["findings"][0]["actual"] is None


def test_non_scalar_result_mapping_is_rejected() -> None:
    bundle = _run_bundle({"rooms": [{"ach": {"value": 20.0}}]})

    with pytest.raises(
        AnalysisRequirementEvidenceError,
        match="could not bind /result/rooms/0/ach",
    ):
        bind_analysis_run_requirement_evidence(
            bundle,
            [_mapping()],
            source_project_revision=SOURCE_PROJECT_REVISION,
            current_project_revision=CURRENT_PROJECT_REVISION,
        )


def test_tampered_analysis_run_bundle_is_rejected_before_binding() -> None:
    bundle = _run_bundle({"rooms": [{"ach": 20.0}]})
    bundle["result"]["rooms"][0]["ach"] = 99.0

    with pytest.raises(ValueError, match="integrity check failed"):
        bind_analysis_run_requirement_evidence(
            bundle,
            [_mapping()],
            source_project_revision=SOURCE_PROJECT_REVISION,
            current_project_revision=CURRENT_PROJECT_REVISION,
        )


def test_duplicate_mapping_ids_are_rejected() -> None:
    bundle = _run_bundle({"rooms": [{"ach": 20.0}]})

    with pytest.raises(
        AnalysisRequirementEvidenceError,
        match="duplicate ids",
    ):
        bind_analysis_run_requirement_evidence(
            bundle,
            [_mapping(), _mapping()],
            source_project_revision=SOURCE_PROJECT_REVISION,
            current_project_revision=CURRENT_PROJECT_REVISION,
        )


def test_mapping_order_does_not_change_binding_order_or_identity() -> None:
    bundle = _run_bundle(
        {
            "rooms": [
                {"ach": 20.0},
                {"ach": 21.0},
            ]
        }
    )
    first = _mapping(mapping_id="E-B", result_path=("rooms", 1, "ach"))
    second = _mapping(mapping_id="E-A", result_path=("rooms", 0, "ach"))

    forward = bind_analysis_run_requirement_evidence(
        bundle,
        [first, second],
        source_project_revision=SOURCE_PROJECT_REVISION,
        current_project_revision=CURRENT_PROJECT_REVISION,
    )
    reverse = bind_analysis_run_requirement_evidence(
        bundle,
        [second, first],
        source_project_revision=SOURCE_PROJECT_REVISION,
        current_project_revision=CURRENT_PROJECT_REVISION,
    )

    assert forward == reverse
    assert [item.id for item in forward] == ["E-A", "E-B"]


def test_locator_uses_json_pointer_escaping_for_traceability() -> None:
    bundle = _run_bundle({"a/b~c": 20.0})
    mapping = _mapping(result_path=("a/b~c",))

    evidence = bind_analysis_run_requirement_evidence(
        bundle,
        [mapping],
        source_project_revision=SOURCE_PROJECT_REVISION,
        current_project_revision=CURRENT_PROJECT_REVISION,
    )[0]

    assert evidence.evidence_locator == "/result/a~1b~0c"


def test_analysis_run_can_flow_directly_to_verified_proofgraph() -> None:
    bundle = _run_bundle({"rooms": [{"ach": 20.0}]})

    graph = proofgraphs_from_project_requirements_analysis_run(
        _requirements(),
        bundle,
        [_mapping()],
        source_project_revision=SOURCE_PROJECT_REVISION,
        current_project_revision=CURRENT_PROJECT_REVISION,
    )[0]

    assert graph.findings[0].status == "pass"
    assert graph.verdicts[0].status == "pass"
    assert graph.evidence[0].provenance[0].origin == (
        "/result/rooms/0/ach"
    )
    assert graph.evidence[0].version == SOURCE_PROJECT_REVISION
    assert graph.verification_runs[0].metadata["project_verified"] is True


def test_invalid_project_revision_identity_is_rejected() -> None:
    bundle = _run_bundle({"rooms": [{"ach": 20.0}]})

    with pytest.raises(
        AnalysisRequirementEvidenceError,
        match="source_project_revision must be a lowercase SHA-256",
    ):
        bind_analysis_run_requirement_evidence(
            bundle,
            [_mapping()],
            source_project_revision="not-a-digest",
            current_project_revision=CURRENT_PROJECT_REVISION,
        )
