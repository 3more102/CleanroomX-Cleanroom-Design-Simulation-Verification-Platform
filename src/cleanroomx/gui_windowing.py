from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk


DEFAULT_DIALOG_MARGIN = 48


@dataclass(frozen=True)
class WindowFit:
    width: int
    height: int
    minimum_width: int
    minimum_height: int


def fit_window_metrics(
    preferred_width: int,
    preferred_height: int,
    minimum_width: int,
    minimum_height: int,
    screen_width: int,
    screen_height: int,
    *,
    margin: int = DEFAULT_DIALOG_MARGIN,
) -> WindowFit:
    """Return display-safe initial and minimum window dimensions.

    The calculation is presentation-only. It reserves a small edge margin for
    window chrome/taskbars and caps minimum sizes as well as initial sizes so a
    Tk toplevel cannot force itself larger than the available display.
    """
    screen_w = max(1, int(screen_width))
    screen_h = max(1, int(screen_height))
    edge = max(0, int(margin))
    available_width = max(1, screen_w - min(screen_w - 1, edge * 2))
    available_height = max(1, screen_h - min(screen_h - 1, edge * 2))

    width = min(max(1, int(preferred_width)), available_width)
    height = min(max(1, int(preferred_height)), available_height)
    min_width = min(max(1, int(minimum_width)), width)
    min_height = min(max(1, int(minimum_height)), height)
    return WindowFit(width, height, min_width, min_height)


def fit_window_to_display(
    window: tk.Misc,
    *,
    preferred_width: int,
    preferred_height: int,
    minimum_width: int,
    minimum_height: int,
    margin: int = DEFAULT_DIALOG_MARGIN,
) -> WindowFit:
    """Apply display-safe geometry to a Tk toplevel and return the metrics."""
    metrics = fit_window_metrics(
        preferred_width,
        preferred_height,
        minimum_width,
        minimum_height,
        window.winfo_screenwidth(),
        window.winfo_screenheight(),
        margin=margin,
    )
    window.geometry(f"{metrics.width}x{metrics.height}")
    window.minsize(metrics.minimum_width, metrics.minimum_height)
    return metrics
