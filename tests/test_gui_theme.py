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
        "surface_high",
        "border_strong",
        "secondary",
        "success",
        "warning",
        "danger",
        "info",
        "simulation",
        "evidence",
        "attention",
        "magenta",
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


def test_dark_palette_matches_industrial_engineering_semantics():
    dark = theme_palette("dark")

    assert dark["background"] == "#0B1220"
    assert dark["surface"] == "#111B2E"
    assert dark["surface_alt"] == "#17243A"
    assert dark["surface_high"] == "#1D2C45"
    assert dark["border"] == "#263750"
    assert dark["border_strong"] == "#334A68"
    assert dark["accent"] == "#22D3EE"
    assert dark["secondary"] == "#38BDF8"
    assert dark["success"] == "#22C55E"
    assert dark["warning"] == "#F59E0B"
    assert dark["danger"] == "#EF4444"
    assert dark["simulation"] == "#A78BFA"
    assert dark["background"].lower() != "#000000"
