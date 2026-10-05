from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .gui_theme import normalize_density_name, normalize_theme_name
from .persistence import atomic_write_text


GUI_LAYOUT_STATE_VERSION = 5
_DEFAULT_GUI_LAYOUT_STATE = {
    "version": GUI_LAYOUT_STATE_VERSION,
    "navigator_visible": True,
    "output_visible": True,
    "inspector_visible": True,
    "theme": "dark",
    "density": "comfortable",
    "recent_projects": [],
    "window_width": 1440,
    "window_height": 900,
    "navigator_fraction": 0.20,
    "output_fraction": 0.72,
    "inspector_fraction": 0.78,
}


def default_gui_layout_state_path() -> Path:
    """Return the per-user GUI layout state path without touching project data."""
    return Path.home() / ".cleanroomx" / "gui-layout.json"


def _bounded_fraction(value: Any, default: float) -> float:
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not 0.05 <= number <= 0.95:
        return default
    return number


def _bounded_dimension(
    value: Any,
    default: int,
    *,
    minimum: int,
    maximum: int = 10000,
) -> int:
    if isinstance(value, bool):
        return default
    try:
        dimension = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not minimum <= dimension <= maximum:
        return default
    return dimension


def clamp_window_size_to_display(
    width: int,
    height: int,
    screen_width: int,
    screen_height: int,
) -> tuple[int, int]:
    """Fit a requested window size within the current display bounds."""
    available_width = max(1, int(screen_width))
    available_height = max(1, int(screen_height))
    fitted_width = min(max(1, int(width)), available_width)
    fitted_height = min(max(1, int(height)), available_height)
    return fitted_width, fitted_height


def _normalize_recent_projects(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    recent: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        path = item.strip()
        if not path or chr(0) in path or path in seen:
            continue
        try:
            Path(path)
        except (OSError, ValueError):
            continue
        seen.add(path)
        recent.append(path)
        if len(recent) >= 8:
            break
    return recent


def normalize_gui_layout_state(value: Any) -> dict[str, Any]:
    """Normalize persisted presentation state and discard unsupported fields."""
    source = value if isinstance(value, dict) else {}
    return {
        "version": GUI_LAYOUT_STATE_VERSION,
        "navigator_visible": (
            source.get("navigator_visible")
            if isinstance(source.get("navigator_visible"), bool)
            else _DEFAULT_GUI_LAYOUT_STATE["navigator_visible"]
        ),
        "output_visible": (
            source.get("output_visible")
            if isinstance(source.get("output_visible"), bool)
            else _DEFAULT_GUI_LAYOUT_STATE["output_visible"]
        ),
        "inspector_visible": (
            source.get("inspector_visible")
            if isinstance(source.get("inspector_visible"), bool)
            else _DEFAULT_GUI_LAYOUT_STATE["inspector_visible"]
        ),
        "theme": normalize_theme_name(
            source.get("theme", _DEFAULT_GUI_LAYOUT_STATE["theme"])
        ),
        "density": normalize_density_name(
            source.get("density", _DEFAULT_GUI_LAYOUT_STATE["density"])
        ),
        "recent_projects": _normalize_recent_projects(
            source.get("recent_projects")
        ),
        "window_width": _bounded_dimension(
            source.get("window_width"),
            _DEFAULT_GUI_LAYOUT_STATE["window_width"],
            minimum=1050,
        ),
        "window_height": _bounded_dimension(
            source.get("window_height"),
            _DEFAULT_GUI_LAYOUT_STATE["window_height"],
            minimum=680,
        ),
        "navigator_fraction": _bounded_fraction(
            source.get("navigator_fraction"),
            _DEFAULT_GUI_LAYOUT_STATE["navigator_fraction"],
        ),
        "output_fraction": _bounded_fraction(
            source.get("output_fraction"),
            _DEFAULT_GUI_LAYOUT_STATE["output_fraction"],
        ),
        "inspector_fraction": _bounded_fraction(
            source.get("inspector_fraction"),
            _DEFAULT_GUI_LAYOUT_STATE["inspector_fraction"],
        ),
    }


def load_gui_layout_state(path: str | Path) -> dict[str, Any]:
    """Load GUI-only layout state; missing or malformed files fall back safely."""
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
        payload = {}
    return normalize_gui_layout_state(payload)


def save_gui_layout_state(path: str | Path, state: Any) -> Path:
    """Atomically persist normalized GUI-only layout state."""
    normalized = normalize_gui_layout_state(state)
    text = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    ) + "\n"
    return atomic_write_text(path, text)
