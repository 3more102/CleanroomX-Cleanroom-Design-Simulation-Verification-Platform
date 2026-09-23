import hashlib
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
    FanCurveScenario,
    FanVariableFrictionLoopUncertaintyStudy,
    analyze_fan_variable_friction_loop_uncertainty,
)
from cleanroomx.fan_variable_friction_uncertainty_models import (
    FanCurveScenario as CompatibilityFanCurveScenario,
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


def test_result_integrity_sha256_is_recomputable_and_input_sensitive() -> None:
    study = load_fan_variable_friction_loop_uncertainty(
        "examples/fan_variable_friction_uncertainty_demo.json"
    )
    first = analyze_fan_variable_friction_loop_uncertainty(study)
    second = analyze_fan_variable_friction_loop_uncertainty(study)

    integrity = first["result_integrity"]
    assert integrity["algorithm"] == "sha256"
    assert integrity["canonicalization"] == "json-sort-keys-compact-utf8-v1"
    assert len(integrity["sha256"]) == 64
    assert second["result_integrity"]["sha256"] == integrity["sha256"]

    payload = dict(first)
    payload.pop("result_integrity")
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    assert hashlib.sha256(encoded).hexdigest() == integrity["sha256"]

    changed_data = _example_data()
    changed_data["fixed_pressure_pa"]["uncertainty_abs"] = 10.0
    changed = analyze_fan_variable_friction_loop_uncertainty(
        fan_variable_friction_loop_uncertainty_from_dict(changed_data)
    )
    assert changed["result_integrity"]["sha256"] != integrity["sha256"]

    report = markdown_fan_variable_friction_loop_uncertainty_report(first)
    assert "Result integrity" in report
    assert integrity["sha256"] in report


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
    assert result["operating_point_extreme_cases"] is None
    assert result["operating_point_extrema_sources"] is None
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
    assert CompatibilityFanCurveScenario is FanCurveScenario

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


def test_complete_envelope_extrema_reference_exact_corner_witnesses() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_curve_scenarios_demo.json"
        )
    )

    witnesses = result["operating_point_extreme_cases"]
    sources = result["operating_point_extrema_sources"]
    assert witnesses is not None
    assert sources is not None
    for metric in (
        "airflow_m3_h",
        "fan_pressure_pa",
        "system_pressure_pa",
        "air_power_kw",
    ):
        envelope = result["operating_point_envelope"][metric]
        metric_witnesses = witnesses[metric]
        metric_sources = sources[metric]
        for bound in ("lower", "upper"):
            witness = metric_witnesses[bound]
            corner = result["corners"][witness["corner_index"]]
            assert witness["value"] == pytest.approx(envelope[bound], abs=1e-6)
            assert corner["operating_point"][metric] == pytest.approx(
                witness["value"],
                abs=1e-6,
            )

            source_group = metric_sources[bound]
            assert source_group["value"] == pytest.approx(
                envelope[bound],
                abs=1e-6,
            )
            assert source_group["sources"]
            for source in source_group["sources"]:
                source_corner = result["corners"][source["corner_index"]]
                assert source_corner["operating_point"][metric] == pytest.approx(
                    source_group["value"],
                    abs=1e-6,
                )
                assert source["fixed_pressure_pa"] == source_corner[
                    "fixed_pressure_pa"
                ]
                assert source["fan_curve_scenario"] == source_corner[
                    "fan_curve_scenario"
                ]


def test_air_power_envelope_matches_exact_evaluated_corner_power() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_curve_scenarios_demo.json"
        )
    )

    envelope = result["operating_point_envelope"]["air_power_kw"]
    witnesses = result["operating_point_extreme_cases"]["air_power_kw"]
    sources = result["operating_point_extrema_sources"]["air_power_kw"]

    for bound in ("lower", "upper"):
        corner = result["corners"][witnesses[bound]["corner_index"]]
        point = corner["operating_point"]
        assert point is not None
        expected_kw = (
            point["airflow_m3_h"] / 3600.0 * point["system_pressure_pa"] / 1000.0
        )
        assert point["air_power_kw"] == pytest.approx(expected_kw, abs=1e-9)
        assert witnesses[bound]["value"] == pytest.approx(
            envelope[bound], abs=1e-6
        )
        assert sources[bound]["value"] == pytest.approx(
            envelope[bound], abs=1e-6
        )


def test_edge_airflow_ranges_reference_exact_corner_witnesses() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_curve_scenarios_demo.json"
        )
    )

    for edge_range in result["edge_airflow_corner_ranges"]:
        edge = edge_range["edge"]
        for bound, field in (
            ("lower", "lower_airflow_m3_h"),
            ("upper", "upper_airflow_m3_h"),
        ):
            corner = result["corners"][
                edge_range[f"{bound}_corner_index"]
            ]
            assert corner["edge_airflows_m3_h"][edge] == pytest.approx(
                edge_range[field],
                abs=1e-6,
            )


def test_uncertainty_report_surfaces_extreme_corner_witnesses() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_curve_scenarios_demo.json"
        )
    )
    report = markdown_fan_variable_friction_loop_uncertainty_report(result)

    assert "corner indices" in report
    assert "Envelope witness provenance" in report
    assert "Internal edge-airflow corner ranges" in report
    assert "Air power" in report
    assert "scenario=" in report


def test_operating_point_extrema_sources_reference_exact_corners() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_curve_scenarios_demo.json"
        )
    )

    envelope = result["operating_point_envelope"]
    sources = result["operating_point_extrema_sources"]
    assert envelope is not None
    assert sources is not None
    assert set(sources) == {
        "airflow_m3_h",
        "fan_pressure_pa",
        "system_pressure_pa",
        "air_power_kw",
    }

    for metric in sources:
        for bound in ("lower", "upper"):
            evidence = sources[metric][bound]
            assert evidence["value"] == pytest.approx(
                envelope[metric][bound]
            )
            assert evidence["sources"]
            for source in evidence["sources"]:
                corner = result["corners"][source["corner_index"]]
                assert corner["operating_point"] is not None
                assert corner["operating_point"][metric] == pytest.approx(
                    evidence["value"],
                    abs=1e-6,
                )
                assert source["fixed_pressure_pa"] == corner[
                    "fixed_pressure_pa"
                ]
                assert source.get("fan_curve_scenario") == corner.get(
                    "fan_curve_scenario"
                )
                assert source.get("fan_speed_ratio") == corner.get(
                    "fan_speed_ratio"
                )


