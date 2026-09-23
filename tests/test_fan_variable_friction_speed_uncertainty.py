import json
import sys

import pytest

from cleanroomx.fan_variable_friction_speed_uncertainty import (
    analyze_fan_variable_friction_speed_uncertainty,
)
from cleanroomx.fan_variable_friction_speed_uncertainty_cli import (
    main as fan_variable_friction_speed_uncertainty_main,
)
from cleanroomx.fan_variable_friction_speed_uncertainty_io import (
    fan_variable_friction_speed_uncertainty_from_dict,
    load_fan_variable_friction_speed_uncertainty,
)
from cleanroomx.fan_variable_friction_speed_uncertainty_report import (
    markdown_fan_variable_friction_speed_uncertainty_report,
)
from cleanroomx.fan_variable_friction_uncertainty import (
    analyze_fan_variable_friction_loop_uncertainty,
)
from cleanroomx.fan_variable_friction_uncertainty_io import (
    load_fan_variable_friction_loop_uncertainty,
)


def _data() -> dict:
    return json.loads(
        open(
            "examples/fan_variable_friction_speed_uncertainty_demo.json",
            encoding="utf-8",
        ).read()
    )


def test_example_completes_every_speed_and_uncertainty_corner() -> None:
    result = analyze_fan_variable_friction_speed_uncertainty(
        load_fan_variable_friction_speed_uncertainty(
            "examples/fan_variable_friction_speed_uncertainty_demo.json"
        )
    )

    assert result["status"] == "screening_complete"
    assert result["counts"] == {"complete": 2}
    assert result["speed_case_count"] == 2
    assert result["uncertainty_corner_count_per_speed"] == 8
    assert result["total_speed_corner_case_count"] == 16
    assert result["unresolved_speed_case_count"] == 0
    for case in result["speed_cases"]:
        assert case["status"] == "complete"
        assert case["corner_count"] == 8
        assert case["solved_corner_count"] == 8
        assert case["operating_point_envelope"] is not None
        assert case["traceability"]["complete"] is True


def test_reference_speed_case_matches_v037_uncertainty_analysis() -> None:
    sweep = analyze_fan_variable_friction_speed_uncertainty(
        load_fan_variable_friction_speed_uncertainty(
            "examples/fan_variable_friction_speed_uncertainty_demo.json"
        )
    )
    reference = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_uncertainty_demo.json"
        )
    )
    one_x = next(
        case for case in sweep["speed_cases"]
        if case["speed_ratio"] == 1.0
    )

    assert one_x["status"] == reference["status"] == "complete"
    assert one_x["corner_count"] == reference["corner_count"]
    assert one_x["operating_point_envelope"] == reference[
        "operating_point_envelope"
    ]
    assert one_x["edge_airflow_corner_ranges"] == reference[
        "edge_airflow_corner_ranges"
    ]


def test_low_speed_preserves_indeterminate_uncertainty_state() -> None:
    data = _data()
    data["speed_ratios"] = [0.1, 1.0]
    result = analyze_fan_variable_friction_speed_uncertainty(
        fan_variable_friction_speed_uncertainty_from_dict(data)
    )

    assert result["status"] == "attention_required"
    assert result["counts"]["indeterminate"] == 1
    low = result["speed_cases"][0]
    assert low["speed_ratio"] == 0.1
    assert low["status"] == "indeterminate"
    assert low["operating_point_envelope"] is None
    assert low["unresolved_corner_count"] == low["corner_count"]


def test_invalid_speed_and_total_case_limit_are_rejected() -> None:
    data = _data()
    data["speed_ratios"] = [1.0, 1.0]
    with pytest.raises(ValueError, match="speed ratios must be unique"):
        fan_variable_friction_speed_uncertainty_from_dict(data)

    data = _data()
    data["max_total_cases"] = 15
    study = fan_variable_friction_speed_uncertainty_from_dict(data)
    with pytest.raises(ValueError, match="total case count 16"):
        analyze_fan_variable_friction_speed_uncertainty(study)


def test_markdown_report_and_cli_surface_speed_corner_evidence(
    monkeypatch,
    capsys,
) -> None:
    result = analyze_fan_variable_friction_speed_uncertainty(
        load_fan_variable_friction_speed_uncertainty(
            "examples/fan_variable_friction_speed_uncertainty_demo.json"
        )
    )
    report = markdown_fan_variable_friction_speed_uncertainty_report(result)
    assert "Fan-Speed / Variable-Friction Uncertainty Study" in report
    assert "Speed × uncertainty summary" in report
    assert "Total speed × corner cases: **16**" in report

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cleanroomx-fan-loop-friction-speed-uncertainty",
            "examples/fan_variable_friction_speed_uncertainty_demo.json",
            "--format",
            "json",
        ],
    )
    assert fan_variable_friction_speed_uncertainty_main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "screening_complete"
    assert payload["total_speed_corner_case_count"] == 16
