import math

import pytest

from cleanroomx.duct_flow import ParallelFlowPath, ParallelFlowSection
from cleanroomx.fan_curve import FanCurve, FanCurvePoint
from cleanroomx.fan_network import (
    FanDrivenParallelNetworkStudy,
    equivalent_parallel_resistance,
    solve_fan_driven_parallel_network,
)
from cleanroomx.fan_network_io import fan_driven_parallel_network_study_from_dict


def _fan() -> FanCurve:
    return FanCurve(
        "Supply fan",
        (
            FanCurvePoint(0, 600),
            FanCurvePoint(3000, 500),
            FanCurvePoint(6000, 300),
            FanCurvePoint(8000, 100),
        ),
    )


def _section(name: str, diameter_m: float, length_m: float = 10) -> ParallelFlowSection:
    return ParallelFlowSection(
        name=name,
        length_m=length_m,
        friction_factor=0.02,
        air_density_kg_m3=1.2,
        local_loss_coefficient=1.0,
        diameter_m=diameter_m,
    )


def test_equal_parallel_paths_are_integrated_with_fan_curve() -> None:
    path_a = ParallelFlowPath("A", (_section("A1", 0.5),))
    path_b = ParallelFlowPath("B", (_section("B1", 0.5),))
    study = FanDrivenParallelNetworkStudy(
        name="Equal branches",
        fan_curve=_fan(),
        fixed_pressure_pa=80,
        paths=(path_a, path_b),
    )

    result = solve_fan_driven_parallel_network(study)

    assert result["status"] == "solved"
    assert result["fan_operating_point"]["airflow_m3_h"] == pytest.approx(
        7935.342, abs=0.001
    )
    network = result["network_solution"]
    assert network is not None
    assert network["paths"][0]["airflow_m3_h"] == pytest.approx(
        network["paths"][1]["airflow_m3_h"], abs=0.001
    )
    assert sum(path["airflow_m3_h"] for path in network["paths"]) == pytest.approx(
        result["fan_operating_point"]["airflow_m3_h"], abs=0.002
    )
    assert network["mass_balance_error_m3_h"] == pytest.approx(0, abs=1e-6)
    assert result["system_pressure_check"]["fan_minus_system_pressure_pa"] == pytest.approx(
        0, abs=0.001
    )


def test_equivalent_resistance_matches_parallel_rq2_relation() -> None:
    path_a = ParallelFlowPath("A", (_section("A1", 0.5),))
    path_b = ParallelFlowPath("B", (_section("B1", 0.4),))
    resistance_a = path_a.resistance_pa_per_m3_s_squared
    resistance_b = path_b.resistance_pa_per_m3_s_squared

    actual = equivalent_parallel_resistance((path_a, path_b))
    expected = 1.0 / (
        1.0 / math.sqrt(resistance_a) + 1.0 / math.sqrt(resistance_b)
    ) ** 2

    assert actual == pytest.approx(expected, rel=1e-12)


def test_unequal_paths_keep_inverse_sqrt_flow_ratio_at_operating_point() -> None:
    low = ParallelFlowPath("Low", (_section("Low 1", 0.5),))
    high = ParallelFlowPath("High", (_section("High 1", 0.4),))
    result = solve_fan_driven_parallel_network(
        FanDrivenParallelNetworkStudy(
            "Unequal branches",
            _fan(),
            60,
            (low, high),
        )
    )

    network = result["network_solution"]
    assert network is not None
    low_result, high_result = network["paths"]
    expected_ratio = math.sqrt(
        high_result["resistance_pa_per_m3_s_squared"]
        / low_result["resistance_pa_per_m3_s_squared"]
    )
    actual_ratio = low_result["airflow_m3_h"] / high_result["airflow_m3_h"]
    assert actual_ratio == pytest.approx(expected_ratio, rel=1e-4)


def test_three_path_solution_preserves_equivalent_pressure_relation() -> None:
    paths = (
        ParallelFlowPath("Wide", (_section("Wide 1", 0.55, 8),)),
        ParallelFlowPath("Medium", (_section("Medium 1", 0.45, 12),)),
        ParallelFlowPath("Narrow", (_section("Narrow 1", 0.35, 16),)),
    )
    result = solve_fan_driven_parallel_network(
        FanDrivenParallelNetworkStudy(
            "Three branches",
            _fan(),
            40,
            paths,
        )
    )

    assert result["status"] == "solved"
    network = result["network_solution"]
    assert network is not None
    operating_q_m3_s = result["fan_operating_point"]["airflow_m3_s"]
    equivalent_r = result["equivalent_network_resistance_pa_per_m3_s_squared"]
    expected_network_pressure = equivalent_r * operating_q_m3_s**2

    assert network["common_pressure_drop_pa"] == pytest.approx(
        expected_network_pressure, abs=0.01
    )
    assert network["mass_balance_error_m3_h"] == pytest.approx(0, abs=1e-6)
    for path in network["paths"]:
        assert path["pressure_balance_error_pa"] == pytest.approx(0, abs=1e-6)


def test_no_intersection_is_reported_without_branch_flow_solution() -> None:
    path_a = ParallelFlowPath("A", (_section("A1", 0.5),))
    path_b = ParallelFlowPath("B", (_section("B1", 0.5),))
    result = solve_fan_driven_parallel_network(
        FanDrivenParallelNetworkStudy(
            "Too much fixed pressure",
            _fan(),
            700,
            (path_a, path_b),
        )
    )

    assert result["status"] == "no_intersection_in_supplied_range"
    assert result["network_solution"] is None
    assert result["system_pressure_check"] is None
    assert "lower-flow extrapolation" in result["message"]


def test_study_requires_two_unique_paths_and_finite_fixed_pressure() -> None:
    path = ParallelFlowPath("A", (_section("A1", 0.5),))
    with pytest.raises(ValueError, match="at least two paths"):
        FanDrivenParallelNetworkStudy("Bad", _fan(), 0, (path,))

    with pytest.raises(ValueError, match="unique"):
        FanDrivenParallelNetworkStudy("Bad", _fan(), 0, (path, path))

    other = ParallelFlowPath("B", (_section("B1", 0.5),))
    with pytest.raises(ValueError, match="finite"):
        FanDrivenParallelNetworkStudy("Bad", _fan(), float("nan"), (path, other))


def test_json_loader_builds_fan_driven_network_study() -> None:
    study = fan_driven_parallel_network_study_from_dict(
        {
            "name": "Loaded",
            "fixed_pressure_pa": 75,
            "fan_curve": {
                "name": "Fan",
                "points": [
                    {"airflow_m3_h": 0, "pressure_pa": 600},
                    {"airflow_m3_h": 7000, "pressure_pa": 150},
                ],
            },
            "paths": [
                {
                    "name": "A",
                    "sections": [
                        {
                            "name": "A1",
                            "length_m": 10,
                            "friction_factor": 0.02,
                            "air_density_kg_m3": 1.2,
                            "local_loss_coefficient": 1,
                            "diameter_m": 0.5,
                        }
                    ],
                },
                {
                    "name": "B",
                    "sections": [
                        {
                            "name": "B1",
                            "length_m": 12,
                            "friction_factor": 0.02,
                            "air_density_kg_m3": 1.2,
                            "local_loss_coefficient": 1,
                            "width_m": 0.5,
                            "height_m": 0.3,
                        }
                    ],
                },
            ],
        }
    )

    assert study.name == "Loaded"
    assert study.fixed_pressure_pa == 75
    assert len(study.paths) == 2
    assert study.paths[1].sections[0].width_m == 0.5
