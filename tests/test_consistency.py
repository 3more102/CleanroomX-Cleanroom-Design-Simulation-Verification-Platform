from __future__ import annotations

import math
from pathlib import Path

import pytest

from cleanroomx.consistency import analyze_project_consistency
from cleanroomx.consistency_report import markdown_consistency_report
from cleanroomx.hvac_io import hvac_project_from_dict, load_hvac_project
from cleanroomx.io import load_project, project_from_dict


def _verification_project(*rooms: tuple[str, float]):
    return project_from_dict(
        {
            "name": "Verification",
            "rooms": [
                {
                    "name": name,
                    "length_m": 4,
                    "width_m": 3,
                    "height_m": 3,
                    "supply_airflow_m3_h": airflow,
                }
                for name, airflow in rooms
            ],
        }
    )


def _hvac_project(*rooms: tuple[str, float]):
    return hvac_project_from_dict(
        {
            "name": "HVAC",
            "rooms": [
                {
                    "name": name,
                    "cleanroom_airflow_m3_h": airflow,
                    "thermal_design": {
                        "room_air": {
                            "dry_bulb_c": 22,
                            "relative_humidity_percent": 45,
                        }
                    },
                }
                for name, airflow in rooms
            ],
        }
    )


def test_exact_matching_room_airflow_passes_by_default() -> None:
    result = analyze_project_consistency(
        _verification_project(("Process", 2700)),
        _hvac_project(("Process", 2700)),
    )
    assert result["status"] == "pass"
    assert result["mismatch_count"] == 0


def test_explicit_airflow_tolerance_is_honored() -> None:
    result = analyze_project_consistency(
        _verification_project(("Process", 2700)),
        _hvac_project(("Process", 2698)),
        room_airflow_abs_tolerance_m3_h=5,
    )
    assert result["status"] == "pass"
    assert result["room_airflow_checks"][0]["absolute_difference_m3_h"] == 2
    assert result["room_airflow_checks"][0]["status"] == "match"


def test_airflow_mismatch_fails_consistency_check() -> None:
    result = analyze_project_consistency(
        _verification_project(("Process", 2700)),
        _hvac_project(("Process", 2680)),
        room_airflow_abs_tolerance_m3_h=5,
    )
    assert result["status"] == "fail"
    assert result["mismatch_count"] == 1
    assert result["room_airflow_checks"][0]["status"] == "mismatch"


def test_scope_difference_is_visible_without_being_implicitly_failed() -> None:
    result = analyze_project_consistency(
        _verification_project(("Process", 2700), ("Ante", 720)),
        _hvac_project(("Process", 2700)),
    )
    assert result["status"] == "pass_with_scope_difference"
    assert result["verification_only_rooms"] == ["Ante"]
    assert result["room_set_mismatch"] is False


def test_identical_room_set_requirement_makes_scope_difference_fail() -> None:
    result = analyze_project_consistency(
        _verification_project(("Process", 2700), ("Ante", 720)),
        _hvac_project(("Process", 2700)),
        require_same_room_set=True,
    )
    assert result["status"] == "fail"
    assert result["room_set_mismatch"] is True


def test_no_shared_rooms_are_reported_as_not_comparable() -> None:
    result = analyze_project_consistency(
        _verification_project(("Process", 2700)),
        _hvac_project(("Process Bay", 2700)),
    )
    assert result["status"] == "not_comparable"
    assert result["shared_room_count"] == 0


@pytest.mark.parametrize("bad", [-1.0, math.nan, math.inf, -math.inf])
def test_invalid_consistency_tolerance_is_rejected(bad: float) -> None:
    with pytest.raises(ValueError, match="finite and >= 0"):
        analyze_project_consistency(
            _verification_project(("Process", 2700)),
            _hvac_project(("Process", 2700)),
            room_airflow_abs_tolerance_m3_h=bad,
        )


def test_report_preserves_scope_and_difference_evidence() -> None:
    result = analyze_project_consistency(
        _verification_project(("Process", 2700), ("Ante", 720)),
        _hvac_project(("Process", 2690)),
        room_airflow_abs_tolerance_m3_h=5,
    )
    text = markdown_consistency_report(result)
    assert "Cross-Module Consistency Report" in text
    assert "Process" in text
    assert "10.0" in text
    assert "Verification-only rooms: Ante" in text
    assert "not a cleanroom acceptance limit" in text


def test_repository_examples_load_and_compare_end_to_end() -> None:
    root = Path(__file__).resolve().parents[1]
    verification = load_project(root / "examples" / "facility_project.json")
    hvac = load_hvac_project(root / "examples" / "consistency_hvac_demo.json")
    result = analyze_project_consistency(
        verification,
        hvac,
        require_same_room_set=True,
    )
    assert result["status"] == "pass"
    assert result["shared_room_count"] == 3
    assert result["mismatch_count"] == 0
