from __future__ import annotations

from cleanroomx.gui_theme import normalize_theme_name, status_style_name, theme_palette


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
        "disabled",
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
        "info_surface",
        "simulation",
        "evidence",
        "attention",
        "magenta",
    }
    assert required <= set(light)
    assert required <= set(dark)
    assert light["background"] != dark["background"]
    assert light["field"] != dark["field"]
    assert light["canvas_2d"] != dark["canvas_2d"]


def test_theme_palette_returns_independent_copy():
    first = theme_palette("dark")
    second = theme_palette("dark")
    first["background"] = "#000000"
    assert second["background"] != "#000000"


def test_dark_palette_matches_cleanroomx_industrial_foundation():
    dark = theme_palette("dark")
    assert dark["background"] == "#0B1220"
    assert dark["surface"] == "#111B2E"
    assert dark["panel"] == "#17243A"
    assert dark["accent"] == "#22D3EE"
    assert dark["success"] == "#22C55E"
    assert dark["warning"] == "#F59E0B"
    assert dark["error"] == "#EF4444"
    assert dark["simulation"] == "#A78BFA"



def test_status_style_name_is_canonical_across_engineering_states():
    assert status_style_name("PASS") == "CX.Status.Pass.TLabel"
    assert status_style_name("verified") == "CX.Status.Pass.TLabel"
    assert status_style_name("critical") == "CX.Status.Fail.TLabel"
    assert status_style_name("stale") == "CX.Status.Warning.TLabel"
    assert status_style_name("running") == "CX.Status.Simulation.TLabel"
    assert status_style_name("available") == "CX.Status.Info.TLabel"
    assert status_style_name("not checked") == "CX.Status.Neutral.TLabel"
