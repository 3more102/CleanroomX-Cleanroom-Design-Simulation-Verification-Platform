import pytest

from cleanroomx.duct import analyze_duct_network, analyze_duct_segment
from cleanroomx.duct_io import duct_network_from_dict
from cleanroomx.hvac_models import DuctNetwork, DuctPath, DuctSegment


def test_rectangular_segment_pressure_loss() -> None:
    result = analyze_duct_segment(
        DuctSegment(
            name="Main",
            length_m=10,
            airflow_m3_h=900,
            darcy_friction_factor=0.02,
            air_density_kg_m3=1.2,
            local_loss_coefficient=2.0,
            width_m=0.5,
            height_m=0.25,
        )
    )
    assert result["area_m2"] == 0.125
    assert result["hydraulic_diameter_m"] == pytest.approx(1 / 3, abs=1e-6)
    assert result["velocity_m_s"] == 2.0
    assert result["velocity_pressure_pa"] == 2.4
    assert result["straight_pressure_drop_pa"] == 1.44
    assert result["local_pressure_drop_pa"] == 4.8
    assert result["total_pressure_drop_pa"] == 6.24


def test_round_segment_uses_diameter_as_hydraulic_diameter() -> None:
    result = analyze_duct_segment(
        DuctSegment(
            name="Round",
            length_m=5,
            airflow_m3_h=1000,
            darcy_friction_factor=0.02,
            air_density_kg_m3=1.2,
            diameter_m=0.4,
        )
    )
    assert result["shape"] == "round"
    assert result["hydraulic_diameter_m"] == 0.4
    assert result["total_pressure_drop_pa"] > 0


def test_network_selects_highest_loss_path() -> None:
    network = DuctNetwork(
        name="Supply",
        paths=(
            DuctPath(
                name="Path A",
                segments=(
                    DuctSegment(
                        name="A1",
                        length_m=10,
                        airflow_m3_h=900,
                        darcy_friction_factor=0.02,
                        air_density_kg_m3=1.2,
                        local_loss_coefficient=2.0,
                        width_m=0.5,
                        height_m=0.25,
                    ),
                ),
            ),
            DuctPath(
                name="Path B",
                segments=(
                    DuctSegment(
                        name="B1",
                        length_m=20,
                        airflow_m3_h=900,
                        darcy_friction_factor=0.02,
                        air_density_kg_m3=1.2,
                        local_loss_coefficient=3.0,
                        width_m=0.5,
                        height_m=0.25,
                    ),
                ),
            ),
        ),
    )
    result = analyze_duct_network(network)
    assert result["critical_path_name"] == "Path B"
    assert result["critical_path_pressure_drop_pa"] > 6.24


def test_requires_exactly_one_geometry_definition() -> None:
    with pytest.raises(ValueError, match="exactly one geometry"):
        DuctSegment(
            name="Invalid",
            length_m=1,
            airflow_m3_h=100,
            darcy_friction_factor=0.02,
        )

    with pytest.raises(ValueError, match="exactly one geometry"):
        DuctSegment(
            name="Invalid",
            length_m=1,
            airflow_m3_h=100,
            darcy_friction_factor=0.02,
            diameter_m=0.2,
            width_m=0.2,
            height_m=0.2,
        )


def test_dict_loader_builds_network() -> None:
    network = duct_network_from_dict(
        {
            "name": "Supply",
            "paths": [
                {
                    "name": "Process",
                    "segments": [
                        {
                            "name": "Main",
                            "length_m": 10.0,
                            "airflow_m3_h": 900.0,
                            "darcy_friction_factor": 0.02,
                            "local_loss_coefficient": 2.0,
                            "width_m": 0.5,
                            "height_m": 0.25
                        }
                    ]
                }
            ]
        }
    )
    assert network.name == "Supply"
    assert network.paths[0].segments[0].hydraulic_diameter_m == pytest.approx(1 / 3)


def test_segment_names_are_unique_within_path() -> None:
    segment = DuctSegment(
        name="Repeated",
        length_m=1,
        airflow_m3_h=100,
        darcy_friction_factor=0.02,
        diameter_m=0.2,
    )
    with pytest.raises(ValueError, match="unique"):
        DuctPath(name="Bad", segments=(segment, segment))


def test_hvac_uses_critical_path_as_fan_duct_loss() -> None:
    from cleanroomx.hvac import analyze_hvac_project
    from cleanroomx.hvac_io import hvac_project_from_dict

    project = hvac_project_from_dict(
        {
            "name": "Integrated",
            "fan_system": {
                "name": "AHU",
                "duct_pressure_drop_pa": 999.0,
                "coil_pressure_drop_pa": 100.0,
                "other_pressure_drop_pa": 50.0,
                "fan_efficiency": 0.7,
                "motor_efficiency": 0.9
            },
            "duct_network": {
                "name": "Supply",
                "paths": [
                    {
                        "name": "Critical",
                        "segments": [
                            {
                                "name": "S1",
                                "length_m": 10.0,
                                "airflow_m3_h": 900.0,
                                "darcy_friction_factor": 0.02,
                                "air_density_kg_m3": 1.2,
                                "local_loss_coefficient": 2.0,
                                "width_m": 0.5,
                                "height_m": 0.25
                            }
                        ]
                    }
                ]
            },
            "rooms": [
                {
                    "name": "Room",
                    "cleanroom_airflow_m3_h": 900.0,
                    "thermal_design": {
                        "room_air": {
                            "dry_bulb_c": 22.0,
                            "relative_humidity_percent": 45.0
                        }
                    }
                }
            ]
        }
    )

    result = analyze_hvac_project(project)

    assert result["duct_network"]["critical_path_pressure_drop_pa"] == 6.24
    assert result["supply_fan"]["pressure_components_pa"]["duct"] == 6.24
    assert result["supply_fan"]["duct_pressure_drop_source"] == "duct_network_critical_path"
    assert result["supply_fan"]["configured_duct_pressure_drop_pa"] == 999.0
    assert result["supply_fan"]["total_static_pressure_pa"] == 156.24
