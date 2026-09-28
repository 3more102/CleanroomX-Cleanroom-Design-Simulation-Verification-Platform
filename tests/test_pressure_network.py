import math

import pytest

from cleanroomx.pressure_network import (
    PressureNode,
    PressurePath,
    PressureTarget,
    RoomPressureNetwork,
    solve_room_pressure_network,
)
from cleanroomx.pressure_network_io import (
    pressure_network_from_dict,
)
from cleanroomx.pressure_network_report import (
    markdown_pressure_network_report,
)


def _linear_room(
    *,
    supply_m3_h: float = 100.0,
    target_pa: float = 2.0,
) -> RoomPressureNetwork:
    return RoomPressureNetwork(
        name="Linear room",
        nodes=(
            PressureNode(
                "Room",
                supply_m3_h=supply_m3_h,
            ),
            PressureNode(
                "Atmosphere",
                fixed_pressure_pa=0.0,
            ),
        ),
        paths=(
            PressurePath(
                "Leak",
                "Room",
                "Atmosphere",
                "crack",
                "power_law",
                coefficient_m3_s_pa_n=0.01,
                exponent=1.0,
            ),
        ),
        targets=(
            PressureTarget(
                "Room positive",
                "Room",
                "Atmosphere",
                target_pa,
            ),
        ),
    )


def test_linear_power_law_matches_analytical_pressure() -> None:
    result = solve_room_pressure_network(_linear_room())
    room = result["nodes"][0]
    path = result["paths"][0]

    expected_pressure = (100.0 / 3600.0) / 0.01
    assert room["pressure_pa"] == pytest.approx(
        expected_pressure,
        abs=1e-9,
    )
    assert path["airflow_m3_h"] == pytest.approx(
        100.0,
        abs=1e-6,
    )
    assert room["mass_balance_residual_m3_h"] == pytest.approx(
        0.0,
        abs=1e-9,
    )
    assert result["target_summary"]["passed"] == 1
    assert result["status"] == "solved"


def test_nonlinear_two_room_cascade_converges() -> None:
    network = pressure_network_from_dict(
        {
            "name": "Two-room cascade",
            "nodes": [
                {
                    "name": "Process",
                    "supply_m3_h": 1200.0,
                    "return_m3_h": 900.0,
                },
                {
                    "name": "Airlock",
                    "supply_m3_h": 600.0,
                    "return_m3_h": 500.0,
                },
                {
                    "name": "Corridor",
                    "fixed_pressure_pa": 0.0,
                },
            ],
            "paths": [
                {
                    "name": "Process-Airlock",
                    "start_node": "Process",
                    "end_node": "Airlock",
                    "kind": "door",
                    "model": "power_law",
                    "coefficient_m3_s_pa_n": 0.01,
                    "exponent": 0.65,
                },
                {
                    "name": "Airlock-Corridor",
                    "start_node": "Airlock",
                    "end_node": "Corridor",
                    "kind": "undercut",
                    "model": "power_law",
                    "coefficient_m3_s_pa_n": 0.012,
                    "exponent": 0.65,
                },
            ],
            "targets": [
                {
                    "name": "Process > Airlock",
                    "high_node": "Process",
                    "low_node": "Airlock",
                    "minimum_delta_pa": 5.0,
                },
                {
                    "name": "Airlock > Corridor",
                    "high_node": "Airlock",
                    "low_node": "Corridor",
                    "minimum_delta_pa": 2.0,
                },
            ],
        }
    )

    result = solve_room_pressure_network(network)
    nodes = {
        item["name"]: item
        for item in result["nodes"]
    }
    paths = {
        item["name"]: item
        for item in result["paths"]
    }

    assert result["solver"]["iterations"] > 0
    assert (
        result["solver"][
            "max_abs_unknown_node_mass_balance_residual_m3_h"
        ]
        <= 1e-6
    )
    assert nodes["Process"]["pressure_pa"] > nodes["Airlock"]["pressure_pa"]
    assert nodes["Airlock"]["pressure_pa"] > nodes["Corridor"]["pressure_pa"]
    assert paths["Process-Airlock"]["airflow_m3_h"] == pytest.approx(
        300.0,
        abs=1e-6,
    )
    assert paths["Airlock-Corridor"]["airflow_m3_h"] == pytest.approx(
        400.0,
        abs=1e-6,
    )
    assert result["target_summary"]["failed"] == 0


