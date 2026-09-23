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
    assert result["power_corner_ranges"] is None


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

def test_geometry_input_uncertainty_produces_complete_envelope() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_geometry_uncertainty_demo.json"
        )
    )

    assert result["status"] == "complete"
    assert result["nominal_status"] == "solved"
    assert result["corner_count"] == 4
    assert result["solved_corner_count"] == 4
    assert result["unresolved_corner_count"] == 0
    assert result["traceability"]["complete"] is True
    assert result["operating_point_envelope"] is not None
    assert result["operating_point_envelope"]["airflow_m3_h"]["lower"] < (
        result["operating_point_envelope"]["airflow_m3_h"]["upper"]
    )
    assert set(result["input_intervals"]["edge_length_m"]) == {"Direct"}
    assert set(result["input_intervals"]["edge_circular_diameter_m"]) == {
        "Direct"
    }
    assert all(
        set(corner["edge_length_m"]) == {"Direct"}
        and set(corner["edge_circular_diameter_m"]) == {"Direct"}
        for corner in result["corners"]
    )


def test_geometry_uncertainty_report_surfaces_length_and_diameter() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_geometry_uncertainty_demo.json"
        )
    )
    report = markdown_fan_variable_friction_loop_uncertainty_report(result)
    assert "Duct length" in report
    assert "Circular diameter" in report
    assert "Direct length=" in report
    assert "Direct diameter=" in report


def test_geometry_uncertainty_rejects_nonpositive_length_bound() -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_geometry_uncertainty_demo.json",
            encoding="utf-8",
        ).read()
    )
    data["edge_length_uncertainty"]["Direct"]["uncertainty_abs"] = 18.0
    with pytest.raises(ValueError, match="length lower uncertainty bound"):
        fan_variable_friction_loop_uncertainty_from_dict(data)


def test_circular_diameter_uncertainty_rejects_rectangular_edge() -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_geometry_uncertainty_demo.json",
            encoding="utf-8",
        ).read()
    )
    geometry = data["loop_network"]["edges"][0]["duct_geometry"]
    geometry.pop("diameter_m")
    geometry["width_m"] = 0.6
    geometry["height_m"] = 0.3
    with pytest.raises(ValueError, match="requires circular duct geometry"):
        fan_variable_friction_loop_uncertainty_from_dict(data)


def test_circular_diameter_bound_must_exceed_bounded_roughness() -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_geometry_uncertainty_demo.json",
            encoding="utf-8",
        ).read()
    )
    data["edge_circular_diameter_uncertainty"]["Direct"][
        "uncertainty_abs"
    ] = 0.4499
    with pytest.raises(
        ValueError,
        match="must remain larger than the maximum bounded absolute roughness",
    ):
        fan_variable_friction_loop_uncertainty_from_dict(data)


def test_geometry_uncertainty_rejects_repeated_nominal_value() -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_geometry_uncertainty_demo.json",
            encoding="utf-8",
        ).read()
    )
    data["edge_length_uncertainty"]["Direct"]["value"] = 18.0
    with pytest.raises(ValueError, match="must not repeat the nominal length"):
        fan_variable_friction_loop_uncertainty_from_dict(data)

def test_rectangular_geometry_uncertainty_produces_complete_envelope() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_rectangular_uncertainty_demo.json"
        )
    )

    assert result["status"] == "complete"
    assert result["nominal_status"] == "solved"
    assert result["corner_count"] == 8
    assert result["solved_corner_count"] == 8
    assert result["unresolved_corner_count"] == 0
    assert result["traceability"]["complete"] is True
    assert result["operating_point_envelope"] is not None
    assert result["input_intervals"]["edge_rectangular_width_m"]["Direct"][
        "nominal"
    ] == pytest.approx(0.5)
    assert result["input_intervals"]["edge_rectangular_height_m"]["Direct"][
        "nominal"
    ] == pytest.approx(0.35)
    assert all(
        set(corner["edge_rectangular_width_m"]) == {"Direct"}
        and set(corner["edge_rectangular_height_m"]) == {"Direct"}
        for corner in result["corners"]
    )


