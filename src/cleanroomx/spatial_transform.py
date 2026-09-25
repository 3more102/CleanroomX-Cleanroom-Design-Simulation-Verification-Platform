from __future__ import annotations

from dataclasses import dataclass
import math


DEFAULT_PIXELS_PER_M = 55.0
MIN_ZOOM = 0.2
MAX_ZOOM = 8.0


@dataclass(frozen=True)
class Viewport2D:
    """Pure metric-to-screen transform used by the 2D spatial editor."""

    width_px: float
    height_px: float
    zoom: float = 1.0
    pan_x_px: float = 0.0
    pan_y_px: float = 0.0
    pixels_per_m: float = DEFAULT_PIXELS_PER_M

    def __post_init__(self) -> None:
        for name, value in (
            ("width_px", self.width_px),
            ("height_px", self.height_px),
            ("zoom", self.zoom),
            ("pan_x_px", self.pan_x_px),
            ("pan_y_px", self.pan_y_px),
            ("pixels_per_m", self.pixels_per_m),
        ):
            if not math.isfinite(float(value)):
                raise ValueError(f"{name} must be finite")
        if self.width_px < 0 or self.height_px < 0:
            raise ValueError("viewport dimensions cannot be negative")
        if self.zoom <= 0 or self.pixels_per_m <= 0:
            raise ValueError("zoom and pixels_per_m must be greater than zero")

    @property
    def scale_px_per_m(self) -> float:
        return self.pixels_per_m * self.zoom

    def model_to_screen(self, x_m: float, y_m: float) -> tuple[float, float]:
        scale = self.scale_px_per_m
        return (
            self.width_px / 2.0 + self.pan_x_px + float(x_m) * scale,
            self.height_px / 2.0 + self.pan_y_px + float(y_m) * scale,
        )

    def screen_to_model(self, x_px: float, y_px: float) -> tuple[float, float]:
        scale = self.scale_px_per_m
        return (
            (float(x_px) - self.width_px / 2.0 - self.pan_x_px) / scale,
            (float(y_px) - self.height_px / 2.0 - self.pan_y_px) / scale,
        )

    def zoom_about(
        self,
        factor: float,
        x_px: float,
        y_px: float,
        *,
        min_zoom: float = MIN_ZOOM,
        max_zoom: float = MAX_ZOOM,
    ) -> "Viewport2D":
        factor = float(factor)
        if not math.isfinite(factor) or factor <= 0:
            raise ValueError("zoom factor must be finite and greater than zero")
        anchor = self.screen_to_model(x_px, y_px)
        zoom = max(min_zoom, min(max_zoom, self.zoom * factor))
        provisional = Viewport2D(
            self.width_px,
            self.height_px,
            zoom,
            self.pan_x_px,
            self.pan_y_px,
            self.pixels_per_m,
        )
        sx, sy = provisional.model_to_screen(*anchor)
        return Viewport2D(
            self.width_px,
            self.height_px,
            zoom,
            provisional.pan_x_px + float(x_px) - sx,
            provisional.pan_y_px + float(y_px) - sy,
            self.pixels_per_m,
        )


def fit_viewport(
    bounds_m: tuple[float, float, float, float],
    *,
    width_px: float,
    height_px: float,
    margin_fraction: float = 0.78,
    pixels_per_m: float = DEFAULT_PIXELS_PER_M,
    min_zoom: float = MIN_ZOOM,
    max_zoom: float = 5.0,
) -> Viewport2D:
    """Fit ordered model bounds into a viewport with deterministic centering."""

    min_x, min_y, max_x, max_y = (float(value) for value in bounds_m)
    if not all(math.isfinite(value) for value in (min_x, min_y, max_x, max_y)):
        raise ValueError("fit bounds must be finite")
    if max_x < min_x or max_y < min_y:
        raise ValueError("fit bounds must be ordered")
    if width_px <= 0 or height_px <= 0:
        raise ValueError("viewport dimensions must be greater than zero")
    if not 0 < margin_fraction <= 1:
        raise ValueError("margin_fraction must be in (0, 1]")

    model_width = max(1.0, max_x - min_x)
    model_height = max(1.0, max_y - min_y)
    zoom = margin_fraction * min(
        float(width_px) / (pixels_per_m * model_width),
        float(height_px) / (pixels_per_m * model_height),
    )
    zoom = max(min_zoom, min(max_zoom, zoom))
    scale = pixels_per_m * zoom
    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0
    return Viewport2D(
        float(width_px),
        float(height_px),
        zoom,
        -center_x * scale,
        -center_y * scale,
        pixels_per_m,
    )
