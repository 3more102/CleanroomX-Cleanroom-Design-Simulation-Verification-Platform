import json
import sys

import pytest

from cleanroomx.fan_variable_friction_loop import (
    solve_fan_variable_friction_loop,
)
from cleanroomx.fan_variable_friction_loop_io import (
    load_fan_variable_friction_loop_study,
)
from cleanroomx.fan_variable_friction_uncertainty import (
    FanVariableFrictionLoopUncertaintyStudy,
    analyze_fan_variable_friction_loop_uncertainty,
)
from cleanroomx.fan_variable_friction_uncertainty_models import (
    FanVariableFrictionLoopUncertaintyStudy as CompatibilityStudy,
)
from cleanroomx.fan_variable_friction_uncertainty_cli import (
    main as fan_variable_friction_uncertainty_main,
)
from cleanroomx.fan_variable_friction_uncertainty_io import (
    fan_variable_friction_loop_uncertainty_from_dict,
    load_fan_variable_friction_loop_uncertainty,
)
from cleanroomx.fan_variable_friction_uncertainty_report import (
    markdown_fan_variable_friction_loop_uncertainty_report,
)


def _example_data() -> dict:
    return json.loads(
        open(
            "examples/fan_variable_friction_uncertainty_demo.json",
            encoding="utf-8",
        ).read()
    )


def test_example_produces_complete_bounded_corner_envelope() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_uncertainty_demo.json"
        )
    )

    assert result["status"] == "complete"
    assert result["nominal_status"] == "solved"
    assert result["corner_count"] == 8
    assert result["solved_corner_count"] == 8
    assert result["unresolved_corner_count"] == 0
    assert result["traceability"]["complete"] is True
    assert result["operating_point_envelope"] is not None
    assert result["edge_airflow_corner_ranges"] is not None
    assert all(corner["status"] == "solved" for corner in result["corners"])
    assert {
        tuple(sorted(corner["edge_local_loss_coefficient"]))
        for corner in result["corners"]
    } == {("Direct", "Upper 1")}


def test_nominal_result_matches_existing_nonlinear_solver() -> None:
    uncertainty = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_uncertainty_demo.json"
        )
    )
    baseline = solve_fan_variable_friction_loop(
        load_fan_variable_friction_loop_study(
            "examples/fan_variable_friction_loop_demo.json"
        )
    )

    assert uncertainty["nominal_status"] == baseline["status"] == "solved"
    assert uncertainty["nominal_operating_point"]["airflow_m3_h"] == pytest.approx(
        baseline["fan_operating_point"]["airflow_m3_h"],
        abs=1e-6,
    )
    assert uncertainty["nominal_operating_point"]["system_pressure_pa"] == pytest.approx(
        baseline["fan_operating_point"]["system_pressure_pa"],
        abs=1e-6,
    )


def test_unresolved_corners_do_not_emit_complete_envelope() -> None:
    data = _example_data()
    data["fixed_pressure_pa"] = {
        "value": 900.0,
        "uncertainty_abs": 0.0,
    }
    result = analyze_fan_variable_friction_loop_uncertainty(
        fan_variable_friction_loop_uncertainty_from_dict(data)
    )

    assert result["status"] == "indeterminate"
    assert result["nominal_status"] == "no_intersection_in_supplied_range"
    assert result["unresolved_corner_count"] == result["corner_count"]
    assert result["operating_point_envelope"] is None
    assert result["edge_airflow_corner_ranges"] is None


def test_network_nonconvergence_is_preserved_as_indeterminate() -> None:
    data = _example_data()
    data["fixed_pressure_pa"] = 20.0
    data["edge_local_loss_uncertainty"] = {}
    data["solver"]["max_outer_iterations"] = 1
    data["solver"]["resistance_relative_tolerance"] = 1e-12

    result = analyze_fan_variable_friction_loop_uncertainty(
        fan_variable_friction_loop_uncertainty_from_dict(data)
    )

    assert result["status"] == "indeterminate"
    assert result["nominal_status"] == "non_converged"
    assert result["corner_count"] == 1
    assert result["corners"][0]["status"] == "non_converged"
    assert result["operating_point_envelope"] is None


def test_corner_limit_is_enforced_without_silent_truncation() -> None:
    data = _example_data()
    data["max_corner_cases"] = 4
    study = fan_variable_friction_loop_uncertainty_from_dict(data)

    with pytest.raises(ValueError, match="corner count 8"):
        analyze_fan_variable_friction_loop_uncertainty(study)


def test_local_loss_uncertainty_rejects_non_geometry_edge() -> None:
    data = _example_data()
    data["loop_network"]["edges"][0] = {
        "name": "Direct",
        "start_node": "Supply",
        "end_node": "Return",
        "resistance_pa_per_m3_s_squared": 500.0,
    }

    with pytest.raises(ValueError, match="no local-loss geometry evidence"):
        fan_variable_friction_loop_uncertainty_from_dict(data)