def test_rectangular_geometry_uncertainty_report_surfaces_dimensions() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_rectangular_uncertainty_demo.json"
        )
    )
    report = markdown_fan_variable_friction_loop_uncertainty_report(result)
    assert "Rectangular width" in report
    assert "Rectangular height" in report
    assert "Direct width=" in report
    assert "Direct height=" in report


def test_rectangular_width_uncertainty_rejects_circular_edge() -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_geometry_uncertainty_demo.json",
            encoding="utf-8",
        ).read()
    )
    data["edge_rectangular_width_uncertainty"] = {
        "Direct": {"uncertainty_abs": 0.01}
    }
    with pytest.raises(ValueError, match="no rectangular-width geometry evidence"):
        fan_variable_friction_loop_uncertainty_from_dict(data)


def test_rectangular_dimension_bounds_respect_roughness_limit() -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_rectangular_uncertainty_demo.json",
            encoding="utf-8",
        ).read()
    )
    data["edge_rectangular_width_uncertainty"]["Direct"][
        "uncertainty_abs"
    ] = 0.49995
    with pytest.raises(
        ValueError,
        match="must keep hydraulic diameter larger than the maximum bounded",
    ):
        fan_variable_friction_loop_uncertainty_from_dict(data)

def test_fan_curve_pressure_uncertainty_produces_complete_envelope() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_fan_curve_uncertainty_demo.json"
        )
    )

    assert result["status"] == "complete"
    assert result["nominal_status"] == "solved"
    assert result["corner_count"] == 4
    assert result["solved_corner_count"] == 4
    assert result["unresolved_corner_count"] == 0
    assert result["traceability"]["complete"] is True
    assert result["operating_point_envelope"] is not None
    assert set(result["input_intervals"]["fan_curve_pressure_pa"]) == {
        "0.0",
        "5400.0",
    }
    assert all(
        set(corner["fan_curve_pressure_pa"]) == {"0.0", "5400.0"}
        for corner in result["corners"]
    )


def test_fan_curve_pressure_uncertainty_report_surfaces_point_bounds() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_fan_curve_uncertainty_demo.json"
        )
    )
    report = markdown_fan_variable_friction_loop_uncertainty_report(result)
    assert "Fan pressure at `0.0 m³/h`" in report
    assert "Fan pressure at `5400.0 m³/h`" in report
    assert "Fan-point pressures Pa" in report


def test_fan_curve_pressure_uncertainty_rejects_negative_pressure_bound() -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_fan_curve_uncertainty_demo.json",
            encoding="utf-8",
        ).read()
    )
    data["fan_curve_pressure_uncertainty"][1]["uncertainty_abs"] = 400.0
    with pytest.raises(ValueError, match="lower uncertainty bound"):
        fan_variable_friction_loop_uncertainty_from_dict(data)


def test_fan_curve_pressure_uncertainty_rejects_nonmonotonic_corner() -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_fan_curve_uncertainty_demo.json",
            encoding="utf-8",
        ).read()
    )
    data["fan_curve_pressure_uncertainty"][0]["uncertainty_abs"] = 460.0
    with pytest.raises(ValueError, match="pressure increase with airflow"):
        fan_variable_friction_loop_uncertainty_from_dict(data)


def test_fan_curve_pressure_uncertainty_rejects_unknown_airflow_point() -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_fan_curve_uncertainty_demo.json",
            encoding="utf-8",
        ).read()
    )
    data["fan_curve_pressure_uncertainty"][0]["airflow_m3_h"] = 1234.0
    with pytest.raises(ValueError, match="unknown supplied airflow point"):
        fan_variable_friction_loop_uncertainty_from_dict(data)


