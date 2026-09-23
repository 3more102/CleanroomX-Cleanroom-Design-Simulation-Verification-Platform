import pytest

from cleanroomx.hvac import analyze_hvac_project
from cleanroomx.hvac_io import hvac_project_from_dict
from cleanroomx.supply_network import (
    SupplyBranch,
    SupplyNetwork,
    SupplyNode,
    solve_supply_network,
)


def test_supply_network_aggregates_downstream_room_demand() -> None:
    network = SupplyNetwork(
        source_node="AHU",
        nodes=(
            SupplyNode(name="AHU"),
            SupplyNode(name="Split", fixed_airflow_m3_h=100.0),
            SupplyNode(name="Process terminal", room_name="Process"),
            SupplyNode(name="Gown terminal", room_name="Gown"),
        ),
        branches=(
            SupplyBranch(
                name="Main trunk",
                upstream_node="AHU",
                downstream_node="Split",
            ),
            SupplyBranch(
                name="Process branch",
                upstream_node="Split",
                downstream_node="Process terminal",
            ),
            SupplyBranch(
                name="Gown branch",
                upstream_node="Split",
                downstream_node="Gown terminal",
            ),
        ),
    )

    result = solve_supply_network(
        network,
        {"Process": 3600.0, "Gown": 900.0},
    )
    branch_flow = {
        branch["name"]: branch["airflow_m3_h"]
        for branch in result["branches"]
    }

    assert result["source_airflow_m3_h"] == 4600.0
    assert result["total_room_airflow_m3_h"] == 4500.0
    assert result["total_fixed_airflow_m3_h"] == 100.0
    assert branch_flow == {
        "Main trunk": 4600.0,
        "Process branch": 3600.0,
        "Gown branch": 900.0,
    }


def test_supply_network_rejects_unreachable_node() -> None:
    with pytest.raises(ValueError, match="exactly one incoming branch"):
        SupplyNetwork(
            source_node="AHU",
            nodes=(
                SupplyNode(name="AHU"),
                SupplyNode(name="Connected"),
                SupplyNode(name="Orphan"),
            ),
            branches=(
                SupplyBranch(
                    name="Connected branch",
                    upstream_node="AHU",
                    downstream_node="Connected",
                ),
            ),
        )


def test_hvac_supply_network_drives_duct_airflow_and_fan_duty() -> None:
    project = hvac_project_from_dict(
        {
            "name": "Branch Flow Integration",
            "fan_system": {
                "name": "Supply AHU",
                "coil_pressure_drop_pa": 100.0,
                "fan_efficiency": 0.7,
                "motor_efficiency": 0.9,
            },
            "supply_network": {
                "source_node": "AHU",
                "nodes": [
                    {"name": "AHU"},
                    {"name": "Split", "fixed_airflow_m3_h": 100.0},
                    {"name": "Process terminal", "room_name": "Process"},
                    {"name": "Gown terminal", "room_name": "Gown"},
                ],
                "branches": [
                    {
                        "name": "Trunk",
                        "upstream_node": "AHU",
                        "downstream_node": "Split",
                    },
                    {
                        "name": "Process branch",
                        "upstream_node": "Split",
                        "downstream_node": "Process terminal",
                    },
                    {
                        "name": "Gown branch",
                        "upstream_node": "Split",
                        "downstream_node": "Gown terminal",
                    },
                ],
            },
            "duct_network": {
                "paths": [
                    {
                        "name": "Process path",
                        "sections": [
                            {
                                "name": "Main trunk duct",
                                "length_m": 10.0,
                                "airflow_m3_h": 1000.0,
                                "flow_source_branch": "Trunk",
                                "friction_factor": 0.02,
                                "air_density_kg_m3": 1.2,
                                "local_loss_coefficient": 1.0,
                                "width_m": 0.5,
                                "height_m": 0.3,
                            },
                            {
                                "name": "Process duct",
                                "length_m": 6.0,
                                "airflow_m3_h": 800.0,
                                "flow_source_branch": "Process branch",
                                "friction_factor": 0.02,
                                "air_density_kg_m3": 1.2,
                                "local_loss_coefficient": 1.0,
                                "diameter_m": 0.4,
                            },
                        ],
                    },
                    {
                        "name": "Gown path",
                        "sections": [
                            {
                                "name": "Main trunk duplicate",
                                "length_m": 10.0,
                                "airflow_m3_h": 1000.0,
                                "flow_source_branch": "Trunk",
                                "friction_factor": 0.02,
                                "air_density_kg_m3": 1.2,
                                "local_loss_coefficient": 1.0,
                                "width_m": 0.5,
                                "height_m": 0.3,
                            },
                            {
                                "name": "Gown duct",
                                "length_m": 4.0,
                                "airflow_m3_h": 250.0,
                                "flow_source_branch": "Gown branch",
                                "friction_factor": 0.02,
                                "air_density_kg_m3": 1.2,
                                "local_loss_coefficient": 1.0,
                                "diameter_m": 0.3,
                            },
                        ],
                    },
                ]
            },
            "rooms": [
                {
                    "name": "Process",
                    "cleanroom_airflow_m3_h": 900.0,
                    "thermal_design": {
                        "room_air": {
                            "dry_bulb_c": 22.0,
                            "relative_humidity_percent": 45.0,
                        }
                    },
                },
                {
                    "name": "Gown",
                    "cleanroom_airflow_m3_h": 300.0,
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
    branches = {
        branch["name"]: branch["airflow_m3_h"]
        for branch in result["supply_network"]["branches"]
    }

    assert result["total_governing_airflow_m3_h"] == 1200.0
    assert result["fan_design_airflow_m3_h"] == 1300.0
    assert result["supply_fan"]["airflow_m3_h"] == 1300.0
    assert branches["Trunk"] == 1300.0
    assert branches["Process branch"] == 900.0
    assert branches["Gown branch"] == 300.0

    process_sections = result["duct_network"]["paths"][0]["sections"]
    assert process_sections[0]["configured_airflow_m3_h"] == 1000.0
    assert process_sections[0]["airflow_m3_h"] == 1300.0
    assert process_sections[0]["airflow_source"] == "supply_branch:Trunk"
    assert process_sections[1]["airflow_m3_h"] == 900.0


def test_hvac_supply_network_requires_every_room_mapping() -> None:
    project = hvac_project_from_dict(
        {
            "name": "Missing Mapping",
            "supply_network": {
                "source_node": "AHU",
                "nodes": [
                    {"name": "AHU"},
                    {"name": "Process terminal", "room_name": "Process"},
                ],
                "branches": [
                    {
                        "name": "Process branch",
                        "upstream_node": "AHU",
                        "downstream_node": "Process terminal",
                    }
                ],
            },
            "rooms": [
                {
                    "name": "Process",
                    "cleanroom_airflow_m3_h": 900.0,
                    "thermal_design": {
                        "room_air": {
                            "dry_bulb_c": 22.0,
                            "relative_humidity_percent": 45.0,
                        }
                    },
                },
                {
                    "name": "Gown",
                    "cleanroom_airflow_m3_h": 300.0,
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

    with pytest.raises(ValueError, match="missing: Gown"):
        analyze_hvac_project(project)
