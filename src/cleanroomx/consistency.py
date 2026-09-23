from __future__ import annotations

import math

from .hvac_models import HVACProject
from .models import ProjectSpec


def _finite_positive(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field_name} must be finite and > 0")
    return value


def analyze_project_consistency(
    verification_project: ProjectSpec,
    hvac_project: HVACProject,
    *,
    room_airflow_abs_tolerance_m3_h: float = 0.0,
    require_same_room_set: bool = False,
) -> dict:
    """Compare duplicated room-airflow inputs across verification and HVAC projects."""
    tolerance = float(room_airflow_abs_tolerance_m3_h)
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError(
            "room_airflow_abs_tolerance_m3_h must be finite and >= 0"
        )
    if not isinstance(require_same_room_set, bool):
        raise ValueError("require_same_room_set must be a boolean")

    verification_rooms = {
        room.name: _finite_positive(
            room.supply_airflow_m3_h,
            f"verification airflow for room {room.name!r}",
        )
        for room in verification_project.rooms
    }
    hvac_rooms = {
        room.name: _finite_positive(
            room.cleanroom_airflow_m3_h,
            f"HVAC airflow for room {room.name!r}",
        )
        for room in hvac_project.rooms
    }

    verification_names = set(verification_rooms)
    hvac_names = set(hvac_rooms)
    shared_names = sorted(verification_names & hvac_names)
    verification_only = sorted(verification_names - hvac_names)
    hvac_only = sorted(hvac_names - verification_names)

    checks: list[dict] = []
    for room_name in shared_names:
        verification_airflow = verification_rooms[room_name]
        hvac_airflow = hvac_rooms[room_name]
        difference = hvac_airflow - verification_airflow
        absolute_difference = abs(difference)
        checks.append(
            {
                "room": room_name,
                "verification_supply_airflow_m3_h": round(
                    verification_airflow, 6
                ),
                "hvac_cleanroom_airflow_m3_h": round(hvac_airflow, 6),
                "difference_m3_h": round(difference, 6),
                "absolute_difference_m3_h": round(absolute_difference, 6),
                "status": (
                    "match"
                    if absolute_difference <= tolerance
                    else "mismatch"
                ),
            }
        )

    mismatch_count = sum(item["status"] == "mismatch" for item in checks)
    room_set_mismatch = bool(
        require_same_room_set and (verification_only or hvac_only)
    )

    if mismatch_count or room_set_mismatch:
        status = "fail"
    elif not shared_names:
        status = "not_comparable"
    elif verification_only or hvac_only:
        status = "pass_with_scope_difference"
    else:
        status = "pass"

    return {
        "verification_project": verification_project.name,
        "hvac_project": hvac_project.name,
        "status": status,
        "room_airflow_abs_tolerance_m3_h": round(tolerance, 6),
        "require_same_room_set": require_same_room_set,
        "shared_room_count": len(shared_names),
        "mismatch_count": mismatch_count,
        "room_set_mismatch": room_set_mismatch,
        "verification_only_rooms": verification_only,
        "hvac_only_rooms": hvac_only,
        "room_airflow_checks": checks,
        "scope_note": (
            "This is a duplicated-input consistency check. Room names are matched "
            "exactly. The airflow tolerance is supplied by the user and is not a "
            "cleanroom acceptance limit, standards-derived tolerance, or substitute "
            "for engineering review."
        ),
    }


