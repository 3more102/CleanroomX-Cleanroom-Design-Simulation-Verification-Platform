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
