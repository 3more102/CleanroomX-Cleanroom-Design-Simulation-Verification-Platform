from __future__ import annotations

from cleanroomx.gui_theme import (
    normalize_density_name,
    normalize_theme_name,
    status_style_name,
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
        "surface_elevated",
        "panel",
        "navigation",
        "text",
        "secondary_text",
        "muted",
        "border",
        "border_strong",
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
        "success",
        "success_surface",
        "warning",
        "warning_surface",
        "error",
        "error_surface",
        "info",
        "requirement",
        "info_surface",
        "simulation",
        "simulation_surface",
        "evidence",
        "attention",
        "attention_surface",
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


def test_status_style_name_maps_engineering_states_without_data_interpretation():
    assert status_style_name("pass") == "CX.Status.Pass.TLabel"
    assert status_style_name("completed") == "CX.Status.Pass.TLabel"
    assert status_style_name("warning") == "CX.Status.Warning.TLabel"
    assert status_style_name("abandon requested") == "CX.Status.Warning.TLabel"
    assert status_style_name("failed") == "CX.Status.Fail.TLabel"
    assert status_style_name("running") == "CX.Status.Running.TLabel"
    assert status_style_name("unknown") == "CX.Status.Neutral.TLabel"


def test_density_name_normalization_is_strict_and_defaults_to_engineering_compact():
    assert normalize_density_name("compact") == "compact"
    assert normalize_density_name(" COMFORTABLE ") == "comfortable"
    assert normalize_density_name("dense-ish") == "compact"
    assert normalize_density_name(None) == "compact"
