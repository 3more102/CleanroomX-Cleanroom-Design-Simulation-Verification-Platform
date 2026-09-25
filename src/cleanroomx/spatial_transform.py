from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ViewTransform2D:
    """Pure model/screen transform used by the interactive layout editor."""

    viewport_width_px: float
    viewport_height_px: float
    zoom: float = 1.0
    pan_x_px: float = 0.0
    pan_y_px: float = 0.0
    pixels_per_m: float = 55.0

    @property
    def scale_px_per_m(self) -> float:
        return self.pixels_per_m * self.zoom

    def model_to_screen(self, x_m: float, y_m: float) -> tuple[float, float]:
        scale = self.scale_px_per_m
        return (
            self.viewport_width_px / 2.0 + self.pan_x_px + x_m * scale,
            self.viewport_height_px / 2.0 + self.pan_y_px + y_m * scale,
        )

    def screen_to_model(self, x_px: float, y_px: float) -> tuple[float, float]:
        scale = self.scale_px_per_m
        if not math.isfinite(scale) or scale <= 0:
            raise ValueError("2D transform scale must be finite and greater than zero")
        return (
            (x_px - self.viewport_width_px / 2.0 - self.pan_x_px) / scale,
            (y_px - self.viewport_height_px / 2.0 - self.pan_y_px) / scale,
        )

    def zoom_about(
        self,
        factor: float,
        anchor_x_px: float,
        anchor_y_px: float,
        *,
        minimum_zoom: float = 0.2,
        maximum_zoom: float = 8.0,
    ) -> "ViewTransform2D":
        if not math.isfinite(factor) or factor <= 0:
            raise ValueError("zoom factor must be finite and greater than zero")
        world_anchor = self.screen_to_model(anchor_x_px, anchor_y_px)
        new_zoom = max(minimum_zoom, min(maximum_zoom, self.zoom * factor))
        provisional = ViewTransform2D(
            self.viewport_width_px,
            self.viewport_height_px,
            zoom=new_zoom,
            pan_x_px=self.pan_x_px,
            pan_y_px=self.pan_y_px,
            pixels_per_m=self.pixels_per_m,
        )
        projected = provisional.model_to_screen(*world_anchor)
        return ViewTransform2D(
            self.viewport_width_px,
            self.viewport_height_px,
            zoom=new_zoom,
            pan_x_px=self.pan_x_px + anchor_x_px - projected[0],
            pan_y_px=self.pan_y_px + anchor_y_px - projected[1],
            pixels_per_m=self.pixels_per_m,
        )


@dataclass(frozen=True)
class IsometricProjector3D:
    """Deterministic lightweight 3D projection without external GUI dependencies."""

    viewport_width_px: float
    viewport_height_px: float
    azimuth_deg: float = 35.0
    elevation_deg: float = 28.0
    zoom: float = 1.0
    pan_x_px: float = 0.0
    pan_y_px: float = 0.0
    pixels_per_m: float = 34.0
    vertical_anchor: float = 0.66

    def project(self, x_m: float, y_m: float, z_m: float) -> tuple[float, float]:
        azimuth = math.radians(self.azimuth_deg)
        elevation = math.radians(self.elevation_deg)
        x_rotated = x_m * math.cos(azimuth) - y_m * math.sin(azimuth)
        y_rotated = x_m * math.sin(azimuth) + y_m * math.cos(azimuth)
        screen_y = y_rotated * math.sin(elevation) - z_m * math.cos(elevation)
        scale = self.pixels_per_m * self.zoom
        return (
            self.viewport_width_px / 2.0 + self.pan_x_px + x_rotated * scale,
            self.viewport_height_px * self.vertical_anchor + self.pan_y_px + screen_y * scale,
        )
