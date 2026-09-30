from __future__ import annotations

from dataclasses import asdict

from .hvac_models import AirState
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
from .psychrometric_uncertainty_models import UncertainAirState
from .thermal_uncertainty import (
    analyze_thermal_uncertainty,
    calculate_thermal_uncertainty_values,
)
from .thermal_uncertainty_models import UncertainThermalDesign
from .uncertainty_models import Provenance, UncertainValue


def _source_for_input(
    provenance: Provenance | None,
    *,
    fallback_source: EvidenceSource,
    sources: dict[str, EvidenceSource],
) -> EvidenceSource:
    if provenance is None:
        return fallback_source

    payload = asdict(provenance)
    digest = _canonical_sha256(payload)
    source_id = f"source:thermal-input:{digest[:16]}"
    reference = provenance.source_name
    if provenance.reference:
        reference = f"{reference} ({provenance.reference})"
    source = EvidenceSource(
        id=source_id,
        kind=provenance.source_type,
        reference=reference,
        revision=provenance.revision or digest,
    )
    sources.setdefault(source.id, source)
    return sources[source.id]


def _uncertain_value(
    item: UncertainValue,
) -> dict[str, float]:
    return {
        "nominal": item.value,
        "lower": item.lower,
        "upper": item.upper,
        "uncertainty_abs": item.uncertainty_abs,
    }


def _input_evidence(
    *,
    evidence_id: str,
    property_name: str,
    item: UncertainValue,
    origin: str,
    version: str,
    subject_ref: str,
    fallback_source: EvidenceSource,
    sources: dict[str, EvidenceSource],
) -> DesignEvidence:
    source = _source_for_input(
        item.provenance,
        fallback_source=fallback_source,
        sources=sources,
    )
    return DesignEvidence(
        id=evidence_id,
        property_name=property_name,
        value=_uncertain_value(item),
        unit=item.unit,
        source_id=source.id,
        version=version,
        subject_ref=subject_ref,
        provenance=(
            ProvenanceRecord(
                id=f"provenance:{evidence_id}",
                source_id=source.id,
                origin=origin,
                method="explicit_uncertain_input",
            ),
        ),
    )


def _fixed_input_evidence(
    *,
    evidence_id: str,
    property_name: str,
    value: float,
    unit: str,
    origin: str,
    version: str,
    subject_ref: str,
    source: EvidenceSource,
) -> DesignEvidence:
    return DesignEvidence(
        id=evidence_id,
        property_name=property_name,
        value=value,
        unit=unit,
        source_id=source.id,
        version=version,
        subject_ref=subject_ref,
        provenance=(
            ProvenanceRecord(
                id=f"provenance:{evidence_id}",
                source_id=source.id,
                origin=origin,
                method="explicit_design_input",
            ),
        ),
    )


