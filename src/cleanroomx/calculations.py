from __future__ import annotations

import math

from .models import RoomSpec
from .numeric import efficiency_float, nonnegative_float, positive_float


def room_volume_m3(room: RoomSpec) -> float:
    """Return geometric room volume in cubic metres."""
    return room.length_m * room.width_m * room.height_m


def air_changes_per_hour(room: RoomSpec) -> float:
    """Calculate nominal supply-air changes per hour (ACH)."""
    return room.supply_airflow_m3_h / room_volume_m3(room)


def decay_concentration(
    initial_concentration_per_m3: float,
    ach: float,
    time_minutes: float,
    removal_efficiency: float = 1.0,
) -> float:
    """Simple well-mixed first-order removal screening model.

    This is not CFD and does not model sources, deposition, leakage, or imperfect
    mixing. removal_efficiency is the effective single-pass removal fraction.
    """
    initial_concentration_per_m3 = nonnegative_float(
        initial_concentration_per_m3, "initial_concentration_per_m3"
    )
    ach = positive_float(ach, "ach")
    time_minutes = nonnegative_float(time_minutes, "time_minutes")
    removal_efficiency = efficiency_float(
        removal_efficiency, "removal_efficiency"
    )

    decay_rate_per_min = (ach / 60.0) * removal_efficiency
    return initial_concentration_per_m3 * math.exp(-decay_rate_per_min * time_minutes)


def recovery_time_minutes(
    initial_concentration_per_m3: float,
    target_concentration_per_m3: float,
    ach: float,
    removal_efficiency: float = 1.0,
) -> float:
    """Time for the screening decay model to fall from initial to target."""
    initial_concentration_per_m3 = positive_float(
        initial_concentration_per_m3, "initial_concentration_per_m3"
    )
    target_concentration_per_m3 = positive_float(
        target_concentration_per_m3, "target_concentration_per_m3"
    )
    ach = positive_float(ach, "ach")
    removal_efficiency = efficiency_float(
        removal_efficiency, "removal_efficiency"
    )
    if target_concentration_per_m3 >= initial_concentration_per_m3:
        return 0.0

    decay_rate_per_min = (ach / 60.0) * removal_efficiency
    return math.log(initial_concentration_per_m3 / target_concentration_per_m3) / decay_rate_per_min
