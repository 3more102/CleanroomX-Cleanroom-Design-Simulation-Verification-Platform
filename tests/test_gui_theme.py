from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

import pytest

from cleanroomx.gui_theme import configure_ttk_theme, normalize_theme_name, status_style_name, theme_palette


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
        "requirement",
        "info_surface",
        "simulation",
        "simulation_surface",
        "evidence",
        "attention",
        "attention_surface",
        "magenta",
    }
    assert required <= set(light)
    assert required <= set(dark)
    assert light["background"] != dark["background"]
    assert light["field"] != dark["field"]
    assert light["canvas_2d"] != dark["canvas_2d"]


def test_execution_completion_uses_shared_healthy_status_semantics():
    assert status_style_name("completed") == "CX.Status.Pass.TLabel"
    assert status_style_name("success") == "CX.Status.Pass.TLabel"
    assert status_style_name("blocked") == "CX.Status.Fail.TLabel"
    assert status_style_name("stale") == "CX.Status.Attention.TLabel"


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
    assert dark["requirement"] == "#2563EB"



def test_status_style_name_is_canonical_across_engineering_states():
    assert status_style_name("PASS") == "CX.Status.Pass.TLabel"
    assert status_style_name("verified") == "CX.Status.Pass.TLabel"
    assert status_style_name("critical") == "CX.Status.Fail.TLabel"
    assert status_style_name("stale") == "CX.Status.Attention.TLabel"
    assert status_style_name("running") == "CX.Status.Running.TLabel"
    assert status_style_name("simulation") == "CX.Status.Simulation.TLabel"
    assert status_style_name("unverified") == "CX.Status.Unverified.TLabel"
    assert status_style_name("available") == "CX.Status.Info.TLabel"
    assert status_style_name("not checked") == "CX.Status.Neutral.TLabel"


def test_surface_aware_label_styles_match_parent_surfaces():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    try:
        palette = configure_ttk_theme(root, "dark")
        style = ttk.Style(root)

        assert style.lookup("CX.PanelTitle.TLabel", "background") == palette["panel"]
        assert style.lookup("CX.PanelMuted.TLabel", "background") == palette["panel"]
        assert (
            style.lookup("CX.SurfaceSection.TLabel", "background")
            == palette["surface_alt"]
        )
        assert (
            style.lookup("CX.SurfaceMuted.TLabel", "background")
            == palette["surface_alt"]
        )
        assert (
            style.lookup("CX.Status.Running.TLabel", "foreground")
            == palette["accent"]
        )
        assert (
            style.lookup("CX.Status.Attention.TLabel", "foreground")
            == palette["attention"]
        )
        assert (
            style.lookup("CX.Instrument.TFrame", "background")
            == palette["panel"]
        )
        assert (
            style.lookup("CX.InstrumentValue.TLabel", "foreground")
            == palette["text"]
        )
        assert (
            style.lookup("CX.Success.Horizontal.TProgressbar", "background")
            == palette["success"]
        )
        assert (
            style.lookup("CX.Warning.Horizontal.TProgressbar", "background")
            == palette["warning"]
        )
        assert (
            style.lookup("CX.Fail.Horizontal.TProgressbar", "background")
            == palette["error"]
        )
        assert (
            style.lookup("CX.Simulation.Horizontal.TProgressbar", "background")
            == palette["simulation"]
        )
    finally:
        root.destroy()
