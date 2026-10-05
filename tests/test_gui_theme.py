from __future__ import annotations

from cleanroomx.gui_theme import (
    density_metrics,
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


def test_density_modes_are_strict_and_compact_reduces_workstation_chrome():
    assert normalize_density_name("compact") == "compact"
    assert normalize_density_name(" COMFORTABLE ") == "comfortable"
    assert normalize_density_name("unsupported") == "comfortable"
    assert normalize_density_name(None) == "comfortable"

    comfortable = density_metrics("comfortable")
    compact = density_metrics("compact")
    assert compact["tree_rowheight"] < comfortable["tree_rowheight"]
    assert compact["button_padding"][1] < comfortable["button_padding"][1]
    assert compact["tab_padding"][1] < comfortable["tab_padding"][1]
    assert compact["primary_padding"][1] < comfortable["primary_padding"][1]
