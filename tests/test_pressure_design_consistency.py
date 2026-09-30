import json

import pytest

from cleanroomx.application import run_analysis
from cleanroomx.pressure_design_consistency import (
    analyze_pressure_design_consistency,
    markdown_pressure_design_consistency_report,
    pressure_design_consistency_from_dict,
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


def test_exact_explicit_mapping_passes() -> None:
    result = analyze_pressure_design_consistency(
        pressure_design_consistency_from_dict(_payload())
    )

    assert result["status"] == "pass"
    assert result["complete"] is True
    assert result["passed"] is True
    assert result["summary"]["pass_count"] == 1
    assert result["findings"][0]["expected"] == pytest.approx(2.0)
    assert result["findings"][0]["actual"] == pytest.approx(2.0)
    assert result["findings"][0]["mapping"] == {
        "node": "Process",
        "reference_node": "Corridor",
    }


def test_verdict_uses_full_precision_pressure_solver_state() -> None:
    payload = _payload(target_pa=2.0000000004)
    payload["pressure_network"]["nodes"][0]["supply_m3_h"] = 72.0000000144
    payload["pressure_abs_tolerance_pa"] = 1e-12

    result = analyze_pressure_design_consistency(
        pressure_design_consistency_from_dict(payload)
    )

    finding = result["findings"][0]
    assert result["status"] == "pass"
    assert finding["status"] == "pass"
    assert finding["actual"] == pytest.approx(2.0000000004, abs=1e-12)
    assert abs(finding["delta"]) <= 1e-12


def test_signed_negative_pressure_target_is_preserved() -> None:
    payload = _payload(target_pa=-2.0)
    payload["pressure_network"]["nodes"][0] = {
        "name": "Process",
        "exhaust_m3_h": 72.0,
    }

    result = analyze_pressure_design_consistency(
        pressure_design_consistency_from_dict(payload)
    )

    assert result["status"] == "pass"
    assert result["findings"][0]["actual"] == pytest.approx(-2.0)


def test_pressure_network_targets_remain_independent_evidence() -> None:
    payload = _payload()
    payload["pressure_network"]["targets"] = [
        {
            "name": "Stricter independent network target",
            "high_node": "Process",
            "low_node": "Corridor",
            "minimum_delta_pa": 3.0,
        }
    ]

    result = analyze_pressure_design_consistency(
        pressure_design_consistency_from_dict(payload)
    )

    assert result["status"] == "pass"
    assert result["findings"][0]["status"] == "pass"
    assert result["source_analyses"]["pressure_network"]["status"] == (
        "solved_with_target_violations"
    )
    assert result["source_analyses"]["pressure_network"]["target_summary"]["failed"] == 1


def test_pressure_difference_outside_tolerance_fails() -> None:
    payload = _payload(target_pa=3.0)
    payload["pressure_abs_tolerance_pa"] = 0.25

    result = analyze_pressure_design_consistency(
        pressure_design_consistency_from_dict(payload)
    )

    finding = result["findings"][0]
    assert result["status"] == "fail"
    assert result["passed"] is False
    assert finding["status"] == "fail"
    assert finding["delta"] == pytest.approx(-1.0)


def test_configured_target_without_mapping_fails_by_default() -> None:
    payload = _payload()
    payload["mappings"] = []

    result = analyze_pressure_design_consistency(
        pressure_design_consistency_from_dict(payload)
    )

    assert result["status"] == "fail"
    assert result["findings"][0]["actual"] is None
    assert "no explicit" in result["findings"][0]["message"].lower()


def test_configured_target_may_be_explicitly_left_unmapped() -> None:
    payload = _payload()
    payload["mappings"] = []
    payload["require_all_configured_targets_mapped"] = False

    result = analyze_pressure_design_consistency(
        pressure_design_consistency_from_dict(payload)
    )

    assert result["status"] == "not_checked"
    assert result["complete"] is False
    assert result["passed"] is True


def test_mapped_room_without_pressure_target_is_not_checked() -> None:
    result = analyze_pressure_design_consistency(
        pressure_design_consistency_from_dict(_payload(target_pa=None))
    )

    finding = result["findings"][0]
    assert result["status"] == "not_checked"
    assert finding["status"] == "not_checked"
    assert finding["expected"] is None
    assert finding["actual"] == pytest.approx(2.0)


def test_unknown_mapping_node_fails_closed() -> None:
    payload = _payload()
    payload["mappings"][0]["node"] = "Missing"

    with pytest.raises(ValueError, match="not present in pressure network"):
        pressure_design_consistency_from_dict(payload)


def test_duplicate_room_mapping_fails_closed() -> None:
    payload = _payload()
    payload["mappings"].append(dict(payload["mappings"][0]))

    with pytest.raises(ValueError, match="at most one entry"):
        pressure_design_consistency_from_dict(payload)


def test_mapping_requires_distinct_node_and_reference() -> None:
    payload = _payload()
    payload["mappings"][0]["reference_node"] = "Process"

    with pytest.raises(ValueError, match="must be different"):
        pressure_design_consistency_from_dict(payload)


@pytest.mark.parametrize("bad_value", [True, "0.5", -0.1, float("inf")])
def test_invalid_pressure_tolerance_fails_closed(bad_value: object) -> None:
    payload = _payload()
    payload["pressure_abs_tolerance_pa"] = bad_value

    with pytest.raises(ValueError, match="pressure_abs_tolerance_pa"):
        pressure_design_consistency_from_dict(payload)


def test_unknown_top_level_field_fails_closed() -> None:
    payload = _payload()
    payload["pressure_abs_tolerence_pa"] = 1.0

    with pytest.raises(ValueError, match="pressure_abs_tolerence_pa"):
        pressure_design_consistency_from_dict(payload)


def test_report_escapes_user_controlled_text() -> None:
    payload = _payload()
    payload["name"] = "Pressure | <study>"

    result = analyze_pressure_design_consistency(
        pressure_design_consistency_from_dict(payload)
    )
    markdown = markdown_pressure_design_consistency_report(result)

    assert "Pressure \\| &lt;study&gt;" in markdown
    assert "Process" in markdown
    assert "Corridor" in markdown


def test_application_path_executes_and_preserves_status() -> None:
    run = run_analysis("pressure_design_consistency", _payload())

    assert run.kind == "pressure_design_consistency"
    assert run.status == "pass"
    assert run.result["complete"] is True
    assert "CleanroomX Pressure Design Consistency" in run.markdown
    json.dumps(run.to_dict(), sort_keys=True, allow_nan=False)