def test_fan_curve_pressure_uncertainty_rejects_repeated_nominal() -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_fan_curve_uncertainty_demo.json",
            encoding="utf-8",
        ).read()
    )
    data["fan_curve_pressure_uncertainty"][0]["pressure_pa"] = 800.0
    with pytest.raises(ValueError, match="must not repeat the nominal"):
        fan_variable_friction_loop_uncertainty_from_dict(data)

def test_fan_curve_airflow_uncertainty_produces_complete_envelope() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_fan_airflow_uncertainty_demo.json"
        )
    )

    assert result["status"] == "complete"
    assert result["nominal_status"] == "solved"
    assert result["corner_count"] == 4
    assert result["solved_corner_count"] == 4
    assert result["unresolved_corner_count"] == 0
    assert result["traceability"]["complete"] is True
    assert result["operating_point_envelope"] is not None
    assert set(result["input_intervals"]["fan_curve_airflow_m3_h"]) == {
        "1",
        "2",
    }
    assert all(
        set(corner["fan_curve_airflow_m3_h"]) == {"1", "2"}
        for corner in result["corners"]
    )


def test_fan_curve_airflow_uncertainty_report_surfaces_point_bounds() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_fan_airflow_uncertainty_demo.json"
        )
    )
    report = markdown_fan_variable_friction_loop_uncertainty_report(result)
    assert "Fan airflow at point index `1`" in report
    assert "Fan airflow at point index `2`" in report
    assert "Fan-point airflows m³/h" in report


def test_fan_curve_airflow_uncertainty_rejects_negative_bound() -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_fan_airflow_uncertainty_demo.json",
            encoding="utf-8",
        ).read()
    )
    data["fan_curve_airflow_uncertainty"][0]["uncertainty_abs"] = 6000.0
    with pytest.raises(ValueError, match="lower uncertainty bound"):
        fan_variable_friction_loop_uncertainty_from_dict(data)


def test_fan_curve_airflow_uncertainty_rejects_crossing_coordinates() -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_fan_airflow_uncertainty_demo.json",
            encoding="utf-8",
        ).read()
    )
    data["fan_curve_airflow_uncertainty"][0]["uncertainty_abs"] = 4000.0
    with pytest.raises(ValueError, match="non-increasing airflow coordinates"):
        fan_variable_friction_loop_uncertainty_from_dict(data)


def test_fan_curve_airflow_uncertainty_rejects_unknown_point_index() -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_fan_airflow_uncertainty_demo.json",
            encoding="utf-8",
        ).read()
    )
    data["fan_curve_airflow_uncertainty"][0]["point_index"] = 99
    with pytest.raises(ValueError, match="point_index must identify"):
        fan_variable_friction_loop_uncertainty_from_dict(data)


def test_fan_curve_airflow_uncertainty_rejects_repeated_nominal() -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_fan_airflow_uncertainty_demo.json",
            encoding="utf-8",
        ).read()
    )
    data["fan_curve_airflow_uncertainty"][0]["airflow_m3_h"] = 5400.0
    with pytest.raises(ValueError, match="must not repeat the nominal"):
        fan_variable_friction_loop_uncertainty_from_dict(data)



def test_corner_limit_rejects_before_cartesian_product_materialization(
    monkeypatch,
) -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_fan_airflow_uncertainty_demo.json",
            encoding="utf-8",
        ).read()
    )
    data["max_corner_cases"] = 1
    study = fan_variable_friction_loop_uncertainty_from_dict(data)

    def _unexpected_product(*args, **kwargs):
        raise AssertionError("Cartesian product must not be materialized")

    monkeypatch.setattr(
        "cleanroomx.fan_variable_friction_uncertainty.product",
        _unexpected_product,
    )
    with pytest.raises(ValueError, match="corner count 4.*max_corner_cases=1"):
        analyze_fan_variable_friction_loop_uncertainty(study)

