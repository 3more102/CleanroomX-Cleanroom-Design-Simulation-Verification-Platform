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
        "state_info_bg",
        "state_info_fg",
        "state_simulation_bg",
        "state_simulation_fg",
        "state_evidence_bg",
        "state_evidence_fg",
        "state_pass_bg",
        "state_pass_fg",
        "state_warning_bg",
        "state_warning_fg",
        "state_error_bg",
        "state_error_fg",
        "state_stale_bg",
        "state_stale_fg",
        "state_suppressed_bg",
        "state_suppressed_fg",
    }
    assert set(light) == required
    assert set(dark) == required
    assert light["background"] != dark["background"]
    assert light["field"] != dark["field"]
    assert light["canvas_2d"] != dark["canvas_2d"]
    for semantic in ("pass", "warning", "error", "evidence", "simulation"):
        assert light[f"state_{semantic}_bg"] != dark[f"state_{semantic}_bg"]
        assert light[f"state_{semantic}_fg"] != dark[f"state_{semantic}_fg"]


def test_theme_palette_returns_independent_copy():
    first = theme_palette("dark")
    second = theme_palette("dark")
    first["background"] = "#000000"
    assert second["background"] != "#000000"
