import pytest

from cleanroomx.branch_network import (
    BranchDuct,
    BranchFlowNetwork,
    TerminalDemand,
    analyze_branch_flow_network,
)
from cleanroomx.hvac import analyze_hvac_project
from cleanroomx.hvac_io import hvac_project_from_dict


def _network() -> BranchFlowNetwork:
    return BranchFlowNetwork(
        source_node="AHU",
        branches=(
            BranchDuct(
                name="Main",
                upstream_node="AHU",
                downstream_node="J1",
                length_m=12,
                friction_factor=0.02,
                air_density_kg_m3=1.2,
                local_loss_coefficient=1.0,
                width_m=0.6,
                height_m=0.4,
            ),
            BranchDuct(
                name="Process branch",
                upstream_node="J1",
                downstream_node="Process",
                length_m=8,
                friction_factor=0.02,
                air_density_kg_m3=1.2,
                local_loss_coefficient=2.0,
                width_m=0.4,
                height_m=0.3,
            ),
            BranchDuct(
                name="Gowning branch",
                upstream_node="J1",
                downstream_node="Gowning",
                length_m=6,
                friction_factor=0.02,
                air_density_kg_m3=1.2,
                local_loss_coefficient=1.5,
                width_m=0.3,
                height_m=0.25,
            ),
        ),
        terminal_demands=(
            TerminalDemand("Process", 1800),
            TerminalDemand("Gowning", 600),
        ),
    )


def test_branch_flows_are_propagated_from_terminal_demands() -> None:
    result = analyze_branch_flow_network(_network())
    by_name = {branch["name"]: branch for branch in result["branches"]}

    assert result["source_airflow_m3_h"] == 2400
    assert by_name["Main"]["airflow_m3_h"] == 2400
    assert by_name["Process branch"]["airflow_m3_h"] == 1800
    assert by_name["Gowning branch"]["airflow_m3_h"] == 600
    assert result["max_abs_continuity_residual_m3_h"] == 0


def test_terminal_pressure_paths_share_upstream_loss() -> None:
    result = analyze_branch_flow_network(_network())
    terminals = {terminal["node"]: terminal for terminal in result["terminals"]}

    assert terminals["Process"]["branch_path"] == ["Main", "Process branch"]
    assert terminals["Gowning"]["branch_path"] == ["Main", "Gowning branch"]
    assert result["critical_terminal"] in {"Process", "Gowning"}
    assert result["critical_path_pressure_drop_pa"] == max(
        terminal["total_pressure_drop_pa"] for terminal in result["terminals"]
    )


def test_network_rejects_missing_leaf_demand() -> None:
    with pytest.raises(ValueError, match="leaf nodes without terminal demand"):
        BranchFlowNetwork(
            source_node="AHU",
            branches=(
                BranchDuct(
                    name="A",
                    upstream_node="AHU",
                    downstream_node="Room",
                    length_m=2,
                    friction_factor=0.02,
                    air_density_kg_m3=1.2,
                    diameter_m=0.25,
                ),
            ),
            terminal_demands=(TerminalDemand("Other", 100),),
        )


def test_network_rejects_multiple_incoming_branches() -> None:
    with pytest.raises(ValueError, match="more than one incoming"):
        BranchFlowNetwork(
            source_node="AHU",
            branches=(
                BranchDuct(
                    "A", "AHU", "J", 2, 0.02, 1.2, diameter_m=0.25
                ),
                BranchDuct(
                    "B", "AHU", "Room", 2, 0.02, 1.2, diameter_m=0.25
                ),
                BranchDuct(
                    "C", "J", "Room", 2, 0.02, 1.2, diameter_m=0.25
                ),
            ),
            terminal_demands=(TerminalDemand("Room", 100),),
        )


def test_hvac_integrates_branch_flow_critical_path() -> None:
    project = hvac_project_from_dict(
        {
            "name": "Branch Flow HVAC",
            "fan_system": {
                "name": "AHU",
                "coil_pressure_drop_pa": 100,
                "other_pressure_drop_pa": 50,
                "fan_efficiency": 0.7,
                "motor_efficiency": 0.9,
            },
            "branch_flow_network": {
                "source_node": "AHU",
                "branches": [
                    {
                        "name": "Main",
                        "upstream_node": "AHU",
                        "downstream_node": "Process",
                        "length_m": 10,
                        "friction_factor": 0.02,
                        "air_density_kg_m3": 1.2,
                        "local_loss_coefficient": 1.0,
                        "width_m": 0.5,
                        "height_m": 0.3,
                    }
                ],
                "terminal_demands": [
                    {"node": "Process", "airflow_m3_h": 900}
                ],
            },
            "rooms": [
                {
                    "name": "Process",
                    "cleanroom_airflow_m3_h": 900,
                    "thermal_design": {
                        "room_air": {
                            "dry_bulb_c": 22,
                            "relative_humidity_percent": 45,
                        }
                    },
                }
            ],
        }
    )

    result = analyze_hvac_project(project)

    network = result["branch_flow_network"]
    assert network["source_airflow_m3_h"] == 900
    assert network["critical_terminal"] == "Process"
    assert result["supply_fan"]["pressure_components_pa"]["duct"] == pytest.approx(
        network["critical_path_pressure_drop_pa"], abs=0.001
    )


def test_hvac_rejects_branch_flow_total_that_differs_from_governing_airflow() -> None:
    project = hvac_project_from_dict(
        {
            "name": "Mismatch",
            "branch_flow_network": {
                "source_node": "AHU",
                "branches": [
                    {
                        "name": "Main",
                        "upstream_node": "AHU",
                        "downstream_node": "Process",
                        "length_m": 10,
                        "friction_factor": 0.02,
                        "air_density_kg_m3": 1.2,
                        "diameter_m": 0.3,
                    }
                ],
                "terminal_demands": [
                    {"node": "Process", "airflow_m3_h": 800}
                ],
            },
            "rooms": [
                {
                    "name": "Process",
                    "cleanroom_airflow_m3_h": 900,
                    "thermal_design": {
                        "room_air": {
                            "dry_bulb_c": 22,
                            "relative_humidity_percent": 45,
                        }
                    },
                }
            ],
        }
    )

    with pytest.raises(ValueError, match="source airflow must match"):
        analyze_hvac_project(project)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_terminal_airflow_must_be_finite(value: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        TerminalDemand("Process", value)
