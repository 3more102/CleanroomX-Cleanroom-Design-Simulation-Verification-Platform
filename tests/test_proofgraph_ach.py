from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from cleanroomx.design_consistency import design_consistency_from_dict
from cleanroomx.proofgraph import proofgraph_from_ach_design, proofgraph_from_dict


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "design_consistency_demo.json"


def _payload() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def _graph(payload: dict):
    return proofgraph_from_ach_design(design_consistency_from_dict(payload))


def _evidence(document: dict, property_name: str) -> dict:
    return next(
        item for item in document["evidence"] if item["property_name"] == property_name
    )


def test_ach_adapter_builds_requirement_volume_supply_and_calculated_ach_chain() -> None:
    document = _graph(_payload()).to_dict()

    assert document["verdicts"][0]["status"] == "pass"
    requirement = document["requirement_set"]["requirements"][0]
    assert requirement["criteria"]["operator"] == "greater_than_or_equal"
    assert requirement["criteria"]["expected"] == pytest.approx(30.0)

    minimum = _evidence(document, "minimum_ach")
    volume = _evidence(document, "room_volume_m3")
    supply = _evidence(document, "governing_supply_airflow_m3_h")
    ach = _evidence(document, "air_changes_per_hour")

    assert minimum["kind"] == "design"
    assert volume["kind"] == "calculation"
    assert volume["value"] == pytest.approx(72.0)
    assert supply["value"] > 2160.0
    assert ach["value"] == pytest.approx(supply["value"] / volume["value"])
    assert ach["provenance"][0]["method"] == "verify_room:air_changes_per_hour"
    assert set(ach["provenance"][0]["upstream_evidence_ids"]) == {
        volume["id"],
        supply["id"],
    }
    assert document["checks"][0]["required_evidence_kinds"] == [
        "design",
        "calculation",
    ]


def test_ach_adapter_preserves_failure_and_signed_delta() -> None:
    payload = _payload()
    payload["requirements"]["rooms"][0]["min_ach"] = 100.0

    document = _graph(payload).to_dict()
    finding = document["findings"][0]

    assert document["verdicts"][0]["status"] == "fail"
    assert finding["actual"] < finding["expected"]
    assert finding["delta"] == pytest.approx(
        finding["actual"] - finding["expected"]
    )


def test_ach_adapter_does_not_repurpose_design_consistency_tolerance() -> None:
    payload = _payload()
    baseline = _graph(payload).to_dict()["findings"][0]["actual"]
    payload["requirements"]["rooms"][0]["min_ach"] = baseline + 0.25
    payload["ach_abs_tolerance_1_h"] = 100.0

    document = _graph(payload).to_dict()

    assert document["verdicts"][0]["status"] == "fail"
    assert document["findings"][0]["delta"] == pytest.approx(-0.25)
    assert document["requirement_set"]["requirements"][0]["criteria"][
        "absolute_tolerance_1_h"
    ] == 0.0


def test_missing_matching_air_system_room_is_unknown_not_pass() -> None:
    payload = _payload()
    payload["air_system"]["rooms"][0]["name"] = "Different room"

    document = _graph(payload).to_dict()

    assert document["verdicts"][0]["status"] == "unknown"
    assert document["findings"][0]["evidence_present"] is False
    assert document["findings"][0]["actual"] is None
    assert all(item["kind"] == "design" for item in document["evidence"])
    assert not any(item["kind"] == "calculation" for item in document["evidence"])


def test_geometry_mismatch_with_calculated_ach_is_unknown_not_pass_or_fail() -> None:
    payload = _payload()
    payload["air_system"]["rooms"][0]["dimensions_m"]["length"] = 6.5

    document = _graph(payload).to_dict()
    finding = document["findings"][0]

    assert document["verdicts"][0]["status"] == "unknown"
    assert finding["evidence_present"] is True
    assert finding["actual"] is not None
    assert (
        document["verification_runs"][0]["metadata"][
            "geometry_consistency_by_room"
        ]["Process"]
        == "mismatch"
    )


def test_adapter_does_not_invent_requirement_when_minimum_ach_is_absent() -> None:
    payload = _payload()
    del payload["requirements"]["reference_profiles"][0]["values"]["min_ach"]

    study = design_consistency_from_dict(payload)
    with pytest.raises(ValueError, match="at least one configured min_ach"):
        proofgraph_from_ach_design(study)


def test_ach_graph_round_trips_through_strict_parser() -> None:
    document = _graph(_payload()).to_dict()

    restored = proofgraph_from_dict(copy.deepcopy(document))

    assert restored.to_dict() == document


def test_ach_graph_is_deterministic() -> None:
    study = design_consistency_from_dict(_payload())

    first = proofgraph_from_ach_design(study).to_dict()
    second = proofgraph_from_ach_design(study).to_dict()

    assert first == second
