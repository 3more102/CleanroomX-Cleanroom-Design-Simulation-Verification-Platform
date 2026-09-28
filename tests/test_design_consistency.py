from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from cleanroomx.application import run_analysis
from cleanroomx.design_consistency import (
    analyze_design_consistency,
    design_consistency_from_dict,
    markdown_design_consistency_report,
)


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "design_consistency_demo.json"


def _payload() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def _finding(result: dict, code: str) -> dict:
    return next(item for item in result["findings"] if item["code"] == code)


def test_design_consistency_reference_case_is_complete_pass() -> None:
    result = analyze_design_consistency(design_consistency_from_dict(_payload()))

    assert result["status"] == "pass"
    assert result["complete"] is True
    assert result["passed"] is True
    assert result["summary"] == {
        "finding_count": 8,
        "pass_count": 8,
        "fail_count": 0,
        "not_checked_count": 0,
        "matched_room_count": 1,
        "requirements_room_count": 1,
        "air_system_room_count": 1,
    }
    assert _finding(result, "requirements.ach_based_supply_airflow")["expected"] == 2160.0
    assert _finding(result, "requirements.provided_sensible_load")["expected"] == 8800.0
    assert _finding(result, "requirements.room_air_temperature")["status"] == "pass"
    json.dumps(result, sort_keys=True, allow_nan=False)


def test_design_consistency_is_deterministic_and_does_not_mutate_input() -> None:
    payload = _payload()
    before = copy.deepcopy(payload)

    first = analyze_design_consistency(design_consistency_from_dict(payload))
    second = analyze_design_consistency(design_consistency_from_dict(payload))

    assert first == second
    assert payload == before


def test_sensible_load_mismatch_fails_with_exact_delta() -> None:
    payload = _payload()
    payload["air_system"]["rooms"][0]["sensible_load_w"] = 8500

    result = analyze_design_consistency(design_consistency_from_dict(payload))
    finding = _finding(result, "requirements.provided_sensible_load")

    assert result["status"] == "fail"
    assert result["complete"] is True
    assert result["passed"] is False
    assert finding["status"] == "fail"
    assert finding["expected"] == 8800.0
    assert finding["actual"] == 8500.0
    assert finding["delta"] == -300.0


def test_configured_tolerance_can_accept_small_explicit_difference() -> None:
    payload = _payload()
    payload["air_system"]["rooms"][0]["sensible_load_w"] = 8500
    payload["sensible_load_abs_tolerance_w"] = 300

    result = analyze_design_consistency(design_consistency_from_dict(payload))
    finding = _finding(result, "requirements.provided_sensible_load")

    assert finding["status"] == "pass"
    assert result["status"] == "pass"


def test_missing_requirements_ach_is_not_promoted_to_pass() -> None:
    payload = _payload()
    del payload["requirements"]["reference_profiles"][0]["values"]["min_ach"]

    result = analyze_design_consistency(design_consistency_from_dict(payload))

    assert result["status"] == "pass_with_unchecked"
    assert result["complete"] is False
    assert result["passed"] is True
    assert _finding(result, "requirements.minimum_ach")["status"] == "not_checked"
    assert _finding(result, "requirements.ach_based_supply_airflow")["status"] == "not_checked"


def test_omitted_sensible_load_requirement_is_not_promoted_to_zero_watt_pass() -> None:
    payload = _payload()
    room = payload["requirements"]["rooms"][0]
    for field in (
        "occupancy",
        "occupant_sensible_w_per_person",
        "equipment_sensible_load_w",
        "process_sensible_load_w",
    ):
        room.pop(field, None)
    payload["air_system"]["rooms"][0]["sensible_load_w"] = 0

    result = analyze_design_consistency(design_consistency_from_dict(payload))
    finding = _finding(result, "requirements.provided_sensible_load")

    assert result["status"] == "pass_with_unchecked"
    assert result["complete"] is False
    assert finding["status"] == "not_checked"
    assert finding["expected"] is None
    assert finding["actual"] == 0.0
    assert finding["provenance"]["configured_requirement_components"] == []


def test_missing_air_system_ach_fails_when_requirement_exists() -> None:
    payload = _payload()
    del payload["air_system"]["rooms"][0]["min_ach"]

    result = analyze_design_consistency(design_consistency_from_dict(payload))

    assert result["status"] == "fail"
    assert _finding(result, "requirements.minimum_ach")["status"] == "fail"
    assert _finding(result, "requirements.ach_based_supply_airflow")["status"] == "fail"


def test_room_temperature_outside_requirement_range_fails() -> None:
    payload = _payload()
    payload["air_system"]["rooms"][0]["room_air_temp_c"] = 23

    result = analyze_design_consistency(design_consistency_from_dict(payload))
    finding = _finding(result, "requirements.room_air_temperature")

    assert finding["status"] == "fail"
    assert finding["expected"] == {"min": 20.0, "max": 22.0}
    assert finding["actual"] == 23.0
    assert finding["delta"] == 1.0


def test_room_set_mismatch_is_explicit_and_deterministic() -> None:
    payload = _payload()
    payload["air_system"]["rooms"][0]["name"] = "Different room"

    result = analyze_design_consistency(design_consistency_from_dict(payload))
    finding = _finding(result, "room_set")

    assert result["status"] == "fail"
    assert result["summary"]["matched_room_count"] == 0
    assert finding["status"] == "fail"
    assert finding["provenance"]["requirements_only"] == ["Process"]
    assert finding["provenance"]["air_system_only"] == ["Different room"]


def test_top_level_typo_fails_closed_with_suggestion() -> None:
    payload = _payload()
    payload["airflow_abs_tolerence_m3_h"] = payload.pop(
        "airflow_abs_tolerance_m3_h"
    )

    with pytest.raises(ValueError, match="airflow_abs_tolerence_m3_h") as raised:
        design_consistency_from_dict(payload)

    assert "airflow_abs_tolerance_m3_h" in str(raised.value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("dimension_abs_tolerance_m", -1),
        ("ach_abs_tolerance_1_h", float("inf")),
        ("airflow_abs_tolerance_m3_h", float("nan")),
        ("sensible_load_abs_tolerance_w", True),
    ],
)
def test_invalid_tolerances_fail_closed(field: str, value: object) -> None:
    payload = _payload()
    payload[field] = value

    with pytest.raises(ValueError, match=field):
        design_consistency_from_dict(payload)


def test_markdown_report_escapes_user_controlled_text() -> None:
    payload = _payload()
    payload["name"] = "Study | <A>"

    result = analyze_design_consistency(design_consistency_from_dict(payload))
    markdown = markdown_design_consistency_report(result)

    assert "Study \\| &lt;A&gt;" in markdown
    assert "Deliberately not evaluated" in markdown
    assert "pressure\\_target\\_pa" in markdown


def test_application_path_executes_and_preserves_status() -> None:
    run = run_analysis("design_consistency", _payload(), base_dir=EXAMPLE.parent)

    assert run.kind == "design_consistency"
    assert run.status == "pass"
    assert run.result["complete"] is True
    assert "CleanroomX Design Consistency" in run.markdown
    json.dumps(run.to_dict(), sort_keys=True, allow_nan=False)