def test_extrema_sources_withheld_when_any_scenario_is_unresolved() -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_curve_scenarios_demo.json",
            encoding="utf-8",
        ).read()
    )
    data["fan_curve_scenarios"][0]["points"] = [
        {"airflow_m3_h": 0, "pressure_pa": 0},
        {"airflow_m3_h": 5200, "pressure_pa": 0},
        {"airflow_m3_h": 8650, "pressure_pa": 0},
    ]

    result = analyze_fan_variable_friction_loop_uncertainty(
        fan_variable_friction_loop_uncertainty_from_dict(data)
    )

    assert result["status"] == "indeterminate"
    assert result["unresolved_corner_count"] >= 1
    assert result["operating_point_envelope"] is None
    assert result["operating_point_extrema_sources"] is None


def test_extrema_source_report_names_exact_corner_context() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_curve_scenarios_demo.json"
        )
    )
    report = markdown_fan_variable_friction_loop_uncertainty_report(result)

    assert "Critical evaluated cases" in report
    assert "Airflow lower" in report
    assert "Fan pressure upper" in report
    assert "corner " in report
    assert "scenario=" in report

def test_corner_outcome_diagnostics_account_for_every_evaluated_corner() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_curve_scenarios_demo.json"
        )
    )

    outcome = result["corner_outcome_diagnostics"]
    assert sum(outcome["status_counts"].values()) == result["corner_count"]
    assert outcome["status_counts"] == {"solved": result["corner_count"]}
    assert (
        sum(outcome["termination_reason_counts"].values())
        == result["corner_count"]
    )
    assert outcome["unresolved_corner_indices"] == []
    assert outcome["unresolved_cases"] == []


def test_indeterminate_analysis_surfaces_unresolved_corner_diagnostics() -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_curve_scenarios_demo.json",
            encoding="utf-8",
        ).read()
    )
    data["fan_curve_scenarios"][0]["points"] = [
        {"airflow_m3_h": 0, "pressure_pa": 0},
        {"airflow_m3_h": 5200, "pressure_pa": 0},
        {"airflow_m3_h": 8650, "pressure_pa": 0},
    ]

    result = analyze_fan_variable_friction_loop_uncertainty(
        fan_variable_friction_loop_uncertainty_from_dict(data)
    )

    assert result["status"] == "indeterminate"
    assert result["operating_point_envelope"] is None

    outcome = result["corner_outcome_diagnostics"]
    assert sum(outcome["status_counts"].values()) == result["corner_count"]
    assert (
        sum(outcome["termination_reason_counts"].values())
        == result["corner_count"]
    )
    assert len(outcome["unresolved_corner_indices"]) == (
        result["unresolved_corner_count"]
    )
    assert outcome["unresolved_cases"]

    for case in outcome["unresolved_cases"]:
        corner = result["corners"][case["corner_index"]]
        assert corner["status"] != "solved"
        assert case["status"] == corner["status"]
        assert case["termination_reason"] == corner["solver_diagnostics"][
            "termination_reason"
        ]
        assert case["fixed_pressure_pa"] == corner["fixed_pressure_pa"]

    report = markdown_fan_variable_friction_loop_uncertainty_report(result)
    assert "Corner outcome diagnostics" in report
    assert "Unresolved evaluated corners" in report
    assert "no_intersection_in_supplied_range" in report



def test_edge_airflow_extrema_sources_reference_exact_corners() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_curve_scenarios_demo.json"
        )
    )

    sources = result["edge_airflow_extrema_sources"]
    assert sources is not None
    assert {item["edge"] for item in sources} == {
        edge["edge"] for edge in result["edge_airflow_corner_ranges"]
    }
    for edge_source in sources:
        edge = edge_source["edge"]
        for bound in ("lower", "upper"):
            evidence = edge_source[bound]
            assert evidence["unit"] == "m3/h"
            assert evidence["sources"]
            for source in evidence["sources"]:
                corner = result["corners"][source["corner_index"]]
                assert corner["edge_airflows_m3_h"][edge] == pytest.approx(
                    evidence["value"],
                    abs=1e-6,
                )
                assert source["fixed_pressure_pa"] == corner["fixed_pressure_pa"]
                assert source.get("fan_curve_scenario") == corner.get(
                    "fan_curve_scenario"
                )
                assert source.get("fan_speed_ratio") == corner.get(
                    "fan_speed_ratio"
                )


def test_edge_airflow_extrema_sources_preserve_all_tied_scenarios() -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_curve_scenarios_demo.json",
            encoding="utf-8",
        ).read()
    )
    nominal_points = data["fan_curve"]["points"]
    for scenario in data["fan_curve_scenarios"]:
        scenario["points"] = [dict(point) for point in nominal_points]

    result = analyze_fan_variable_friction_loop_uncertainty(
        fan_variable_friction_loop_uncertainty_from_dict(data)
    )

    assert result["status"] == "complete"
    assert result["corner_count"] == 3
    for edge_source in result["edge_airflow_extrema_sources"]:
        for bound in ("lower", "upper"):
            sources = edge_source[bound]["sources"]
            assert len(sources) == 3
            assert {
                source["fan_curve_scenario"] for source in sources
            } == {"nominal", "lower_envelope", "upper_envelope"}


def test_indeterminate_analysis_withholds_edge_extrema_sources() -> None:
    data = _example_data()
    data["fixed_pressure_pa"] = {
        "value": 900.0,
        "uncertainty_abs": 0.0,
    }
    result = analyze_fan_variable_friction_loop_uncertainty(
        fan_variable_friction_loop_uncertainty_from_dict(data)
    )

    assert result["status"] == "indeterminate"
    assert result["edge_airflow_corner_ranges"] is None
    assert result["edge_airflow_extrema_sources"] is None


