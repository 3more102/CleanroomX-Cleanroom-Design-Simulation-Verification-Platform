import pytest

from cleanroomx.fan_curve import FanCurve, FanCurvePoint
from cleanroomx.fan_loop_network import (
    FanDrivenLoopNetworkStudy,
    derive_equivalent_loop_resistance,
    solve_fan_driven_loop_network,
)
from cleanroomx.fan_loop_network_io import fan_driven_loop_network_study_from_dict
from cleanroomx.fan_loop_network_report import markdown_fan_driven_loop_network_report
from cleanroomx.loop_network import LoopedFlowNetwork, QuadraticFlowEdge


def _reference_loop(reference_airflow_m3_h: float = 3600.0) -> LoopedFlowNetwork:
    return LoopedFlowNetwork(
        name="Equal-path loop",
        node_injections_m3_h={
            "Source": reference_airflow_m3_h,
            "Mid": 0.0,
            "Sink": -reference_airflow_m3_h,
        },
        edges=(
            QuadraticFlowEdge("Direct", "Source", "Sink", 200.0),
            QuadraticFlowEdge("Upper 1", "Source", "Mid", 100.0),
            QuadraticFlowEdge("Upper 2", "Mid", "Sink", 100.0),
        ),
        reference_node="Sink",
    )


def _matching_fan() -> FanCurve:
    return FanCurve(
        name="Matching fan",
        points=(
            FanCurvePoint(0.0, 100.0),
            FanCurvePoint(3600.0, 50.0),
            FanCurvePoint(7200.0, 0.0),
        ),
    )


def _study(reference_airflow_m3_h: float = 3600.0) -> FanDrivenLoopNetworkStudy:
    return FanDrivenLoopNetworkStudy(
        name="Fan loop study",
        fan_curve=_matching_fan(),
        fixed_pressure_pa=0.0,
        reference_network=_reference_loop(reference_airflow_m3_h),
        source_node="Source",
        sink_node="Sink",
    )


def test_equivalent_loop_resistance_matches_analytical_parallel_paths() -> None:
    result = derive_equivalent_loop_resistance(_study())

    assert result["reference_network_pressure_pa"] == pytest.approx(50.0)
    assert result["equivalent_network_resistance_pa_per_m3_s_squared"] == pytest.approx(
        50.0
    )


def test_equivalent_resistance_is_reference_flow_invariant() -> None:
    high = derive_equivalent_loop_resistance(_study(3600.0))
    low = derive_equivalent_loop_resistance(_study(1800.0))

    assert high["equivalent_network_resistance_pa_per_m3_s_squared"] == pytest.approx(
        low["equivalent_network_resistance_pa_per_m3_s_squared"],
        abs=1e-8,
    )


def test_fan_loop_operating_point_resolves_full_mesh_and_closes_pressure() -> None:
    result = solve_fan_driven_loop_network(_study())

    assert result["status"] == "solved"
    assert result["fan_operating_point"]["airflow_m3_h"] == pytest.approx(3600.0)
    assert result["system_pressure_check"]["loop_network_pressure_pa"] == pytest.approx(
        50.0
    )
    assert abs(result["system_pressure_check"]["fan_minus_system_pressure_pa"]) <= 1e-6
    assert (
        abs(result["system_pressure_check"]["loop_minus_equivalent_pressure_pa"])
        <= 1e-6
    )
    assert (
        result["operating_network_solution"]["max_abs_mass_balance_residual_m3_h"]
        <= 1e-6
    )


def test_no_intersection_returns_no_operating_network() -> None:
    study = FanDrivenLoopNetworkStudy(
        name="No intersection",
        fan_curve=FanCurve(
            name="Low fan",
            points=(
                FanCurvePoint(0.0, 40.0),
                FanCurvePoint(3600.0, 20.0),
            ),
        ),
        fixed_pressure_pa=50.0,
        reference_network=_reference_loop(),
        source_node="Source",
        sink_node="Sink",
    )

    result = solve_fan_driven_loop_network(study)

    assert result["status"] == "no_intersection_in_supplied_range"
    assert result["fan_operating_point"] is None
    assert result["operating_network_solution"] is None
    assert result["system_pressure_check"] is None


