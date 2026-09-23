import json

from cleanroomx.airflow import analyze_air_balance
from cleanroomx.fan import analyze_supply_fan
from cleanroomx.hvac import analyze_hvac_project
from cleanroomx.hvac_io import load_hvac_project
from cleanroomx.hvac_models import AirBalanceDesign, FanSystem


def test_hvac_project_load_and_analysis(tmp_path) -> None:
    path = tmp_path / "hvac.json"
    path.write_text(
        json.dumps(
            {
                "name": "HVAC Demo",
                "filter_unit": {
                    "name": "FFU",
                    "rated_airflow_m3_h": 1200,
                    "design_utilization": 0.9,
                    "pressure_drop_pa": 180
                },
                "fan_system": {
                    "name": "Supply AHU",
                    "duct_pressure_drop_pa": 420,
                    "coil_pressure_drop_pa": 160,
                    "other_pressure_drop_pa": 90,
                    "fan_efficiency": 0.7,
                    "motor_efficiency": 0.92
                },
                "rooms": [
                    {
                        "name": "Process",
                        "cleanroom_airflow_m3_h": 2000,
                        "air_balance": {
                            "return_airflow_m3_h": 1900,
                            "exhaust_airflow_m3_h": 200,
                            "minimum_surplus_m3_h": 100
                        },
                        "thermal_design": {
                            "room_air": {
                                "dry_bulb_c": 22,
                                "relative_humidity_percent": 45
                            },
                            "loads": {"equipment_w": 8000},
                            "supply_air_temp_c": 16
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    result = analyze_hvac_project(load_hvac_project(path))
    room = result["rooms"][0]
    assert room["governing_airflow_m3_h"] > 2000
    assert room["filter_units"] is not None
    assert room["air_balance"]["passes_minimum_surplus"] is True
    assert result["all_air_balances_pass"] is True
    assert result["supply_fan"]["total_static_pressure_pa"] == 850
    assert result["supply_fan"]["estimated_electrical_input_kw"] > 0
    assert result["total_preliminary_cooling_capacity_kw"] == 8.0


def test_air_balance_detects_shortfall() -> None:
    result = analyze_air_balance(
        1000,
        AirBalanceDesign(
            return_airflow_m3_h=800,
            exhaust_airflow_m3_h=150,
            transfer_out_airflow_m3_h=100,
            minimum_surplus_m3_h=50,
        ),
    )
    assert result["net_surplus_m3_h"] == -50
    assert result["surplus_margin_m3_h"] == -100
    assert result["passes_minimum_surplus"] is False


def test_air_balance_counts_transfer_in() -> None:
    result = analyze_air_balance(
        1000,
        AirBalanceDesign(
            return_airflow_m3_h=900,
            transfer_in_airflow_m3_h=100,
            transfer_out_airflow_m3_h=50,
            minimum_surplus_m3_h=100,
        ),
    )
    assert result["net_surplus_m3_h"] == 150
    assert result["surplus_margin_m3_h"] == 50
    assert result["passes_minimum_surplus"] is True


def test_fan_power_uses_total_entered_static_pressure() -> None:
    result = analyze_supply_fan(
        3600,
        FanSystem(
            name="Supply",
            duct_pressure_drop_pa=300,
            coil_pressure_drop_pa=150,
            other_pressure_drop_pa=50,
            fan_efficiency=0.5,
            motor_efficiency=0.8,
        ),
        terminal_filter_pressure_drop_pa=100,
    )
    assert result["airflow_m3_s"] == 1.0
    assert result["total_static_pressure_pa"] == 600
    assert result["air_power_kw"] == 0.6
    assert result["shaft_power_kw"] == 1.2
    assert result["estimated_electrical_input_kw"] == 1.5



def test_hvac_project_adds_network_critical_path_to_fan_static(tmp_path) -> None:
    path = tmp_path / "hvac-duct.json"
    path.write_text(
        json.dumps(
            {
                "name": "HVAC Duct Demo",
                "fan_system": {
                    "name": "Supply AHU",
                    "duct_pressure_drop_pa": 50,
                    "coil_pressure_drop_pa": 100,
                    "other_pressure_drop_pa": 0,
                    "fan_efficiency": 0.7,
                    "motor_efficiency": 0.9
                },
                "duct_network": {
                    "name": "Supply network",
                    "paths": [
                        {
                            "name": "Process path",
                            "sections": [
                                {
                                    "name": "Main",
                                    "length_m": 10,
                                    "hydraulic_diameter_m": 0.5,
                                    "cross_section_area_m2": 0.5,
                                    "airflow_m3_h": 3600,
                                    "darcy_friction_factor": 0.02,
                                    "minor_loss_coefficient": 1.5,
                                    "additional_pressure_drop_pa": 10,
                                    "air_density_kg_m3": 1.2
                                }
                            ]
                        }
                    ]
                },
                "rooms": [
                    {
                        "name": "Process",
                        "cleanroom_airflow_m3_h": 3600,
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

    assert result["duct_network"]["critical_path"] == "Process path"
    assert result["duct_network"]["critical_path_pressure_drop_pa"] == 14.56
    pressure = result["supply_fan"]["pressure_components_pa"]
    assert pressure["entered_duct"] == 50
    assert pressure["network_critical_path"] == 14.56
    assert pressure["duct"] == 64.56
    assert result["supply_fan"]["total_static_pressure_pa"] == 164.56
