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



def test_hvac_filter_count_uses_unrounded_governing_airflow() -> None:
    from cleanroomx.hvac_io import hvac_project_from_dict

    project = hvac_project_from_dict(
        {
            "name": "Filter threshold precision",
            "filter_unit": {
                "name": "FFU",
                "rated_airflow_m3_h": 1000.0,
                "design_utilization": 1.0,
                "pressure_drop_pa": 0.0,
            },
            "rooms": [
                {
                    "name": "Room",
                    "cleanroom_airflow_m3_h": 1000.0004,
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

    result = analyze_hvac_project(project)
    room = result["rooms"][0]

    assert room["governing_airflow_m3_h"] == 1000.0
    assert room["filter_units"] == 2
    assert room["delivered_airflow_m3_h"] == 2000.0


def test_hvac_air_balance_status_uses_unrounded_governing_airflow() -> None:
    from cleanroomx.hvac_io import hvac_project_from_dict

    project = hvac_project_from_dict(
        {
            "name": "Balance threshold precision",
            "rooms": [
                {
                    "name": "Room",
                    "cleanroom_airflow_m3_h": 1000.0004,
                    "air_balance": {
                        "return_airflow_m3_h": 1000.0,
                        "minimum_surplus_m3_h": 0.0002,
                    },
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

    result = analyze_hvac_project(project)
    balance = result["rooms"][0]["air_balance"]

    assert balance["net_surplus_m3_h"] == 0.0
    assert balance["passes_minimum_surplus"] is True
    assert result["all_air_balances_pass"] is True


def test_hvac_total_surplus_aggregates_before_presentation_rounding() -> None:
    from cleanroomx.hvac_io import hvac_project_from_dict

    rooms = [
        {
            "name": f"Room {index}",
            "cleanroom_airflow_m3_h": 1000.00049,
            "air_balance": {"return_airflow_m3_h": 1000.0},
            "thermal_design": {
                "room_air": {
                    "dry_bulb_c": 22.0,
                    "relative_humidity_percent": 45.0,
                }
            },
        }
        for index in range(10)
    ]
    result = analyze_hvac_project(
        hvac_project_from_dict({"name": "Aggregate precision", "rooms": rooms})
    )

    assert all(room["air_balance"]["net_surplus_m3_h"] == 0.0 for room in result["rooms"])
    assert result["total_net_surplus_m3_h"] == 0.005
