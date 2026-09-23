import pytest

from cleanroomx.branched_duct import (
    BranchedDuctNetwork,
    DuctBranch,
    DuctTerminal,
    analyze_branched_duct_network,
)
from cleanroomx.hvac import analyze_hvac_project
from cleanroomx.hvac_io import hvac_project_from_dict


def demo_network() -> BranchedDuctNetwork:
    return BranchedDuctNetwork(
        root_node="AHU",
        branches=(
            DuctBranch(
                "Main trunk", "AHU", "J1", 18.0, 0.02, 1.2, 1.8,
                width_m=0.8, height_m=0.45,
            ),
            DuctBranch(
                "Process branch", "J1", "Process terminal", 12.0, 0.021, 1.2, 2.4,
                diameter_m=0.5,
            ),
            DuctBranch(
                "Gowning branch", "J1", "Gowning terminal", 10.0, 0.021, 1.2, 2.0,
                width_m=0.4, height_m=0.25,
            ),
        ),
        terminals=(
            DuctTerminal("Process Bay", "Process terminal"),
            DuctTerminal("Gowning", "Gowning terminal"),
        ),
    )


def test_branch_airflow_is_sum_of_downstream_terminal_demands() -> None:
    result = analyze_branched_duct_network(
        demo_network(),
        {"Process Bay": 3600.0, "Gowning": 900.0},
    )
    flows = {
        branch["name"]: branch["airflow_m3_h"]
        for branch in result["branches"]
    }

    assert result["root_airflow_m3_h"] == 4500.0
    assert flows == {
        "Main trunk": 4500.0,
        "Process branch": 3600.0,
        "Gowning branch": 900.0,
    }
    assert result["critical_terminal_room"] == "Process Bay"
    assert result["critical_path"] == "Main trunk -> Process branch"
    assert result["critical_path_pressure_drop_pa"] == pytest.approx(
        62.7368, abs=1e-4
    )


def test_terminal_airflow_mapping_must_match_all_terminals() -> None:
    with pytest.raises(ValueError, match="missing: Gowning"):
        analyze_branched_duct_network(
            demo_network(),
            {"Process Bay": 3600.0},
        )

    with pytest.raises(ValueError, match="unexpected: Other"):
        analyze_branched_duct_network(
            demo_network(),
            {
                "Process Bay": 3600.0,
                "Gowning": 900.0,
                "Other": 100.0,
            },
        )


def test_multiple_incoming_branches_are_rejected() -> None:
    with pytest.raises(ValueError, match="exactly one incoming"):
        BranchedDuctNetwork(
            root_node="AHU",
            branches=(
                DuctBranch(
                    "A", "AHU", "T", 1.0, 0.02, 1.2, diameter_m=0.3
                ),
                DuctBranch(
                    "B", "AHU", "T", 1.0, 0.02, 1.2, diameter_m=0.3
                ),
            ),
            terminals=(DuctTerminal("Room", "T"),),
        )


def test_every_leaf_requires_a_terminal() -> None:
    with pytest.raises(ValueError, match="one-to-one"):
        BranchedDuctNetwork(
            root_node="AHU",
            branches=(
                DuctBranch(
                    "A", "AHU", "T1", 1.0, 0.02, 1.2, diameter_m=0.3
                ),
                DuctBranch(
                    "B", "AHU", "T2", 1.0, 0.02, 1.2, diameter_m=0.3
                ),
            ),
            terminals=(DuctTerminal("Room 1", "T1"),),
        )


def test_disconnected_subnetwork_is_rejected() -> None:
    with pytest.raises(ValueError, match="connected to root_node"):
        BranchedDuctNetwork(
            root_node="AHU",
            branches=(
                DuctBranch(
                    "Connected", "AHU", "T1", 1.0, 0.02, 1.2,
                    diameter_m=0.3,
                ),
                DuctBranch(
                    "Cycle A", "N3", "N2", 1.0, 0.02, 1.2,
                    diameter_m=0.3,
                ),
                DuctBranch(
                    "Cycle B", "N2", "N3", 1.0, 0.02, 1.2,
                    diameter_m=0.3,
                ),
            ),
            terminals=(DuctTerminal("Room 1", "T1"),),
        )


