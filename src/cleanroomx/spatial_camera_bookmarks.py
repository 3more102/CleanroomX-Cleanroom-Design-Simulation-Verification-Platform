"""Session-only camera bookmarks for the CleanroomX 3D design workspace.

Bookmarks never touch CAD room/device geometry, OpenFOAM solver output or
verification evidence. They are local to the active project in this GUI session
and are discarded when a different project object is loaded.
"""
from __future__ import annotations

import math
from typing import Any

SLOTS = (1, 2, 3)
CAMERA_FIELDS = (
    "azimuth_deg",
    "elevation_deg",
    "zoom_3d",
    "pan_3d_x",
    "pan_3d_y",
    "projection_mode",
)


def camera_snapshot(view: dict[str, Any]) -> dict[str, float | str]:
    """Capture real, bounded camera values without normalizing bad inputs."""
    data: dict[str, float | str] = {}
    for name in CAMERA_FIELDS:
        if name == "projection_mode":
            mode = view.get(name, "orthographic")
            if mode not in {"orthographic", "perspective"}:
                raise ValueError("Invalid camera projection")
            data[name] = mode
            continue
        value = view.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Camera field {name} must be numeric")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"Camera field {name} must be finite")
        if name == "zoom_3d" and not 0 < number <= 1000:
            raise ValueError("Camera zoom is outside supported bounds")
        if name == "elevation_deg" and not -90 <= number <= 90:
            raise ValueError("Camera elevation is outside supported bounds")
        if name in ("pan_3d_x", "pan_3d_y") and abs(number) > 10000000:
            raise ValueError("Camera pan is outside supported bounds")
        if name == "azimuth_deg" and abs(number) > 10000000:
            raise ValueError("Camera azimuth is outside supported bounds")
        data[name] = number
    return data


class CameraBookmarkStore:
    """Bounded, non-persistent camera state for three per-session slots."""

    def __init__(self) -> None:
        self._slots: dict[int, dict[str, float | str]] = {}

    @staticmethod
    def _check_slot(slot: int) -> None:
        if type(slot) is not int or slot not in SLOTS:
            raise ValueError("Camera bookmark must be slot 1, 2, or 3")

    def save(self, slot: int, view: dict[str, Any]) -> None:
        self._check_slot(slot)
        self._slots[slot] = camera_snapshot(view)

    def recall(self, slot: int) -> dict[str, float | str] | None:
        self._check_slot(slot)
        item = self._slots.get(slot)
        return dict(item) if item is not None else None

    def filled(self, slot: int) -> bool:
        self._check_slot(slot)
        return slot in self._slots

    def clear(self) -> None:
        self._slots.clear()
