from __future__ import annotations

import math


BASE_2D_PIXELS_PER_M = 55.0
BASE_3D_PIXELS_PER_M = 34.0
MIN_ZOOM = 0.2
MAX_ZOOM = 8.0


def clamp_zoom(value: float, *, minimum: float = MIN_ZOOM, maximum: float = MAX_ZOOM) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("zoom must be finite")
    if minimum <= 0 or maximum < minimum:
        raise ValueError("invalid zoom bounds")
    return max(minimum, min(maximum, number))


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
        float(width_px) / 2.0 + float(pan_x_px) + float(x_m) * scale,
        float(height_px) / 2.0 + float(pan_y_px) + float(y_m) * scale,
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
        (float(x_px) - float(width_px) / 2.0 - float(pan_x_px)) / scale,
        (float(y_px) - float(height_px) / 2.0 - float(pan_y_px)) / scale,
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
    world_x, world_y = screen_to_model_2d(
        anchor_x_px,
        anchor_y_px,
        width_px=width_px,
        height_px=height_px,
        zoom=zoom,
        pan_x_px=pan_x_px,
        pan_y_px=pan_y_px,
    )
    next_zoom = clamp_zoom(float(zoom) * factor_value)
    projected_x, projected_y = model_to_screen_2d(
        world_x,
        world_y,
        width_px=width_px,
        height_px=height_px,
        zoom=next_zoom,
        pan_x_px=pan_x_px,
        pan_y_px=pan_y_px,
    )
    return (
        next_zoom,
        float(pan_x_px) + float(anchor_x_px) - projected_x,
        float(pan_y_px) + float(anchor_y_px) - projected_y,
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
    xr = float(x_m) * math.cos(azimuth) - float(y_m) * math.sin(azimuth)
    yr = float(x_m) * math.sin(azimuth) + float(y_m) * math.cos(azimuth)
    sy = yr * math.sin(elevation) - float(z_m) * math.cos(elevation)
    scale = BASE_3D_PIXELS_PER_M * clamp_zoom(zoom)
    return (
        float(width_px) / 2.0 + float(pan_x_px) + xr * scale,
        float(height_px) * 0.66 + float(pan_y_px) + sy * scale,
    )
