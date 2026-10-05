from __future__ import annotations

from cleanroomx.gui_theme import (
    density_profile,
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
        "elevated",
        "text",
        "secondary_text",
        "muted",
        "border",
        "strong_border",
        "accent",
        "accent_hover",
        "accent_text",
        "blue",
        "success",
        "lime",
        "warning",
        "attention",
        "error",
        "info",
        "simulation",
        "magenta",
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


def test_dark_palette_matches_industrial_workstation_foundation():
    dark = theme_palette("dark")

    assert dark["background"] == "#0B1220"
    assert dark["surface"] == "#111B2E"
    assert dark["panel"] == "#17243A"
    assert dark["accent"] == "#22D3EE"
    assert dark["success"] == "#22C55E"
    assert dark["warning"] == "#F59E0B"
    assert dark["error"] == "#EF4444"
    assert dark["simulation"] == "#A78BFA"


def test_density_profiles_are_strict_independent_and_more_compact():
    assert normalize_density_name("compact") == "compact"
    assert normalize_density_name(" COMFORTABLE ") == "comfortable"
    assert normalize_density_name("tiny") == "comfortable"

    comfortable = density_profile("comfortable")
    compact = density_profile("compact")
    assert compact["tree_rowheight"] < comfortable["tree_rowheight"]
    assert compact["tab_padding"][1] < comfortable["tab_padding"][1]
    assert compact["compact_padding"][1] < comfortable["compact_padding"][1]

    compact["tree_rowheight"] = 99
    assert density_profile("compact")["tree_rowheight"] != 99