def test_hvac_uses_branch_solver_for_fan_duty() -> None:
    project = hvac_project_from_dict(
        {
            "name": "Integrated branch network",
            "fan_system": {
                "name": "Supply AHU",
                "duct_pressure_drop_pa": 999.0,
                "coil_pressure_drop_pa": 180.0,
                "other_pressure_drop_pa": 90.0,
                "fan_efficiency": 0.68,
                "motor_efficiency": 0.92,
            },
            "branched_duct_network": {
                "root_node": "AHU",
                "branches": [
                    {
                        "name": "Main trunk",
                        "parent_node": "AHU",
                        "child_node": "J1",
                        "length_m": 18.0,
                        "friction_factor": 0.02,
                        "air_density_kg_m3": 1.2,
                        "local_loss_coefficient": 1.8,
                        "width_m": 0.8,
                        "height_m": 0.45,
                    },
                    {
                        "name": "Process branch",
                        "parent_node": "J1",
                        "child_node": "Process terminal",
                        "length_m": 12.0,
                        "friction_factor": 0.021,
                        "air_density_kg_m3": 1.2,
                        "local_loss_coefficient": 2.4,
                        "diameter_m": 0.5,
                    },
                    {
                        "name": "Gowning branch",
                        "parent_node": "J1",
                        "child_node": "Gowning terminal",
                        "length_m": 10.0,
                        "friction_factor": 0.021,
                        "air_density_kg_m3": 1.2,
                        "local_loss_coefficient": 2.0,
                        "width_m": 0.4,
                        "height_m": 0.25,
                    },
                ],
                "terminals": [
                    {"room_name": "Process Bay", "node": "Process terminal"},
                    {"room_name": "Gowning", "node": "Gowning terminal"},
                ],
            },
            "rooms": [
                {
                    "name": "Process Bay",
                    "cleanroom_airflow_m3_h": 3600.0,
                    "thermal_design": {
                        "room_air": {
                            "dry_bulb_c": 22.0,
                            "relative_humidity_percent": 45.0,
                        }
                    },
                },
                {
                    "name": "Gowning",
                    "cleanroom_airflow_m3_h": 900.0,
                    "thermal_design": {
                        "room_air": {
                            "dry_bulb_c": 22.0,
                            "relative_humidity_percent": 45.0,
                        }
                    },
                },
            ],
        }
    )

    result = analyze_hvac_project(project)
    network = result["branched_duct_network"]

    assert network["root_airflow_m3_h"] == 4500.0
    assert network["critical_path_pressure_drop_pa"] == pytest.approx(
        62.7368, abs=1e-4
    )
    assert result["supply_fan"]["airflow_m3_h"] == 4500.0
    assert result["supply_fan"]["pressure_components_pa"]["duct"] == pytest.approx(
        62.737, abs=1e-3
    )
    assert result["supply_fan"]["duct_pressure_drop_source"] == (
        "computed_branched_duct_network"
    )
    assert result["supply_fan"]["total_static_pressure_pa"] == pytest.approx(
        332.737, abs=1e-3
    )


def test_legacy_and_branched_networks_cannot_be_used_together() -> None:
    with pytest.raises(ValueError, match="not both"):
        hvac_project_from_dict(
            {
                "name": "Ambiguous",
                "duct_network": {
                    "paths": [
                        {
                            "name": "Legacy",
                            "sections": [
                                {
                                    "name": "S1",
                                    "length_m": 1.0,
                                    "airflow_m3_h": 100.0,
                                    "friction_factor": 0.02,
                                    "air_density_kg_m3": 1.2,
                                    "diameter_m": 0.3,
                                }
                            ],
                        }
                    ]
                },
                "branched_duct_network": {
                    "root_node": "AHU",
                    "branches": [
                        {
                            "name": "B1",
                            "parent_node": "AHU",
                            "child_node": "T",
                            "length_m": 1.0,
                            "friction_factor": 0.02,
                            "air_density_kg_m3": 1.2,
                            "diameter_m": 0.3,
                        }
                    ],
                    "terminals": [{"room_name": "Room", "node": "T"}],
                },
                "rooms": [
                    {
                        "name": "Room",
                        "cleanroom_airflow_m3_h": 100.0,
                        "thermal_design": {
                            "room_air": {
                                "dry_bulb_c": 22.0,
                                "relative_humidity_percent": 45.0,
                            }
                        },
                    }
                ],
            }
        )