def test_fan_speed_ratio_uncertainty_produces_complete_envelope() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_speed_uncertainty_demo.json"
        )
    )

    assert result["status"] == "complete"
    assert result["nominal_status"] == "solved"
    assert result["corner_count"] == 2
    assert result["solved_corner_count"] == 2
    assert result["unresolved_corner_count"] == 0
    assert result["traceability"]["complete"] is True
    assert result["input_intervals"]["fan_speed_ratio"] == {
        "nominal": 1.0,
        "lower": 0.9,
        "upper": 1.1,
        "unit": "1",
    }
    assert {
        corner["fan_speed_ratio"] for corner in result["corners"]
    } == {0.9, 1.1}
    envelope = result["operating_point_envelope"]
    assert envelope is not None
    assert envelope["airflow_m3_h"]["lower"] < envelope["airflow_m3_h"]["upper"]


def test_fan_speed_ratio_uncertainty_report_surfaces_bounds() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_speed_uncertainty_demo.json"
        )
    )
    report = markdown_fan_variable_friction_loop_uncertainty_report(result)

    assert "Fan speed ratio" in report
    assert "0.9 to 1.1" in report
    assert "Speed ratio" in report


def test_fan_speed_ratio_uncertainty_rejects_nonpositive_lower_bound() -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_speed_uncertainty_demo.json",
            encoding="utf-8",
        ).read()
    )
    data["fan_speed_ratio"]["value"] = 0.1
    data["fan_speed_ratio"]["uncertainty_abs"] = 0.1

    with pytest.raises(ValueError, match="lower uncertainty bound must remain > 0"):
        fan_variable_friction_loop_uncertainty_from_dict(data)


def test_fan_speed_ratio_uncertainty_counts_toward_corner_limit() -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_speed_uncertainty_demo.json",
            encoding="utf-8",
        ).read()
    )
    data["max_corner_cases"] = 1
    study = fan_variable_friction_loop_uncertainty_from_dict(data)

    with pytest.raises(ValueError, match="corner count 2"):
        analyze_fan_variable_friction_loop_uncertainty(study)



def test_whole_fan_curve_scenarios_preserve_correlated_cases() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_curve_scenarios_demo.json"
        )
    )

    assert result["status"] == "complete"
    assert result["nominal_status"] == "solved"
    assert result["corner_count"] == 3
    assert result["solved_corner_count"] == 3
    assert result["unresolved_corner_count"] == 0
    assert result["traceability"]["complete"] is True
    assert result["operating_point_envelope"] is not None
    assert {
        corner["fan_curve_scenario"] for corner in result["corners"]
    } == {"nominal", "lower_envelope", "upper_envelope"}
    assert [scenario["name"] for scenario in result["fan_curve_scenarios"]] == [
        "lower_envelope",
        "upper_envelope",
    ]
    assert all(
        corner["fan_curve_pressure_pa"] == {}
        and corner["fan_curve_airflow_m3_h"] == {}
        for corner in result["corners"]
    )


def test_whole_fan_curve_scenario_report_surfaces_named_curves() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_curve_scenarios_demo.json"
        )
    )
    report = markdown_fan_variable_friction_loop_uncertainty_report(result)

    assert "Whole fan-curve scenarios" in report
    assert "lower_envelope" in report
    assert "upper_envelope" in report
    assert "Fan-curve scenario" in report


def test_whole_fan_curve_scenarios_combine_with_speed_ratio() -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_curve_scenarios_demo.json",
            encoding="utf-8",
        ).read()
    )
    data["fan_speed_ratio"] = {
        "value": 1.0,
        "uncertainty_abs": 0.05,
        "provenance": {
            "source_type": "design_basis",
            "source_name": "Illustrative speed-ratio interval",
        },
    }

    result = analyze_fan_variable_friction_loop_uncertainty(
        fan_variable_friction_loop_uncertainty_from_dict(data)
    )

    assert result["status"] == "complete"
    assert result["corner_count"] == 6
    assert {
        (corner["fan_curve_scenario"], corner["fan_speed_ratio"])
        for corner in result["corners"]
    } == {
        ("nominal", 0.95),
        ("nominal", 1.05),
        ("lower_envelope", 0.95),
        ("lower_envelope", 1.05),
        ("upper_envelope", 0.95),
        ("upper_envelope", 1.05),
    }


