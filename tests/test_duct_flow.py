import pytest

from cleanroomx.duct_flow import (
    ParallelFlowNetwork,
    ParallelFlowPath,
    ParallelFlowSection,
    solve_parallel_branch_flows,
)


def _section(name: str, diameter_m: float) -> ParallelFlowSection:
    return ParallelFlowSection(
        name=name,
        length_m=10,
        friction_factor=0.02,
        air_density_kg_m3=1.2,
        local_loss_coefficient=1.0,
        diameter_m=diameter_m,
    )


def test_identical_parallel_paths_split_flow_equally() -> None:
    network = ParallelFlowNetwork(
        name="Equal branches",
        total_airflow_m3_h=3600,
        paths=(
            ParallelFlowPath("A", (_section("A1", 0.5),)),
            ParallelFlowPath("B", (_section("B1", 0.5),)),
        ),
    )

    result = solve_parallel_branch_flows(network)

    assert result["paths"][0]["airflow_m3_h"] == pytest.approx(1800, abs=0.001)
    assert result["paths"][1]["airflow_m3_h"] == pytest.approx(1800, abs=0.001)
    assert result["mass_balance_error_m3_h"] == pytest.approx(0, abs=1e-6)
    assert result["paths"][0]["pressure_drop_pa"] == pytest.approx(
        result["paths"][1]["pressure_drop_pa"], abs=1e-4
    )


def test_flow_distribution_is_inverse_sqrt_of_path_resistance() -> None:
    low = ParallelFlowSection(
        "Low R", 10, 0.02, 1.2, local_loss_coefficient=1.0, diameter_m=0.5
    )
    high = ParallelFlowSection(
        "High R", 40, 0.02, 1.2, local_loss_coefficient=4.0, diameter_m=0.5
    )
    network = ParallelFlowNetwork(
        name="Unequal",
        total_airflow_m3_h=3000,
        paths=(
            ParallelFlowPath("Low", (low,)),
            ParallelFlowPath("High", (high,)),
        ),
    )

    result = solve_parallel_branch_flows(network)
    low_result, high_result = result["paths"]

    expected_ratio = (
        high_result["resistance_pa_per_m3_s_squared"]
        / low_result["resistance_pa_per_m3_s_squared"]
    ) ** 0.5
    actual_ratio = low_result["airflow_m3_h"] / high_result["airflow_m3_h"]
    assert actual_ratio == pytest.approx(expected_ratio, rel=1e-4)
    assert sum(path["airflow_m3_h"] for path in result["paths"]) == pytest.approx(
        3000, abs=0.002
    )


def test_solver_requires_at_least_two_paths() -> None:
    with pytest.raises(ValueError, match="at least two paths"):
        ParallelFlowNetwork(
            name="Bad",
            total_airflow_m3_h=1000,
            paths=(ParallelFlowPath("Only", (_section("S", 0.5),)),),
        )


def test_zero_resistance_section_is_rejected() -> None:
    with pytest.raises(ValueError, match="positive friction or local resistance"):
        ParallelFlowSection(
            name="Zero R",
            length_m=10,
            friction_factor=0,
            air_density_kg_m3=1.2,
            local_loss_coefficient=0,
            diameter_m=0.5,
        )
