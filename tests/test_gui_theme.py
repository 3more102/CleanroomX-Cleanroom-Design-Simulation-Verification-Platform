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
        "toolbar",
        "topbar",
        "topbar_text",
        "statusbar",
        "statusbar_text",
        "text",
        "muted",
        "border",
        "border_strong",
        "accent",
        "accent_hover",
        "accent_soft",
        "accent_text",
        "selection",
        "selection_text",
        "field",
        "field_text",
        "tree",
        "disabled",
        "success",
        "success_soft",
        "warning",
        "warning_soft",
        "danger",
        "danger_soft",
        "info",
        "info_soft",
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


def _relative_luminance(hex_color: str) -> float:
    value = hex_color.lstrip("#")
    channels = [int(value[index:index + 2], 16) / 255.0 for index in (0, 2, 4)]

    def linear(channel: float) -> float:
        if channel <= 0.04045:
            return channel / 12.92
        return ((channel + 0.055) / 1.055) ** 2.4

    red, green, blue = (linear(channel) for channel in channels)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast_ratio(first: str, second: str) -> float:
    high, low = sorted(
        (_relative_luminance(first), _relative_luminance(second)),
        reverse=True,
    )
    return (high + 0.05) / (low + 0.05)


def test_primary_chrome_and_text_colors_keep_readable_contrast():
    for name in ("light", "dark"):
        palette = theme_palette(name)
        pairs = (
            ("text", "panel"),
            ("field_text", "field"),
            ("topbar_text", "topbar"),
            ("statusbar_text", "statusbar"),
            ("accent_text", "accent"),
        )
        for foreground, background in pairs:
            assert _contrast_ratio(
                palette[foreground],
                palette[background],
            ) >= 4.5, (name, foreground, background)
