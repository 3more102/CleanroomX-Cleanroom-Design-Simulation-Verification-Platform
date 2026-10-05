from __future__ import annotations

from copy import deepcopy
from typing import Any

import tkinter as tk
from tkinter import ttk


# CleanroomX presentation tokens.  Keep engineering semantics centralized here so
# individual views do not grow their own incompatible status/domain palettes.
_THEME_PALETTES: dict[str, dict[str, str]] = {
    "light": {
        "background": "#E9EEF5",
        "surface": "#F7F9FC",
        "surface_alt": "#EDF2F7",
        "panel": "#FFFFFF",
        "raised": "#F8FAFC",
        "hover": "#E7EEF7",
        "text": "#172033",
        "secondary_text": "#334155",
        "muted": "#64748B",
        "disabled": "#94A3B8",
        "border": "#CBD5E1",
        "strong_border": "#94A3B8",
        "accent": "#0284C7",
        "accent_hover": "#0369A1",
        "accent_text": "#FFFFFF",
        "selection": "#D7F1F8",
        "selection_text": "#0C4A6E",
        "field": "#FFFFFF",
        "field_text": "#172033",
        "tree": "#FBFDFF",
        "canvas_2d": "#F4F7FA",
        "canvas_3d": "#111827",
        "plot": "#FFFFFF",
        "grid": "#D7E0EA",
        "success": "#16A34A",
        "success_bg": "#DCFCE7",
        "warning": "#D97706",
        "warning_bg": "#FEF3C7",
        "error": "#DC2626",
        "error_bg": "#FEE2E2",
        "running": "#0284C7",
        "running_bg": "#E0F2FE",
        "unknown": "#64748B",
        "unknown_bg": "#E2E8F0",
        "stale": "#EA580C",
        "stale_bg": "#FFEDD5",
        "verified": "#059669",
        "verified_bg": "#D1FAE5",
        "simulation": "#7C3AED",
        "simulation_bg": "#EDE9FE",
        "evidence": "#16A34A",
        "evidence_bg": "#DCFCE7",
        "geometry": "#0891B2",
        "hvac": "#2563EB",
        "airflow": "#0891B2",
        "pressure": "#7C3AED",
        "electrical": "#CA8A04",
        "utilities": "#EA580C",
        "safety": "#DC2626",
        "verification": "#059669",
        "magenta": "#C026D3",
    },
    "dark": {
        # Requested industrial workstation foundation.
        "background": "#0B1220",
        "surface": "#111B2E",
        "surface_alt": "#142034",
        "panel": "#17243A",
        "raised": "#17243A",
        "hover": "#1D2C45",
        "text": "#F1F5F9",
        "secondary_text": "#CBD5E1",
        "muted": "#94A3B8",
        "disabled": "#64748B",
        "border": "#263750",
        "strong_border": "#334A68",
        "accent": "#22D3EE",
        "accent_hover": "#38BDF8",
        "accent_text": "#082F49",
        "selection": "#164E63",
        "selection_text": "#ECFEFF",
        "field": "#0F1929",
        "field_text": "#F1F5F9",
        "tree": "#0F1929",
        "canvas_2d": "#0B1423",
        "canvas_3d": "#080D17",
        "plot": "#0D1727",
        "grid": "#263750",
        "success": "#22C55E",
        "success_bg": "#123221",
        "warning": "#F59E0B",
        "warning_bg": "#38270C",
        "error": "#EF4444",
        "error_bg": "#3A171C",
        "running": "#38BDF8",
        "running_bg": "#102D43",
        "unknown": "#94A3B8",
        "unknown_bg": "#1E293B",
        "stale": "#F97316",
        "stale_bg": "#3A2415",
        "verified": "#22C55E",
        "verified_bg": "#123221",
        "simulation": "#A78BFA",
        "simulation_bg": "#291F46",
        "evidence": "#22C55E",
        "evidence_bg": "#123221",
        "geometry": "#22D3EE",
        "hvac": "#38BDF8",
        "airflow": "#2DD4BF",
        "pressure": "#A78BFA",
        "electrical": "#FACC15",
        "utilities": "#F97316",
        "safety": "#EF4444",
        "verification": "#34D399",
        "magenta": "#E879F9",
    },
}

_STATUS_KEYS = {
    "pass": "success",
    "passed": "success",
    "ok": "success",
    "healthy": "success",
    "valid": "success",
    "verified": "verified",
    "fail": "error",
    "failed": "error",
    "error": "error",
    "critical": "error",
    "warning": "warning",
    "warn": "warning",
    "attention": "warning",
    "running": "running",
    "active": "running",
    "working": "running",
    "unknown": "unknown",
    "not checked": "unknown",
    "unchecked": "unknown",
    "unverified": "unknown",
    "stale": "stale",
    "incomplete": "stale",
}

