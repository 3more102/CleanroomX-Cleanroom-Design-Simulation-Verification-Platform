from __future__ import annotations

from cleanroomx.gui_theme import normalize_theme_name, theme_palette


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
        "border_strong",
        "info",
        "success",
        "warning",
        "error",
        "purple",
        "orange",
        "magenta",
        "blue_surface",
        "cyan_surface",
        "green_surface",
        "success_surface",
        "warning_surface",
        "error_surface",
        "purple_surface",
        "orange_surface",
        "magenta_surface",
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


def test_dark_palette_matches_industrial_cleanroom_workstation_tokens():
    dark = theme_palette("dark")
    assert dark["background"] == "#0B1220"
    assert dark["surface"] == "#111B2E"
    assert dark["panel"] == "#17243A"
    assert dark["accent"] == "#22D3EE"
    assert dark["success"] == "#22C55E"
    assert dark["warning"] == "#F59E0B"
    assert dark["error"] == "#EF4444"
    assert dark["purple"] == "#A78BFA"
