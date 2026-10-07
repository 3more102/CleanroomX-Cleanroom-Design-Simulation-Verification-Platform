import math

import pytest

from cleanroomx.calculations import air_changes_per_hour, decay_concentration, recovery_time_minutes, room_volume_m3
from cleanroomx.models import RoomSpec


def test_volume_and_ach():
    room = RoomSpec("R1", 6, 4, 3, 1800)
    assert room_volume_m3(room) == 72
    assert air_changes_per_hour(room) == 25


def test_decay_after_one_air_change_time_constant():
    result = decay_concentration(1000, ach=60, time_minutes=1)
    assert result == pytest.approx(1000 / math.e)


def test_recovery_time_round_trip():
    minutes = recovery_time_minutes(1000, 100, ach=30)
    assert decay_concentration(1000, ach=30, time_minutes=minutes) == pytest.approx(100)


def test_decay_rejects_invalid_efficiency():
    with pytest.raises(ValueError):
        decay_concentration(1000, ach=20, time_minutes=5, removal_efficiency=0)

def test_room_volume_rejects_nonfinite_derived_product() -> None:
    room = RoomSpec("Extreme", 1.0e200, 1.0e200, 1.0e10, 1.0e300)

    with pytest.raises(ValueError, match="room_volume_m3 must be finite"):
        room_volume_m3(room)


def test_ach_rejects_positive_result_that_underflows_to_zero() -> None:
    room = RoomSpec("Underflow", 1.0e100, 1.0e100, 1.0e100, 5.0e-324)

    with pytest.raises(ValueError, match="air_changes_per_hour must be > 0"):
        air_changes_per_hour(room)


def test_recovery_time_avoids_overflow_in_concentration_ratio() -> None:
    result = recovery_time_minutes(1.0e308, 1.0e-308, ach=60.0)
    expected = math.log(1.0e308) - math.log(1.0e-308)

    assert math.isfinite(result)
    assert result == pytest.approx(expected, rel=1e-15)


def test_recovery_time_preserves_precision_for_near_equal_concentrations() -> None:
    initial = math.nextafter(1.0, math.inf)

    result = recovery_time_minutes(initial, 1.0, ach=60.0)

    assert result == pytest.approx(math.log1p(initial - 1.0), rel=1e-15)
    assert result > 0.0


def test_decay_and_recovery_reject_unrepresentable_positive_decay_rate() -> None:
    tiny_ach = 5.0e-324

    with pytest.raises(ValueError, match="decay_rate_per_min must be > 0"):
        decay_concentration(1000.0, ach=tiny_ach, time_minutes=1.0)
    with pytest.raises(ValueError, match="decay_rate_per_min must be > 0"):
        recovery_time_minutes(1000.0, 100.0, ach=tiny_ach)

