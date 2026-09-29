from __future__ import annotations

from dataclasses import asdict

from .airflow import calculate_air_balance
from .hvac_models import AirBalanceDesign
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


def proofgraph_from_air_balance(
    *,
    room_name: str,
    supply_airflow_m3_h: float,
    design: AirBalanceDesign,
    graph_id: str | None = None,
) -> ProofGraph:
    """Map the canonical steady-state room airflow balance into ProofGraph.

    The adapter treats the supplied flow terms and minimum surplus as explicit
    design inputs, then reuses calculate_air_balance for net-surplus and margin
    evidence. It does not infer room pressure or leakage beyond the flows that
    are explicitly represented by AirBalanceDesign.
    """
    if not isinstance(room_name, str) or not room_name.strip():
        raise ValueError("room_name must be a non-empty string")
    if not isinstance(design, AirBalanceDesign):
        raise ValueError("design must be an hvac_models.AirBalanceDesign")

    result = calculate_air_balance(supply_airflow_m3_h, design)
    input_revision = _canonical_sha256(
        {
            "room_name": room_name,
            "supply_airflow_m3_h": result["supply_airflow_m3_h"],
            "air_balance_design": asdict(design),
        }
    )
    design_source_id = f"source:air-balance-design:{input_revision[:16]}"
    calculation_source_id = f"source:air-balance-calculation:{input_revision[:16]}"
    evidence_sources = (
        EvidenceSource(
            id=design_source_id,
            kind="air_balance_design",
            reference=room_name,
            revision=input_revision,
        ),
        EvidenceSource(
            id=calculation_source_id,
            kind="air_balance_calculation",
            reference=room_name,
            revision=input_revision,
        ),
    )

    requirement_id = f"minimum-airflow-surplus:{room_name}"
    requirement = Requirement(
        id=requirement_id,
        title=f"Minimum airflow surplus for {room_name}",
        source="air_balance_design",
        reference=room_name,
        scope=(f"room:{room_name}",),
        criteria={
            "property": "net_surplus_m3_h",
            "operator": "greater_than_or_equal",
            "expected": result["minimum_surplus_m3_h"],
            "unit": "m^3/h",
            "absolute_tolerance_m3_h": 0.0,
            "calculation_service": "calculate_air_balance",
        },
    )
    requirement_set = RequirementSet(
        id=f"air-balance:{input_revision[:16]}",
        version=input_revision,
        title=f"{room_name} airflow balance requirement",
        source="air_balance_design",
        requirements=(requirement,),
    )

    fields = (
        ("supply_airflow_m3_h", result["supply_airflow_m3_h"]),
        ("return_airflow_m3_h", result["return_airflow_m3_h"]),
        ("exhaust_airflow_m3_h", result["exhaust_airflow_m3_h"]),
        ("transfer_in_airflow_m3_h", result["transfer_in_airflow_m3_h"]),
        ("transfer_out_airflow_m3_h", result["transfer_out_airflow_m3_h"]),
        ("minimum_surplus_m3_h", result["minimum_surplus_m3_h"]),
    )
    design_evidence: list[DesignEvidence] = []
    for field_name, value in fields:
        evidence_id = f"design-air-balance:{room_name}:{field_name}"
        design_evidence.append(
            DesignEvidence(
                id=evidence_id,
                property_name=field_name,
                value=value,
                unit="m^3/h",
                source_id=design_source_id,
                version=input_revision,
                subject_ref=room_name,
                provenance=(
                    ProvenanceRecord(
                        id=f"provenance:{evidence_id}",
                        source_id=design_source_id,
                        origin=f"air_balance_design.{field_name}",
                        method="explicit_air_balance_input",
                    ),
                ),
            )
        )

    upstream_ids = tuple(item.id for item in design_evidence)
    net_surplus_id = f"calculated-net-surplus:{room_name}"
    margin_id = f"calculated-surplus-margin:{room_name}"
    calculation_evidence = (
        CalculationEvidence(
            id=net_surplus_id,
            property_name="net_surplus_m3_h",
            value=result["net_surplus_m3_h"],
            unit="m^3/h",
            source_id=calculation_source_id,
            version=input_revision,
            subject_ref=room_name,
            provenance=(
                ProvenanceRecord(
                    id=f"provenance:{net_surplus_id}",
                    source_id=calculation_source_id,
                    origin=(
                        "supply + transfer_in - return - exhaust - transfer_out"
                    ),
                    upstream_evidence_ids=upstream_ids[:-1],
                    originating_calculation="calculate_air_balance",
                    method="calculate_air_balance",
                ),
            ),
        ),
        CalculationEvidence(
            id=margin_id,
            property_name="surplus_margin_m3_h",
            value=result["surplus_margin_m3_h"],
            unit="m^3/h",
            source_id=calculation_source_id,
            version=input_revision,
            subject_ref=room_name,
            provenance=(
                ProvenanceRecord(
                    id=f"provenance:{margin_id}",
                    source_id=calculation_source_id,
                    origin="net_surplus_m3_h - minimum_surplus_m3_h",
                    upstream_evidence_ids=(net_surplus_id, design_evidence[-1].id),
                    originating_calculation="calculate_air_balance",
                    method="calculate_air_balance",
                ),
            ),
        ),
    )
    evidence: tuple[Evidence, ...] = tuple(design_evidence) + calculation_evidence

    status = "pass" if result["passes_minimum_surplus"] else "fail"
    reason = (
        "Calculated steady-state airflow surplus meets the configured minimum."
        if status == "pass"
        else "Calculated steady-state airflow surplus is below the configured minimum."
    )
    check_id = f"check:minimum-airflow-surplus:{room_name}"
    finding_id = f"finding:minimum-airflow-surplus:{room_name}"
    verdict_id = f"verdict:minimum-airflow-surplus:{room_name}"
    check = ComplianceCheck(
        id=check_id,
        requirement_id=requirement_id,
        evidence_ids=tuple(item.id for item in evidence),
        required_evidence_kinds=("design", "calculation"),
    )
    finding = ComplianceFinding(
        id=finding_id,
        check_id=check_id,
        requirement_id=requirement_id,
        status=status,
        reason=reason,
        evidence_ids=tuple(item.id for item in evidence),
        evidence_present=True,
        expected=result["minimum_surplus_m3_h"],
        actual=result["net_surplus_m3_h"],
        unit="m^3/h",
        delta=result["surplus_margin_m3_h"],
    )
    verdict = ComplianceVerdict(
        id=verdict_id,
        requirement_id=requirement_id,
        status=status,
        finding_ids=(finding_id,),
        reason=reason,
    )
    run = VerificationRun(
        id=f"verification:air-balance:{input_revision[:16]}",
        requirement_set_id=requirement_set.id,
        check_ids=(check_id,),
        verdict_ids=(verdict_id,),
        input_sha256=input_revision,
        metadata={
            "adapter": "air_balance",
            "calculation_service": "calculate_air_balance",
            "balance_interpretation": result["balance_interpretation"],
            "pressure_calculated": False,
        },
    )
    return ProofGraph(
        id=graph_id or f"proofgraph:air-balance:{input_revision[:16]}",
        requirement_set=requirement_set,
        evidence_sources=evidence_sources,
        evidence=evidence,
        checks=(check,),
        findings=(finding,),
        verdicts=(verdict,),
        verification_runs=(run,),
    )
