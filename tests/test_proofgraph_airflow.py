from __future__ import annotations

import copy

import pytest

from cleanroomx.hvac_models import AirBalanceDesign
from cleanroomx.proofgraph import proofgraph_from_air_balance, proofgraph_from_dict


def _design(*, minimum_surplus_m3_h: float = 100.0) -> AirBalanceDesign:
    return AirBalanceDesign(
        return_airflow_m3_h=800.0,
        exhaust_airflow_m3_h=200.0,
        transfer_in_airflow_m3_h=50.0,
        transfer_out_airflow_m3_h=25.0,
        minimum_surplus_m3_h=minimum_surplus_m3_h,
    )


def test_air_balance_adapter_preserves_explicit_flows_and_dependencies() -> None:
    document = proofgraph_from_air_balance(
        room_name="Process",
        supply_airflow_m3_h=1200.0,
        design=_design(),
    ).to_dict()

    assert document["verdicts"][0]["status"] == "pass"
    by_property = {item["property_name"]: item for item in document["evidence"]}
    assert by_property["supply_airflow_m3_h"]["value"] == pytest.approx(1200.0)
    assert by_property["return_airflow_m3_h"]["value"] == pytest.approx(800.0)
    assert by_property["exhaust_airflow_m3_h"]["value"] == pytest.approx(200.0)
    assert by_property["transfer_in_airflow_m3_h"]["value"] == pytest.approx(50.0)
    assert by_property["transfer_out_airflow_m3_h"]["value"] == pytest.approx(25.0)
    assert by_property["net_surplus_m3_h"]["value"] == pytest.approx(225.0)
    assert by_property["surplus_margin_m3_h"]["value"] == pytest.approx(125.0)
    assert set(by_property["surplus_margin_m3_h"]["provenance"][0]["upstream_evidence_ids"]) == {
        by_property["net_surplus_m3_h"]["id"],
        by_property["minimum_surplus_m3_h"]["id"],
    }
    assert document["verification_runs"][0]["metadata"]["pressure_calculated"] is False


def test_air_balance_adapter_preserves_fail_and_signed_margin() -> None:
    document = proofgraph_from_air_balance(
        room_name="Process",
        supply_airflow_m3_h=1000.0,
        design=_design(minimum_surplus_m3_h=100.0),
    ).to_dict()

    finding = document["findings"][0]
    assert document["verdicts"][0]["status"] == "fail"
    assert finding["actual"] == pytest.approx(25.0)
    assert finding["expected"] == pytest.approx(100.0)
    assert finding["delta"] == pytest.approx(-75.0)


def test_air_balance_adapter_does_not_claim_pressure() -> None:
    document = proofgraph_from_air_balance(
        room_name="Process",
        supply_airflow_m3_h=1200.0,
        design=_design(),
    ).to_dict()

    assert document["verification_runs"][0]["metadata"]["pressure_calculated"] is False
    assert not any(
        item["property_name"].endswith("pressure_pa")
        for item in document["evidence"]
    )


def test_air_balance_adapter_rejects_nonfinite_derived_calculation() -> None:
    with pytest.raises(ValueError, match="incoming_airflow_m3_h"):
        proofgraph_from_air_balance(
            room_name="Process",
            supply_airflow_m3_h=1e308,
            design=AirBalanceDesign(transfer_in_airflow_m3_h=1e308),
        )


def test_air_balance_graph_round_trips_through_strict_parser() -> None:
    document = proofgraph_from_air_balance(
        room_name="Process",
        supply_airflow_m3_h=1200.0,
        design=_design(),
    ).to_dict()

    restored = proofgraph_from_dict(copy.deepcopy(document))

    assert restored.to_dict() == document


def test_air_balance_graph_is_deterministic() -> None:
    first = proofgraph_from_air_balance(
        room_name="Process",
        supply_airflow_m3_h=1200.0,
        design=_design(),
    ).to_dict()
    second = proofgraph_from_air_balance(
        room_name="Process",
        supply_airflow_m3_h=1200.0,
        design=_design(),
    ).to_dict()

    assert first == second