def test_whole_fan_curve_scenarios_reject_independent_point_bounds() -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_curve_scenarios_demo.json",
            encoding="utf-8",
        ).read()
    )
    data["fan_curve_pressure_uncertainty"] = [
        {"airflow_m3_h": 5400, "uncertainty_abs": 10}
    ]

    with pytest.raises(ValueError, match="cannot be combined with independent"):
        fan_variable_friction_loop_uncertainty_from_dict(data)


def test_whole_fan_curve_scenarios_reject_duplicate_names() -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_curve_scenarios_demo.json",
            encoding="utf-8",
        ).read()
    )
    data["fan_curve_scenarios"][1]["name"] = "lower_envelope"

    with pytest.raises(ValueError, match="duplicate fan-curve scenario name"):
        fan_variable_friction_loop_uncertainty_from_dict(data)


def test_whole_fan_curve_scenarios_reject_reserved_nominal_name() -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_curve_scenarios_demo.json",
            encoding="utf-8",
        ).read()
    )
    data["fan_curve_scenarios"][0]["name"] = "nominal"

    with pytest.raises(ValueError, match="name 'nominal' is reserved"):
        fan_variable_friction_loop_uncertainty_from_dict(data)


def test_whole_fan_curve_scenarios_count_toward_corner_limit() -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_curve_scenarios_demo.json",
            encoding="utf-8",
        ).read()
    )
    data["max_corner_cases"] = 2
    study = fan_variable_friction_loop_uncertainty_from_dict(data)

    with pytest.raises(ValueError, match="corner count 3"):
        analyze_fan_variable_friction_loop_uncertainty(study)

def test_power_evidence_is_retained_for_each_solved_corner() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_speed_uncertainty_demo.json"
        )
    )

    assert result["status"] == "complete"
    assert result["nominal_power_evidence"] is not None
    assert all(corner["power_evidence"] is not None for corner in result["corners"])
    assert all(
        corner["power_evidence"]["electrical_input_kw"] is not None
        for corner in result["corners"]
    )

    ranges = result["power_corner_ranges"]
    assert ranges is not None
    assert ranges["evaluated_corner_count"] == result["corner_count"]
    assert {
        "fluid_air_power_kw",
        "shaft_power_kw",
        "electrical_input_kw",
        "specific_fan_power_w_per_m3_s",
    } <= set(ranges["metrics"])
    assert (
        ranges["metrics"]["electrical_input_kw"]["lower"]
        < ranges["metrics"]["electrical_input_kw"]["upper"]
    )


def test_power_corner_ranges_do_not_infer_missing_efficiencies() -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_speed_uncertainty_demo.json",
            encoding="utf-8",
        ).read()
    )
    data.pop("power_efficiencies")

    result = analyze_fan_variable_friction_loop_uncertainty(
        fan_variable_friction_loop_uncertainty_from_dict(data)
    )

    ranges = result["power_corner_ranges"]
    assert ranges is not None
    assert set(ranges["metrics"]) == {"fluid_air_power_kw"}
    assert all(
        corner["power_evidence"]["shaft_power_kw"] is None
        and corner["power_evidence"]["electrical_input_kw"] is None
        for corner in result["corners"]
    )


def test_power_corner_report_is_explicitly_evaluated_only() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_speed_uncertainty_demo.json"
        )
    )
    report = markdown_fan_variable_friction_loop_uncertainty_report(result)

    assert "Evaluated power corner ranges" in report
    assert "Electrical input" in report
    assert "evaluated solved uncertainty corners only" in report
    assert "not claimed as guaranteed continuous-box power extrema" in report