def test_report_surfaces_edge_airflow_witness_provenance() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_curve_scenarios_demo.json"
        )
    )
    report = markdown_fan_variable_friction_loop_uncertainty_report(result)

    assert "Internal edge-airflow witness provenance" in report
    assert "Source corner input(s)" in report
    assert "scenario=" in report



def test_power_chain_corner_ranges_preserve_exact_source_corners() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_uncertainty_demo.json"
        )
    )

    ranges = result["power_evidence_corner_ranges"]
    sources = result["power_evidence_extrema_sources"]
    assert ranges is not None
    assert sources is not None
    assert result["power_efficiencies"] == {
        "fan_efficiency": 0.72,
        "motor_efficiency": 0.93,
        "vfd_efficiency": 0.97,
    }

    metrics = {
        "fluid_air_power_kw": "kW",
        "shaft_power_kw": "kW",
        "electrical_input_kw": "kW",
        "specific_fan_power_w_per_m3_s": "W/(m3/s)",
    }
    for metric, unit in metrics.items():
        metric_range = ranges[metric]
        metric_sources = sources[metric]
        assert metric_range is not None
        assert metric_sources is not None
        assert metric_range["unit"] == unit
        assert metric_range["lower"] <= metric_range["upper"]

        for bound in ("lower", "upper"):
            evidence = metric_sources[bound]
            assert evidence["value"] == pytest.approx(
                metric_range[bound],
                abs=1e-6,
            )
            assert evidence["sources"]
            for source in evidence["sources"]:
                corner = result["corners"][source["corner_index"]]
                assert corner["power_evidence"] is not None
                assert corner["power_evidence"][metric] == pytest.approx(
                    evidence["value"],
                    abs=1e-6,
                )


def test_power_chain_corner_ranges_do_not_infer_missing_efficiencies() -> None:
    data = _example_data()
    data.pop("power_efficiencies")

    result = analyze_fan_variable_friction_loop_uncertainty(
        fan_variable_friction_loop_uncertainty_from_dict(data)
    )

    ranges = result["power_evidence_corner_ranges"]
    sources = result["power_evidence_extrema_sources"]
    assert result["status"] == "complete"
    assert result["power_efficiencies"] is None
    assert ranges is not None
    assert sources is not None
    assert ranges["fluid_air_power_kw"] is not None
    assert sources["fluid_air_power_kw"] is not None
    assert ranges["shaft_power_kw"] is None
    assert ranges["electrical_input_kw"] is None
    assert ranges["specific_fan_power_w_per_m3_s"] is None
    assert sources["shaft_power_kw"] is None
    assert sources["electrical_input_kw"] is None
    assert sources["specific_fan_power_w_per_m3_s"] is None


def test_indeterminate_analysis_withholds_power_chain_corner_ranges() -> None:
    data = _example_data()
    data["fixed_pressure_pa"] = {
        "value": 900.0,
        "uncertainty_abs": 0.0,
    }

    result = analyze_fan_variable_friction_loop_uncertainty(
        fan_variable_friction_loop_uncertainty_from_dict(data)
    )

    assert result["status"] == "indeterminate"
    assert result["power_evidence_corner_ranges"] is None
    assert result["power_evidence_extrema_sources"] is None


def test_uncertainty_report_surfaces_power_chain_corner_evidence() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_uncertainty_demo.json"
        )
    )
    report = markdown_fan_variable_friction_loop_uncertainty_report(result)

    assert "Power-chain evaluated-corner ranges" in report
    assert "Shaft power" in report
    assert "Electrical input" in report
    assert "Specific fan power" in report
    assert "fixed efficiencies" in report
    assert "not uncertain variables" in report


def test_solver_quality_summary_preserves_worst_metric_witnesses() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_curve_scenarios_demo.json"
        )
    )

    quality = result["solver_quality_summary"]
    assert quality["corner_count"] == result["corner_count"]
    assert quality["solved_corner_count"] == result["solved_corner_count"]
    assert quality["complete_evaluated_corner_coverage"] is True
    assert quality["complete_study_coverage"] is True
    assert quality["nominal_status"] == "solved"

    expected_metrics = {
        "absolute_operating_pressure_residual_pa",
        "network_max_relative_resistance_closure_error",
        "max_abs_mass_balance_residual_m3_h",
        "max_abs_pressure_law_residual_pa",
        "network_outer_iterations",
        "network_newton_iterations",
        "operating_iterations",
    }
    assert set(quality["worst_metrics"]) == expected_metrics

    for metric, evidence in quality["worst_metrics"].items():
        assert evidence is not None
        assert evidence["sources"]
        for source in evidence["sources"]:
            corner = result["corners"][source["corner_index"]]
            assert corner["status"] == "solved"
            if metric == "absolute_operating_pressure_residual_pa":
                assert abs(source["observed_value"]) == pytest.approx(
                    evidence["value"], abs=1e-9
                )
            else:
                assert source["observed_value"] == pytest.approx(
                    evidence["value"], abs=1e-9
                )

    tolerances = quality["configured_tolerances"]
    assert quality["worst_metrics"][
        "absolute_operating_pressure_residual_pa"
    ]["value"] <= tolerances["operating_pressure_tolerance_pa"] + 1e-9
    assert quality["worst_metrics"][
        "network_max_relative_resistance_closure_error"
    ]["value"] <= tolerances["resistance_relative_tolerance"] + 1e-9
    assert quality["worst_metrics"][
        "max_abs_mass_balance_residual_m3_h"
    ]["value"] <= tolerances["mass_balance_tolerance_m3_h"] + 1e-9

    checks = quality["configured_tolerance_checks"]
    assessment = quality["configured_tolerance_assessment"]
    assert assessment["status"] == "within_configured_tolerances"
    assert assessment["configured_check_count"] == 3
    assert assessment["evaluable_check_count"] == 3
    assert assessment["within_tolerance_count"] == 3
    assert assessment["exceeded_tolerance_count"] == 0
    assert assessment["not_evaluable_count"] == 0
    assert assessment["complete_study_coverage"] is True

    expected_tolerance_keys = {
        "absolute_operating_pressure_residual_pa":
            "operating_pressure_tolerance_pa",
        "network_max_relative_resistance_closure_error":
            "resistance_relative_tolerance",
        "max_abs_mass_balance_residual_m3_h":
            "mass_balance_tolerance_m3_h",
    }
    for metric_key, tolerance_key in expected_tolerance_keys.items():
        check = checks[metric_key]
        assert check["status"] == "within_tolerance"
        assert check["observed_value"] == pytest.approx(
            quality["worst_metrics"][metric_key]["value"], abs=1e-9
        )
        assert check["configured_tolerance"] == pytest.approx(
            tolerances[tolerance_key]
        )
        assert check["utilization_ratio"] == pytest.approx(
            check["observed_value"] / check["configured_tolerance"],
            abs=1e-9,
        )
        assert check["remaining_margin"] == pytest.approx(
            check["configured_tolerance"] - check["observed_value"],
            abs=1e-9,
        )

    iteration_limits = quality["configured_iteration_limits"]
    assert iteration_limits == {
        "max_outer_iterations": 50,
        "max_newton_iterations": 100,
        "max_operating_iterations": 80,
    }
    iteration_checks = quality["configured_iteration_checks"]
    iteration_assessment = quality["configured_iteration_assessment"]
    assert iteration_assessment["status"] == (
        "within_configured_iteration_limits"
    )
    assert iteration_assessment["configured_check_count"] == 3
    assert iteration_assessment["evaluable_check_count"] == 3
    assert iteration_assessment["within_limit_count"] == 3
    assert iteration_assessment["exceeded_limit_count"] == 0
    assert iteration_assessment["not_evaluable_count"] == 0
    assert iteration_assessment["complete_study_coverage"] is True

    expected_iteration_keys = {
        "network_outer_iterations": "max_outer_iterations",
        "network_newton_iterations": "max_newton_iterations",
        "operating_iterations": "max_operating_iterations",
    }
    for metric_key, limit_key in expected_iteration_keys.items():
        check = iteration_checks[metric_key]
        assert check["status"] == "within_iteration_limit"
        assert check["observed_iterations"] == pytest.approx(
            quality["worst_metrics"][metric_key]["value"], abs=1e-9
        )
        assert check["configured_limit"] == iteration_limits[limit_key]
        assert check["utilization_ratio"] == pytest.approx(
            check["observed_iterations"] / check["configured_limit"],
            abs=1e-9,
        )
        assert check["remaining_iterations"] == (
            check["configured_limit"] - check["observed_iterations"]
        )

