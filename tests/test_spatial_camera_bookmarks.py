"""Camera-bookmark tests independent of the GUI and CFD engine."""
from __future__ import annotations

import copy
import math

import pytest

from cleanroomx.spatial_camera_bookmarks import CameraBookmarkStore, camera_snapshot


def view():
    return {
        "azimuth_deg": 35,
        "elevation_deg": 28.0,
        "zoom_3d": 1.5,
        "pan_3d_x": -82.2,
        "pan_3d_y": 40.75,
        "projection_mode": "perspective",
        "show_pressure": True,
        "overlay_mode": "pressure",
    }


def test_bookmark_captures_only_camera_fields_and_returns_an_independent_copy():
    data = view()
    before = copy.deepcopy(data)
    saved = camera_snapshot(data)
    assert data == before
    assert "show_pressure" not in saved
    assert "overlay_mode" not in saved
    assert saved["projection_mode"] == "perspective"
    store = CameraBookmarkStore()
    store.save(1, data)
    data["azimuth_deg"] = 190
    saved["zoom_3d"] = 99
    restored = store.recall(1)
    assert restored["azimuth_deg"] == 35
    assert restored["zoom_3d"] == 1.5
    restored["zoom_3d"] = 4
    assert store.recall(1)["zoom_3d"] == 1.5


def test_independent_slots_replacement_and_clear():
    store = CameraBookmarkStore()
    assert store.recall(1) is None
    assert not store.filled(2)
    store.save(1, view())
    second = view()
    second["azimuth_deg"] = 120.0
    store.save(2, second)
    assert store.recall(1)["azimuth_deg"] == 35
    assert store.recall(2)["azimuth_deg"] == 120
    store.save(1, second)
    assert store.recall(1)["azimuth_deg"] == 120
    store.clear()
    assert all(store.recall(i) is None for i in (1, 2, 3))


@pytest.mark.parametrize("slot", [0, 4, -1, "2", True, 2.0])
def test_invalid_slot_cannot_be_saved_or_recalled(slot):
    store = CameraBookmarkStore()
    with pytest.raises(ValueError, match="slot 1, 2, or 3"):
        store.save(slot, view())
    with pytest.raises(ValueError):
        store.recall(slot)


@pytest.mark.parametrize("key,bad", [
    ("azimuth_deg", math.nan),
    ("elevation_deg", math.inf),
    ("zoom_3d", 0),
    ("zoom_3d", -1),
    ("pan_3d_x", -math.inf),
    ("pan_3d_y", True),
    ("projection_mode", "fisheye"),
])
def test_malformed_camera_rejected_before_overwriting_saved_slot(key, bad):
    store = CameraBookmarkStore()
    store.save(1, view())
    data = view()
    data[key] = bad
    with pytest.raises(ValueError):
        store.save(1, data)
    assert store.recall(1) == camera_snapshot(view())


def test_missing_projection_defaults_to_orthographic_without_guessing_other_fields():
    data = view()
    data.pop("projection_mode")
    assert camera_snapshot(data)["projection_mode"] == "orthographic"
    data.pop("azimuth_deg")
    with pytest.raises(ValueError):
        camera_snapshot(data)
