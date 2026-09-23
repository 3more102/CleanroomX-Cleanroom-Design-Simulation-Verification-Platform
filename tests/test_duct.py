import json

import pytest

from cleanroomx.duct import analyze_duct_network, analyze_duct_section
from cleanroomx.hvac import analyze_hvac_project
from cleanroomx.hvac_io import load_hvac_project
from cleanroomx.hvac_models import DuctNetwork, DuctPath, DuctSection


def test_round_duct_section_pressure_loss() -> None:
    result = analyze_duct_section(
        DuctSection(
            name="Main",
            length_m=10,
            airflow_m3_h=3600,
            roughness_m=0.00009,
            local_loss_coefficient=1.5,
            diameter_m=0.5,
        ),
        air_density_kg_m3=1.204,
        dynamic_viscosity_pa_s=1.825e-5,
    )
    assert result["shape"] == "round"
    assert result["velocity_m_s"] == pytest.approx(5.09296, abs=1e-5)
    assert result["reynolds_number"] > 100_000
    assert result["friction_pressure_loss_pa"] > 0
    assert result["local_pressure_loss_pa"] == pytest.approx(
        1.5 * result["velocity_pressure_pa"], abs=0.001
    )
    assert result["total_pressure_loss_pa"] == pytest.approx(
        result["friction_pressure_loss_pa"] + result["local_pressure_loss_pa"],
        abs=0.001,
    )


def test_rectangular_duct_hydraulic_diameter() -> None:
    result = analyze_duct_section(
        DuctSection(
            name="Branch",
            length_m=5,
            airflow_m3_h=1800,
            roughness_m=0.00009,
            width_m=0.4,
            height_m=0.2,
        ),
        air_density_kg_m3=1.204,
        dynamic_viscosity_pa_s=1.825e-5,
    )
    assert result["shape"] == "rectangular"
    assert result["area_m2"] == pytest.approx(0.08)
    assert result["hydraulic_diameter_m"] == pytest.approx(0.266667, abs=1e-6)


def test_network_selects_highest_loss_path() -> None:
    network = DuctNetwork(
        air_density_kg_m3=1.204,
        dynamic_viscosity_pa_s=1.825e-5,
        paths=(
            DuctPath(
                name="Short",
                sections=(
                    DuctSection(
                        name="S1",
                        length_m=5,
                        airflow_m3_h=1800,
                        roughness_m=0.00009,
                        diameter_m=0.4,
                    ),
                ),
            ),
            DuctPath(
                name="Long",
                sections=(
                    DuctSection(
                        name="L1",
                        length_m=20,
                        airflow_m3_h=1800,
                        roughness_m=0.00009,
                        local_loss_coefficient=2.0,
                        diameter_m=0.4,
                    ),
                ),
            ),
        ),
    )
    result = analyze_duct_network(network)
    assert result["critical_path"] == "Long"
    assert result["critical_path_pressure_loss_pa"] > result["paths"][0]["total_pressure_loss_pa"]


def test_duct_geometry_must_be_unambiguous() -> None:
    with pytest.raises(ValueError, match="exactly one geometry"):
        DuctSection(
            name="Bad",
            length_m=1,
            airflow_m3_h=100,
            roughness_m=0.00009,
            diameter_m=0.2,
            width_m=0.2,
            height_m=0.2,
        )


def test_hvac_uses_critical_duct_path_for_fan(tmp_path) -> None:
    path = tmp_path / "hvac.json"
    path.write_text(
        json.dumps(
            {
                "name": "Duct Integration",
                "fan_system": {
                    "name": "Supply AHU",
                    "duct_pressure_drop_pa": 999,
                    "coil_pressure_drop_pa": 100,
                    "other_pressure_drop_pa": 50,
                    "fan_efficiency": 0.7,
                    "motor_efficiency": 0.92
                },
                "supply_duct_network": {
                    "air_density_kg_m3": 1.204,
                    "dynamic_viscosity_pa_s": 0.00001825,
                    "paths": [
                        {
                            "name": "Critical",
                            "sections": [
                                {
                                    "name": "Main",
                                    "length_m": 20,
                                    "airflow_m3_h": 2000,
                                    "roughness_m": 0.00009,
                                    "local_loss_coefficient": 2.0,
                                    "diameter_m": 0.4
                                }
                            ]
                        }
                    ]
                },
                "rooms": [
                    {
                        "name": "Process",
                        "cleanroom_airflow_m3_h": 2000,
                        "thermal_design": {
                            "room_air": {
                                "dry_bulb_c": 22,
                                "relative_humidity_percent": 45
                            }
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    result = analyze_hvac_project(load_hvac_project(path))
    duct_loss = result["supply_duct_network"]["critical_path_pressure_loss_pa"]
    fan = result["supply_fan"]
    assert fan["duct_pressure_source"] == "network_critical_path"
    assert fan["pressure_components_pa"]["duct"] == pytest.approx(duct_loss, abs=0.001)
    assert fan["pressure_components_pa"]["duct"] != 999
    assert fan["total_static_pressure_pa"] == pytest.approx(
        duct_loss + 100 + 50, abs=0.001
    )