def test_solver_quality_summary_marks_zero_solved_corner_coverage() -> None:
    data = _example_data()
    data["fixed_pressure_pa"] = {"value": 900.0, "uncertainty_abs": 0.0}
    result = analyze_fan_variable_friction_loop_uncertainty(
        fan_variable_friction_loop_uncertainty_from_dict(data)
    )

    quality = result["solver_quality_summary"]
    assert result["status"] == "indeterminate"
    assert quality["corner_count"] == result["corner_count"]
    assert quality["solved_corner_count"] == 0
    assert quality["complete_evaluated_corner_coverage"] is False
    assert quality["complete_study_coverage"] is False
    assert quality["nominal_status"] == "no_intersection_in_supplied_range"
    assert all(evidence is None for evidence in quality["worst_metrics"].values())

    assert quality["configured_tolerance_assessment"]["status"] == (
        "incomplete_coverage"
    )
    assert quality["configured_tolerance_assessment"]["evaluable_check_count"] == 0
    assert quality["configured_tolerance_assessment"]["not_evaluable_count"] == 3
    assert all(
        check["status"] == "not_evaluable"
        for check in quality["configured_tolerance_checks"].values()
    )
    assert quality["configured_iteration_assessment"]["status"] == (
        "incomplete_coverage"
    )
    assert quality["configured_iteration_assessment"]["evaluable_check_count"] == 0
    assert quality["configured_iteration_assessment"]["not_evaluable_count"] == 3
    assert all(
        check["status"] == "not_evaluable"
        for check in quality["configured_iteration_checks"].values()
    )

def test_report_surfaces_aggregate_solver_quality_evidence() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_curve_scenarios_demo.json"
        )
    )
    report = markdown_fan_variable_friction_loop_uncertainty_report(result)

    assert "Aggregate solver-quality evidence" in report
    assert "Solved evaluated corners" in report
    assert "Absolute operating pressure residual" in report
    assert "Resistance closure error" in report
    assert "Pressure-law residual" in report
    assert "Witness source corner(s)" in report
    assert "Configured solver-tolerance checks" in report
    assert "within_configured_tolerances" in report
    assert "Utilization" in report
    assert "Remaining margin" in report
    assert "Network Newton iterations" in report
    assert "Configured solver-iteration checks" in report
    assert "within_configured_iteration_limits" in report
    assert "Remaining iterations" in report

def test_nominal_relative_corner_excursions_are_auditable() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_uncertainty_demo.json"
        )
    )

    assert result["status"] == "complete"
    excursions = result["operating_point_excursions_from_nominal"]
    assert excursions is not None
    envelope = result["operating_point_envelope"]
    nominal = result["nominal_operating_point"]

    for key in (
        "airflow_m3_h",
        "fan_pressure_pa",
        "system_pressure_pa",
        "air_power_kw",
    ):
        evidence = excursions[key]
        assert evidence["nominal"] == pytest.approx(nominal[key], abs=1e-6)
        assert evidence["lower_delta"] == pytest.approx(
            envelope[key]["lower"] - nominal[key],
            abs=1e-6,
        )
        assert evidence["upper_delta"] == pytest.approx(
            envelope[key]["upper"] - nominal[key],
            abs=1e-6,
        )
        if abs(nominal[key]) > 1e-15:
            assert evidence["lower_percent"] == pytest.approx(
                (envelope[key]["lower"] - nominal[key])
                / abs(nominal[key])
                * 100.0,
                abs=1e-6,
            )
            assert evidence["upper_percent"] == pytest.approx(
                (envelope[key]["upper"] - nominal[key])
                / abs(nominal[key])
                * 100.0,
                abs=1e-6,
            )

    power_excursions = result["power_evidence_excursions_from_nominal"]
    assert power_excursions is not None
    assert power_excursions["fluid_air_power_kw"] is not None
    assert power_excursions["shaft_power_kw"] is not None
    assert power_excursions["electrical_input_kw"] is not None
    assert power_excursions["specific_fan_power_w_per_m3_s"] is not None

    report = markdown_fan_variable_friction_loop_uncertainty_report(result)
    assert "Evaluated-corner excursions from nominal" in report
    assert "Operating airflow" in report
    assert "Electrical input" in report
    assert "not sensitivity coefficients" in report