_DOMAIN_KEYS = {
    "geometry": "geometry",
    "layout": "geometry",
    "bim": "geometry",
    "ifc": "geometry",
    "hvac": "hvac",
    "airflow": "airflow",
    "ach": "airflow",
    "pressure": "pressure",
    "electrical": "electrical",
    "utilities": "utilities",
    "utility": "utilities",
    "safety": "safety",
    "evidence": "evidence",
    "proofgraph": "simulation",
    "verification": "verification",
    "verify": "verification",
    "simulation": "simulation",
    "solver": "simulation",
}


def normalize_theme_name(value: Any) -> str:
    name = str(value or "").strip().lower()
    return name if name in _THEME_PALETTES else "light"


def theme_palette(value: Any) -> dict[str, str]:
    return deepcopy(_THEME_PALETTES[normalize_theme_name(value)])


def status_color(value: Any, theme: Any = "dark") -> str:
    """Return the semantic foreground color for an engineering status."""
    palette = theme_palette(theme)
    key = _STATUS_KEYS.get(str(value or "").strip().casefold(), "unknown")
    return palette[key]


def status_background(value: Any, theme: Any = "dark") -> str:
    """Return the restrained background color for an engineering status."""
    palette = theme_palette(theme)
    key = _STATUS_KEYS.get(str(value or "").strip().casefold(), "unknown")
    return palette[f"{key}_bg"] if f"{key}_bg" in palette else palette["unknown_bg"]


def domain_color(value: Any, theme: Any = "dark") -> str:
    """Return the semantic accent for an engineering domain."""
    palette = theme_palette(theme)
    key = _DOMAIN_KEYS.get(str(value or "").strip().casefold(), "accent")
    return palette[key]


def _configure_status_styles(style: ttk.Style, palette: dict[str, str]) -> None:
    for semantic, foreground, background in (
        ("Pass", palette["success"], palette["success_bg"]),
        ("Fail", palette["error"], palette["error_bg"]),
        ("Warning", palette["warning"], palette["warning_bg"]),
        ("Running", palette["running"], palette["running_bg"]),
        ("Unknown", palette["unknown"], palette["unknown_bg"]),
        ("Stale", palette["stale"], palette["stale_bg"]),
        ("Verified", palette["verified"], palette["verified_bg"]),
        ("Simulation", palette["simulation"], palette["simulation_bg"]),
        ("Evidence", palette["evidence"], palette["evidence_bg"]),
    ):
        style.configure(
            f"CX.Status.{semantic}.TLabel",
            background=background,
            foreground=foreground,
            padding=(6, 2),
            font=("TkDefaultFont", 8, "bold"),
        )