def test_orifice_model_matches_explicit_injection() -> None:
    network = RoomPressureNetwork(
        name="Orifice room",
        nodes=(
            PressureNode(
                "Room",
                supply_m3_h=360.0,
            ),
            PressureNode(
                "Reference",
                fixed_pressure_pa=0.0,
            ),
        ),
        paths=(
            PressurePath(
                "Opening",
                "Room",
                "Reference",
                "generic_opening",
                "orifice",
                discharge_coefficient=0.6,
                area_m2=0.05,
                air_density_kg_m3=1.2,
            ),
        ),
    )

    result = solve_room_pressure_network(network)
    room_pressure = result["nodes"][0]["pressure_pa"]
    q_m3_s = 0.1
    expected = (
        1.2
        / 2.0
        * (
            q_m3_s
            / (0.6 * 0.05)
        )
        ** 2
    )

    assert room_pressure == pytest.approx(
        expected,
        rel=1e-8,
    )
    assert result["paths"][0]["airflow_m3_h"] == pytest.approx(
        360.0,
        abs=1e-6,
    )


def test_exhaust_can_drive_room_negative() -> None:
    network = RoomPressureNetwork(
        name="Negative room",
        nodes=(
            PressureNode(
                "Isolation",
                exhaust_m3_h=180.0,
            ),
            PressureNode(
                "Corridor",
                fixed_pressure_pa=0.0,
            ),
        ),
        paths=(
            PressurePath(
                "Door leakage",
                "Isolation",
                "Corridor",
                "door",
                "power_law",
                coefficient_m3_s_pa_n=0.01,
                exponent=1.0,
            ),
        ),
    )

    result = solve_room_pressure_network(network)
    assert result["nodes"][0]["pressure_pa"] == pytest.approx(
        -5.0,
        abs=1e-9,
    )
    assert result["paths"][0]["flow_direction"] == (
        "Corridor -> Isolation"
    )


def test_pressure_target_violation_is_explicit() -> None:
    result = solve_room_pressure_network(
        _linear_room(target_pa=10.0)
    )

    assert result["status"] == "solved_with_target_violations"
    assert result["target_summary"]["failed"] == 1
    assert result["targets"][0]["status"] == "fail"
    assert result["targets"][0]["minimum_margin_pa"] < 0.0


def test_pressure_offset_is_explicit_driving_pressure() -> None:
    network = RoomPressureNetwork(
        name="Offset",
        nodes=(
            PressureNode(
                "A",
                fixed_pressure_pa=0.0,
            ),
            PressureNode(
                "B",
                fixed_pressure_pa=0.0,
            ),
        ),
        paths=(
            PressurePath(
                "Offset path",
                "A",
                "B",
                "generic",
                "power_law",
                coefficient_m3_s_pa_n=0.01,
                exponent=1.0,
                pressure_offset_pa=3.0,
            ),
        ),
    )

    result = solve_room_pressure_network(network)
    assert result["paths"][0][
        "effective_pressure_difference_pa"
    ] == pytest.approx(3.0)
    assert result["paths"][0]["airflow_m3_h"] == pytest.approx(
        108.0
    )


@pytest.mark.parametrize("bad_exponent", [0.49, 1.01])
def test_power_law_exponent_domain_is_rejected(
    bad_exponent: float,
) -> None:
    with pytest.raises(ValueError, match="exponent"):
        PressurePath(
            "Bad",
            "A",
            "B",
            "crack",
            "power_law",
            coefficient_m3_s_pa_n=0.01,
            exponent=bad_exponent,
        )


def test_every_unknown_node_must_connect_to_fixed_boundary() -> None:
    with pytest.raises(ValueError, match="fixed-pressure boundary"):
        RoomPressureNetwork(
            name="Disconnected",
            nodes=(
                PressureNode("A"),
                PressureNode("B"),
                PressureNode(
                    "Outside",
                    fixed_pressure_pa=0.0,
                ),
            ),
            paths=(
                PressurePath(
                    "AB",
                    "A",
                    "B",
                    "crack",
                    "power_law",
                    coefficient_m3_s_pa_n=0.01,
                    exponent=0.65,
                ),
            ),
        )


