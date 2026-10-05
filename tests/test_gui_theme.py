from __future__ import annotations

from cleanroomx.gui_theme import (
    normalize_density_name,
    normalize_theme_name,
    theme_palette,
)


def test_theme_name_normalization_is_strict_and_deterministic():
    assert normalize_theme_name("light") == "light"
    assert normalize_theme_name(" DARK ") == "dark"
    assert normalize_theme_name("") == "light"
    assert normalize_theme_name("system") == "light"
    assert normalize_theme_name(None) == "light"


def test_light_and_dark_palettes_are_complete_and_distinct():
    light = theme_palette("light")
    dark = theme_palette("dark")

    required = {
        "background",
        "surface",
        "surface_alt",
        "panel",
        "text",
        "muted",
        "border",
        "accent",
        "accent_hover",
        "accent_text",
        "selection",
        "selection_text",
        "field",
        "field_text",
        "tree",
        "disabled",
        "canvas_2d",
        "canvas_3d",
        "plot",
        "grid",
        "info",
        "simulation",
        "evidence",
        "pass",
        "warning",
        "error",
        "stale",
        "suppressed",
        "pass_surface",
        "warning_surface",
        "error_surface",
        "stale_surface",
    }
    assert set(light) == required
    assert set(dark) == required
    assert light["background"] != dark["background"]
    assert light["field"] != dark["field"]
    assert light["canvas_2d"] != dark["canvas_2d"]


def test_theme_palette_returns_independent_copy():
    first = theme_palette("dark")
    second = theme_palette("dark")
    first["background"] = "#000000"
    assert second["background"] != "#000000"


def test_density_name_normalization_is_strict_and_deterministic():
    assert normalize_density_name("comfortable") == "comfortable"
    assert normalize_density_name(" COMPACT ") == "compact"
    assert normalize_density_name("") == "comfortable"
    assert normalize_density_name("ultra-dense") == "comfortable"
    assert normalize_density_name(None) == "comfortable"


def test_semantic_state_tokens_remain_distinct_in_each_theme():
    for theme in ("light", "dark"):
        palette = theme_palette(theme)
        assert palette["pass"] != palette["warning"]
        assert palette["warning"] != palette["error"]
        assert palette["pass_surface"] != palette["warning_surface"]
        assert palette["warning_surface"] != palette["error_surface"]
