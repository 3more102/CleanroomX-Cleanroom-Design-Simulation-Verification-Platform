from __future__ import annotations

import math


BASE_2D_PIXELS_PER_M = 55.0
BASE_3D_PIXELS_PER_M = 34.0
MIN_ZOOM = 0.2
MAX_ZOOM = 8.0


def clamp_zoom(value: float) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError("zoom must be a finite positive number")
    return max(MIN_ZOOM, min(MAX_ZOOM, number))


def model_to_screen_2d(
    x_m: float,
    y_m: float,
    *,
    width_px: float,
    height_px: float,
    zoom: float,
    pan_x_px: float,
    pan_y_px: float,
) -> tuple[float, float]:
    scale = BASE_2D_PIXELS_PER_M * clamp_zoom(zoom)
    return (
        width_px / 2.0 + pan_x_px + x_m * scale,
        height_px / 2.0 + pan_y_px + y_m * scale,
    )


def screen_to_model_2d(
    x_px: float,
    y_px: float,
    *,
    width_px: float,
    height_px: float,
    zoom: float,
    pan_x_px: float,
    pan_y_px: float,
) -> tuple[float, float]:
    scale = BASE_2D_PIXELS_PER_M * clamp_zoom(zoom)
    return (
        (x_px - width_px / 2.0 - pan_x_px) / scale,
        (y_px - height_px / 2.0 - pan_y_px) / scale,
    )


def zoom_2d_at(
    factor: float,
    anchor_x_px: float,
    anchor_y_px: float,
    *,
    width_px: float,
    height_px: float,
    zoom: float,
    pan_x_px: float,
    pan_y_px: float,
) -> tuple[float, float, float]:
    factor_value = float(factor)
    if not math.isfinite(factor_value) or factor_value <= 0:
        raise ValueError("zoom factor must be a finite positive number")
    model_anchor = screen_to_model_2d(
        anchor_x_px,
        anchor_y_px,
        width_px=width_px,
        height_px=height_px,
        zoom=zoom,
        pan_x_px=pan_x_px,
        pan_y_px=pan_y_px,
    )
    new_zoom = clamp_zoom(clamp_zoom(zoom) * factor_value)
    after_x, after_y = model_to_screen_2d(
        *model_anchor,
        width_px=width_px,
        height_px=height_px,
        zoom=new_zoom,
        pan_x_px=pan_x_px,
        pan_y_px=pan_y_px,
    )
    return (
        new_zoom,
        pan_x_px + anchor_x_px - after_x,
        pan_y_px + anchor_y_px - after_y,
    )


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
) -> tuple[float, float]:
    azimuth = math.radians(float(azimuth_deg))
    elevation = math.radians(float(elevation_deg))
    xr = x_m * math.cos(azimuth) - y_m * math.sin(azimuth)
    yr = x_m * math.sin(azimuth) + y_m * math.cos(azimuth)
    sy = yr * math.sin(elevation) - z_m * math.cos(elevation)
    scale = BASE_3D_PIXELS_PER_M * clamp_zoom(zoom)
    return (
        width_px / 2.0 + pan_x_px + xr * scale,
        height_px * 0.66 + pan_y_px + sy * scale,
    )


def fit_3d_view(
    points_m: list[tuple[float, float, float]],
    *,
    width_px: float,
    height_px: float,
    azimuth_deg: float,
    elevation_deg: float,
    padding_fraction: float = 0.10,
    max_zoom: float = 5.0,
) -> tuple[float, float, float]:
    """Return zoom and pan that fit model-space points in the 3D viewport."""
    if not points_m:
        return 1.0, 0.0, 0.0

    width = float(width_px)
    height = float(height_px)
    padding = float(padding_fraction)
    zoom_limit = float(max_zoom)
    if not math.isfinite(width) or not math.isfinite(height) or width <= 0 or height <= 0:
        raise ValueError("viewport dimensions must be finite positive numbers")
    if not math.isfinite(padding) or not 0 <= padding < 0.5:
        raise ValueError("padding_fraction must be finite and between 0 and 0.5")
    if not math.isfinite(zoom_limit) or zoom_limit < MIN_ZOOM:
        raise ValueError("max_zoom must be finite and at least MIN_ZOOM")

    azimuth = math.radians(float(azimuth_deg))
    elevation = math.radians(float(elevation_deg))
    projected_m: list[tuple[float, float]] = []
    for x_m, y_m, z_m in points_m:
        values = (float(x_m), float(y_m), float(z_m))
        if not all(math.isfinite(value) for value in values):
            raise ValueError("3D fit points must be finite")
        x, y, z = values
        xr = x * math.cos(azimuth) - y * math.sin(azimuth)
        yr = x * math.sin(azimuth) + y * math.cos(azimuth)
        projected_m.append((xr, yr * math.sin(elevation) - z * math.cos(elevation)))

    min_x = min(x for x, _ in projected_m)
    max_x = max(x for x, _ in projected_m)
    min_y = min(y for _, y in projected_m)
    max_y = max(y for _, y in projected_m)
    span_x = max(max_x - min_x, 1e-12)
    span_y = max(max_y - min_y, 1e-12)
    usable_width = width * (1.0 - 2.0 * padding)
    usable_height = height * (1.0 - 2.0 * padding)
    raw_zoom = min(
        usable_width / (BASE_3D_PIXELS_PER_M * span_x),
        usable_height / (BASE_3D_PIXELS_PER_M * span_y),
    )
    zoom = max(MIN_ZOOM, min(MAX_ZOOM, zoom_limit, raw_zoom))
    scale = BASE_3D_PIXELS_PER_M * zoom

    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0
    pan_x = -center_x * scale
    pan_y = height / 2.0 - height * 0.66 - center_y * scale
    return zoom, pan_x, pan_y