def test_parser_rejects_unknown_top_level_fields() -> None:
    with pytest.raises(
        ValueError,
        match="unsupported pressure-network",
    ):
        pressure_network_from_dict(
            {
                "name": "Bad",
                "nodes": [
                    {
                        "name": "A",
                        "fixed_pressure_pa": 0.0,
                    },
                    {
                        "name": "B",
                        "fixed_pressure_pa": 0.0,
                    },
                ],
                "paths": [
                    {
                        "name": "AB",
                        "start_node": "A",
                        "end_node": "B",
                        "kind": "crack",
                        "model": "power_law",
                        "coefficient_m3_s_pa_n": 0.01,
                        "exponent": 1.0,
                    }
                ],
                "unexpected": True,
            }
        )


def test_solver_is_deterministic_and_report_exposes_scope() -> None:
    network = _linear_room()
    first = solve_room_pressure_network(network)
    second = solve_room_pressure_network(network)
    report = markdown_pressure_network_report(first)

    assert first == second
    assert "Room Pressure-Network Report" in report
    assert "Pressure targets" in report
    assert "does not invent" in report
    assert math.isfinite(
        first["paths"][0][
            "local_flow_sensitivity_m3_s_pa"
        ]
    )


def test_pressure_node_rejects_nonfinite_combined_mechanical_injection() -> None:
    with pytest.raises(
        ValueError,
        match="mechanical_injection_m3_h must remain finite",
    ):
        PressureNode(
            "Overflow room",
            return_m3_h=1e308,
            exhaust_m3_h=1e308,
        )