def test_indeterminate_study_withholds_nominal_relative_excursions() -> None:
    data = _example_data()
    data["fixed_pressure_pa"] = {"value": 900.0, "uncertainty_abs": 0.0}
    result = analyze_fan_variable_friction_loop_uncertainty(
        fan_variable_friction_loop_uncertainty_from_dict(data)
    )

    assert result["status"] == "indeterminate"
    assert result["operating_point_excursions_from_nominal"] is None
    assert result["power_evidence_excursions_from_nominal"] is None



def test_fan_curve_boundary_clearance_preserves_exact_corner_ranges() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_curve_scenarios_demo.json"
        )
    )

    assert result["status"] == "complete"
    nominal = result["nominal_fan_curve_boundary_clearance"]
    summary = result["fan_curve_boundary_clearance_summary"]
    assert nominal is not None
    assert summary["complete_study_coverage"] is True
    assert summary["solved_corner_count"] == result["corner_count"]

    clearances = []
    for corner in result["corners"]:
        clearance = corner["fan_curve_boundary_clearance"]
        assert clearance is not None
        lower, upper = corner["fan_curve_airflow_range_m3_h"]
        airflow = corner["operating_point"]["airflow_m3_h"]
        span = upper - lower

        assert clearance["operating_airflow_m3_h"] == pytest.approx(
            airflow, abs=1e-6
        )
        assert clearance["lower_boundary_headroom_m3_h"] == pytest.approx(
            airflow - lower, abs=1e-6
        )
        assert clearance["upper_boundary_headroom_m3_h"] == pytest.approx(
            upper - airflow, abs=1e-6
        )
        assert clearance["nearest_boundary_headroom_m3_h"] == pytest.approx(
            min(airflow - lower, upper - airflow), abs=1e-6
        )
        assert clearance["normalized_airflow_position"] == pytest.approx(
            (airflow - lower) / span, abs=1e-9
        )
        assert clearance[
            "nearest_boundary_headroom_fraction"
        ] == pytest.approx(
            min(airflow - lower, upper - airflow) / span,
            abs=1e-9,
        )
        clearances.append(clearance)

    minimum_absolute = min(
        item["nearest_boundary_headroom_m3_h"] for item in clearances
    )
    minimum_fraction = min(
        item["nearest_boundary_headroom_fraction"] for item in clearances
    )
    absolute_evidence = summary[
        "minimum_nearest_boundary_headroom_m3_h"
    ]
    normalized_evidence = summary[
        "minimum_nearest_boundary_headroom_fraction"
    ]
    assert absolute_evidence["value"] == pytest.approx(
        minimum_absolute, abs=1e-6
    )
    assert normalized_evidence["value"] == pytest.approx(
        minimum_fraction, abs=1e-9
    )

    for evidence in (absolute_evidence, normalized_evidence):
        assert evidence["sources"]
        for source in evidence["sources"]:
            corner = result["corners"][source["corner_index"]]
            clearance = corner["fan_curve_boundary_clearance"]
            assert source["operating_airflow_m3_h"] == pytest.approx(
                clearance["operating_airflow_m3_h"], abs=1e-6
            )
            assert source["fan_curve_airflow_range_m3_h"] == (
                clearance["fan_curve_airflow_range_m3_h"]
            )
            assert source["nearest_boundary"] == clearance[
                "nearest_boundary"
            ]

    report = markdown_fan_variable_friction_loop_uncertainty_report(result)
    assert "Supplied fan-curve boundary clearance" in report
    assert "Nearest endpoint airflow headroom" in report
    assert "no-extrapolation audit diagnostic only" in report


def test_fan_curve_boundary_clearance_marks_zero_solved_corner_coverage() -> None:
    data = _example_data()
    data["fixed_pressure_pa"] = {"value": 900.0, "uncertainty_abs": 0.0}
    result = analyze_fan_variable_friction_loop_uncertainty(
        fan_variable_friction_loop_uncertainty_from_dict(data)
    )

    summary = result["fan_curve_boundary_clearance_summary"]
    assert result["status"] == "indeterminate"
    assert result["nominal_fan_curve_boundary_clearance"] is None
    assert summary["complete_study_coverage"] is False
    assert summary["solved_corner_count"] == 0
    assert summary["minimum_nearest_boundary_headroom_m3_h"] is None
    assert summary["minimum_nearest_boundary_headroom_fraction"] is None
    assert all(
        corner["fan_curve_boundary_clearance"] is None
        for corner in result["corners"]
    )



def test_no_intersection_endpoint_diagnostics_preserve_lower_boundary_gap() -> None:
    data = _example_data()
    data["fixed_pressure_pa"] = {
        "value": 900.0,
        "uncertainty_abs": 0.0,
    }
    result = analyze_fan_variable_friction_loop_uncertainty(
        fan_variable_friction_loop_uncertainty_from_dict(data)
    )

    summary = result["fan_curve_no_intersection_summary"]
    assert result["status"] == "indeterminate"
    assert summary["no_intersection_corner_count"] == result["corner_count"]
    assert summary["lower_boundary_corner_count"] == result["corner_count"]
    assert summary["upper_boundary_corner_count"] == 0

    for corner in result["corners"]:
        diagnostic = corner["fan_curve_no_intersection_diagnostic"]
        assert diagnostic is not None
        assert diagnostic["boundary"] == "lower"
        assert diagnostic["mismatch_kind"] == "fan_pressure_deficit"
        assert diagnostic["airflow_m3_h"] == pytest.approx(0.0)
        assert diagnostic["fan_pressure_pa"] == pytest.approx(800.0)
        assert diagnostic["system_pressure_pa"] == pytest.approx(900.0)
        assert diagnostic["fan_minus_system_pressure_pa"] == pytest.approx(
            -100.0
        )
        assert diagnostic["absolute_boundary_pressure_gap_pa"] == pytest.approx(
            100.0
        )

    largest = summary["largest_absolute_boundary_pressure_gap_pa"]
    assert largest is not None
    assert largest["value"] == pytest.approx(100.0)
    assert len(largest["sources"]) == result["corner_count"]

    report = markdown_fan_variable_friction_loop_uncertainty_report(result)
    assert "No-intersection supplied-boundary diagnostics" in report
    assert "Lower supplied-airflow boundary cases" in report
    assert "fan_pressure_deficit" in report
    assert "does not extrapolate the fan curve" in report


