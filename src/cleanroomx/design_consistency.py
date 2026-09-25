from __future__ import annotations

import math
from typing import Any

from .air_system_design import AirSystemDesign
from .design_requirements import DesignRequirementsProject


NUMERIC_REL_TOLERANCE = 1e-12
NUMERIC_ABS_TOLERANCE = 1e-9


def _close(left: float, right: float) -> bool:
    return math.isclose(
        float(left),
        float(right),
        rel_tol=NUMERIC_REL_TOLERANCE,
        abs_tol=NUMERIC_ABS_TOLERANCE,
    )


def _origin(room: Any, key: str) -> dict[str, str] | None:
    value = room.origins.get(key)
    return dict(value) if isinstance(value, dict) else None


def analyze_design_air_system_consistency(
    requirements: DesignRequirementsProject,
    air_system: AirSystemDesign,
) -> dict[str, Any]:
    """Compare duplicated requirement/design inputs without inventing acceptance rules.

    Exact room names are the only linkage key. The tiny numeric tolerances are solely
    for floating-point representation noise and are not engineering acceptance bands.
    """
    if not isinstance(requirements, DesignRequirementsProject):
        raise TypeError("requirements must be a DesignRequirementsProject")
    if not isinstance(air_system, AirSystemDesign):
        raise TypeError("air_system must be an AirSystemDesign")

    requirement_rooms = {room.name: room for room in requirements.rooms}
    air_rooms = {room.name: room for room in air_system.rooms}
    requirement_names = set(requirement_rooms)
    air_names = set(air_rooms)

    shared_names = sorted(requirement_names & air_names)
    requirements_only = sorted(requirement_names - air_names)
    air_system_only = sorted(air_names - requirement_names)

    room_checks: list[dict[str, Any]] = []
    geometry_mismatch_count = 0
    ach_mismatch_count = 0
    temperature_mismatch_count = 0
    sensible_load_mismatch_count = 0

    for name in shared_names:
        requirement = requirement_rooms[name]
        design = air_rooms[name]

        geometry_checks: list[dict[str, Any]] = []
        for field_name, unit in (
            ("length_m", "m"),
            ("width_m", "m"),
            ("height_m", "m"),
        ):
            expected = float(getattr(requirement, field_name))
            actual = float(getattr(design, field_name))
            status = "match" if _close(expected, actual) else "mismatch"
            if status == "mismatch":
                geometry_mismatch_count += 1
            geometry_checks.append(
                {
                    "field": field_name,
                    "unit": unit,
                    "requirement_value": expected,
                    "air_system_value": actual,
                    "difference": actual - expected,
                    "status": status,
                }
            )

        if requirement.min_ach is None:
            ach_check = {
                "requirement_value": None,
                "air_system_value": design.min_ach,
                "unit": "1/h",
                "status": "unchecked",
                "provenance": None,
            }
        elif design.min_ach is None:
            ach_mismatch_count += 1
            ach_check = {
                "requirement_value": requirement.min_ach,
                "air_system_value": None,
                "unit": "1/h",
                "status": "missing",
                "provenance": _origin(requirement, "min_ach"),
            }
        else:
            ach_status = (
                "match"
                if _close(requirement.min_ach, design.min_ach)
                else "mismatch"
            )
            if ach_status == "mismatch":
                ach_mismatch_count += 1
            ach_check = {
                "requirement_value": requirement.min_ach,
                "air_system_value": design.min_ach,
                "unit": "1/h",
                "difference": design.min_ach - requirement.min_ach,
                "status": ach_status,
                "provenance": _origin(requirement, "min_ach"),
            }

        if requirement.temperature_c is None:
            temperature_check = {
                "requirement_range_c": None,
                "air_system_room_air_temp_c": design.room_air_temp_c,
                "status": "unchecked",
                "provenance": None,
            }
        elif design.room_air_temp_c is None:
            temperature_mismatch_count += 1
            temperature_check = {
                "requirement_range_c": {
                    "min": requirement.temperature_c[0],
                    "max": requirement.temperature_c[1],
                },
                "air_system_room_air_temp_c": None,
                "status": "missing",
                "provenance": _origin(requirement, "temperature_c"),
            }
        else:
            minimum, maximum = requirement.temperature_c
            in_range = (
                design.room_air_temp_c > minimum
                or _close(design.room_air_temp_c, minimum)
            ) and (
                design.room_air_temp_c < maximum
                or _close(design.room_air_temp_c, maximum)
            )
            temperature_status = "match" if in_range else "mismatch"
            if temperature_status == "mismatch":
                temperature_mismatch_count += 1
            temperature_check = {
                "requirement_range_c": {"min": minimum, "max": maximum},
                "air_system_room_air_temp_c": design.room_air_temp_c,
                "status": temperature_status,
                "provenance": _origin(requirement, "temperature_c"),
            }

        provided_sensible_load = (
            requirement.occupancy * requirement.occupant_sensible_w_per_person
            + requirement.equipment_sensible_load_w
            + requirement.process_sensible_load_w
        )
        if provided_sensible_load <= NUMERIC_ABS_TOLERANCE:
            sensible_check = {
                "requirements_explicit_sensible_load_w": provided_sensible_load,
                "air_system_sensible_load_w": design.sensible_load_w,
                "status": "not_comparable",
                "component_origins": {
                    key: origin
                    for key in (
                        "occupancy",
                        "occupant_sensible_w_per_person",
                        "equipment_sensible_load_w",
                        "process_sensible_load_w",
                    )
                    if (origin := _origin(requirement, key)) is not None
                },
            }
        else:
            sensible_status = (
                "match"
                if _close(provided_sensible_load, design.sensible_load_w)
                else "mismatch"
            )
            if sensible_status == "mismatch":
                sensible_load_mismatch_count += 1
            sensible_check = {
                "requirements_explicit_sensible_load_w": provided_sensible_load,
                "air_system_sensible_load_w": design.sensible_load_w,
                "difference_w": design.sensible_load_w - provided_sensible_load,
                "status": sensible_status,
                "component_origins": {
                    key: origin
                    for key in (
                        "occupancy",
                        "occupant_sensible_w_per_person",
                        "equipment_sensible_load_w",
                        "process_sensible_load_w",
                    )
                    if (origin := _origin(requirement, key)) is not None
                },
            }

        room_checks.append(
            {
                "room": name,
                "geometry": geometry_checks,
                "minimum_ach": ach_check,
                "room_temperature": temperature_check,
                "sensible_load": sensible_check,
            }
        )

    scope_difference = bool(requirements_only or air_system_only)
    if geometry_mismatch_count or ach_mismatch_count or temperature_mismatch_count:
        status = "fail"
    elif scope_difference or sensible_load_mismatch_count:
        status = "review"
    elif not shared_names:
        status = "not_comparable"
    else:
        status = "pass"

    return {
        "requirements_project": requirements.name,
        "air_system_design": air_system.name,
        "status": status,
        "shared_room_count": len(shared_names),
        "requirements_only_rooms": requirements_only,
        "air_system_only_rooms": air_system_only,
        "geometry_mismatch_count": geometry_mismatch_count,
        "ach_mismatch_count": ach_mismatch_count,
        "temperature_mismatch_count": temperature_mismatch_count,
        "sensible_load_mismatch_count": sensible_load_mismatch_count,
        "room_checks": room_checks,
        "numeric_comparison": {
            "relative_tolerance": NUMERIC_REL_TOLERANCE,
            "absolute_tolerance": NUMERIC_ABS_TOLERANCE,
            "purpose": "floating-point representation noise only; not an engineering acceptance tolerance",
        },
        "scope_note": (
            "This is requirement-to-design traceability for duplicated inputs. Room names "
            "are matched exactly. Geometry, configured minimum ACH, and configured room "
            "temperature are compared directly. Sensible-load comparison uses only the "
            "explicit occupancy/equipment/process components represented by the design-"
            "requirements workflow, so a mismatch is a review item rather than proof that "
            "the air-system load is wrong. No standards-derived acceptance criteria are "
            "introduced."
        ),
    }