def analyze_hvac_fan_airflow_consistency(
    hvac_result: dict,
    *,
    fan_operating_points: list[dict] | None = None,
    fan_duct_networks: list[dict] | None = None,
    fan_parallel_networks: list[dict] | None = None,
    fan_loop_networks: list[dict] | None = None,
    fan_speed_studies: list[dict] | None = None,
    fan_loop_speed_studies: list[dict] | None = None,
    airflow_abs_tolerance_m3_h: float = 0.0,
) -> dict:
    """Compare solved fan-study airflow against the HVAC governing airflow."""
    tolerance = float(airflow_abs_tolerance_m3_h)
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("airflow_abs_tolerance_m3_h must be finite and >= 0")

    required_airflow = _finite_positive(
        hvac_result["total_governing_airflow_m3_h"],
        "HVAC total governing airflow",
    )

    checks: list[dict] = []

    def add_check(kind: str, item: dict, point_key: str) -> None:
        point = item.get(point_key)
        study_name = str(item.get("study", "")).strip() or "unnamed"
        if point is None:
            checks.append(
                {
                    "study_kind": kind,
                    "study": study_name,
                    "study_status": item.get("status"),
                    "hvac_governing_airflow_m3_h": round(required_airflow, 6),
                    "fan_operating_airflow_m3_h": None,
                    "difference_m3_h": None,
                    "absolute_difference_m3_h": None,
                    "status": "not_comparable",
                }
            )
            return

        operating_airflow = _finite_positive(
            point["airflow_m3_h"],
            f"fan operating airflow for study {study_name!r}",
        )
        difference = operating_airflow - required_airflow
        absolute_difference = abs(difference)
        checks.append(
            {
                "study_kind": kind,
                "study": study_name,
                "study_status": item.get("status"),
                "hvac_governing_airflow_m3_h": round(required_airflow, 6),
                "fan_operating_airflow_m3_h": round(operating_airflow, 6),
                "difference_m3_h": round(difference, 6),
                "absolute_difference_m3_h": round(absolute_difference, 6),
                "status": (
                    "match" if absolute_difference <= tolerance else "mismatch"
                ),
            }
        )

    for item in fan_operating_points or []:
        add_check("fan_operating_point", item, "operating_point")
    for item in fan_duct_networks or []:
        add_check("fan_duct_network", item, "operating_point")
    for item in fan_parallel_networks or []:
        add_check("fan_parallel_network", item, "fan_operating_point")
    for item in fan_loop_networks or []:
        add_check("fan_loop_network", item, "fan_operating_point")
    for study in fan_speed_studies or []:
        study_name = str(study.get("study", "")).strip() or "unnamed"
        for case in study.get("speed_cases", []):
            ratio = case.get("speed_ratio")
            add_check(
                "fan_speed_case",
                {
                    "study": f"{study_name} @ {ratio}x",
                    "status": case.get("status"),
                    "operating_point": case.get("operating_point"),
                },
                "operating_point",
            )
    for study in fan_loop_speed_studies or []:
        study_name = str(study.get("study", "")).strip() or "unnamed"
        for case in study.get("speed_cases", []):
            ratio = case.get("speed_ratio")
            add_check(
                "fan_loop_speed_case",
                {
                    "study": f"{study_name} @ {ratio}x",
                    "status": case.get("status"),
                    "fan_operating_point": case.get("fan_operating_point"),
                },
                "fan_operating_point",
            )

    if not checks:
        raise ValueError(
            "HVAC/fan airflow consistency requires at least one fan study result"
        )

    mismatch_count = sum(item["status"] == "mismatch" for item in checks)
    unresolved_count = sum(item["status"] == "not_comparable" for item in checks)
    solved_count = len(checks) - unresolved_count

    if mismatch_count:
        status = "fail"
    elif solved_count == 0:
        status = "not_comparable"
    elif unresolved_count:
        status = "pass_with_unresolved_studies"
    else:
        status = "pass"

    return {
        "status": status,
        "hvac_governing_airflow_m3_h": round(required_airflow, 6),
        "airflow_abs_tolerance_m3_h": round(tolerance, 6),
        "study_count": len(checks),
        "solved_study_count": solved_count,
        "mismatch_count": mismatch_count,
        "unresolved_study_count": unresolved_count,
        "study_airflow_checks": checks,
        "scope_note": (
            "This is a cross-study airflow consistency check. The absolute airflow "
            "tolerance is supplied by the user. Unsolved fan studies are preserved as "
            "not comparable rather than failed. This check does not establish airflow "
            "adequacy, fan selection, commissioning acceptance, cleanroom certification, "
            "or a standards-derived tolerance."
        ),
    }