def test_no_intersection_endpoint_diagnostics_preserve_upper_boundary_gap() -> None:
    data = _example_data()
    data["fixed_pressure_pa"] = {
        "value": 0.0,
        "uncertainty_abs": 0.0,
    }
    data["fan_curve"]["points"] = [
        {"airflow_m3_h": 0, "pressure_pa": 10000},
        {"airflow_m3_h": 5400, "pressure_pa": 9000},
        {"airflow_m3_h": 9000, "pressure_pa": 8000},
    ]
    result = analyze_fan_variable_friction_loop_uncertainty(
        fan_variable_friction_loop_uncertainty_from_dict(data)
    )

    summary = result["fan_curve_no_intersection_summary"]
    assert result["status"] == "indeterminate"
    assert summary["no_intersection_corner_count"] == result["corner_count"]
    assert summary["lower_boundary_corner_count"] == 0
    assert summary["upper_boundary_corner_count"] == result["corner_count"]

    for corner in result["corners"]:
        diagnostic = corner["fan_curve_no_intersection_diagnostic"]
        assert diagnostic is not None
        assert diagnostic["boundary"] == "upper"
        assert diagnostic["mismatch_kind"] == "fan_pressure_surplus"
        assert diagnostic["airflow_m3_h"] == pytest.approx(9000.0)
        assert diagnostic["fan_pressure_pa"] == pytest.approx(8000.0)
        assert diagnostic["fan_minus_system_pressure_pa"] > 0.0
        assert diagnostic["absolute_boundary_pressure_gap_pa"] == pytest.approx(
            diagnostic["fan_minus_system_pressure_pa"],
            abs=1e-9,
        )


def test_power_metric_ranges_require_complete_corner_coverage() -> None:
    from cleanroomx.fan_variable_friction_uncertainty import (
        _power_metric_availability,
        _power_metric_corner_range,
        _power_metric_extrema_sources,
    )

    corners = [
        {"power_evidence": {"specific_fan_power_w_per_m3_s": 825.0}},
        {"power_evidence": {"specific_fan_power_w_per_m3_s": None}},
    ]

    availability = _power_metric_availability(
        corners,
        "specific_fan_power_w_per_m3_s",
    )
    assert availability == {
        "status": "partial",
        "available_corner_count": 1,
        "total_corner_count": 2,
        "missing_corner_indices": [1],
    }
    assert _power_metric_corner_range(
        corners,
        "specific_fan_power_w_per_m3_s",
        "W/(m3/s)",
    ) is None
    assert _power_metric_extrema_sources(
        corners,
        "specific_fan_power_w_per_m3_s",
        "W/(m3/s)",
    ) is None


def test_power_evidence_availability_is_auditable_for_complete_study() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_uncertainty_demo.json"
        )
    )

    assert result["status"] == "complete"
    assert result["nominal_power_evidence"] == result["nominal_result"]["power_evidence"]
    availability = result["power_evidence_availability"]
    assert availability is not None
    for metric in (
        "fluid_air_power_kw",
        "shaft_power_kw",
        "electrical_input_kw",
        "specific_fan_power_w_per_m3_s",
    ):
        assert availability[metric]["status"] == "complete"
        assert availability[metric]["available_corner_count"] == result["corner_count"]
        assert availability[metric]["total_corner_count"] == result["corner_count"]
        assert availability[metric]["missing_corner_indices"] == []


def test_missing_efficiencies_report_unavailable_power_metric_coverage() -> None:
    data = _example_data()
    data.pop("power_efficiencies")

    result = analyze_fan_variable_friction_loop_uncertainty(
        fan_variable_friction_loop_uncertainty_from_dict(data)
    )

    availability = result["power_evidence_availability"]
    assert availability["fluid_air_power_kw"]["status"] == "complete"
    for metric in (
        "shaft_power_kw",
        "electrical_input_kw",
        "specific_fan_power_w_per_m3_s",
    ):
        assert availability[metric]["status"] == "unavailable"
        assert availability[metric]["available_corner_count"] == 0
        assert availability[metric]["missing_corner_indices"] == list(
            range(result["corner_count"])
        )


def test_power_report_surfaces_metric_coverage_and_withholding_rule() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_uncertainty_demo.json"
        )
    )
    report = markdown_fan_variable_friction_loop_uncertainty_report(result)

    assert "Availability" in report
    assert "complete (" in report
    assert "partial coverage is withheld" in report



