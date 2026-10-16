from __future__ import annotations

from cleanroomx.gui_theme import normalize_theme_name, theme_palette


def _relative_luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        channel / 12.92
        if channel <= 0.04045
        else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(first: str, second: str) -> float:
    high, low = sorted(
        (_relative_luminance(first), _relative_luminance(second)),
        reverse=True,
    )
    return (high + 0.05) / (low + 0.05)


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
        "design",
        "design_surface",
        "analyze",
        "analyze_surface",
        "verify",
        "verify_surface",
        "evidence",
        "evidence_surface",
        "release",
        "release_surface",
    }
    assert set(light) == required
    assert set(dark) == required
    assert light["background"] != dark["background"]
    assert light["field"] != dark["field"]
    assert light["canvas_2d"] != dark["canvas_2d"]


def test_workflow_colors_distinguish_each_stage_in_both_themes():
    for theme_name in ("light", "dark"):
        palette = theme_palette(theme_name)
        accents = [
            palette[stage]
            for stage in ("design", "analyze", "verify", "evidence", "release")
        ]
        surfaces = [
            palette[f"{stage}_surface"]
            for stage in ("design", "analyze", "verify", "evidence", "release")
        ]
        assert len(set(accents)) == 5
        assert len(set(surfaces)) == 5
        assert all(accent != surface for accent, surface in zip(accents, surfaces))
        assert _contrast_ratio(palette["accent"], palette["accent_text"]) >= 4.5
        assert all(
            _contrast_ratio(palette[stage], palette[f"{stage}_surface"]) >= 4.5
            for stage in ("design", "analyze", "verify", "evidence", "release")
        )


def test_theme_palette_returns_independent_copy():
    first = theme_palette("dark")
    second = theme_palette("dark")
    first["background"] = "#000000"
    assert second["background"] != "#000000"
