from __future__ import annotations

from cleanroomx.gui_results import _flatten_result, _format_scalar, _humanize, _unit_hint


def test_result_scalar_formatting_is_engineering_dense():
    assert _format_scalar(1250.0) == "1,250"
    assert _format_scalar(12.5000000) == "12.5"
    assert _format_scalar(0.000123456) == "0.00012346"
    assert _format_scalar(True) == "YES"


def test_result_projection_preserves_units_when_result_supplies_them():
    rows = _flatten_result(
        {
            "airflow": {"value": 1250.0, "unit": "m³/h"},
            "pressure": {"value": 12.5, "unit": "Pa"},
            "status": "pass",
        }
    )
    assert ("airflow", "1,250 m³/h") in rows
    assert ("pressure", "12.5 Pa") in rows
    assert ("status", "pass") in rows
    assert _humanize("room.pressure_pa") == "Room / Pressure Pa"



def test_result_projection_infers_units_only_from_explicit_field_suffixes():
    rows = _flatten_result(
        {
            "supply_airflow_m3_h": 1250.0,
            "pressure_difference_pa": 12.5,
            "room_temperature_c": 22.0,
            "ach": 21.3,
            "status": "pass",
        }
    )

    assert ("supply_airflow_m3_h", "1,250 m³/h") in rows
    assert ("pressure_difference_pa", "12.5 Pa") in rows
    assert ("room_temperature_c", "22 °C") in rows
    assert ("ach", "21.3 1/h") in rows
    assert ("status", "pass") in rows
    assert _unit_hint("result.margin_percent") == "%"
    assert _unit_hint("result.status") == ""