def test_markdown_report_and_cli_surface_corner_evidence(
    monkeypatch,
    capsys,
) -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_uncertainty_demo.json"
        )
    )
    report = markdown_fan_variable_friction_loop_uncertainty_report(result)
    assert "Variable-Friction Loop Uncertainty Report" in report
    assert "Local-loss K values" in report
    assert "Solved corners" in report

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cleanroomx-fan-loop-friction-uncertainty",
            "examples/fan_variable_friction_uncertainty_demo.json",
            "--format",
            "json",
        ],
    )
    assert fan_variable_friction_uncertainty_main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "complete"
    assert payload["corner_count"] == 8


def test_physical_darcy_input_uncertainty_produces_complete_envelope() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_physical_uncertainty_demo.json"
        )
    )

    assert result["status"] == "complete"
    assert result["nominal_status"] == "solved"
    assert result["corner_count"] == 8
    assert result["solved_corner_count"] == 8
    assert result["unresolved_corner_count"] == 0
    assert result["traceability"]["complete"] is True
    assert result["operating_point_envelope"] is not None
    assert result["operating_point_envelope"]["airflow_m3_h"]["lower"] < (
        result["operating_point_envelope"]["airflow_m3_h"]["upper"]
    )
    assert set(result["input_intervals"]["edge_absolute_roughness_m"]) == {
        "Direct"
    }
    assert set(
        result["input_intervals"]["edge_kinematic_viscosity_m2_s"]
    ) == {"Direct"}
    assert set(result["input_intervals"]["edge_air_density_kg_m3"]) == {
        "Direct"
    }
    assert all(
        set(corner["edge_absolute_roughness_m"]) == {"Direct"}
        and set(corner["edge_kinematic_viscosity_m2_s"]) == {"Direct"}
        and set(corner["edge_air_density_kg_m3"]) == {"Direct"}
        for corner in result["corners"]
    )


def test_physical_uncertainty_nominal_matches_existing_nonlinear_solver() -> None:
    uncertainty = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_physical_uncertainty_demo.json"
        )
    )
    baseline = solve_fan_variable_friction_loop(
        load_fan_variable_friction_loop_study(
            "examples/fan_variable_friction_loop_demo.json"
        )
    )

    assert uncertainty["nominal_status"] == baseline["status"] == "solved"
    assert uncertainty["nominal_operating_point"]["airflow_m3_h"] == pytest.approx(
        baseline["fan_operating_point"]["airflow_m3_h"], abs=1e-6
    )
    assert uncertainty["nominal_operating_point"]["system_pressure_pa"] == pytest.approx(
        baseline["fan_operating_point"]["system_pressure_pa"], abs=1e-6
    )


@pytest.mark.parametrize(
    ("block_name", "uncertainty_abs", "message"),
    [
        (
            "edge_absolute_roughness_uncertainty",
            0.5,
            "lower uncertainty bound",
        ),
        (
            "edge_kinematic_viscosity_uncertainty",
            0.00002,
            "lower uncertainty bound",
        ),
        (
            "edge_air_density_uncertainty",
            2.0,
            "lower uncertainty bound",
        ),
    ],
)
def test_physical_uncertainty_rejects_nonphysical_bounds(
    block_name,
    uncertainty_abs,
    message,
) -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_physical_uncertainty_demo.json",
            encoding="utf-8",
        ).read()
    )
    data[block_name]["Direct"]["uncertainty_abs"] = uncertainty_abs
    with pytest.raises(ValueError, match=message):
        fan_variable_friction_loop_uncertainty_from_dict(data)



def test_physical_uncertainty_rejects_roughness_above_hydraulic_diameter() -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_physical_uncertainty_demo.json",
            encoding="utf-8",
        ).read()
    )
    data["loop_network"]["edges"][0]["duct_geometry"][
        "absolute_roughness_m"
    ] = 0.3
    data["edge_absolute_roughness_uncertainty"]["Direct"][
        "uncertainty_abs"
    ] = 0.16
    with pytest.raises(ValueError, match="smaller than the hydraulic diameter"):
        fan_variable_friction_loop_uncertainty_from_dict(data)


def test_physical_uncertainty_rejects_repeated_nominal_value() -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_physical_uncertainty_demo.json",
            encoding="utf-8",
        ).read()
    )
    data["edge_air_density_uncertainty"]["Direct"]["value"] = 1.2
    with pytest.raises(ValueError, match="must not repeat the nominal"):
        fan_variable_friction_loop_uncertainty_from_dict(data)


def test_physical_uncertainty_report_surfaces_all_bounded_inputs() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_physical_uncertainty_demo.json"
        )
    )
    report = markdown_fan_variable_friction_loop_uncertainty_report(result)
    assert "Absolute roughness" in report
    assert "Kinematic viscosity" in report
    assert "Air density" in report
    assert "Physical-input values" in report


def test_uncertainty_model_compatibility_export_is_canonical() -> None:
    assert CompatibilityStudy is FanVariableFrictionLoopUncertaintyStudy
