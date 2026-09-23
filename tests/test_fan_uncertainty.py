import pytest

from cleanroomx.fan_uncertainty import analyze_fan_system_uncertainty
from cleanroomx.fan_uncertainty_io import fan_system_uncertainty_from_dict
from cleanroomx.fan_uncertainty_report import markdown_fan_system_uncertainty_report


def _data() -> dict:
    return {
        "name": "Fan uncertainty",
        "fan_curve": {
            "name": "Supply fan",
            "provenance": {
                "source_type": "manufacturer_data",
                "source_name": "Fan schedule",
                "reference": "FAN-001",
            },
            "points": [
                {"airflow_m3_h": 0, "pressure_pa": 600},
                {"airflow_m3_h": 3000, "pressure_pa": 500},
                {"airflow_m3_h": 6000, "pressure_pa": 300},
                {"airflow_m3_h": 8000, "pressure_pa": 100},
            ],
        },
        "system_curve": {
            "name": "System",
            "fixed_pressure_pa": {
                "value": 80,
                "uncertainty_abs": 20,
                "provenance": {
                    "source_type": "design",
                    "source_name": "Fixed pressure basis",
                },
            },
            "resistance_pa_per_m3_s_squared": {
                "value": 100,
                "uncertainty_abs": 20,
                "provenance": {
                    "source_type": "design",
                    "source_name": "Resistance basis",
                },
            },
        },
    }


def test_complete_corner_envelope_is_reported() -> None:
    result = analyze_fan_system_uncertainty(
        fan_system_uncertainty_from_dict(_data())
    )

    assert result["status"] == "complete"
    assert result["corner_count"] == 4
    assert result["solved_corner_count"] == 4
    assert result["unresolved_corner_count"] == 0
    assert result["nominal_operating_point"]["airflow_m3_h"] == pytest.approx(
        5630.598, abs=0.001
    )

    envelope = result["operating_point_envelope"]
    assert envelope is not None
    assert envelope["airflow_m3_h"]["lower"] == pytest.approx(
        5218.163074, abs=1e-6
    )
    assert envelope["airflow_m3_h"]["upper"] == pytest.approx(
        6101.760454, abs=1e-6
    )
    assert envelope["system_pressure_pa"]["lower"] == pytest.approx(
        289.823955, abs=1e-6
    )
    assert envelope["system_pressure_pa"]["upper"] == pytest.approx(
        352.122462, abs=1e-6
    )
    assert result["traceability"]["complete"] is True


def test_unsolved_corner_makes_result_indeterminate_and_withholds_envelope() -> None:
    data = _data()
    data["system_curve"]["fixed_pressure_pa"]["value"] = 500
    data["system_curve"]["fixed_pressure_pa"]["uncertainty_abs"] = 200

    result = analyze_fan_system_uncertainty(
        fan_system_uncertainty_from_dict(data)
    )

    assert result["status"] == "indeterminate"
    assert result["unresolved_corner_count"] >= 1
    assert result["operating_point_envelope"] is None
    assert any(
        item["status"] == "no_intersection_in_supplied_range"
        for item in result["corners"]
    )


def test_resistance_interval_must_remain_positive() -> None:
    data = _data()
    data["system_curve"]["resistance_pa_per_m3_s_squared"] = {
        "value": 10,
        "uncertainty_abs": 10,
    }
    with pytest.raises(ValueError, match="lower uncertainty bound"):
        fan_system_uncertainty_from_dict(data)


def test_missing_provenance_is_separate_from_numerical_status() -> None:
    data = _data()
    del data["fan_curve"]["provenance"]
    del data["system_curve"]["fixed_pressure_pa"]["provenance"]

    result = analyze_fan_system_uncertainty(
        fan_system_uncertainty_from_dict(data)
    )

    assert result["status"] == "complete"
    assert result["traceability"]["complete"] is False
    assert "fan_curve" in result["traceability"]["missing_provenance"]
    assert "fixed_pressure_pa" in result["traceability"]["missing_provenance"]


def test_markdown_report_contains_envelope_and_corner_table() -> None:
    result = analyze_fan_system_uncertainty(
        fan_system_uncertainty_from_dict(_data())
    )
    text = markdown_fan_system_uncertainty_report(result)

    assert "Bounded operating-point envelope" in text
    assert "Corner results" in text
    assert "Provenance complete: **yes**" in text
