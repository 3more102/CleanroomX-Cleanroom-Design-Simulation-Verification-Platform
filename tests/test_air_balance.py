import pytest

from cleanroomx.air_balance import analyze_air_balance
from cleanroomx.hvac import analyze_hvac_project
from cleanroomx.hvac_io import hvac_project_from_dict
from cleanroomx.hvac_models import AirBalanceDesign


def test_balanced_positive_pressure_room_accounts_for_passive_outflow() -> None:
    design = AirBalanceDesign(
        return_air_m3_h=2400,
        exhaust_air_m3_h=300,
        transfer_out_m3_h=200,
        leakage_out_m3_h=100,
    )
    result = analyze_air_balance(design, 3000)
    assert result["mechanical_surplus_m3_h"] == 300.0
    assert result["passive_net_outflow_m3_h"] == 300.0
    assert result["balance_residual_m3_h"] == 0.0
    assert result["status"] == "balanced"


def test_unaccounted_outflow_is_reported() -> None:
    design = AirBalanceDesign(return_air_m3_h=2500, exhaust_air_m3_h=200)
    result = analyze_air_balance(design, 3000)
    assert result["balance_residual_m3_h"] == 300.0
    assert result["required_unmodeled_outflow_m3_h"] == 300.0
    assert result["status"] == "unaccounted_outflow_required"


def test_tolerance_can_accept_small_closure_error() -> None:
    design = AirBalanceDesign(return_air_m3_h=990, balance_tolerance_m3_h=15)
    result = analyze_air_balance(design, 1000)
    assert result["balance_residual_m3_h"] == 10.0
    assert result["status"] == "balanced"


def test_negative_airflow_is_rejected() -> None:
    with pytest.raises(ValueError):
        AirBalanceDesign(exhaust_air_m3_h=-1)


def test_hvac_project_integrates_air_balance_from_json() -> None:
    project = hvac_project_from_dict(
        {
            "name": "Air Balance Demo",
            "rooms": [
                {
                    "name": "Process",
                    "cleanroom_airflow_m3_h": 2000,
                    "thermal_design": {
                        "room_air": {
                            "dry_bulb_c": 22,
                            "relative_humidity_percent": 45
                        }
                    },
                    "air_balance": {
                        "return_air_m3_h": 1700,
                        "exhaust_air_m3_h": 100,
                        "leakage_out_m3_h": 200
                    }
                }
            ]
        }
    )
    result = analyze_hvac_project(project)
    balance = result["rooms"][0]["air_balance"]
    assert balance["analysis_supply_airflow_m3_h"] == 2000.0
    assert balance["status"] == "balanced"
    assert result["air_balance_summary"]["rooms_balanced"] == 1
