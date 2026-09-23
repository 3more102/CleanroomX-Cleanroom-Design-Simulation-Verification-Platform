import pytest

from cleanroomx.fan_control import (
    FanSpeedControlStudy,
    analyze_fan_speed_control,
    scale_fan_curve_for_speed,
)
from cleanroomx.fan_control_io import fan_speed_control_study_from_dict
from cleanroomx.fan_control_report import markdown_fan_speed_control_report
from cleanroomx.fan_curve import FanCurve, FanCurvePoint, SystemCurve


def _curve() -> FanCurve:
    return FanCurve(
        "Reference supply fan",
        (
            FanCurvePoint(0, 600),
            FanCurvePoint(3000, 500),
            FanCurvePoint(6000, 300),
            FanCurvePoint(8000, 100),
        ),
    )


def _system() -> SystemCurve:
    return SystemCurve(
        "Reference duct system",
        fixed_pressure_pa=80,
        resistance_pa_per_m3_s_squared=100,
    )


def test_speed_scaling_follows_affinity_flow_and_pressure_relations() -> None:
    scaled = scale_fan_curve_for_speed(_curve(), 0.8)

    assert [point.airflow_m3_h for point in scaled.points] == [
        0,
        2400,
        4800,
        6400,
    ]
    assert [point.pressure_pa for point in scaled.points] == pytest.approx(
        [384, 320, 192, 64]
    )


def test_speed_sweep_solves_each_scaled_curve_and_tracks_discrete_target() -> None:
    result = analyze_fan_speed_control(
        FanSpeedControlStudy(
            name="VFD sweep",
            reference_fan_curve=_curve(),
            system_curve=_system(),
            speed_ratios=(0.8, 1.0, 1.1),
            reference_speed_rpm=1450,
            required_airflow_m3_h=5000,
        )
    )

    assert result["status"] == "target_met_in_tested_scenarios"
    assert result["solved_scenario_count"] == 3
    assert result["unresolved_scenario_count"] == 0
    assert result["scenarios"][0]["operating_point"]["airflow_m3_h"] == pytest.approx(
        4266.483, abs=0.001
    )
    assert result["scenarios"][1]["operating_point"]["airflow_m3_h"] == pytest.approx(
        5630.598, abs=0.001
    )
    assert result["scenarios"][2]["speed_rpm"] == pytest.approx(1595.0)
    assert result["target_summary"][
        "lowest_tested_speed_ratio_meeting_requirement"
    ] == 1.0
    assert result["target_summary"][
        "lowest_tested_speed_rpm_meeting_requirement"
    ] == 1450.0


def test_low_speed_no_intersection_remains_bounded_without_extrapolation() -> None:
    result = analyze_fan_speed_control(
        FanSpeedControlStudy(
            name="Low-speed sweep",
            reference_fan_curve=_curve(),
            system_curve=_system(),
            speed_ratios=(0.3, 1.0),
        )
    )

    assert result["status"] == "complete_with_unresolved_scenarios"
    assert result["unresolved_scenario_count"] == 1
    assert result["scenarios"][0]["status"] == "no_intersection_in_supplied_range"
    assert result["scenarios"][0]["operating_point"] is None
    assert "lower-flow extrapolation" in result["scenarios"][0]["message"]
    assert result["scenarios"][1]["status"] == "solved"


def test_target_not_met_is_reported_only_against_tested_speed_scenarios() -> None:
    result = analyze_fan_speed_control(
        FanSpeedControlStudy(
            name="Target sweep",
            reference_fan_curve=_curve(),
            system_curve=_system(),
            speed_ratios=(0.6, 0.8),
            required_airflow_m3_h=5000,
        )
    )

    assert result["status"] == "target_not_met_in_tested_scenarios"
    assert result["target_summary"]["status"] == "not_met_in_tested_scenarios"
    assert result["target_summary"][
        "lowest_tested_speed_ratio_meeting_requirement"
    ] is None


@pytest.mark.parametrize("bad", [0, -0.1, float("nan"), float("inf")])
def test_invalid_speed_ratios_are_rejected(bad: float) -> None:
    with pytest.raises(ValueError, match="speed_ratio"):
        FanSpeedControlStudy(
            "Bad",
            _curve(),
            _system(),
            (bad,),
        )


def test_duplicate_ratios_and_invalid_reference_speed_are_rejected() -> None:
    with pytest.raises(ValueError, match="unique"):
        FanSpeedControlStudy(
            "Duplicate",
            _curve(),
            _system(),
            (1.0, 1.0),
        )

    with pytest.raises(ValueError, match="reference_speed_rpm"):
        FanSpeedControlStudy(
            "Bad rpm",
            _curve(),
            _system(),
            (1.0,),
            reference_speed_rpm=0,
        )


def test_json_loader_builds_speed_control_study() -> None:
    study = fan_speed_control_study_from_dict(
        {
            "name": "Loaded",
            "reference_speed_rpm": 1450,
            "required_airflow_m3_h": 5000,
            "speed_ratios": [0.8, 1.0],
            "reference_fan_curve": {
                "name": "Fan",
                "points": [
                    {"airflow_m3_h": 0, "pressure_pa": 600},
                    {"airflow_m3_h": 6000, "pressure_pa": 300},
                ],
            },
            "system_curve": {
                "name": "System",
                "fixed_pressure_pa": 80,
                "resistance_pa_per_m3_s_squared": 100,
            },
        }
    )

    assert study.name == "Loaded"
    assert study.reference_speed_rpm == 1450
    assert study.speed_ratios == (0.8, 1.0)
    assert study.required_airflow_m3_h == 5000


def test_markdown_report_contains_scenario_and_scope_evidence() -> None:
    result = analyze_fan_speed_control(
        FanSpeedControlStudy(
            "Report",
            _curve(),
            _system(),
            (0.8, 1.0),
            reference_speed_rpm=1450,
            required_airflow_m3_h=5000,
        )
    )
    text = markdown_fan_speed_control_report(result)

    assert "Fan-Speed Control Study" in text
    assert "Speed scenarios" in text
    assert "Airflow target screening" in text
    assert "manufacturer-approved limits" in text
