from __future__ import annotations

import math
from collections.abc import Iterable


BASE_3D_PIXELS_PER_M = 34.0
MIN_ZOOM = 0.2
MAX_ZOOM = 8.0


def _finite(value: float, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def clamp_zoom(value: float, *, minimum: float = MIN_ZOOM, maximum: float = MAX_ZOOM) -> float:
    zoom = _finite(value, "zoom")
    low = _finite(minimum, "minimum")
    high = _finite(maximum, "maximum")
    if low <= 0 or high < low:
        raise ValueError("invalid zoom bounds")
    return max(low, min(high, zoom))


def project_3d(
    x_m: float,
    y_m: float,
    z_m: float,
    *,
    width_px: float,
    height_px: float,
    azimuth_deg: float,
    elevation_deg: float,
    zoom: float,
    pan_x_px: float,
    pan_y_px: float,
    pixels_per_meter: float = BASE_3D_PIXELS_PER_M,
) -> tuple[float, float]:
    """Project one model-space point into the Tk 3D viewport.

    The projection is intentionally orthographic: the 3D workspace is a
    deterministic engineering visualization, not a perspective/CFD renderer.
    """
    x = _finite(x_m, "x_m")
    y = _finite(y_m, "y_m")
    z = _finite(z_m, "z_m")
    width = _finite(width_px, "width_px")
    height = _finite(height_px, "height_px")
    azimuth = math.radians(_finite(azimuth_deg, "azimuth_deg"))
    elevation = math.radians(_finite(elevation_deg, "elevation_deg"))
    scale = _finite(pixels_per_meter, "pixels_per_meter") * clamp_zoom(zoom)
    pan_x = _finite(pan_x_px, "pan_x_px")
    pan_y = _finite(pan_y_px, "pan_y_px")
    if width <= 0 or height <= 0 or scale <= 0:
        raise ValueError("viewport dimensions and projection scale must be positive")

    xr = x * math.cos(azimuth) - y * math.sin(azimuth)
    yr = x * math.sin(azimuth) + y * math.cos(azimuth)
    sy = yr * math.sin(elevation) - z * math.cos(elevation)
    return (
        width / 2.0 + pan_x + xr * scale,
        height * 0.66 + pan_y + sy * scale,
    )


def fit_3d_view(
    points_m: Iterable[tuple[float, float, float]],
    *,
    width_px: float,
    height_px: float,
    azimuth_deg: float,
    elevation_deg: float,
    padding_fraction: float = 0.10,
    pixels_per_meter: float = BASE_3D_PIXELS_PER_M,
    min_zoom: float = MIN_ZOOM,
    max_zoom: float = MAX_ZOOM,
) -> tuple[float, float, float]:
    """Return (zoom, pan_x_px, pan_y_px) fitting projected points in view."""
    points = list(points_m)
    if not points:
        return 1.0, 0.0, 0.0

    width = _finite(width_px, "width_px")
    height = _finite(height_px, "height_px")
    padding = _finite(padding_fraction, "padding_fraction")
    ppm = _finite(pixels_per_meter, "pixels_per_meter")
    if width <= 0 or height <= 0:
        raise ValueError("viewport dimensions must be positive")
    if ppm <= 0:
        raise ValueError("pixels_per_meter must be positive")
    if not 0 <= padding < 0.5:
        raise ValueError("padding_fraction must be between 0 and 0.5")

    azimuth = math.radians(_finite(azimuth_deg, "azimuth_deg"))
    elevation = math.radians(_finite(elevation_deg, "elevation_deg"))
    projected_m: list[tuple[float, float]] = []
    for x_m, y_m, z_m in points:
        x = _finite(x_m, "x_m")
        y = _finite(y_m, "y_m")
        z = _finite(z_m, "z_m")
        xr = x * math.cos(azimuth) - y * math.sin(azimuth)
        yr = x * math.sin(azimuth) + y * math.cos(azimuth)
        projected_m.append((xr, yr * math.sin(elevation) - z * math.cos(elevation)))

    min_x = min(point[0] for point in projected_m)
    max_x = max(point[0] for point in projected_m)
    min_y = min(point[1] for point in projected_m)
    max_y = max(point[1] for point in projected_m)
    span_x = max(max_x - min_x, 1e-12)
    span_y = max(max_y - min_y, 1e-12)
    usable_width = width * (1.0 - 2.0 * padding)
    usable_height = height * (1.0 - 2.0 * padding)
    scale = min(usable_width / span_x, usable_height / span_y)
    zoom = clamp_zoom(scale / ppm, minimum=min_zoom, maximum=max_zoom)
    final_scale = ppm * zoom

    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0
    pan_x = -center_x * final_scale
    pan_y = height / 2.0 - height * 0.66 - center_y * final_scale
    return zoom, pan_x, pan_y