def configure_ttk_theme(root: tk.Misc, value: Any) -> dict[str, str]:
    """Apply the centralized CleanroomX engineering workstation design system."""
    palette = theme_palette(value)
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    root.configure(background=palette["background"])

    style.configure(
        ".",
        background=palette["background"],
        foreground=palette["text"],
        font=("TkDefaultFont", 9),
    )
    style.configure("TFrame", background=palette["background"])
    style.configure(
        "CX.Surface.TFrame",
        background=palette["surface"],
    )
    style.configure(
        "CX.Panel.TFrame",
        background=palette["panel"],
        bordercolor=palette["border"],
        relief="solid",
        borderwidth=1,
    )
    style.configure(
        "CX.Raised.TFrame",
        background=palette["raised"],
        bordercolor=palette["border"],
        relief="solid",
        borderwidth=1,
    )
    style.configure(
        "TLabel",
        background=palette["background"],
        foreground=palette["text"],
    )
    style.configure(
        "CX.Secondary.TLabel",
        background=palette["background"],
        foreground=palette["secondary_text"],
    )
    style.configure(
        "CX.Muted.TLabel",
        background=palette["background"],
        foreground=palette["muted"],
    )
    style.configure(
        "TLabelframe",
        background=palette["background"],
        foreground=palette["text"],
        bordercolor=palette["border"],
        lightcolor=palette["border"],
        darkcolor=palette["border"],
        relief="solid",
        borderwidth=1,
    )
    style.configure(
        "TLabelframe.Label",
        background=palette["background"],
        foreground=palette["secondary_text"],
        font=("TkDefaultFont", 9, "bold"),
    )
    style.configure(
        "TButton",
        background=palette["surface_alt"],
        foreground=palette["text"],
        bordercolor=palette["border"],
        lightcolor=palette["border"],
        darkcolor=palette["border"],
        padding=(8, 5),
        relief="flat",
    )
    style.map(
        "TButton",
        background=[
            ("active", palette["hover"]),
            ("pressed", palette["selection"]),
            ("disabled", palette["surface_alt"]),
        ],
        foreground=[
            ("disabled", palette["disabled"]),
            ("!disabled", palette["text"]),
        ],
        bordercolor=[
            ("focus", palette["accent"]),
            ("active", palette["strong_border"]),
        ],
    )
    for widget in ("TCheckbutton", "TRadiobutton"):
        style.configure(widget, background=palette["background"], foreground=palette["text"])
        style.map(
            widget,
            background=[("active", palette["background"])],
            foreground=[("disabled", palette["disabled"])],
        )
    style.configure(
        "TEntry",
        fieldbackground=palette["field"],
        foreground=palette["field_text"],
        bordercolor=palette["border"],
        insertcolor=palette["text"],
        lightcolor=palette["border"],
        darkcolor=palette["border"],
        padding=(5, 4),
    )
    style.map(
        "TEntry",
        fieldbackground=[
            ("focus", palette["field"]),
            ("disabled", palette["surface_alt"]),
            ("readonly", palette["surface_alt"]),
        ],
        bordercolor=[("focus", palette["accent"])],
        foreground=[("disabled", palette["disabled"])],
    )
    style.configure(
        "TCombobox",
        fieldbackground=palette["field"],
        background=palette["surface_alt"],
        foreground=palette["field_text"],
        arrowcolor=palette["secondary_text"],
        bordercolor=palette["border"],
        lightcolor=palette["border"],
        darkcolor=palette["border"],
        padding=(4, 3),
    )
    style.map(
        "TCombobox",
        fieldbackground=[
            ("readonly", palette["field"]),
            ("disabled", palette["surface_alt"]),
        ],
        background=[("active", palette["hover"])],
        foreground=[("disabled", palette["disabled"])],
        selectbackground=[("readonly", palette["selection"])],
        selectforeground=[("readonly", palette["selection_text"])],
        bordercolor=[("focus", palette["accent"])],
    )
    style.configure(
        "TSpinbox",
        fieldbackground=palette["field"],
        foreground=palette["field_text"],
        arrowcolor=palette["secondary_text"],
        bordercolor=palette["border"],
        lightcolor=palette["border"],
        darkcolor=palette["border"],
    )
    style.configure(
        "TNotebook",
        background=palette["background"],
        bordercolor=palette["border"],
        tabmargins=(0, 2, 0, 0),
    )
    style.configure(
        "TNotebook.Tab",
        background=palette["surface_alt"],
        foreground=palette["muted"],
        padding=(11, 6),
        bordercolor=palette["border"],
        font=("TkDefaultFont", 9, "bold"),
    )
    style.map(
        "TNotebook.Tab",
        background=[
            ("selected", palette["panel"]),
            ("active", palette["hover"]),
        ],
        foreground=[
            ("selected", palette["accent"]),
            ("active", palette["text"]),
        ],
        bordercolor=[("selected", palette["accent"])],
    )
    style.configure(
        "Treeview",
        background=palette["tree"],
        fieldbackground=palette["tree"],
        foreground=palette["secondary_text"],
        bordercolor=palette["border"],
        rowheight=25,
        relief="flat",
    )
    style.map(
        "Treeview",
        background=[("selected", palette["selection"])],
        foreground=[("selected", palette["selection_text"])],
    )
    style.configure(
        "Treeview.Heading",
        background=palette["surface_alt"],
        foreground=palette["text"],
        bordercolor=palette["border"],
        relief="flat",
        padding=(5, 4),
        font=("TkDefaultFont", 9, "bold"),
    )
    style.map(
        "Treeview.Heading",
        background=[("active", palette["hover"])],
        foreground=[("active", palette["accent"])],
    )
    style.configure("TPanedwindow", background=palette["strong_border"])
    style.configure("TSeparator", background=palette["border"])
    style.configure(
        "TMenubutton",
        background=palette["surface_alt"],
        foreground=palette["text"],
        bordercolor=palette["border"],
        arrowcolor=palette["secondary_text"],
        padding=(7, 4),
    )
    style.map(
        "TMenubutton",
        background=[("active", palette["hover"])],
        foreground=[("disabled", palette["disabled"])],
    )
    style.configure(
        "TProgressbar",
        troughcolor=palette["surface_alt"],
        background=palette["accent"],
        bordercolor=palette["border"],
        lightcolor=palette["accent"],
        darkcolor=palette["accent"],
    )

    # CleanroomX shell and hierarchy.
    style.configure(
        "CX.Brand.TLabel",
        background=palette["background"],
        foreground=palette["accent"],
        font=("TkDefaultFont", 15, "bold"),
    )
    style.configure(
        "CX.ProductSubtle.TLabel",
        background=palette["background"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 8),
    )
    style.configure(
        "CX.Section.TLabel",
        background=palette["background"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 8, "bold"),
    )
    style.configure(
        "CX.ViewTitle.TLabel",
        background=palette["background"],
        foreground=palette["text"],
        font=("TkDefaultFont", 11, "bold"),
    )
    style.configure(
        "CX.Metric.TLabel",
        background=palette["background"],
        foreground=palette["text"],
        font=("TkDefaultFont", 15, "bold"),
    )
    style.configure(
        "CX.Navigator.Treeview",
        background=palette["tree"],
        fieldbackground=palette["tree"],
        foreground=palette["secondary_text"],
        rowheight=26,
        bordercolor=palette["border"],
    )
    style.map(
        "CX.Navigator.Treeview",
        background=[("selected", palette["selection"])],
        foreground=[("selected", palette["selection_text"])],
    )
    style.configure(
        "CX.Primary.TButton",
        background=palette["accent"],
        foreground=palette["accent_text"],
        bordercolor=palette["accent"],
        padding=(12, 6),
        font=("TkDefaultFont", 9, "bold"),
    )
    style.map(
        "CX.Primary.TButton",
        background=[
            ("active", palette["accent_hover"]),
            ("pressed", palette["accent_hover"]),
            ("disabled", palette["surface_alt"]),
        ],
        foreground=[
            ("disabled", palette["disabled"]),
            ("!disabled", palette["accent_text"]),
        ],
    )
    style.configure(
        "CX.Danger.TButton",
        background=palette["error_bg"],
        foreground=palette["error"],
        bordercolor=palette["error"],
        padding=(8, 4),
    )
    style.map(
        "CX.Danger.TButton",
        background=[("active", palette["hover"])],
    )
    style.configure(
        "CX.Toolbar.TFrame",
        background=palette["surface"],
        bordercolor=palette["border"],
        relief="solid",
        borderwidth=1,
        padding=(4, 3),
    )
    style.configure(
        "CX.Toolbar.TLabel",
        background=palette["surface"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 8, "bold"),
    )
    style.configure(
        "CX.PanelHeader.TFrame",
        background=palette["surface_alt"],
        bordercolor=palette["border"],
        relief="solid",
        borderwidth=1,
        padding=(7, 4),
    )
    style.configure(
        "CX.PanelHeader.TLabel",
        background=palette["surface_alt"],
        foreground=palette["text"],
        font=("TkDefaultFont", 9, "bold"),
    )
    style.configure(
        "CX.Compact.TButton",
        background=palette["surface_alt"],
        foreground=palette["secondary_text"],
        bordercolor=palette["border"],
        padding=(6, 3),
    )
    style.map(
        "CX.Compact.TButton",
        background=[
            ("active", palette["hover"]),
            ("pressed", palette["selection"]),
            ("disabled", palette["surface_alt"]),
        ],
        foreground=[
            ("active", palette["text"]),
            ("disabled", palette["disabled"]),
        ],
        bordercolor=[("focus", palette["accent"])],
    )
    style.configure(
        "CX.StatusBar.TFrame",
        background=palette["surface"],
        bordercolor=palette["border"],
        relief="solid",
        borderwidth=1,
        padding=(5, 2),
    )
    style.configure(
        "CX.StatusBar.TLabel",
        background=palette["surface"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 8),
    )
    _configure_status_styles(style, palette)

    # Tk-native widgets are not themed by ttk.  These defaults cover widgets
    # created after this call; existing widgets are rethemed by their owning view.
    root.option_add("*Text.background", palette["field"])
    root.option_add("*Text.foreground", palette["field_text"])
    root.option_add("*Text.insertBackground", palette["text"])
    root.option_add("*Text.selectBackground", palette["selection"])
    root.option_add("*Text.selectForeground", palette["selection_text"])
    root.option_add("*Text.highlightBackground", palette["border"])
    root.option_add("*Text.highlightColor", palette["accent"])
    root.option_add("*Menu.background", palette["surface"])
    root.option_add("*Menu.foreground", palette["text"])
    root.option_add("*Menu.activeBackground", palette["selection"])
    root.option_add("*Menu.activeForeground", palette["selection_text"])
    root.option_add("*Menu.disabledForeground", palette["disabled"])
    root.option_add("*Listbox.background", palette["field"])
    root.option_add("*Listbox.foreground", palette["field_text"])
    root.option_add("*Listbox.selectBackground", palette["selection"])
    root.option_add("*Listbox.selectForeground", palette["selection_text"])

    return palette
