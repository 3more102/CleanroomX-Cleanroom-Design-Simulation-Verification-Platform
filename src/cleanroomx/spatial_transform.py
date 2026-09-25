from __future__ import annotations

from dataclasses import dataclass
import math


DEFAULT_PIXELS_PER_METER = 55.0
MIN_ZOOM = 0.2
MAX_ZOOM = 8.0


def _finite(value: float, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


@dataclass(frozen=True)
class ViewTransform2D:
    """Pure model/screen transform used by the Tk editor and headless tests."""

    width_px: float
    height_px: float
    zoom: float = 1.0
    pan_x_px: float = 0.0
    pan_y_px: float = 0.0
    pixels_per_meter: float = DEFAULT_PIXELS_PER_METER

    def __post_init__(self) -> None:
        for field_name in (
            "width_px",
            "height_px",
            "zoom",
            "pan_x_px",
            "pan_y_px",
            "pixels_per_meter",
        ):
            value = _finite(getattr(self, field_name), field_name)
            object.__setattr__(self, field_name, value)
        if self.width_px <= 0 or self.height_px <= 0:
            raise ValueError("viewport dimensions must be greater than zero")
        if self.zoom <= 0 or self.pixels_per_meter <= 0:
            raise ValueError("zoom and pixels_per_meter must be greater than zero")

    @property
    def scale_px_per_m(self) -> float:
        return self.zoom * self.pixels_per_meter

    def model_to_screen(self, x_m: float, y_m: float) -> tuple[float, float]:
        x = _finite(x_m, "x_m")
        y = _finite(y_m, "y_m")
        scale = self.scale_px_per_m
        return (
            self.width_px / 2.0 + self.pan_x_px + x * scale,
            self.height_px / 2.0 + self.pan_y_px + y * scale,
        )

    def screen_to_model(self, x_px: float, y_px: float) -> tuple[float, float]:
        x = _finite(x_px, "x_px")
        y = _finite(y_px, "y_px")
        scale = self.scale_px_per_m
        return (
            (x - self.width_px / 2.0 - self.pan_x_px) / scale,
            (y - self.height_px / 2.0 - self.pan_y_px) / scale,
        )

    def zoom_about(
        self,
        factor: float,
        anchor_x_px: float,
        anchor_y_px: float,
        *,
        min_zoom: float = MIN_ZOOM,
        max_zoom: float = MAX_ZOOM,
    ) -> "ViewTransform2D":
        factor_value = _finite(factor, "factor")
        if factor_value <= 0:
            raise ValueError("factor must be greater than zero")
        minimum = _finite(min_zoom, "min_zoom")
        maximum = _finite(max_zoom, "max_zoom")
        if minimum <= 0 or maximum < minimum:
            raise ValueError("invalid zoom bounds")
        anchor_x = _finite(anchor_x_px, "anchor_x_px")
        anchor_y = _finite(anchor_y_px, "anchor_y_px")
        world_x, world_y = self.screen_to_model(anchor_x, anchor_y)
        new_zoom = max(minimum, min(maximum, self.zoom * factor_value))
        new_scale = new_zoom * self.pixels_per_meter
        return ViewTransform2D(
            width_px=self.width_px,
            height_px=self.height_px,
            zoom=new_zoom,
            pan_x_px=anchor_x - self.width_px / 2.0 - world_x * new_scale,
            pan_y_px=anchor_y - self.height_px / 2.0 - world_y * new_scale,
            pixels_per_meter=self.pixels_per_meter,
        )

    @classmethod
    def fit_bounds(
        cls,
        bounds_m: tuple[float, float, float, float],
        *,
        width_px: float,
        height_px: float,
        padding_fraction: float = 0.12,
        pixels_per_meter: float = DEFAULT_PIXELS_PER_METER,
        min_zoom: float = MIN_ZOOM,
        max_zoom: float = MAX_ZOOM,
    ) -> "ViewTransform2D":
        min_x, min_y, max_x, max_y = (_finite(value, "bounds") for value in bounds_m)
        if max_x < min_x or max_y < min_y:
            raise ValueError("bounds must be ordered")
        width = _finite(width_px, "width_px")
        height = _finite(height_px, "height_px")
        if width <= 0 or height <= 0:
            raise ValueError("viewport dimensions must be greater than zero")
        padding = _finite(padding_fraction, "padding_fraction")
        if not 0 <= padding < 0.5:
            raise ValueError("padding_fraction must be between 0 and 0.5")
        ppm = _finite(pixels_per_meter, "pixels_per_meter")
        if ppm <= 0:
            raise ValueError("pixels_per_meter must be greater than zero")
        model_width = max(max_x - min_x, 1e-12)
        model_height = max(max_y - min_y, 1e-12)
        usable_width = width * (1.0 - 2.0 * padding)
        usable_height = height * (1.0 - 2.0 * padding)
        zoom = min(usable_width / (ppm * model_width), usable_height / (ppm * model_height))
        zoom = max(min_zoom, min(max_zoom, zoom))
        scale = ppm * zoom
        center_x = (min_x + max_x) / 2.0
        center_y = (min_y + max_y) / 2.0
        return cls(
            width_px=width,
            height_px=height,
            zoom=zoom,
            pan_x_px=-center_x * scale,
            pan_y_px=-center_y * scale,
            pixels_per_meter=ppm,
        )


def snap_point(
    x_m: float,
    y_m: float,
    grid_m: float,
    *,
    enabled: bool = True,
) -> tuple[float, float]:
    x = _finite(x_m, "x_m")
    y = _finite(y_m, "y_m")
    grid = _finite(grid_m, "grid_m")
    if grid <= 0:
        raise ValueError("grid_m must be greater than zero")
    if not enabled:
        return x, y
    return round(x / grid) * grid, round(y / grid) * grid
