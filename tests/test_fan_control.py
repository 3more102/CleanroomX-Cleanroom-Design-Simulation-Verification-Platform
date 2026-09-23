import pytest

from cleanroomx.fan_control import (
    FanControlState,
    FanControlStudy,
    analyze_fan_control_study,
)
from cleanroomx.fan_control_io import fan_control_study_from_dict
from cleanroomx.fan_control_report import markdown_fan_control_report
from cleanroomx.fan_curve import FanCurve, FanCurvePoint, SystemCurve


def _curve(name: str, airflow_m3_h: float, pressure_pa: float) -> FanCurve:
    return FanCurve(
        name,
        (
            FanCurvePoint(0.0, pressure_pa + 200.0),
            FanCurvePoint(airflow_m3_h, pressure_pa),
        ),
    )


def test_explicit_control_states_solve_and_hit_target_band() -> None:
    system = SystemCurve(
        "System",
        fixed_pressure_pa=0.0,
        resistance_pa_per_m3_s_squared=100.0,
    )
    study = FanControlStudy(
        "Three-state study",
        system_curve=system,
        states=(
            FanControlState("Low", 40.0, _curve("Low curve", 3600.0, 100.0)),
            FanControlState("Mid", 60.0, _curve("Mid curve", 5400.0, 225.0)),
            FanControlState("High", 80.0, _curve("High curve", 7200.0, 400.0)),
        ),
        target_airflow_m3_h=5400.0,
        target_tolerance_m3_h=100.0,
    )

    result = analyze_fan_control_study(study)

    assert result["analysis_status"] == "screening_complete"
    assert result["target_status"] == "target_met"
    assert result["target_band_m3_h"] == [5300.0, 5500.0]
    assert result["response_monotonic_non_decreasing"] is True
    assert result["unresolved_state_count"] == 0
    assert result["closest_solved_state"]["state"] == "Mid"
    assert [item["target_status"] for item in result["states"]] == [
        "below_target_band",
        "within_target_band",
        "above_target_band",
    ]


def test_unresolved_state_is_preserved_as_attention() -> None:
    system = SystemCurve(
        "System",
        fixed_pressure_pa=100.0,
        resistance_pa_per_m3_s_squared=100.0,
    )
    study = FanControlStudy(
        "Unresolved",
        system_curve=system,
        states=(
            FanControlState(
                "Too weak",
                20.0,
                FanCurve(
                    "Weak curve",
                    (
                        FanCurvePoint(0.0, 50.0),
                        FanCurvePoint(1000.0, 40.0),
                    ),
                ),
            ),
            FanControlState(
                "Solved",
                80.0,
                FanCurve(
                    "Strong curve",
                    (
                        FanCurvePoint(0.0, 500.0),
                        FanCurvePoint(3600.0, 200.0),
                    ),
                ),
            ),
        ),
        target_airflow_m3_h=3600.0,
    )

    result = analyze_fan_control_study(study)

    assert result["analysis_status"] == "attention_required"
    assert result["unresolved_state_count"] == 1
    assert result["states"][0]["status"] == "no_intersection_in_supplied_range"
    assert result["states"][0]["target_status"] == "not_comparable"
    assert result["states"][1]["target_status"] == "within_target_band"


def test_nonmonotonic_explicit_response_is_flagged() -> None:
    system = SystemCurve(
        "System",
        fixed_pressure_pa=0.0,
        resistance_pa_per_m3_s_squared=100.0,
    )
    study = FanControlStudy(
        "Nonmonotonic",
        system_curve=system,
        states=(
            FanControlState("First", 40.0, _curve("Higher curve", 7200.0, 400.0)),
            FanControlState("Second", 80.0, _curve("Lower curve", 3600.0, 100.0)),
        ),
    )

    result = analyze_fan_control_study(study)

    assert result["analysis_status"] == "attention_required"
    assert result["target_status"] == "not_checked"
    assert result["response_monotonic_non_decreasing"] is False


def test_loader_and_markdown_report() -> None:
    study = fan_control_study_from_dict(
        {
            "name": "Loaded",
            "system_curve": {
                "name": "System",
                "fixed_pressure_pa": 0,
                "resistance_pa_per_m3_s_squared": 100,
            },
            "target_airflow_m3_h": 5400,
            "target_tolerance_m3_h": 100,
            "states": [
                {
                    "name": "Low",
                    "control_signal_percent": 40,
                    "fan_curve": {
                        "name": "Low curve",
                        "points": [
                            {"airflow_m3_h": 0, "pressure_pa": 300},
                            {"airflow_m3_h": 3600, "pressure_pa": 100},
                        ],
                    },
                },
                {
                    "name": "Mid",
                    "control_signal_percent": 60,
                    "fan_curve": {
                        "name": "Mid curve",
                        "points": [
                            {"airflow_m3_h": 0, "pressure_pa": 425},
                            {"airflow_m3_h": 5400, "pressure_pa": 225},
                        ],
                    },
                },
            ],
        }
    )

    result = analyze_fan_control_study(study)
    text = markdown_fan_control_report(result)

    assert study.states[1].control_signal_percent == 60
    assert "Fan-Control Study" in text
    assert "Target band" in text
    assert "| Mid | 60.0 | solved | 5400.0 | 225.0 | within_target_band |" in text


def test_control_state_validation() -> None:
    system = SystemCurve("System", 0, 100)
    curve = _curve("Curve", 3600, 100)

    with pytest.raises(ValueError, match="between 0 and 100"):
        FanControlState("Bad", 101, curve)

    with pytest.raises(ValueError, match="strictly increasing"):
        FanControlStudy(
            "Bad order",
            system,
            (
                FanControlState("A", 60, curve),
                FanControlState("B", 40, curve),
            ),
        )

    with pytest.raises(ValueError, match="requires target_airflow"):
        FanControlStudy(
            "Bad tolerance",
            system,
            (
                FanControlState("A", 40, curve),
                FanControlState("B", 60, curve),
            ),
            target_tolerance_m3_h=10,
        )