def test_fan_curve_intersection_bracket_evidence_is_auditable() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_curve_scenarios_demo.json"
        )
    )

    assert result["status"] == "complete"
    nominal = result["nominal_fan_curve_intersection_bracket"]
    summary = result["fan_curve_intersection_bracket_summary"]
    assert nominal is not None
    assert summary["complete_study_coverage"] is True
    assert summary["bracket_evidence_corner_count"] == result["corner_count"]
    assert summary["bounded_intersection_supported_count"] == (
        result["corner_count"]
    )

    nearest_gaps = []
    residual_spans = []
    for corner in result["corners"]:
        diagnostic = corner["fan_curve_intersection_bracket"]
        assert diagnostic is not None
        point = corner["operating_point"]
        segment = point["interpolation_segment"]
        low = diagnostic["low_endpoint"]
        high = diagnostic["high_endpoint"]
        tolerance = diagnostic["operating_pressure_tolerance_pa"]

        assert low["airflow_m3_h"] == pytest.approx(
            segment["low_airflow_m3_h"], abs=1e-6
        )
        assert high["airflow_m3_h"] == pytest.approx(
            segment["high_airflow_m3_h"], abs=1e-6
        )
        assert low["fan_minus_system_pressure_pa"] >= -tolerance
        assert high["fan_minus_system_pressure_pa"] <= tolerance
        assert diagnostic["bounded_intersection_supported"] is True

        expected_nearest = min(
            abs(low["fan_minus_system_pressure_pa"]),
            abs(high["fan_minus_system_pressure_pa"]),
        )
        expected_span = abs(
            low["fan_minus_system_pressure_pa"]
            - high["fan_minus_system_pressure_pa"]
        )
        assert diagnostic[
            "nearest_endpoint_absolute_pressure_gap_pa"
        ] == pytest.approx(expected_nearest, abs=1e-9)
        assert diagnostic["endpoint_pressure_residual_span_pa"] == pytest.approx(
            expected_span,
            abs=1e-9,
        )
        nearest_gaps.append(expected_nearest)
        residual_spans.append(expected_span)

    minimum_gap = summary[
        "minimum_nearest_endpoint_absolute_pressure_gap_pa"
    ]
    minimum_span = summary["minimum_endpoint_pressure_residual_span_pa"]
    assert minimum_gap["value"] == pytest.approx(min(nearest_gaps), abs=1e-9)
    assert minimum_span["value"] == pytest.approx(min(residual_spans), abs=1e-9)
    assert minimum_gap["sources"]
    assert minimum_span["sources"]

    report = markdown_fan_variable_friction_loop_uncertainty_report(result)
    assert "Fan/system supplied-curve intersection brackets" in report
    assert "Bounded intersection supported by endpoint residuals" in report
    assert "numerical root-bracketing provenance only" in report


def test_fan_curve_intersection_bracket_marks_zero_solved_corner_coverage() -> None:
    data = _example_data()
    data["fixed_pressure_pa"] = {"value": 900.0, "uncertainty_abs": 0.0}
    result = analyze_fan_variable_friction_loop_uncertainty(
        fan_variable_friction_loop_uncertainty_from_dict(data)
    )

    summary = result["fan_curve_intersection_bracket_summary"]
    assert result["status"] == "indeterminate"
    assert result["nominal_fan_curve_intersection_bracket"] is None
    assert summary["complete_study_coverage"] is False
    assert summary["bracket_evidence_corner_count"] == 0
    assert summary["bounded_intersection_supported_count"] == 0
    assert summary["minimum_nearest_endpoint_absolute_pressure_gap_pa"] is None
    assert summary["minimum_endpoint_pressure_residual_span_pa"] is None
    assert all(
        corner["fan_curve_intersection_bracket"] is None
        for corner in result["corners"]
    )

def test_fan_curve_crossing_conditioning_is_auditable() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_curve_scenarios_demo.json"
        )
    )

    summary = result["fan_curve_crossing_conditioning_summary"]
    nominal = result["nominal_fan_curve_crossing_conditioning"]
    assert nominal is not None
    assert summary["complete_study_coverage"] is True
    assert summary["conditioning_evidence_corner_count"] == result["corner_count"]
    assert summary["secant_root_evidence_corner_count"] == result["corner_count"]

    absolute_slopes = []
    secant_errors = []
    normalized_errors = []
    for corner in result["corners"]:
        diagnostic = corner["fan_curve_crossing_conditioning"]
        bracket = corner["fan_curve_intersection_bracket"]
        assert diagnostic is not None
        assert bracket is not None

        low = bracket["low_endpoint"]
        high = bracket["high_endpoint"]
        span = high["airflow_m3_h"] - low["airflow_m3_h"]
        expected_fan_slope = (
            high["fan_pressure_pa"] - low["fan_pressure_pa"]
        ) / span
        expected_system_slope = (
            high["system_pressure_pa"] - low["system_pressure_pa"]
        ) / span
        expected_residual_slope = (
            high["fan_minus_system_pressure_pa"]
            - low["fan_minus_system_pressure_pa"]
        ) / span

        assert diagnostic["fan_pressure_slope_pa_per_m3_h"] == pytest.approx(
            expected_fan_slope, abs=1e-12
        )
        assert diagnostic[
            "system_pressure_secant_slope_pa_per_m3_h"
        ] == pytest.approx(expected_system_slope, abs=1e-12)
        assert diagnostic["fan_minus_system_slope_pa_per_m3_h"] == pytest.approx(
            expected_residual_slope, abs=1e-12
        )
        assert diagnostic[
            "absolute_fan_minus_system_slope_pa_per_m3_h"
        ] == pytest.approx(abs(expected_residual_slope), abs=1e-12)

        secant_root = low["airflow_m3_h"] - (
            low["fan_minus_system_pressure_pa"] / expected_residual_slope
        )
        solved_airflow = corner["operating_point"]["airflow_m3_h"]
        expected_error = abs(solved_airflow - secant_root)
        expected_normalized_error = expected_error / span
        assert diagnostic["secant_root_airflow_m3_h"] == pytest.approx(
            secant_root, abs=1e-9
        )
        assert diagnostic["secant_root_absolute_error_m3_h"] == pytest.approx(
            expected_error, abs=1e-9
        )
        assert diagnostic[
            "normalized_secant_root_error_fraction"
        ] == pytest.approx(expected_normalized_error, abs=1e-12)

        absolute_slopes.append(abs(expected_residual_slope))
        secant_errors.append(expected_error)
        normalized_errors.append(expected_normalized_error)

    minimum_slope = summary[
        "minimum_absolute_fan_minus_system_slope_pa_per_m3_h"
    ]
    maximum_error = summary["maximum_secant_root_absolute_error_m3_h"]
    maximum_normalized = summary[
        "maximum_normalized_secant_root_error_fraction"
    ]
    assert minimum_slope["value"] == pytest.approx(
        min(absolute_slopes), abs=1e-12
    )
    assert maximum_error["value"] == pytest.approx(max(secant_errors), abs=1e-9)
    assert maximum_normalized["value"] == pytest.approx(
        max(normalized_errors), abs=1e-12
    )
    assert minimum_slope["sources"]
    assert maximum_error["sources"]

    report = markdown_fan_variable_friction_loop_uncertainty_report(result)
    assert "Fan/system local crossing conditioning" in report
    assert "Nominal fan-minus-system slope" in report
    assert "No stability criterion" in report


