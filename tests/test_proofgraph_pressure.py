from __future__ import annotations

import copy

import pytest

from cleanroomx.pressure_design_consistency import (
    pressure_design_consistency_from_dict,
)
from cleanroomx.proofgraph import (
    proofgraph_from_dict,
    proofgraph_from_pressure_design_consistency,
)


def _payload(*, target_pa: float | None = 2.0) -> dict:
    room = {
        "name": "Process",
        "dimensions_m": {"length": 4.0, "width": 3.0, "height": 2.8},
    }
    if target_pa is not None:
        room["pressure_target_pa"] = target_pa
    return {
        "name": "Pressure requirement cross-check",
        "requirements": {
            "name": "Requirements",
            "rooms": [room],
        },
        "pressure_network": {
            "name": "Pressure network",
            "nodes": [
                {"name": "Process", "supply_m3_h": 72.0},
                {"name": "Corridor", "fixed_pressure_pa": 0.0},
            ],
            "paths": [
                {
                    "name": "Process-Corridor leakage",
                    "start_node": "Process",
                    "end_node": "Corridor",
                    "kind": "crack",
                    "model": "power_law",
                    "coefficient_m3_s_pa_n": 0.01,
                    "exponent": 1.0,
                }
            ],
        },
        "mappings": [
            {
                "room": "Process",
                "node": "Process",
                "reference_node": "Corridor",
            }
        ],
        "pressure_abs_tolerance_pa": 1e-9,
    }


def _graph(payload: dict):
    return proofgraph_from_pressure_design_consistency(
        pressure_design_consistency_from_dict(payload)
    )


def test_pressure_adapter_builds_design_to_calculation_evidence_chain() -> None:
    document = _graph(_payload()).to_dict()

    assert document["verdicts"][0]["status"] == "pass"
    assert [item["kind"] for item in document["evidence"]] == [
        "design",
        "calculation",
    ]
    design, calculation = document["evidence"]
    assert design["property_name"] == "pressure_target_pa"
    assert design["value"] == pytest.approx(2.0)
    assert calculation["property_name"] == "pressure_difference_pa"
    assert calculation["value"] == pytest.approx(2.0)
    assert calculation["provenance"][0]["method"] == "pressure_network_solver"
    assert document["checks"][0]["required_evidence_kinds"] == [
        "design",
        "calculation",
    ]
    assert len(document["evidence_sources"][0]["revision"]) == 64
    assert len(document["evidence_sources"][1]["revision"]) == 64


def test_pressure_adapter_preserves_failure_and_delta() -> None:
    payload = _payload(target_pa=3.0)
    payload["pressure_abs_tolerance_pa"] = 0.25

    document = _graph(payload).to_dict()

    assert document["verdicts"][0]["status"] == "fail"
    assert document["findings"][0]["actual"] == pytest.approx(2.0)
    assert document["findings"][0]["delta"] == pytest.approx(-1.0)


def test_required_mapping_failure_keeps_target_without_inventing_calculation() -> None:
    payload = _payload()
    payload["mappings"] = []

    document = _graph(payload).to_dict()

    assert document["verdicts"][0]["status"] == "fail"
    assert [item["kind"] for item in document["evidence"]] == ["design"]
    assert document["findings"][0]["evidence_present"] is False
    assert document["findings"][0]["actual"] is None


def test_explicitly_optional_mapping_preserves_not_checked() -> None:
    payload = _payload()
    payload["mappings"] = []
    payload["require_all_configured_targets_mapped"] = False

    document = _graph(payload).to_dict()

    assert document["verdicts"][0]["status"] == "not_checked"
    assert document["findings"][0]["status"] == "not_checked"
    assert document["verification_runs"][0]["metadata"]["source_status"] == "not_checked"
    assert proofgraph_from_dict(copy.deepcopy(document)).to_dict() == document


def test_negative_pressure_target_sign_is_preserved() -> None:
    payload = _payload(target_pa=-2.0)
    payload["pressure_network"]["nodes"][0] = {
        "name": "Process",
        "exhaust_m3_h": 72.0,
    }

    document = _graph(payload).to_dict()

    assert document["verdicts"][0]["status"] == "pass"
    assert document["findings"][0]["expected"] == pytest.approx(-2.0)
    assert document["findings"][0]["actual"] == pytest.approx(-2.0)


def test_adapter_does_not_invent_requirement_when_no_target_exists() -> None:
    study = pressure_design_consistency_from_dict(_payload(target_pa=None))

    with pytest.raises(ValueError, match="at least one configured pressure_target_pa"):
        proofgraph_from_pressure_design_consistency(study)


def test_pressure_graph_round_trips_through_strict_parser() -> None:
    document = _graph(_payload()).to_dict()

    restored = proofgraph_from_dict(copy.deepcopy(document))

    assert restored.to_dict() == document


def test_pressure_graph_is_deterministic() -> None:
    study = pressure_design_consistency_from_dict(_payload())

    first = proofgraph_from_pressure_design_consistency(study).to_dict()
    second = proofgraph_from_pressure_design_consistency(study).to_dict()

    assert first == second
