import pytest

from cleanroomx.duct_tree import (
    DuctTreeNetwork,
    DuctTreeSection,
    TerminalAirflowDemand,
    analyze_duct_tree_network,
)
from cleanroomx.hvac import analyze_hvac_project
from cleanroomx.hvac_io import hvac_project_from_dict


def _tree() -> DuctTreeNetwork:
    return DuctTreeNetwork(
        root_node="AHU",
        sections=(
            DuctTreeSection(
                name="Main",
                from_node="AHU",
                to_node="J1",
                length_m=10,
                friction_factor=0.02,
                air_density_kg_m3=1.2,
                local_loss_coefficient=1.0,
                width_m=0.5,
                height_m=0.3,
            ),
            DuctTreeSection(
                name="Process branch",
                from_node="J1",
                to_node="Process",
                length_m=12,
                friction_factor=0.02,
                air_density_kg_m3=1.2,
                local_loss_coefficient=2.0,
                width_m=0.4,
                height_m=0.25,
            ),
            DuctTreeSection(
                name="Gowning branch",
                from_node="J1",
                to_node="Gowning",
                length_m=6,
                friction_factor=0.02,
                air_density_kg_m3=1.2,
                local_loss_coefficient=1.0,
                width_m=0.35,
                height_m=0.25,
            ),
        ),
        terminal_demands=(
            TerminalAirflowDemand("Process", 1000),
            TerminalAirflowDemand("Gowning", 500),
        ),
    )


def test_tree_aggregates_terminal_demands_upstream() -> None:
    result = analyze_duct_tree_network(_tree())
    flows = {section["name"]: section["airflow_m3_h"] for section in result["sections"]}
    assert result["root_airflow_m3_h"] == 1500
    assert flows["Main"] == 1500
    assert flows["Process branch"] == 1000
    assert flows["Gowning branch"] == 500
    assert all(
        balance["balance_residual_m3_h"] == pytest.approx(0.0, abs=1e-9)
        for balance in result["node_balances"]
    )


def test_tree_reports_terminal_paths_and_critical_path() -> None:
    result = analyze_duct_tree_network(_tree())
    paths = {item["terminal_node"]: item for item in result["terminal_paths"]}
    assert paths["Process"]["sections"] == ["Main", "Process branch"]
    assert paths["Gowning"]["sections"] == ["Main", "Gowning branch"]
    assert result["critical_terminal_node"] == "Process"
    assert result["critical_path_pressure_drop_pa"] == paths["Process"]["total_pressure_drop_pa"]


def test_tree_rejects_multiple_parents() -> None:
    with pytest.raises(ValueError, match="more than one incoming"):
        DuctTreeNetwork(
            root_node="AHU",
            sections=(
                DuctTreeSection(
                    "A", "AHU", "X", 1, 0.02, 1.2, diameter_m=0.3
                ),
                DuctTreeSection(
                    "B", "AHU", "Y", 1, 0.02, 1.2, diameter_m=0.3
                ),
                DuctTreeSection(
                    "C", "Y", "X", 1, 0.02, 1.2, diameter_m=0.3
                ),
            ),
            terminal_demands=(TerminalAirflowDemand("X", 100),),
        )


def test_tree_requires_demand_at_every_leaf() -> None:
    with pytest.raises(ValueError, match="every duct-tree leaf"):
        DuctTreeNetwork(
            root_node="AHU",
            sections=(
                DuctTreeSection(
                    "A", "AHU", "X", 1, 0.02, 1.2, diameter_m=0.3
                ),
                DuctTreeSection(
                    "B", "AHU", "Y", 1, 0.02, 1.2, diameter_m=0.3
                ),
            ),
            terminal_demands=(TerminalAirflowDemand("X", 100),),
        )


