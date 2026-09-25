from __future__ import annotations

import math


BASE_2D_PIXELS_PER_M = 55.0
BASE_3D_PIXELS_PER_M = 34.0
MIN_ZOOM = 0.2
MAX_ZOOM = 8.0


def clamp_zoom(value: float) -> float:
    return max(MIN_ZOOM, min(MAX_ZOOM, float(value)))


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
    """Return zoom/pan preserving the model coordinate beneath the cursor."""
    if not math.isfinite(factor) or factor <= 0:
        raise ValueError("zoom factor must be a finite positive number")
    before = screen_to_model_2d(
        anchor_x_px,
        anchor_y_px,
        width_px=width_px,
        height_px=height_px,
        zoom=zoom,
        pan_x_px=pan_x_px,
        pan_y_px=pan_y_px,
    )
    new_zoom = clamp_zoom(zoom * factor)
    anchor_after = model_to_screen_2d(
        *before,
        width_px=width_px,
        height_px=height_px,
        zoom=new_zoom,
        pan_x_px=pan_x_px,
        pan_y_px=pan_y_px,
    )
    return (
        new_zoom,
        pan_x_px + anchor_x_px - anchor_after[0],
        pan_y_px + anchor_y_px - anchor_after[1],
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
    """Project model coordinates into the dependency-free engineering 3D canvas."""
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