def test_study_rejects_nonzero_interior_injection() -> None:
    network = LoopedFlowNetwork(
        name="Distributed injection",
        node_injections_m3_h={
            "Source": 1000.0,
            "Mid": 100.0,
            "Sink": -1100.0,
        },
        edges=(
            QuadraticFlowEdge("SM", "Source", "Mid", 100.0),
            QuadraticFlowEdge("MT", "Mid", "Sink", 100.0),
        ),
        reference_node="Sink",
    )

    with pytest.raises(ValueError, match="zero injection"):
        FanDrivenLoopNetworkStudy(
            name="Invalid distributed study",
            fan_curve=_matching_fan(),
            fixed_pressure_pa=0.0,
            reference_network=network,
            source_node="Source",
            sink_node="Sink",
        )


def test_loader_supports_mixed_explicit_and_geometry_derived_edges() -> None:
    study = fan_driven_loop_network_study_from_dict(
        {
            "name": "Mixed edge fan loop",
            "source_node": "Source",
            "sink_node": "Sink",
            "network_reference_airflow_m3_h": 3600.0,
            "fixed_pressure_pa": 0.0,
            "fan_curve": {
                "name": "Mixed-edge fan",
                "points": [
                    {"airflow_m3_h": 0.0, "pressure_pa": 100.0},
                    {"airflow_m3_h": 3600.0, "pressure_pa": 25.0},
                    {"airflow_m3_h": 7200.0, "pressure_pa": 0.0},
                ],
            },
            "loop_network": {
                "name": "Two-edge parallel network",
                "reference_node": "Sink",
                "edges": [
                    {
                        "name": "Explicit path",
                        "start_node": "Source",
                        "end_node": "Sink",
                        "resistance_pa_per_m3_s_squared": 100.0,
                    },
                    {
                        "name": "Geometry path",
                        "start_node": "Source",
                        "end_node": "Sink",
                        "duct_geometry": {
                            "length_m": 0.0,
                            "air_density_kg_m3": 2.0,
                            "friction_factor": 0.0,
                            "local_loss_coefficient": 100.0,
                            "width_m": 1.0,
                            "height_m": 1.0,
                        },
                    },
                ],
            },
        }
    )

    result = solve_fan_driven_loop_network(study)
    edge_basis = {
        edge["name"]: edge["resistance_basis"]
        for edge in result["operating_network_solution"]["edges"]
    }

    assert result["status"] == "solved"
    assert result["equivalent_loop_network"][
        "equivalent_network_resistance_pa_per_m3_s_squared"
    ] == pytest.approx(25.0)
    assert edge_basis["Explicit path"] == "explicit"
    assert edge_basis["Geometry path"] == "duct_geometry"


def test_loader_rejects_embedded_node_injections() -> None:
    with pytest.raises(ValueError, match="owns the source/sink injection pattern"):
        fan_driven_loop_network_study_from_dict(
            {
                "name": "Bad input",
                "source_node": "A",
                "sink_node": "B",
                "fan_curve": {
                    "name": "Fan",
                    "points": [
                        {"airflow_m3_h": 0.0, "pressure_pa": 100.0},
                        {"airflow_m3_h": 1000.0, "pressure_pa": 0.0},
                    ],
                },
                "loop_network": {
                    "node_injections_m3_h": {"A": 1.0, "B": -1.0},
                    "edges": [],
                },
            }
        )


def test_markdown_report_contains_network_closure_evidence() -> None:
    report = markdown_fan_driven_loop_network_report(
        solve_fan_driven_loop_network(_study())
    )

    assert "Equivalent loop resistance" in report
    assert "Loop − equivalent-network residual" in report
    assert "Operating network edges" in report
