from __future__ import annotations

from dataclasses import asdict

from .air_system_design import analyze_air_system_design
from .design_consistency import DesignConsistencyStudy, analyze_design_consistency
from .models import RoomSpec
from .proofgraph_models import (
    CalculationEvidence,
    ComplianceCheck,
    ComplianceFinding,
    ComplianceVerdict,
    DesignEvidence,
    Evidence,
    EvidenceSource,
    ProofGraph,
    ProvenanceRecord,
    Requirement,
    RequirementSet,
    VerificationRun,
    _canonical_sha256,
)
from .verification import verify_room


def proofgraph_from_ach_design(
    study: DesignConsistencyStudy,
    *,
    graph_id: str | None = None,
) -> ProofGraph:
    """Map configured minimum-ACH requirements to calculated design ACH evidence.

    The adapter reuses the canonical preliminary air-system result for governing
    supply airflow and the canonical room-volume/ACH calculation helpers. It does
    not introduce a second airflow solver or promote design calculations into
    commissioning/operational evidence.
    """
    if not isinstance(study, DesignConsistencyStudy):
        raise ValueError("study must be a design_consistency.DesignConsistencyStudy")

    configured_rooms = tuple(
        room for room in study.requirements.rooms if room.min_ach is not None
    )
    if not configured_rooms:
        raise ValueError(
            "ACH ProofGraph adaptation requires at least one configured min_ach; "
            "no requirement is invented for observation-only rooms"
        )

    consistency_result = analyze_design_consistency(study)
    air_result = analyze_air_system_design(study.air_system)
    air_models = {room.name: room for room in study.air_system.rooms}
    air_results = {room["name"]: room for room in air_result["rooms"]}

    requirements_revision = _canonical_sha256(asdict(study.requirements))
    air_system_revision = _canonical_sha256(asdict(study.air_system))
    policy_revision = _canonical_sha256(
        {
            "ach_verification": "verify_room",
            "ach_comparison": "actual_greater_than_or_equal_minimum",
            "dimension_abs_tolerance_m": study.dimension_abs_tolerance_m,
        }
    )
    input_sha256 = _canonical_sha256(
        {
            "requirements_sha256": requirements_revision,
            "air_system_sha256": air_system_revision,
            "ach_policy_sha256": policy_revision,
        }
    )

    design_source_id = f"source:design-requirements:{requirements_revision[:16]}"
    calculation_source_id = f"source:air-system-design:{air_system_revision[:16]}"
    evidence_sources = (
        EvidenceSource(
            id=design_source_id,
            kind="design_requirements",
            reference=study.requirements.name,
            revision=requirements_revision,
        ),
        EvidenceSource(
            id=calculation_source_id,
            kind="air_system_design",
            reference=study.air_system.name,
            revision=air_system_revision,
        ),
    )

    requirements: list[Requirement] = []
    evidence: list[Evidence] = []
    checks: list[ComplianceCheck] = []
    findings: list[ComplianceFinding] = []
    verdicts: list[ComplianceVerdict] = []

    for room in configured_rooms:
        expected = room.min_ach
        assert expected is not None
        origin = room.origins.get("min_ach") or {}
        origin_kind = origin.get("kind") or "design_requirements"
        origin_name = origin.get("name") or study.requirements.name
        origin_reference = origin.get("reference") or study.requirements.name

        requirement_id = f"minimum-ach:{room.name}"
        requirements.append(
            Requirement(
                id=requirement_id,
                title=f"Minimum ACH for {room.name}",
                source=f"{origin_kind}:{origin_name}",
                reference=origin_reference,
                scope=(f"room:{room.name}",),
                criteria={
                    "property": "air_changes_per_hour",
                    "operator": "greater_than_or_equal",
                    "expected": expected,
                    "unit": "1/h",
                    "absolute_tolerance_1_h": 0.0,
                    "verification_service": "verify_room",
                },
            )
        )

        design_evidence_id = f"design-minimum-ach:{room.name}"
        requirement_dimensions_id = f"design-room-dimensions:{room.name}"
        evidence_ids = [design_evidence_id, requirement_dimensions_id]
        evidence.extend(
            [
                DesignEvidence(
                    id=design_evidence_id,
                    property_name="minimum_ach",
                    value=expected,
                    unit="1/h",
                    source_id=design_source_id,
                    version=requirements_revision,
                    subject_ref=room.name,
                    provenance=(
                        ProvenanceRecord(
                            id=f"provenance:design-minimum-ach:{room.name}",
                            source_id=design_source_id,
                            origin=f"design_requirements.rooms[{room.name}].min_ach",
                            method=origin_kind,
                        ),
                    ),
                ),
                DesignEvidence(
                    id=requirement_dimensions_id,
                    property_name="room_dimensions_m",
                    value={
                        "length": room.length_m,
                        "width": room.width_m,
                        "height": room.height_m,
                    },
                    unit="m",
                    source_id=design_source_id,
                    version=requirements_revision,
                    subject_ref=room.name,
                    provenance=(
                        ProvenanceRecord(
                            id=f"provenance:design-room-dimensions:{room.name}",
                            source_id=design_source_id,
                            origin=f"design_requirements.rooms[{room.name}].dimensions_m",
                            method="design_requirements",
                        ),
                    ),
                ),
            ]
        )

        actual: float | None = None
        delta: float | None = None
        air_model = air_models.get(room.name)
        air_room_result = air_results.get(room.name)
        if air_model is not None and air_room_result is not None:
            supply_airflow = air_room_result["governing_airflow_m3_h"]
            calculation_room = RoomSpec(
                name=room.name,
                length_m=air_model.length_m,
                width_m=air_model.width_m,
                height_m=air_model.height_m,
                supply_airflow_m3_h=supply_airflow,
                min_ach=expected,
            )
            verification_report = verify_room(calculation_room)
            ach_finding = next(
                item for item in verification_report.findings if item.code == "ACH"
            )
            volume = verification_report.volume_m3
            reported_volume = air_room_result["volume_m3"]
            if volume != reported_volume:
                raise RuntimeError(
                    f"air-system room {room.name!r} volume diverged from the canonical "
                    "room-volume calculation"
                )
            actual = verification_report.ach
            delta = actual - expected

            air_dimensions_evidence_id = f"air-system-room-dimensions:{room.name}"
            volume_evidence_id = f"calculated-room-volume:{room.name}"
            supply_evidence_id = f"calculated-governing-supply:{room.name}"
            ach_evidence_id = f"calculated-ach:{room.name}"
            evidence_ids.extend(
                [
                    air_dimensions_evidence_id,
                    volume_evidence_id,
                    supply_evidence_id,
                    ach_evidence_id,
                ]
            )
            evidence.extend(
                [
                    DesignEvidence(
                        id=air_dimensions_evidence_id,
                        property_name="air_system_room_dimensions_m",
                        value={
                            "length": air_model.length_m,
                            "width": air_model.width_m,
                            "height": air_model.height_m,
                        },
                        unit="m",
                        source_id=calculation_source_id,
                        version=air_system_revision,
                        subject_ref=room.name,
                        provenance=(
                            ProvenanceRecord(
                                id=f"provenance:air-system-room-dimensions:{room.name}",
                                source_id=calculation_source_id,
                                origin=f"air_system_design.rooms[{room.name}].dimensions_m",
                                method="air_system_design_input",
                            ),
                        ),
                    ),
                    CalculationEvidence(
                        id=volume_evidence_id,
                        property_name="room_volume_m3",
                        value=volume,
                        unit="m^3",
                        source_id=calculation_source_id,
                        version=air_system_revision,
                        subject_ref=room.name,
                        provenance=(
                            ProvenanceRecord(
                                id=f"provenance:calculated-room-volume:{room.name}",
                                source_id=calculation_source_id,
                                origin=f"air_system_design.rooms[{room.name}].volume_m3",
                                upstream_evidence_ids=(air_dimensions_evidence_id,),
                                originating_calculation=study.air_system.name,
                                method="verify_room:room_volume_m3",
                            ),
                        ),
                    ),
                    CalculationEvidence(
                        id=supply_evidence_id,
                        property_name="governing_supply_airflow_m3_h",
                        value=supply_airflow,
                        unit="m^3/h",
                        source_id=calculation_source_id,
                        version=air_system_revision,
                        subject_ref=room.name,
                        provenance=(
                            ProvenanceRecord(
                                id=f"provenance:calculated-governing-supply:{room.name}",
                                source_id=calculation_source_id,
                                origin=(
                                    f"air_system_design.rooms[{room.name}]."
                                    "governing_airflow_m3_h"
                                ),
                                originating_calculation=study.air_system.name,
                                method=(
                                    "air_system_design:"
                                    + str(air_room_result["governing_basis"])
                                ),
                            ),
                        ),
                    ),
                    CalculationEvidence(
                        id=ach_evidence_id,
                        property_name="air_changes_per_hour",
                        value=actual,
                        unit="1/h",
                        source_id=calculation_source_id,
                        version=air_system_revision,
                        subject_ref=room.name,
                        provenance=(
                            ProvenanceRecord(
                                id=f"provenance:calculated-ach:{room.name}",
                                source_id=calculation_source_id,
                                origin=(
                                    "governing_supply_airflow_m3_h / room_volume_m3"
                                ),
                                upstream_evidence_ids=(
                                    volume_evidence_id,
                                    supply_evidence_id,
                                ),
                                originating_calculation=study.air_system.name,
                                method="verify_room:air_changes_per_hour",
                            ),
                        ),
                    ),
                ]
            )

        geometry_findings = [
            finding
            for finding in consistency_result["findings"]
            if finding["room"] == room.name
            and finding["code"]
            in {"geometry.length_m", "geometry.width_m", "geometry.height_m"}
        ]
        if len(geometry_findings) != 3:
            geometry_state = "missing"
        elif any(finding["status"] == "fail" for finding in geometry_findings):
            geometry_state = "mismatch"
        elif all(finding["status"] == "pass" for finding in geometry_findings):
            geometry_state = "consistent"
        else:
            geometry_state = "unknown"

        if actual is None:
            status = "unknown"
            reason = (
                "No exactly matching air-system room is available; calculated ACH "
                "evidence is missing."
            )
        elif geometry_state != "consistent":
            status = "unknown"
            reason = (
                "Calculated ACH exists, but canonical design-consistency checks do "
                "not establish matching room geometry; the evidence is not used for "
                "a compliance pass/fail verdict."
            )
        elif ach_finding.status == "pass":
            status = "pass"
            reason = ach_finding.message
        else:
            status = "fail"
            reason = ach_finding.message

        check_id = f"check:minimum-ach:{room.name}"
        finding_id = f"finding:minimum-ach:{room.name}"
        verdict_id = f"verdict:minimum-ach:{room.name}"
        checks.append(
            ComplianceCheck(
                id=check_id,
                requirement_id=requirement_id,
                evidence_ids=tuple(evidence_ids),
                required_evidence_kinds=("design", "calculation"),
            )
        )
        findings.append(
            ComplianceFinding(
                id=finding_id,
                check_id=check_id,
                requirement_id=requirement_id,
                status=status,
                reason=reason,
                evidence_ids=tuple(evidence_ids),
                evidence_present=actual is not None,
                expected=expected,
                actual=actual,
                unit="1/h",
                delta=delta,
            )
        )
        verdicts.append(
            ComplianceVerdict(
                id=verdict_id,
                requirement_id=requirement_id,
                status=status,
                finding_ids=(finding_id,),
                reason=reason,
            )
        )

    requirement_set = RequirementSet(
        id=f"minimum-ach:{requirements_revision[:16]}",
        version=requirements_revision,
        title=f"{study.requirements.name} minimum ACH requirements",
        source=study.requirements.name,
        requirements=tuple(requirements),
    )
    skipped_unconfigured = tuple(
        room.name for room in study.requirements.rooms if room.min_ach is None
    )
    unmatched_air_rooms = tuple(
        sorted(set(air_models) - {room.name for room in configured_rooms})
    )
    geometry_status_by_room = {}
    for room in configured_rooms:
        room_geometry_findings = [
            finding
            for finding in consistency_result["findings"]
            if finding["room"] == room.name
            and finding["code"]
            in {"geometry.length_m", "geometry.width_m", "geometry.height_m"}
        ]
        if len(room_geometry_findings) != 3:
            geometry_status_by_room[room.name] = "missing"
        elif any(finding["status"] == "fail" for finding in room_geometry_findings):
            geometry_status_by_room[room.name] = "mismatch"
        elif all(finding["status"] == "pass" for finding in room_geometry_findings):
            geometry_status_by_room[room.name] = "consistent"
        else:
            geometry_status_by_room[room.name] = "unknown"

    run = VerificationRun(
        id=f"verification:ach-design:{input_sha256[:16]}",
        requirement_set_id=requirement_set.id,
        check_ids=tuple(item.id for item in checks),
        verdict_ids=tuple(item.id for item in verdicts),
        input_sha256=input_sha256,
        metadata={
            "adapter": "ach_design",
            "air_system_status": air_result["status"],
            "requirements_sha256": requirements_revision,
            "air_system_sha256": air_system_revision,
            "ach_policy_sha256": policy_revision,
            "skipped_unconfigured_rooms": list(skipped_unconfigured),
            "unmatched_air_system_rooms": list(unmatched_air_rooms),
            "geometry_consistency_by_room": geometry_status_by_room,
        },
    )
    return ProofGraph(
        id=graph_id or f"proofgraph:ach-design:{input_sha256[:16]}",
        requirement_set=requirement_set,
        evidence_sources=evidence_sources,
        evidence=tuple(evidence),
        checks=tuple(checks),
        findings=tuple(findings),
        verdicts=tuple(verdicts),
        verification_runs=(run,),
    )
