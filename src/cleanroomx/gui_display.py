from __future__ import annotations

from dataclasses import dataclass
import sys
from typing import Any


_BASE_DPI = 96.0
_POINTS_PER_INCH = 72.0
_BASE_TK_SCALING = _BASE_DPI / _POINTS_PER_INCH


@dataclass(frozen=True)
class DisplayMetrics:
    tk_scaling: float
    effective_dpi: float
    layout_scale: float


def layout_scale_from_tk_scaling(value: Any) -> float:
    """Translate Tk pixels-per-point scaling into a Windows 96-DPI ratio."""
    try:
        scaling = float(value)
    except (TypeError, ValueError, OverflowError):
        scaling = _BASE_TK_SCALING
    if not 0.5 <= scaling <= 8.0:
        scaling = _BASE_TK_SCALING
    ratio = scaling / _BASE_TK_SCALING
    return min(3.0, max(0.75, ratio))


def detect_display_metrics(root: Any) -> DisplayMetrics:
    try:
        scaling = float(root.tk.call("tk", "scaling"))
    except (AttributeError, TypeError, ValueError, OverflowError, RuntimeError):
        scaling = _BASE_TK_SCALING
    scale = layout_scale_from_tk_scaling(scaling)
    return DisplayMetrics(
        tk_scaling=scaling,
        effective_dpi=scaling * _POINTS_PER_INCH,
        layout_scale=scale,
    )


def platform_layout_scale(root: Any, *, platform: str | None = None) -> float:
    """Return geometry scaling only where CleanroomX opts into Windows DPI awareness.

    Tk already handles point/font scaling on other platforms, so changing geometry
    there would double-apply desktop scaling.
    """
    token = sys.platform if platform is None else str(platform)
    if token != "win32":
        return 1.0
    return detect_display_metrics(root).layout_scale


def scale_window_size(
    width: int,
    height: int,
    scale: float,
    *,
    screen_width: int,
    screen_height: int,
) -> tuple[int, int]:
    factor = min(3.0, max(0.75, float(scale)))
    scaled_width = max(1, int(round(int(width) * factor)))
    scaled_height = max(1, int(round(int(height) * factor)))
    return (
        min(scaled_width, max(1, int(screen_width))),
        min(scaled_height, max(1, int(screen_height))),
    )


def enable_windows_per_monitor_dpi_awareness(
    *,
    platform: str | None = None,
) -> str:
    """Request the strongest available Windows DPI-awareness mode.

    This must run before Tk creates the first window. Failure is deliberately
    non-fatal because awareness may already be established by an executable
    manifest or host process.
    """
    token = sys.platform if platform is None else str(platform)
    if token != "win32":
        return "not-windows"

    try:
        import ctypes
    except ImportError:
        return "unavailable"

    try:
        user32 = ctypes.windll.user32
        setter = getattr(user32, "SetProcessDpiAwarenessContext", None)
        if setter is not None:
            setter.restype = ctypes.c_bool
            # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
            if setter(ctypes.c_void_p(-4)):
                return "per-monitor-v2"
    except (AttributeError, OSError, TypeError, ValueError):
        pass

    try:
        shcore = ctypes.windll.shcore
        setter = getattr(shcore, "SetProcessDpiAwareness", None)
        if setter is not None:
            result = int(setter(2))  # PROCESS_PER_MONITOR_DPI_AWARE
            if result == 0:
                return "per-monitor"
            # E_ACCESSDENIED commonly means the process awareness was set already.
            if result & 0xFFFFFFFF == 0x80070005:
                return "already-configured"
    except (AttributeError, OSError, TypeError, ValueError):
        pass

    try:
        user32 = ctypes.windll.user32
        setter = getattr(user32, "SetProcessDPIAware", None)
        if setter is not None and setter():
            return "system"
    except (AttributeError, OSError, TypeError, ValueError):
        pass

    return "unavailable"
