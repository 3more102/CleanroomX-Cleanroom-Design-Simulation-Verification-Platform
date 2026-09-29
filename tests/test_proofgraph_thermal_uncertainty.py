from __future__ import annotations

import copy

import pytest

from cleanroomx.hvac_models import AirState
from cleanroomx.proofgraph import (
    ComplianceFinding,
    ComplianceVerdict,
    proofgraph_from_dict,
    proofgraph_from_thermal_uncertainty,
)
from cleanroomx.thermal_uncertainty_models import UncertainThermalDesign
from cleanroomx.uncertainty_models import Provenance, UncertainValue


def uv(
    value: float,
    unit: str,
    uncertainty: float = 0.0,
    *,
    with_provenance: bool = True,
) -> UncertainValue:
    provenance = (
        Provenance(
            source_type="design_input",
            source_name="Thermal test basis",
            reference="TH-001",
            revision="R1",
            uncertainty_basis="Explicit test interval",
        )
        if with_provenance
        else None
    )
    return UncertainValue(value, unit, uncertainty, provenance)


def cooling_design(
    *,
    available_cooling_capacity_kw: float | None = 6.0,
    available_heating_capacity_kw: float | None = None,
    latent_with_provenance: bool = True,
) -> UncertainThermalDesign:
    return UncertainThermalDesign(
        name="Process",
        room_air=AirState(22.0, 45.0),
        cleanroom_airflow_m3_h=uv(1500.0, "m3/h", 100.0),
        internal_sensible_kw=uv(4.0, "kW", 0.4),
        internal_latent_kw=uv(
            0.5,
            "kW",
            0.1,
            with_provenance=latent_with_provenance,
        ),
        makeup_airflow_m3_h=uv(0.0, "m3/h"),
        supply_air_temp_c=uv(16.0, "C", 1.0),
        capacity_margin_percent=10.0,
        available_cooling_capacity_kw=available_cooling_capacity_kw,
        available_heating_capacity_kw=available_heating_capacity_kw,
    )


def test_thermal_adapter_preserves_capacity_interval_and_dependencies() -> None:
    document = proofgraph_from_thermal_uncertainty(cooling_design()).to_dict()

    assert document["verification_runs"][0]["metadata"]["traceability"]["complete"] is True
    assert document["verdicts"][0]["status"] == "pass"
    by_property = {item["property_name"]: item for item in document["evidence"]}
    cooling = by_property["cooling_capacity_kw"]
    assert cooling["value"]["nominal"] == pytest.approx(4.95)
    assert cooling["value"]["lower"] == pytest.approx(4.4)
    assert cooling["value"]["upper"] == pytest.approx(5.5)
    assert set(cooling["provenance"][0]["upstream_evidence_ids"]) == {
        by_property["net_room_plus_makeup_kw"]["id"],
        by_property["capacity_margin_percent"]["id"],
    }
    assert document["findings"][0]["expected"] == pytest.approx(6.0)
    assert document["findings"][0]["actual"]["upper"] == pytest.approx(5.5)
    assert document["findings"][0]["delta"] == pytest.approx(0.5)
    assert (
        document["requirement_set"]["requirements"][0]["criteria"]["operator"]
        == "available_covers_complete_required_interval"
    )


def test_thermal_adapter_preserves_indeterminate_without_promoting_to_pass() -> None:
    document = proofgraph_from_thermal_uncertainty(
        cooling_design(available_cooling_capacity_kw=5.0)
    ).to_dict()

    assert document["findings"][0]["status"] == "indeterminate"
    assert document["verdicts"][0]["status"] == "indeterminate"
    assert document["findings"][0]["delta"] < 0


def test_thermal_adapter_preserves_capacity_failure() -> None:
    document = proofgraph_from_thermal_uncertainty(
        cooling_design(available_cooling_capacity_kw=3.5)
    ).to_dict()

    assert document["findings"][0]["status"] == "fail"
    assert document["verdicts"][0]["status"] == "fail"


def test_thermal_adapter_does_not_invent_missing_capacity_requirement() -> None:
    with pytest.raises(ValueError, match="requires at least one explicitly configured"):
        proofgraph_from_thermal_uncertainty(
            cooling_design(
                available_cooling_capacity_kw=None,
                available_heating_capacity_kw=None,
            )
        )


def test_thermal_adapter_can_check_heating_without_inventing_cooling_requirement() -> None:
    design = UncertainThermalDesign(
        name="Winter",
        room_air=AirState(22.0, 45.0),
        outdoor_air=AirState(0.0, 50.0),
        cleanroom_airflow_m3_h=uv(1200.0, "m3/h", 50.0),
        internal_sensible_kw=uv(0.0, "kW"),
        internal_latent_kw=uv(0.0, "kW"),
        makeup_airflow_m3_h=uv(800.0, "m3/h", 80.0),
        available_heating_capacity_kw=10.0,
    )

    document = proofgraph_from_thermal_uncertainty(design).to_dict()

    assert len(document["requirement_set"]["requirements"]) == 1
    assert document["requirement_set"]["requirements"][0]["id"].startswith(
        "available-heating-capacity:"
    )
    assert document["verdicts"][0]["status"] in {"pass", "indeterminate"}
    assert "available_cooling_capacity_kw" not in {
        item["property_name"] for item in document["evidence"]
    }
    assert document["verification_runs"][0]["metadata"]["unconfigured_capacities"] == [
        "cooling_capacity_kw"
    ]


def test_thermal_adapter_preserves_missing_input_provenance_as_traceability_gap() -> None:
    document = proofgraph_from_thermal_uncertainty(
        cooling_design(latent_with_provenance=False)
    ).to_dict()

    traceability = document["verification_runs"][0]["metadata"]["traceability"]
    assert traceability["complete"] is False
    assert "internal_latent_kw" in traceability["missing_provenance"]
    assert document["verification_runs"][0]["metadata"]["canonical_overall_status"] == "pass"
    assert document["verdicts"][0]["status"] == "unknown"
    assert "cannot issue a verified capacity verdict" in document["verdicts"][0]["reason"]


def test_thermal_graph_round_trips_and_is_deterministic() -> None:
    first = proofgraph_from_thermal_uncertainty(cooling_design()).to_dict()
    second = proofgraph_from_thermal_uncertainty(cooling_design()).to_dict()

    assert first == second
    assert proofgraph_from_dict(copy.deepcopy(first)).to_dict() == first


def test_proofgraph_status_vocabulary_accepts_not_checked() -> None:
    finding = ComplianceFinding(
        id="finding:not-checked",
        check_id="check:not-checked",
        requirement_id="requirement:not-checked",
        status="not_checked",
        reason="No applicable evidence was checked.",
        evidence_present=False,
    )
    verdict = ComplianceVerdict(
        id="verdict:not-checked",
        requirement_id="requirement:not-checked",
        status="not_checked",
        finding_ids=(finding.id,),
        reason=finding.reason,
    )

    assert finding.status == "not_checked"
    assert verdict.status == "not_checked"
