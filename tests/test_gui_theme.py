from __future__ import annotations

from cleanroomx.gui_theme import (
    engineering_status_style,
    normalize_theme_name,
    theme_palette,
)


def test_theme_name_normalization_is_strict_and_deterministic():
    assert normalize_theme_name("light") == "light"
    assert normalize_theme_name(" DARK ") == "dark"
    assert normalize_theme_name("") == "dark"
    assert normalize_theme_name("system") == "dark"
    assert normalize_theme_name(None) == "dark"


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
        "muted",
        "border",
        "strong_border",
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
        "warning",
        "error",
        "running",
        "unknown",
        "stale",
        "verified",
        "unverified",
        "geometry",
        "hvac",
        "airflow",
        "pressure",
        "electrical",
        "utilities",
        "safety",
        "evidence",
        "verification",
        "simulation",
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


def test_engineering_status_styles_are_semantic_and_consistent():
    assert engineering_status_style("PASS") == "CX.Badge.Pass.TLabel"
    assert engineering_status_style("failed") == "CX.Badge.Fail.TLabel"
    assert engineering_status_style("warning") == "CX.Badge.Warning.TLabel"
    assert engineering_status_style("running") == "CX.Badge.Running.TLabel"
    assert engineering_status_style("verified") == "CX.Badge.Verified.TLabel"
    assert engineering_status_style("stale") == "CX.Badge.Stale.TLabel"
    assert engineering_status_style("not checked") == "CX.Badge.Unverified.TLabel"
    assert engineering_status_style("something-new") == "CX.Badge.Unknown.TLabel"
