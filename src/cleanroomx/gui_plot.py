from __future__ import annotations

import math
from typing import Any


def finite_series_points(plot: Any) -> list[dict[str, Any]]:
    """Extract only finite backend-supplied samples from a plot payload."""
    if not isinstance(plot, dict):
        return []
    series_items = plot.get("series")
    if not isinstance(series_items, list):
        return []
    points: list[dict[str, Any]] = []
    for series_index, series in enumerate(series_items):
        if not isinstance(series, dict):
            continue
        xs = series.get("x")
        ys = series.get("y")
        if not isinstance(xs, (list, tuple)) or not isinstance(ys, (list, tuple)):
            continue
        name = str(series.get("name") or f"Series {series_index + 1}")
        for point_index, (raw_x, raw_y) in enumerate(zip(xs, ys)):
            if isinstance(raw_x, bool) or isinstance(raw_y, bool):
                continue
            try:
                x = float(raw_x)
                y = float(raw_y)
            except (TypeError, ValueError, OverflowError):
                continue
            if not math.isfinite(x) or not math.isfinite(y):
                continue
            points.append(
                {
                    "series_index": series_index,
                    "point_index": point_index,
                    "series": name,
                    "x": x,
                    "y": y,
                }
            )
    return points


def finite_marker_points(plot: Any) -> list[dict[str, Any]]:
    """Extract finite explicit markers without creating derived engineering values."""
    if not isinstance(plot, dict):
        return []
    markers = plot.get("markers")
    if not isinstance(markers, list):
        return []
    result: list[dict[str, Any]] = []
    for index, marker in enumerate(markers):
        if not isinstance(marker, dict):
            continue
        raw_x = marker.get("x")
        raw_y = marker.get("y")
        if isinstance(raw_x, bool) or isinstance(raw_y, bool):
            continue
        try:
            x = float(raw_x)
            y = float(raw_y)
        except (TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(x) or not math.isfinite(y):
            continue
        result.append(
            {
                "marker_index": index,
                "name": str(marker.get("name") or f"Marker {index + 1}"),
                "x": x,
                "y": y,
            }
        )
    return result


def padded_plot_bounds(
    series_points: list[dict[str, Any]],
    marker_points: list[dict[str, Any]] | None = None,
) -> tuple[float, float, float, float] | None:
    """Return presentation bounds around existing samples and explicit markers."""
    points = list(series_points)
    if marker_points:
        points.extend(marker_points)
    if not points:
        return None
    xs = [float(item["x"]) for item in points]
    ys = [float(item["y"]) for item in points]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    if xmax == xmin:
        delta = max(1.0, abs(xmin) * 0.05)
        xmin -= delta
        xmax += delta
    else:
        delta = (xmax - xmin) * 0.05
        xmin -= delta
        xmax += delta
    if ymax == ymin:
        delta = max(1.0, abs(ymin) * 0.08)
        ymin -= delta
        ymax += delta
    else:
        delta = (ymax - ymin) * 0.08
        ymin -= delta
        ymax += delta
    return xmin, xmax, ymin, ymax


def linear_ticks(low: float, high: float, *, count: int = 6) -> tuple[float, ...]:
    """Generate deterministic display ticks over an already-established range."""
    total = max(2, int(count))
    if not math.isfinite(low) or not math.isfinite(high):
        return ()
    if high <= low:
        return (float(low),)
    step = (high - low) / float(total - 1)
    return tuple(low + step * index for index in range(total))


def nearest_screen_point(
    points: list[dict[str, Any]],
    x: float,
    y: float,
    *,
    max_distance: float = 14.0,
) -> dict[str, Any] | None:
    """Return the nearest rendered point inside a pixel-distance threshold."""
    limit = max(0.0, float(max_distance))
    best: dict[str, Any] | None = None
    best_distance_sq = limit * limit
    for item in points:
        try:
            px = float(item["px"])
            py = float(item["py"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(px) or not math.isfinite(py):
            continue
        distance_sq = (px - x) ** 2 + (py - y) ** 2
        if distance_sq <= best_distance_sq:
            best_distance_sq = distance_sq
            best = item
    return best
