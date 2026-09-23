import pytest

from cleanroomx.fan_loop_uncertainty import (
    analyze_fan_loop_network_uncertainty,
)
from cleanroomx.fan_loop_uncertainty_io import (
    fan_loop_network_uncertainty_from_dict,
)
from cleanroomx.fan_loop_uncertainty_report import (
    markdown_fan_loop_network_uncertainty_report,
)


def _data() -> dict:
    return {
        "name": "Fan loop uncertainty",
        "fan_discharge_node": "Supply",
        "fan_suction_node": "Return",
        "fixed_pressure_pa": {
            "value": 20.0,
            "uncertainty_abs": 10.0,
            "provenance": {
                "source_type": "design",
                "source_name": "Terminal pressure allowance",
            },
        },
        "fan_curve": {
            "name": "Reference fan",
            "provenance": {
                "source_type": "manufacturer_data",
                "source_name": "Fan schedule",
                "reference": "FAN-LOOP-001",
            },
            "points": [
                {"airflow_m3_h": 0.0, "pressure_pa": 500.0},
                {"airflow_m3_h": 3600.0, "pressure_pa": 125.0},
                {"airflow_m3_h": 7200.0, "pressure_pa": 0.0},
            ],
        },
        "loop_network": {
            "name": "Reference two-path loop",
            "reference_node": "Supply",
            "node_injections_m3_h": {
                "Supply": 3600.0,
                "Mid": 0.0,
                "Return": -3600.0,
            },
            "edges": [
                {
                    "name": "Direct",
                    "start_node": "Supply",
                    "end_node": "Return",
                    "resistance_pa_per_m3_s_squared": 500.0,
                },
                {
                    "name": "Upper 1",
                    "start_node": "Supply",
                    "end_node": "Mid",
                    "resistance_pa_per_m3_s_squared": 250.0,
                },
                {
                    "name": "Upper 2",
                    "start_node": "Mid",
                    "end_node": "Return",
                    "resistance_pa_per_m3_s_squared": 250.0,
                },
            ],
        },
        "edge_resistance_uncertainty": {
            "Direct": {
                "uncertainty_abs": 50.0,
                "provenance": {
                    "source_type": "design",
                    "source_name": "Direct-path resistance allowance",
                },
            },
            "Upper 1": {
                "uncertainty_abs": 25.0,
                "provenance": {
                    "source_type": "design",
                    "source_name": "Upper-path section allowance",
                },
            },
            "Upper 2": {
                "uncertainty_abs": 25.0,
                "provenance": {
                    "source_type": "design",
                    "source_name": "Upper-path section allowance",
                },
            },
        },
    }


def test_complete_corner_analysis_reports_operating_envelope() -> None:
    result = analyze_fan_loop_network_uncertainty(
        fan_loop_network_uncertainty_from_dict(_data())
    )

    assert result["status"] == "complete"
    assert result["corner_count"] == 16
    assert result["solved_corner_count"] == 16
    assert result["unresolved_corner_count"] == 0
    assert result["operating_point_envelope"] is not None
    assert result["equivalent_loop_resistance_envelope"] is not None
    assert result["traceability"]["complete"] is True
    assert result["nominal_equivalent_loop_resistance_pa_per_m3_s_squared"] == pytest.approx(
        125.0, abs=1e-8
    )


def test_zero_uncertainty_collapses_duplicate_corner_dimensions() -> None:
    data = _data()
    data["fixed_pressure_pa"]["uncertainty_abs"] = 0.0
    for item in data["edge_resistance_uncertainty"].values():
        item["uncertainty_abs"] = 0.0

    result = analyze_fan_loop_network_uncertainty(
        fan_loop_network_uncertainty_from_dict(data)
    )
    assert result["corner_count"] == 1
    assert result["solved_corner_count"] == 1


def test_unsolved_corner_makes_analysis_indeterminate() -> None:
    data = _data()
    data["fixed_pressure_pa"]["value"] = 450.0
    data["fixed_pressure_pa"]["uncertainty_abs"] = 100.0

    result = analyze_fan_loop_network_uncertainty(
        fan_loop_network_uncertainty_from_dict(data)
    )
    assert result["status"] == "indeterminate"
    assert result["unresolved_corner_count"] >= 1
    assert result["operating_point_envelope"] is None
    assert any(
        corner["status"] == "no_intersection_in_supplied_range"
        for corner in result["corners"]
    )


def test_unknown_edge_uncertainty_is_rejected() -> None:
    data = _data()
    data["edge_resistance_uncertainty"]["Missing"] = {"uncertainty_abs": 1.0}
    with pytest.raises(ValueError, match="unknown edge"):
        fan_loop_network_uncertainty_from_dict(data)


def test_edge_resistance_interval_must_remain_positive() -> None:
    data = _data()
    data["edge_resistance_uncertainty"]["Direct"]["uncertainty_abs"] = 500.0
    with pytest.raises(ValueError, match="lower uncertainty bound"):
        fan_loop_network_uncertainty_from_dict(data)


def test_corner_limit_prevents_combinatorial_explosion() -> None:
    data = _data()
    data["max_corner_cases"] = 8
    study = fan_loop_network_uncertainty_from_dict(data)
    with pytest.raises(ValueError, match="exceeding max_corner_cases"):
        analyze_fan_loop_network_uncertainty(study)


def test_missing_provenance_is_separate_from_numerical_status() -> None:
    data = _data()
    del data["fan_curve"]["provenance"]
    del data["edge_resistance_uncertainty"]["Direct"]["provenance"]

    result = analyze_fan_loop_network_uncertainty(
        fan_loop_network_uncertainty_from_dict(data)
    )
    assert result["status"] == "complete"
    assert result["traceability"]["complete"] is False
    assert "fan_curve" in result["traceability"]["missing_provenance"]
    assert "edge:Direct" in result["traceability"]["missing_provenance"]


def test_markdown_report_contains_corner_envelope_and_traceability() -> None:
    result = analyze_fan_loop_network_uncertainty(
        fan_loop_network_uncertainty_from_dict(_data())
    )
    text = markdown_fan_loop_network_uncertainty_report(result)
    assert "Fan/Loop-Network Uncertainty Report" in text
    assert "Bounded corner envelope" in text
    assert "Corner results" in text
    assert "Provenance complete for bounded inputs: **yes**" in text
