import pytest

from cleanroomx.fan_curve import FanCurve, FanCurvePoint
from cleanroomx.fan_loop_network import (
    FanLoopNetworkStudy,
    derive_loop_equivalent_resistance,
    solve_fan_loop_network,
)
from cleanroomx.fan_loop_network_io import fan_loop_network_study_from_dict
from cleanroomx.fan_loop_network_report import markdown_fan_loop_network_report
from cleanroomx.loop_network import LoopedFlowNetwork, QuadraticFlowEdge


def _reference_loop() -> LoopedFlowNetwork:
    return LoopedFlowNetwork(
        name="Reference two-path loop",
        node_injections_m3_h={
            "Supply": 3600.0,
            "Mid": 0.0,
            "Return": -3600.0,
        },
        edges=(
            QuadraticFlowEdge("Direct", "Supply", "Return", 500.0),
            QuadraticFlowEdge("Upper 1", "Supply", "Mid", 250.0),
            QuadraticFlowEdge("Upper 2", "Mid", "Return", 250.0),
        ),
        reference_node="Supply",
    )


def _fan_curve() -> FanCurve:
    return FanCurve(
        name="Reference fan",
        points=(
            FanCurvePoint(0.0, 500.0),
            FanCurvePoint(3600.0, 125.0),
            FanCurvePoint(7200.0, 0.0),
        ),
    )


def _study(*, fixed_pressure_pa: float = 0.0) -> FanLoopNetworkStudy:
    return FanLoopNetworkStudy(
        name="Fan loop study",
        fan_curve=_fan_curve(),
        loop_network=_reference_loop(),
        fan_discharge_node="Supply",
        fan_suction_node="Return",
        fixed_pressure_pa=fixed_pressure_pa,
    )


def test_reference_loop_derives_exact_two_terminal_resistance() -> None:
    resistance, reference = derive_loop_equivalent_resistance(_study())
    assert resistance == pytest.approx(125.0, abs=1e-8)
    assert reference["max_abs_mass_balance_residual_m3_h"] <= 1e-6


def test_fan_loop_operating_point_resolves_full_network() -> None:
    result = solve_fan_loop_network(_study())
    assert result["status"] == "solved"
    assert result["fan_operating_point"]["airflow_m3_h"] == pytest.approx(
        3600.0, abs=1e-3
    )
    assert result["equivalent_loop_resistance_pa_per_m3_s_squared"] == pytest.approx(
        125.0, abs=1e-8
    )
    flows = {
        edge["name"]: edge["airflow_m3_h"]
        for edge in result["operating_network_solution"]["edges"]
    }
    assert flows["Direct"] == pytest.approx(1800.0, abs=1e-5)
    assert flows["Upper 1"] == pytest.approx(1800.0, abs=1e-5)
    assert flows["Upper 2"] == pytest.approx(1800.0, abs=1e-5)
    assert abs(result["system_pressure_check"]["fan_minus_system_pressure_pa"]) <= 1e-6
    assert abs(result["system_pressure_check"]["network_pressure_residual_pa"]) <= 1e-6


def test_no_bounded_fan_intersection_preserves_reference_evidence() -> None:
    result = solve_fan_loop_network(_study(fixed_pressure_pa=600.0))
    assert result["status"] == "no_intersection_in_supplied_range"
    assert result["fan_operating_point"] is None
    assert result["operating_network_solution"] is None
    assert result["system_pressure_check"] is None
    assert result["reference_network_solution"]["status"] == "solved"


def test_coupling_rejects_nonzero_third_party_injection() -> None:
    network = LoopedFlowNetwork(
        name="Three-terminal reference",
        node_injections_m3_h={
            "Supply": 3600.0,
            "Process": -1000.0,
            "Return": -2600.0,
        },
        edges=(
            QuadraticFlowEdge("SP", "Supply", "Process", 100.0),
            QuadraticFlowEdge("PR", "Process", "Return", 100.0),
            QuadraticFlowEdge("SR", "Supply", "Return", 200.0),
        ),
        reference_node="Supply",
    )
    with pytest.raises(ValueError, match="zero injection"):
        FanLoopNetworkStudy(
            name="Unsupported multi-terminal fan loop",
            fan_curve=_fan_curve(),
            loop_network=network,
            fan_discharge_node="Supply",
            fan_suction_node="Return",
        )


def test_loader_reuses_v025_geometry_derived_edge_inputs() -> None:
    data = {
        "name": "Loaded fan loop",
        "fan_discharge_node": "Supply",
        "fan_suction_node": "Return",
        "fixed_pressure_pa": 0.0,
        "fan_curve": {
            "name": "Loaded fan",
            "points": [
                {"airflow_m3_h": 0.0, "pressure_pa": 500.0},
                {"airflow_m3_h": 7200.0, "pressure_pa": 0.0}
            ]
        },
        "loop_network": {
            "name": "Geometry loop",
            "reference_node": "Supply",
            "node_injections_m3_h": {
                "Supply": 3600.0,
                "Return": -3600.0
            },
            "edges": [
                {
                    "name": "Geometry edge",
                    "start_node": "Supply",
                    "end_node": "Return",
                    "duct_geometry": {
                        "length_m": 0.0,
                        "air_density_kg_m3": 1.0,
                        "friction_factor": 0.0,
                        "local_loss_coefficient": 2.0,
                        "width_m": 1.0,
                        "height_m": 1.0
                    }
                }
            ]
        }
    }
    study = fan_loop_network_study_from_dict(data)
    result = solve_fan_loop_network(study)
    assert study.loop_network.edges[0].resistance_basis == "duct_geometry"
    assert result["status"] == "solved"
    assert result["operating_network_solution"]["edges"][0][
        "resistance_basis"
    ] == "duct_geometry"


def test_markdown_report_surfaces_network_and_fan_residuals() -> None:
    result = solve_fan_loop_network(_study())
    report = markdown_fan_loop_network_report(result)
    assert "Fan/Loop-Network Report" in report
    assert "Equivalent loop resistance" in report
    assert "Equivalent-network residual" in report
    assert "Solved loop edges" in report
