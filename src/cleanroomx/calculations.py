from __future__ import annotations

import math

from .models import RoomSpec


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
    if initial_concentration_per_m3 < 0:
        raise ValueError("initial concentration cannot be negative")
    if ach <= 0:
        raise ValueError("ach must be positive")
    if time_minutes < 0:
        raise ValueError("time_minutes cannot be negative")
    if not 0 < removal_efficiency <= 1:
        raise ValueError("removal_efficiency must be in (0, 1]")

    decay_rate_per_min = (ach / 60.0) * removal_efficiency
    return initial_concentration_per_m3 * math.exp(-decay_rate_per_min * time_minutes)


def recovery_time_minutes(
    initial_concentration_per_m3: float,
    target_concentration_per_m3: float,
    ach: float,
    removal_efficiency: float = 1.0,
) -> float:
    """Time for the screening decay model to fall from initial to target."""
    if initial_concentration_per_m3 <= 0:
        raise ValueError("initial concentration must be positive")
    if target_concentration_per_m3 <= 0:
        raise ValueError("target concentration must be positive")
    if target_concentration_per_m3 >= initial_concentration_per_m3:
        return 0.0
    if ach <= 0:
        raise ValueError("ach must be positive")
    if not 0 < removal_efficiency <= 1:
        raise ValueError("removal_efficiency must be in (0, 1]")

    decay_rate_per_min = (ach / 60.0) * removal_efficiency
    return math.log(initial_concentration_per_m3 / target_concentration_per_m3) / decay_rate_per_min
