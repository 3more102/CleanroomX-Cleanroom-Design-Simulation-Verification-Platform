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
        "surface_raised",
        "panel",
        "text",
        "muted",
        "border",
        "accent",
        "accent_secondary",
        "accent_hover",
        "accent_text",
        "success",
        "warning",
        "danger",
        "info",
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
    }
    assert set(light) == required
    assert set(dark) == required
    assert light["background"] != dark["background"]
    assert light["field"] != dark["field"]
    assert light["canvas_2d"] != dark["canvas_2d"]


def test_semantic_engineering_colors_are_distinct():
    for theme in ("light", "dark"):
        palette = theme_palette(theme)
        semantic = {
            palette["success"],
            palette["warning"],
            palette["danger"],
            palette["info"],
        }
        assert len(semantic) == 4
        assert palette["surface"] != palette["surface_raised"]
        assert palette["accent"] != palette["accent_secondary"]


def test_theme_palette_returns_independent_copy():
    first = theme_palette("dark")
    second = theme_palette("dark")
    first["background"] = "#000000"
    assert second["background"] != "#000000"
