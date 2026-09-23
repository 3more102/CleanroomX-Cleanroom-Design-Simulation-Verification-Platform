import pytest

from cleanroomx.branch_network import (
    BranchDuct,
    BranchFlowNetwork,
    RoomTerminal,
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
                downstream_node="T_Process",
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
                downstream_node="T_Gowning",
                length_m=6,
                friction_factor=0.02,
                air_density_kg_m3=1.2,
                local_loss_coefficient=1.5,
                width_m=0.3,
                height_m=0.25,
            ),
        ),
        terminals=(
            RoomTerminal("T_Process", "Process"),
            RoomTerminal("T_Gowning", "Gowning"),
        ),
    )


def test_branch_flows_are_propagated_from_room_demands() -> None:
    result = analyze_branch_flow_network(
        _network(),
        {"Process": 1800.0, "Gowning": 600.0},
    )
    by_name = {branch["name"]: branch for branch in result["branches"]}

    assert result["source_airflow_m3_h"] == 2400
    assert result["terminal_airflow_source"] == "hvac_room_governing_airflow"
    assert by_name["Main"]["airflow_m3_h"] == 2400
    assert by_name["Process branch"]["airflow_m3_h"] == 1800
    assert by_name["Gowning branch"]["airflow_m3_h"] == 600
    assert result["max_abs_continuity_residual_m3_h"] == 0


def test_terminal_pressure_paths_share_upstream_loss() -> None:
    result = analyze_branch_flow_network(
        _network(),
        {"Process": 1800.0, "Gowning": 600.0},
    )
    terminals = {
        terminal["room_name"]: terminal for terminal in result["terminals"]
    }

    assert terminals["Process"]["branch_path"] == ["Main", "Process branch"]
    assert terminals["Gowning"]["branch_path"] == ["Main", "Gowning branch"]
    assert result["critical_room"] in {"Process", "Gowning"}
    assert result["critical_path_pressure_drop_pa"] == max(
        terminal["total_pressure_drop_pa"] for terminal in result["terminals"]
    )


def test_network_rejects_missing_leaf_terminal() -> None:
    with pytest.raises(ValueError, match="leaf nodes without terminal mapping"):
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
            terminals=(RoomTerminal("Other", "Process"),),
        )


def test_network_rejects_multiple_incoming_branches() -> None:
    with pytest.raises(ValueError, match="more than one incoming"):
        BranchFlowNetwork(
            source_node="AHU",
            branches=(
                BranchDuct("A", "AHU", "J", 2, 0.02, 1.2, diameter_m=0.25),
                BranchDuct("B", "AHU", "Room", 2, 0.02, 1.2, diameter_m=0.25),
                BranchDuct("C", "J", "Room", 2, 0.02, 1.2, diameter_m=0.25),
            ),
            terminals=(RoomTerminal("Room", "Process"),),
        )


def test_network_rejects_duplicate_room_mapping() -> None:
    with pytest.raises(ValueError, match="room_name values must be unique"):
        BranchFlowNetwork(
            source_node="AHU",
            branches=(
                BranchDuct("A", "AHU", "R1", 2, 0.02, 1.2, diameter_m=0.25),
                BranchDuct("B", "AHU", "R2", 2, 0.02, 1.2, diameter_m=0.25),
            ),
            terminals=(
                RoomTerminal("R1", "Process"),
                RoomTerminal("R2", "Process"),
            ),
        )


def test_analyzer_requires_exact_room_terminal_mapping() -> None:
    with pytest.raises(ValueError, match="missing room airflow: Gowning"):
        analyze_branch_flow_network(
            _network(),
            {"Process": 1800.0},
        )


def test_hvac_uses_computed_governing_room_airflow_as_terminal_demand() -> None:
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
                        "downstream_node": "T_Process",
                        "length_m": 10,
                        "friction_factor": 0.02,
                        "air_density_kg_m3": 1.2,
                        "local_loss_coefficient": 1.0,
                        "width_m": 0.5,
                        "height_m": 0.3,
                    }
                ],
                "terminals": [
                    {"node": "T_Process", "room_name": "Process"}
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
                        },
                        "outdoor_air": {
                            "dry_bulb_c": 35,
                            "relative_humidity_percent": 45,
                        },
                        "makeup_air_m3_h": 1000,
                    },
                }
            ],
        }
    )

    result = analyze_hvac_project(project)
    network = result["branch_flow_network"]

    assert result["rooms"][0]["governing_airflow_m3_h"] == 1000
    assert result["rooms"][0]["thermal"]["governing_airflow_basis"] == "makeup_air"
    assert network["source_airflow_m3_h"] == 1000
    assert network["terminals"][0]["airflow_m3_h"] == 1000
    assert network["critical_room"] == "Process"
    assert result["supply_fan"]["pressure_components_pa"]["duct"] == pytest.approx(
        network["critical_path_pressure_drop_pa"], abs=0.001
    )
    assert (
        result["supply_fan"]["duct_pressure_drop_source"]
        == "computed_branch_flow_network"
    )


def test_hvac_rejects_room_without_terminal_mapping() -> None:
    project = hvac_project_from_dict(
        {
            "name": "Mismatch",
            "branch_flow_network": {
                "source_node": "AHU",
                "branches": [
                    {
                        "name": "Main",
                        "upstream_node": "AHU",
                        "downstream_node": "T_Process",
                        "length_m": 10,
                        "friction_factor": 0.02,
                        "air_density_kg_m3": 1.2,
                        "diameter_m": 0.3,
                    }
                ],
                "terminals": [
                    {"node": "T_Process", "room_name": "Process"}
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
                },
                {
                    "name": "Gowning",
                    "cleanroom_airflow_m3_h": 300,
                    "thermal_design": {
                        "room_air": {
                            "dry_bulb_c": 22,
                            "relative_humidity_percent": 45,
                        }
                    },
                },
            ],
        }
    )

    with pytest.raises(ValueError, match="rooms without terminal mapping: Gowning"):
        analyze_hvac_project(project)