def test_hvac_tree_drives_fan_duct_loss_and_requires_airflow_consistency() -> None:
    project = hvac_project_from_dict(
        {
            "name": "Tree HVAC",
            "fan_system": {
                "name": "AHU",
                "duct_pressure_drop_pa": 999,
                "coil_pressure_drop_pa": 100,
                "other_pressure_drop_pa": 50,
                "fan_efficiency": 0.7,
                "motor_efficiency": 0.9
            },
            "duct_tree_network": {
                "root_node": "AHU",
                "sections": [
                    {
                        "name": "Main",
                        "from_node": "AHU",
                        "to_node": "J1",
                        "length_m": 10,
                        "friction_factor": 0.02,
                        "air_density_kg_m3": 1.2,
                        "local_loss_coefficient": 1.0,
                        "width_m": 0.5,
                        "height_m": 0.3
                    },
                    {
                        "name": "Process",
                        "from_node": "J1",
                        "to_node": "Process",
                        "length_m": 8,
                        "friction_factor": 0.02,
                        "air_density_kg_m3": 1.2,
                        "local_loss_coefficient": 1.5,
                        "diameter_m": 0.4
                    },
                    {
                        "name": "Gowning",
                        "from_node": "J1",
                        "to_node": "Gowning",
                        "length_m": 5,
                        "friction_factor": 0.02,
                        "air_density_kg_m3": 1.2,
                        "local_loss_coefficient": 1.0,
                        "diameter_m": 0.3
                    }
                ],
                "terminal_demands": [
                    {"node": "Process", "airflow_m3_h": 1000},
                    {"node": "Gowning", "airflow_m3_h": 500}
                ]
            },
            "rooms": [
                {
                    "name": "Process",
                    "cleanroom_airflow_m3_h": 1000,
                    "thermal_design": {
                        "room_air": {
                            "dry_bulb_c": 22,
                            "relative_humidity_percent": 45
                        }
                    }
                },
                {
                    "name": "Gowning",
                    "cleanroom_airflow_m3_h": 500,
                    "thermal_design": {
                        "room_air": {
                            "dry_bulb_c": 22,
                            "relative_humidity_percent": 45
                        }
                    }
                }
            ]
        }
    )
    result = analyze_hvac_project(project)
    tree = result["duct_tree_network"]
    fan = result["supply_fan"]
    assert tree["root_airflow_m3_h"] == result["total_governing_airflow_m3_h"]
    assert fan["pressure_components_pa"]["duct"] == pytest.approx(
        tree["critical_path_pressure_drop_pa"], abs=0.001
    )
    assert fan["duct_pressure_drop_source"] == "computed_duct_tree_network"


def test_hvac_tree_rejects_mismatched_total_airflow() -> None:
    project = hvac_project_from_dict(
        {
            "name": "Mismatch",
            "duct_tree_network": {
                "root_node": "AHU",
                "sections": [
                    {
                        "name": "Only",
                        "from_node": "AHU",
                        "to_node": "Room",
                        "length_m": 1,
                        "friction_factor": 0.02,
                        "air_density_kg_m3": 1.2,
                        "diameter_m": 0.3
                    }
                ],
                "terminal_demands": [
                    {"node": "Room", "airflow_m3_h": 900}
                ]
            },
            "rooms": [
                {
                    "name": "Room",
                    "cleanroom_airflow_m3_h": 1000,
                    "thermal_design": {
                        "room_air": {
                            "dry_bulb_c": 22,
                            "relative_humidity_percent": 45
                        }
                    }
                }
            ]
        }
    )
    with pytest.raises(ValueError, match="terminal airflow"):
        analyze_hvac_project(project)


def test_hvac_rejects_both_path_and_tree_networks() -> None:
    data = {
        "name": "Ambiguous",
        "duct_network": {
            "paths": [
                {
                    "name": "P",
                    "sections": [
                        {
                            "name": "S",
                            "length_m": 1,
                            "airflow_m3_h": 100,
                            "friction_factor": 0.02,
                            "air_density_kg_m3": 1.2,
                            "diameter_m": 0.3
                        }
                    ]
                }
            ]
        },
        "duct_tree_network": {
            "root_node": "AHU",
            "sections": [
                {
                    "name": "T",
                    "from_node": "AHU",
                    "to_node": "Room",
                    "length_m": 1,
                    "friction_factor": 0.02,
                    "air_density_kg_m3": 1.2,
                    "diameter_m": 0.3
                }
            ],
            "terminal_demands": [{"node": "Room", "airflow_m3_h": 100}]
        },
        "rooms": [
            {
                "name": "Room",
                "cleanroom_airflow_m3_h": 100,
                "thermal_design": {
                    "room_air": {
                        "dry_bulb_c": 22,
                        "relative_humidity_percent": 45
                    }
                }
            }
        ]
    }
    with pytest.raises(ValueError, match="only one duct network model"):
        hvac_project_from_dict(data)
