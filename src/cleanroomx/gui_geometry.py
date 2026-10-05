from __future__ import annotations

from typing import Any


def clamp_dimension_to_display(value: int, screen_value: int) -> int:
    """Clamp a positive window dimension to the current display extent."""
    return min(max(1, int(value)), max(1, int(screen_value)))


def configure_toplevel_geometry(
    window: Any,
    *,
    width: int,
    height: int,
    min_width: int,
    min_height: int,
) -> tuple[int, int, int, int]:
    """Apply display-bounded geometry to a Tk-like top-level window.

    Tk reports screen dimensions through the window itself. Keeping this helper
    toolkit-light makes the sizing policy testable without requiring a display.
    """
    screen_width = max(1, int(window.winfo_screenwidth()))
    screen_height = max(1, int(window.winfo_screenheight()))
    fitted_width = clamp_dimension_to_display(width, screen_width)
    fitted_height = clamp_dimension_to_display(height, screen_height)
    fitted_min_width = clamp_dimension_to_display(min_width, fitted_width)
    fitted_min_height = clamp_dimension_to_display(min_height, fitted_height)

    window.geometry(f"{fitted_width}x{fitted_height}")
    window.minsize(fitted_min_width, fitted_min_height)
    return (
        fitted_width,
        fitted_height,
        fitted_min_width,
        fitted_min_height,
    )
