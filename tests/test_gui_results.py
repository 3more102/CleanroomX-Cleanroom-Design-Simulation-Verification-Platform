from __future__ import annotations

from cleanroomx.gui_results import (
    _flatten_result,
    _format_scalar,
    _humanize,
    _result_class,
)


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


def test_result_classification_separates_calculated_requirements_and_verdicts():
    assert _result_class("airflow.supply_airflow_m3_h") == "CALCULATED"
    assert _result_class("requirements.minimum_ach") == "REQUIREMENT"
    assert _result_class("design_target_pa") == "REQUIREMENT"
    assert _result_class("compliance.status") == "VERDICT"
    assert _result_class("pressure_verdict") == "VERDICT"
    assert _result_class("metadata.solver_version") == "METADATA"