def test_solver_rejects_nonfinite_effective_pressure_difference() -> None:
    network = RoomPressureNetwork(
        name="Extreme pressure boundary",
        nodes=(
            PressureNode(
                "High",
                fixed_pressure_pa=1e308,
            ),
            PressureNode(
                "Low",
                fixed_pressure_pa=-1e308,
            ),
        ),
        paths=(
            PressurePath(
                "Extreme delta",
                "High",
                "Low",
                "crack",
                "power_law",
                coefficient_m3_s_pa_n=0.01,
                exponent=1.0,
            ),
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="Extreme delta effective_pressure_difference_pa",
    ):
        solve_room_pressure_network(network)


def test_solver_rejects_nonfinite_power_law_flow() -> None:
    network = RoomPressureNetwork(
        name="Extreme power-law flow",
        nodes=(
            PressureNode(
                "High",
                fixed_pressure_pa=2.0,
            ),
            PressureNode(
                "Low",
                fixed_pressure_pa=0.0,
            ),
        ),
        paths=(
            PressurePath(
                "Extreme leak",
                "High",
                "Low",
                "crack",
                "power_law",
                coefficient_m3_s_pa_n=1e308,
                exponent=1.0,
            ),
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="Extreme leak airflow_m3_s",
    ):
        solve_room_pressure_network(network)


def test_solver_rejects_nonfinite_orifice_coefficient() -> None:
    network = RoomPressureNetwork(
        name="Extreme orifice",
        nodes=(
            PressureNode(
                "High",
                fixed_pressure_pa=1.0,
            ),
            PressureNode(
                "Low",
                fixed_pressure_pa=0.0,
            ),
        ),
        paths=(
            PressurePath(
                "Extreme opening",
                "High",
                "Low",
                "generic_opening",
                "orifice",
                discharge_coefficient=1e308,
                area_m2=1e308,
                air_density_kg_m3=1.2,
            ),
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="Extreme opening orifice_flow_coefficient",
    ):
        solve_room_pressure_network(network)


def test_solver_rejects_nonfinite_report_unit_conversion() -> None:
    network = RoomPressureNetwork(
        name="Extreme output conversion",
        nodes=(
            PressureNode(
                "High",
                fixed_pressure_pa=1.0,
            ),
            PressureNode(
                "Low",
                fixed_pressure_pa=0.0,
            ),
        ),
        paths=(
            PressurePath(
                "Large finite leak",
                "High",
                "Low",
                "crack",
                "power_law",
                coefficient_m3_s_pa_n=1e305,
                exponent=1.0,
            ),
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="mass_balance_residual_m3_h",
    ):
        solve_room_pressure_network(network)


@pytest.mark.parametrize(
    ("maximum_delta_pa", "expected_context"),
    (
        (None, "minimum_margin_pa"),
        (1e308, "maximum_margin_pa"),
    ),
)
def test_solver_rejects_nonfinite_target_margin(
    maximum_delta_pa: float | None,
    expected_context: str,
) -> None:
    network = RoomPressureNetwork(
        name="Extreme target margin",
        nodes=(
            PressureNode(
                "Low-pressure boundary",
                fixed_pressure_pa=-1e308,
            ),
            PressureNode(
                "Reference",
                fixed_pressure_pa=0.0,
            ),
        ),
        paths=(
            PressurePath(
                "Finite extreme path",
                "Low-pressure boundary",
                "Reference",
                "crack",
                "power_law",
                coefficient_m3_s_pa_n=1e-308,
                exponent=0.5,
            ),
        ),
        targets=(
            PressureTarget(
                "Extreme target",
                "Low-pressure boundary",
                "Reference",
                1e308 if maximum_delta_pa is None else 0.0,
                maximum_delta_pa,
            ),
        ),
    )

    with pytest.raises(
        RuntimeError,
        match=expected_context,
    ):
        solve_room_pressure_network(network)


@pytest.mark.parametrize("bad_value", [True, "100.0"])
def test_parser_rejects_non_numeric_engineering_scalars(
    bad_value: object,
) -> None:
    with pytest.raises(ValueError, match="must be a finite number"):
        pressure_network_from_dict(
            {
                "name": "Strict numeric input",
                "nodes": [
                    {
                        "name": "Room",
                        "supply_m3_h": bad_value,
                    },
                    {
                        "name": "Outside",
                        "fixed_pressure_pa": 0.0,
                    },
                ],
                "paths": [
                    {
                        "name": "Leak",
                        "start_node": "Room",
                        "end_node": "Outside",
                        "kind": "crack",
                        "model": "power_law",
                        "coefficient_m3_s_pa_n": 0.01,
                        "exponent": 1.0,
                    }
                ],
            }
        )


def test_initial_pressure_mean_avoids_finite_input_overflow() -> None:
    network = RoomPressureNetwork(
        name="Large finite fixed pressures",
        nodes=(
            PressureNode("Room"),
            PressureNode("Boundary A", fixed_pressure_pa=1e308),
            PressureNode("Boundary B", fixed_pressure_pa=1e308),
        ),
        paths=(
            PressurePath(
                "Room-Boundary A",
                "Room",
                "Boundary A",
                "crack",
                "power_law",
                coefficient_m3_s_pa_n=0.01,
                exponent=1.0,
            ),
        ),
    )

    result = solve_room_pressure_network(network)
    room = next(
        item for item in result["nodes"] if item["name"] == "Room"
    )

    assert math.isfinite(room["pressure_pa"])
    assert room["pressure_pa"] == pytest.approx(1e308)
    assert result["solver"]["iterations"] == 0


def test_zero_flow_dominant_path_is_not_reported_as_inflow() -> None:
    network = RoomPressureNetwork(
        name="Zero-flow room",
        nodes=(
            PressureNode("Room"),
            PressureNode("Outside", fixed_pressure_pa=0.0),
        ),
        paths=(
            PressurePath(
                "Leak",
                "Room",
                "Outside",
                "crack",
                "power_law",
                coefficient_m3_s_pa_n=0.01,
                exponent=1.0,
            ),
        ),
    )

    result = solve_room_pressure_network(network)
    room = next(
        item for item in result["nodes"] if item["name"] == "Room"
    )

    assert room["dominant_pressure_path"]["airflow_m3_h"] == 0.0
    assert room["dominant_pressure_path"]["direction"] == "zero flow"
