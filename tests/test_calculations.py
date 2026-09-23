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