def proofgraph_from_thermal_uncertainty(
    design: UncertainThermalDesign,
    *,
    graph_id: str | None = None,
) -> ProofGraph:
    """Map canonical thermal uncertainty capacity checks into ProofGraph.

    The adapter reuses analyze_thermal_uncertainty and preserves its complete-
    interval capacity semantics. It creates requirements only for explicitly
    configured available cooling/heating capacities; absent capacities do not
    become invented requirements.
    """
    if not isinstance(design, UncertainThermalDesign):
        raise ValueError(
            "design must be a thermal_uncertainty_models.UncertainThermalDesign"
        )
    if (
        design.available_cooling_capacity_kw is None
        and design.available_heating_capacity_kw is None
    ):
        raise ValueError(
            "thermal ProofGraph adaptation requires at least one explicitly "
            "configured available cooling or heating capacity"
        )

    result = analyze_thermal_uncertainty(design)
    calculation = calculate_thermal_uncertainty_values(design)
    input_revision = _canonical_sha256(asdict(design))
    subject_ref = design.name

    design_source = EvidenceSource(
        id=f"source:thermal-design:{input_revision[:16]}",
        kind="thermal_uncertainty_design",
        reference=design.name,
        revision=input_revision,
    )
    calculation_source = EvidenceSource(
        id=f"source:thermal-calculation:{input_revision[:16]}",
        kind="thermal_uncertainty_calculation",
        reference=design.name,
        revision=input_revision,
    )
    sources: dict[str, EvidenceSource] = {
        design_source.id: design_source,
        calculation_source.id: calculation_source,
    }

    design_evidence: list[DesignEvidence] = []
    by_property: dict[str, str] = {}

    def add_uncertain(
        property_name: str,
        item: UncertainValue,
        origin: str,
    ) -> None:
        evidence_id = f"design-thermal:{design.name}:{property_name}"
        evidence = _input_evidence(
            evidence_id=evidence_id,
            property_name=property_name,
            item=item,
            origin=origin,
            version=input_revision,
            subject_ref=subject_ref,
            fallback_source=design_source,
            sources=sources,
        )
        design_evidence.append(evidence)
        by_property[property_name] = evidence.id

    def add_fixed(
        property_name: str,
        value: float,
        unit: str,
        origin: str,
    ) -> None:
        evidence_id = f"design-thermal:{design.name}:{property_name}"
        evidence = _fixed_input_evidence(
            evidence_id=evidence_id,
            property_name=property_name,
            value=value,
            unit=unit,
            origin=origin,
            version=input_revision,
            subject_ref=subject_ref,
            source=design_source,
        )
        design_evidence.append(evidence)
        by_property[property_name] = evidence.id

    add_uncertain(
        "cleanroom_airflow_m3_h",
        design.cleanroom_airflow_m3_h,
        "thermal_uncertainty_design.cleanroom_airflow_m3_h",
    )
    add_uncertain(
        "internal_sensible_kw",
        design.internal_sensible_kw,
        "thermal_uncertainty_design.internal_sensible_kw",
    )
    add_uncertain(
        "internal_latent_kw",
        design.internal_latent_kw,
        "thermal_uncertainty_design.internal_latent_kw",
    )
    add_uncertain(
        "makeup_airflow_m3_h",
        design.makeup_airflow_m3_h,
        "thermal_uncertainty_design.makeup_airflow_m3_h",
    )
    if design.supply_air_temp_c is not None:
        add_uncertain(
            "supply_air_temp_c",
            design.supply_air_temp_c,
            "thermal_uncertainty_design.supply_air_temp_c",
        )

    def add_air_state(prefix: str, state: AirState | UncertainAirState | None) -> None:
        if state is None:
            return
        fields = (
            ("dry_bulb_c", "C"),
            ("relative_humidity_percent", "%"),
            ("pressure_kpa", "kPa"),
        )
        for field_name, unit in fields:
            property_name = f"{prefix}.{field_name}"
            origin = f"thermal_uncertainty_design.{property_name}"
            value = getattr(state, field_name)
            if isinstance(value, UncertainValue):
                add_uncertain(property_name, value, origin)
            else:
                add_fixed(property_name, value, unit, origin)

    add_air_state("room_air", design.room_air)
    add_air_state("outdoor_air", design.outdoor_air)

    add_fixed(
        "capacity_margin_percent",
        design.capacity_margin_percent,
        "%",
        "thermal_uncertainty_design.capacity_margin_percent",
    )
    if design.available_cooling_capacity_kw is not None:
        add_fixed(
            "available_cooling_capacity_kw",
            design.available_cooling_capacity_kw,
            "kW",
            "thermal_uncertainty_design.available_cooling_capacity_kw",
        )
    if design.available_heating_capacity_kw is not None:
        add_fixed(
            "available_heating_capacity_kw",
            design.available_heating_capacity_kw,
            "kW",
            "thermal_uncertainty_design.available_heating_capacity_kw",
        )

    calculation_evidence: list[CalculationEvidence] = []

    def add_calculation(
        property_name: str,
        value: dict,
        *,
        unit: str,
        upstream_properties: tuple[str, ...],
        origin: str,
    ) -> None:
        evidence_id = f"calculated-thermal:{design.name}:{property_name}"
        upstream_ids = tuple(
            by_property[name]
            for name in upstream_properties
            if name in by_property
        )
        evidence = CalculationEvidence(
            id=evidence_id,
            property_name=property_name,
            value=value,
            unit=unit,
            source_id=calculation_source.id,
            version=input_revision,
            subject_ref=subject_ref,
            provenance=(
                ProvenanceRecord(
                    id=f"provenance:{evidence_id}",
                    source_id=calculation_source.id,
                    origin=origin,
                    upstream_evidence_ids=upstream_ids,
                    originating_calculation="analyze_thermal_uncertainty",
                    method=result["method"],
                ),
            ),
        )
        calculation_evidence.append(evidence)
        by_property[property_name] = evidence.id

    add_calculation(
        "internal_total_kw",
        calculation["loads_kw"]["internal_total"],
        unit="kW",
        upstream_properties=("internal_sensible_kw", "internal_latent_kw"),
        origin="internal_sensible_kw + internal_latent_kw",
    )
    makeup_upstream = (
        "makeup_airflow_m3_h",
        "room_air.dry_bulb_c",
        "room_air.relative_humidity_percent",
        "room_air.pressure_kpa",
        "outdoor_air.dry_bulb_c",
        "outdoor_air.relative_humidity_percent",
        "outdoor_air.pressure_kpa",
    )
    add_calculation(
        "makeup_air_total_kw",
        calculation["loads_kw"]["makeup_air_total"],
        unit="kW",
        upstream_properties=makeup_upstream,
        origin="makeup_air_psychrometric_load_interval",
    )
    add_calculation(
        "net_room_plus_makeup_kw",
        calculation["loads_kw"]["net_room_plus_makeup"],
        unit="kW",
        upstream_properties=("internal_total_kw", "makeup_air_total_kw"),
        origin="internal_total_kw + makeup_air_total_kw",
    )

    thermal_airflow = calculation["airflow_m3_h"]["thermal_for_internal_sensible"]
    if thermal_airflow is not None:
        add_calculation(
            "thermal_airflow_for_internal_sensible_m3_h",
            thermal_airflow,
            unit="m3/h",
            upstream_properties=(
                "internal_sensible_kw",
                "supply_air_temp_c",
                "room_air.dry_bulb_c",
                "room_air.relative_humidity_percent",
                "room_air.pressure_kpa",
            ),
            origin="sensible_load_supply_airflow_interval",
        )

    governing_upstream = [
        "cleanroom_airflow_m3_h",
        "makeup_airflow_m3_h",
    ]
    if thermal_airflow is not None:
        governing_upstream.append("thermal_airflow_for_internal_sensible_m3_h")
    add_calculation(
        "governing_supply_airflow_m3_h",
        calculation["airflow_m3_h"]["governing"],
        unit="m3/h",
        upstream_properties=tuple(governing_upstream),
        origin="maximum_of_explicit_airflow_requirements",
    )

    for mode in ("cooling", "heating"):
        add_calculation(
            f"{mode}_capacity_kw",
            calculation[f"{mode}_capacity_kw"],
            unit="kW",
            upstream_properties=(
                "net_room_plus_makeup_kw",
                "capacity_margin_percent",
            ),
            origin=f"conservative_{mode}_capacity_interval",
        )

    evidence: tuple[Evidence, ...] = (
        tuple(design_evidence) + tuple(calculation_evidence)
    )

    requirements: list[Requirement] = []
    checks: list[ComplianceCheck] = []
    findings: list[ComplianceFinding] = []
    verdicts: list[ComplianceVerdict] = []

    for mode in ("cooling", "heating"):
        available = getattr(design, f"available_{mode}_capacity_kw")
        if available is None:
            continue
        capacity_result = result[f"{mode}_capacity_kw"]
        capacity_values = calculation[f"{mode}_capacity_kw"]
        canonical_status = capacity_result["status"]
        if canonical_status not in {"pass", "fail", "indeterminate"}:
            raise ValueError(
                f"unexpected canonical {mode} capacity status: {canonical_status!r}"
            )
        if result["traceability"]["complete"]:
            status = canonical_status
            reason = capacity_result["message"]
        else:
            status = "unknown"
            missing = ", ".join(result["traceability"]["missing_provenance"])
            reason = (
                f"Canonical {mode} capacity status is {canonical_status.upper()}, "
                f"but input provenance is incomplete for: {missing}. "
                "ProofGraph cannot issue a verified capacity verdict."
            )

        requirement_id = f"available-{mode}-capacity:{design.name}"
        requirement = Requirement(
            id=requirement_id,
            title=f"Available {mode} capacity for {design.name}",
            source="thermal_uncertainty_design",
            reference=design.name,
            scope=(f"thermal-analysis:{design.name}",),
            criteria={
                "property": f"{mode}_capacity_kw",
                "operator": "available_covers_complete_required_interval",
                "available_capacity_kw": available,
                "unit": "kW",
                "calculation_service": "analyze_thermal_uncertainty",
                "uncertainty_method": result["method"],
            },
        )
        requirements.append(requirement)

        available_id = by_property[f"available_{mode}_capacity_kw"]
        calculated_id = by_property[f"{mode}_capacity_kw"]
        evidence_ids = (available_id, calculated_id)
        check_id = f"check:available-{mode}-capacity:{design.name}"
        finding_id = f"finding:available-{mode}-capacity:{design.name}"
        verdict_id = f"verdict:available-{mode}-capacity:{design.name}"

        checks.append(
            ComplianceCheck(
                id=check_id,
                requirement_id=requirement_id,
                evidence_ids=evidence_ids,
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
                evidence_ids=evidence_ids,
                evidence_present=True,
                expected=available,
                actual={
                    "nominal": capacity_values["nominal"],
                    "lower": capacity_values["lower"],
                    "upper": capacity_values["upper"],
                },
                unit="kW",
                delta=available - capacity_values["upper"],
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
        id=f"thermal-capacity:{input_revision[:16]}",
        version=input_revision,
        title=f"{design.name} thermal capacity requirements",
        source="thermal_uncertainty_design",
        requirements=tuple(requirements),
    )
    run = VerificationRun(
        id=f"verification:thermal-capacity:{input_revision[:16]}",
        requirement_set_id=requirement_set.id,
        check_ids=tuple(item.id for item in checks),
        verdict_ids=tuple(item.id for item in verdicts),
        input_sha256=input_revision,
        metadata={
            "adapter": "thermal_uncertainty",
            "calculation_service": "analyze_thermal_uncertainty",
            "method": result["method"],
            "canonical_overall_status": result["overall_status"],
            "canonical_capacity_statuses": {
                mode: result[f"{mode}_capacity_kw"]["status"]
                for mode in ("cooling", "heating")
            },
            "traceability": result["traceability"],
            "engineering_note": result["engineering_note"],
            "unconfigured_capacities": [
                f"{mode}_capacity_kw"
                for mode in ("cooling", "heating")
                if getattr(design, f"available_{mode}_capacity_kw") is None
            ],
        },
    )
    return ProofGraph(
        id=graph_id or f"proofgraph:thermal-capacity:{input_revision[:16]}",
        requirement_set=requirement_set,
        evidence_sources=tuple(sources.values()),
        evidence=evidence,
        checks=tuple(checks),
        findings=tuple(findings),
        verdicts=tuple(verdicts),
        verification_runs=(run,),
    )