def test_crossing_conditioning_marks_zero_solved_corner_coverage() -> None:
    data = _example_data()
    data["fixed_pressure_pa"] = {"value": 900.0, "uncertainty_abs": 0.0}
    result = analyze_fan_variable_friction_loop_uncertainty(
        fan_variable_friction_loop_uncertainty_from_dict(data)
    )

    summary = result["fan_curve_crossing_conditioning_summary"]
    assert result["status"] == "indeterminate"
    assert result["nominal_fan_curve_crossing_conditioning"] is None
    assert summary["complete_study_coverage"] is False
    assert summary["conditioning_evidence_corner_count"] == 0
    assert summary["secant_root_evidence_corner_count"] == 0
    assert (
        summary["minimum_absolute_fan_minus_system_slope_pa_per_m3_h"]
        is None
    )
    assert summary["maximum_secant_root_absolute_error_m3_h"] is None
    assert all(
        corner["fan_curve_crossing_conditioning"] is None
        for corner in result["corners"]
    )

def test_supplied_point_residual_topology_propagates_across_corners() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_curve_scenarios_demo.json"
        )
    )

    summary = result["fan_curve_supplied_point_residual_summary"]
    nominal = result["nominal_fan_curve_supplied_point_residual_audit"]
    assert nominal is not None
    assert summary["complete_study_coverage"] is True
    assert summary["audit_evidence_corner_count"] == result["corner_count"]
    assert summary["complete_supplied_point_coverage_corner_count"] == (
        result["corner_count"]
    )
    assert summary["monotonic_non_increasing_corner_count"] == (
        result["corner_count"]
    )
    assert summary["residual_increase_corner_count"] == 0
    assert summary["residual_increase_corner_indices"] == []
    assert summary["maximum_positive_residual_increase_pa"] is None

    for corner in result["corners"]:
        audit = corner["fan_curve_supplied_point_residual_audit"]
        assert audit is not None
        assert audit["complete_supplied_point_coverage"] is True
        assert audit[
            "residual_monotonic_non_increasing_with_tolerance"
        ] is True

    report = markdown_fan_variable_friction_loop_uncertainty_report(result)
    assert "Supplied-point residual topology across corners" in report
    assert "Corners monotonic non-increasing within tolerance" in report
    assert "do not prove continuous uniqueness" in report


def test_fan_curve_segment_position_is_auditable() -> None:
    result = analyze_fan_variable_friction_loop_uncertainty(
        load_fan_variable_friction_loop_uncertainty(
            "examples/fan_variable_friction_curve_scenarios_demo.json"
        )
    )
    summary = result["fan_curve_segment_position_summary"]
    nominal = result["nominal_fan_curve_segment_position"]
    assert nominal is not None
    assert summary["complete_study_coverage"] is True
    assert summary["segment_position_evidence_corner_count"] == result["corner_count"]

    nearest_clearances = []
    normalized_clearances = []
    segment_spans = []
    for corner in result["corners"]:
        diagnostic = corner["fan_curve_segment_position"]
        bracket = corner["fan_curve_intersection_bracket"]
        assert diagnostic is not None
        assert bracket is not None
        airflow = corner["operating_point"]["airflow_m3_h"]
        low = bracket["low_endpoint"]["airflow_m3_h"]
        high = bracket["high_endpoint"]["airflow_m3_h"]
        span = high - low
        lower_clearance = max(0.0, airflow - low)
        upper_clearance = max(0.0, high - airflow)
        nearest = min(lower_clearance, upper_clearance)
        assert diagnostic["segment_airflow_span_m3_h"] == pytest.approx(span, abs=1e-9)
        assert diagnostic["nearest_segment_endpoint_clearance_m3_h"] == pytest.approx(nearest, abs=1e-9)
        assert diagnostic["normalized_segment_position_fraction"] == pytest.approx(lower_clearance / span, abs=1e-12)
        assert diagnostic["normalized_nearest_segment_endpoint_clearance_fraction"] == pytest.approx(nearest / span, abs=1e-12)
        nearest_clearances.append(nearest)
        normalized_clearances.append(nearest / span)
        segment_spans.append(span)

    assert summary["minimum_nearest_segment_endpoint_clearance_m3_h"]["value"] == pytest.approx(min(nearest_clearances), abs=1e-9)
    assert summary["minimum_normalized_nearest_segment_endpoint_clearance_fraction"]["value"] == pytest.approx(min(normalized_clearances), abs=1e-12)
    assert summary["maximum_segment_airflow_span_m3_h"]["value"] == pytest.approx(max(segment_spans), abs=1e-9)
    assert summary["minimum_nearest_segment_endpoint_clearance_m3_h"]["sources"]

    report = markdown_fan_variable_friction_loop_uncertainty_report(result)
    assert "Fan-curve interpolation segment position" in report
    assert "Minimum nearest segment-endpoint clearance" in report
    assert "not an interpolation-error estimate" in report


def test_fan_curve_segment_position_marks_zero_solved_corner_coverage() -> None:
    data = _example_data()
    data["fixed_pressure_pa"] = {"value": 900.0, "uncertainty_abs": 0.0}
    result = analyze_fan_variable_friction_loop_uncertainty(
        fan_variable_friction_loop_uncertainty_from_dict(data)
    )
    summary = result["fan_curve_segment_position_summary"]
    assert result["status"] == "indeterminate"
    assert result["nominal_fan_curve_segment_position"] is None
    assert summary["complete_study_coverage"] is False
    assert summary["segment_position_evidence_corner_count"] == 0
    assert summary["minimum_nearest_segment_endpoint_clearance_m3_h"] is None
    assert summary["minimum_normalized_nearest_segment_endpoint_clearance_fraction"] is None
    assert summary["maximum_segment_airflow_span_m3_h"] is None
    assert all(corner["fan_curve_segment_position"] is None for corner in result["corners"])

