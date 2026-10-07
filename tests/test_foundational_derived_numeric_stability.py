from __future__ import annotations

import math

import pytest

from cleanroomx.calculations import (
    air_changes_per_hour,
    recovery_time_minutes,
    room_volume_m3,
)
from cleanroomx.models import RoomSpec


@pytest.mark.parametrize("dimension_m", (1e200, 1e-200))
def test_room_volume_rejects_derived_overflow_and_underflow(
    dimension_m: float,
) -> None:
    room = RoomSpec(
        "Extreme geometry",
        dimension_m,
        dimension_m,
        dimension_m,
        1200.0,
    )

    with pytest.raises(ValueError, match="room volume.*finite"):
        room_volume_m3(room)


def test_ach_rejects_derived_overflow() -> None:
    room = RoomSpec(
        "Extreme ACH",
        1e-100,
        1e-100,
        1e-100,
        1e308,
    )

    with pytest.raises(ValueError, match="air changes per hour.*finite"):
        air_changes_per_hour(room)


def test_recovery_time_avoids_intermediate_concentration_ratio_overflow() -> None:
    initial = 1e308
    target = 1e-308

    minutes = recovery_time_minutes(initial, target, ach=20.0)

    expected = 60.0 * (math.log(initial) - math.log(target)) / 20.0
    assert math.isfinite(minutes)
    assert minutes == pytest.approx(expected, rel=1e-15)


def test_recovery_time_rejects_nonrepresentable_finite_result() -> None:
    with pytest.raises(ValueError, match="recovery time result.*finite"):
        recovery_time_minutes(2.0, 1.0, ach=5e-324)


def test_normal_derived_calculations_are_unchanged() -> None:
    room = RoomSpec("R1", 6.0, 4.0, 3.0, 1800.0)

    assert room_volume_m3(room) == 72.0
    assert air_changes_per_hour(room) == 25.0
    assert recovery_time_minutes(1000.0, 100.0, ach=30.0) == pytest.approx(
        4.605170185988092
    )
