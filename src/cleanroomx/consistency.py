from __future__ import annotations

import math


def _finite_positive(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field_name} must be finite and > 0")
    return value


def _finite_nonnegative(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{field_name} must be finite and >= 0")
    return value


def _bool_option(config: dict, key: str) -> bool:
    value = config.get(key, False)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def check_verification_hvac_airflow_consistency(
    verification: dict | None,
    hvac: dict | None,
    config: dict | None,
) -> dict:
    """Compare verification supply airflow with HVAC cleanroom airflow.

    No engineering tolerance is embedded. When configured,
    airflow_tolerance_percent must be supplied explicitly.
    """
    if config is None:
        return {
            "status": "not_configured",
            "airflow_tolerance_percent": None,
            "room_mapping_mode": None,
            "comparisons": [],
            "failed_comparison_count": 0,
            "unmapped_verification_rooms": [],
            "unmapped_hvac_rooms": [],
            "required_unmapped_verification_rooms": [],
            "required_unmapped_hvac_rooms": [],
            "issue_count": 0,
            "reason": "No verification/HVAC airflow consistency check is configured.",
        }
    if not isinstance(config, dict):
        raise ValueError(
            "verification_hvac_airflow consistency configuration must be an object"
        )
    if "airflow_tolerance_percent" not in config:
        raise ValueError(
            "verification_hvac_airflow requires explicit airflow_tolerance_percent"
        )

    tolerance = _finite_nonnegative(
        config["airflow_tolerance_percent"],
        "airflow_tolerance_percent",
    )
    require_all_verification = _bool_option(
        config, "require_all_verification_rooms"
    )
    require_all_hvac = _bool_option(config, "require_all_hvac_rooms")
    room_map = config.get("room_map")
    if room_map is not None and not isinstance(room_map, dict):
        raise ValueError(
            "room_map must be an object mapping verification rooms to HVAC rooms"
        )

    mapping_mode = "explicit" if room_map is not None else "exact_name"
    if verification is None or hvac is None:
        return {
            "status": "not_checked",
            "airflow_tolerance_percent": tolerance,
            "room_mapping_mode": mapping_mode,
            "require_all_verification_rooms": require_all_verification,
            "require_all_hvac_rooms": require_all_hvac,
            "comparisons": [],
            "failed_comparison_count": 0,
            "unmapped_verification_rooms": [],
            "unmapped_hvac_rooms": [],
            "required_unmapped_verification_rooms": [],
            "required_unmapped_hvac_rooms": [],
            "issue_count": 0,
            "reason": (
                "The configured airflow consistency check requires both verification "
                "and HVAC analyses in the dossier."
            ),
        }

    verification_rooms = {
        item["room"]: item for item in verification.get("rooms", [])
    }
    hvac_rooms = {item["name"]: item for item in hvac.get("rooms", [])}

    if room_map is None:
        pairs = [
            (name, name)
            for name in sorted(set(verification_rooms) & set(hvac_rooms))
        ]
    else:
        pairs = []
        hvac_targets: set[str] = set()
        for verification_name, hvac_name in room_map.items():
            if not isinstance(verification_name, str) or not verification_name.strip():
                raise ValueError(
                    "room_map verification room names must be non-empty strings"
                )
            if not isinstance(hvac_name, str) or not hvac_name.strip():
                raise ValueError("room_map HVAC room names must be non-empty strings")
            if verification_name not in verification_rooms:
                raise ValueError(
                    f"room_map references unknown verification room: {verification_name!r}"
                )
            if hvac_name not in hvac_rooms:
                raise ValueError(
                    f"room_map references unknown HVAC room: {hvac_name!r}"
                )
            if hvac_name in hvac_targets:
                raise ValueError(
                    "room_map cannot map multiple verification rooms to "
                    f"HVAC room {hvac_name!r}"
                )
            hvac_targets.add(hvac_name)
            pairs.append((verification_name, hvac_name))
        pairs.sort()

    comparisons: list[dict] = []
    for verification_name, hvac_name in pairs:
        verification_room = verification_rooms[verification_name]
        hvac_room = hvac_rooms[hvac_name]
        verification_airflow = _finite_positive(
            float(verification_room["volume_m3"]) * float(verification_room["ach"]),
            f"verification airflow for {verification_name}",
        )
        hvac_airflow = _finite_positive(
            hvac_room["cleanroom_airflow_m3_h"],
            f"HVAC cleanroom airflow for {hvac_name}",
        )
        delta = hvac_airflow - verification_airflow
        deviation_percent = abs(delta) / verification_airflow * 100.0
        comparisons.append(
            {
                "verification_room": verification_name,
                "hvac_room": hvac_name,
                "verification_airflow_m3_h": round(verification_airflow, 6),
                "hvac_cleanroom_airflow_m3_h": round(hvac_airflow, 6),
                "delta_m3_h": round(delta, 6),
                "absolute_deviation_percent": round(deviation_percent, 6),
                "tolerance_percent": tolerance,
                "status": "pass" if deviation_percent <= tolerance else "fail",
            }
        )

    mapped_verification = {verification_name for verification_name, _ in pairs}
    mapped_hvac = {hvac_name for _, hvac_name in pairs}
    unmapped_verification = sorted(set(verification_rooms) - mapped_verification)
    unmapped_hvac = sorted(set(hvac_rooms) - mapped_hvac)
    required_unmapped_verification = (
        unmapped_verification if require_all_verification else []
    )
    required_unmapped_hvac = unmapped_hvac if require_all_hvac else []

    failed = sum(item["status"] == "fail" for item in comparisons)
    issue_count = (
        failed
        + len(required_unmapped_verification)
        + len(required_unmapped_hvac)
    )
    if issue_count:
        status = "fail"
        reason = "One or more configured cross-module consistency requirements failed."
    elif not comparisons:
        status = "not_checked"
        reason = (
            "No verification/HVAC room pairs were available for comparison. "
            "Use matching room names or configure room_map."
        )
    else:
        status = "pass"
        reason = "All configured verification/HVAC airflow consistency checks passed."

    return {
        "status": status,
        "airflow_tolerance_percent": tolerance,
        "room_mapping_mode": mapping_mode,
        "require_all_verification_rooms": require_all_verification,
        "require_all_hvac_rooms": require_all_hvac,
        "comparisons": comparisons,
        "failed_comparison_count": failed,
        "unmapped_verification_rooms": unmapped_verification,
        "unmapped_hvac_rooms": unmapped_hvac,
        "required_unmapped_verification_rooms": required_unmapped_verification,
        "required_unmapped_hvac_rooms": required_unmapped_hvac,
        "issue_count": issue_count,
        "reason": reason,
        "scope_note": (
            "This check only reconciles airflow values between CleanroomX modules "
            "against a user-supplied tolerance. It does not establish design adequacy, "
            "cleanroom classification, commissioning acceptance, or an engineering tolerance."
        ),
    }
