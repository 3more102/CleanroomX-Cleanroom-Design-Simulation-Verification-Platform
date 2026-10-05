from __future__ import annotations

from copy import deepcopy
from typing import Any

import tkinter as tk
from tkinter import ttk


_DENSITY_PROFILES: dict[str, dict[str, int | tuple[int, int]]] = {
    "comfortable": {
        "button_padding": (8, 5),
        "entry_padding": (5, 4),
        "combo_padding": (4, 3),
        "tab_padding": (10, 6),
        "tree_rowheight": 25,
        "heading_padding": (5, 5),
        "menubutton_padding": (7, 4),
        "appbar_padding": (8, 5),
        "panel_header_padding": (7, 5),
        "toolbar_padding": (4, 3),
        "primary_padding": (12, 6),
        "danger_padding": (8, 5),
        "compact_padding": (6, 3),
    },
    "compact": {
        "button_padding": (6, 3),
        "entry_padding": (4, 2),
        "combo_padding": (3, 2),
        "tab_padding": (8, 3),
        "tree_rowheight": 21,
        "heading_padding": (4, 3),
        "menubutton_padding": (5, 2),
        "appbar_padding": (6, 3),
        "panel_header_padding": (5, 3),
        "toolbar_padding": (3, 2),
        "primary_padding": (9, 4),
        "danger_padding": (6, 3),
        "compact_padding": (5, 2),
    },
}


_THEME_PALETTES: dict[str, dict[str, str]] = {
    "light": {
        "background": "#E8EEF5",
        "surface": "#F4F7FA",
        "surface_alt": "#E9EFF5",
        "panel": "#FFFFFF",
        "elevated": "#F8FAFC",
        "text": "#142033",
        "secondary_text": "#334155",
        "muted": "#64748B",
        "border": "#C6D2E1",
        "strong_border": "#94A3B8",
        "accent": "#0E7490",
        "accent_hover": "#155E75",
        "accent_text": "#FFFFFF",
        "blue": "#2563EB",
        "success": "#15803D",
        "lime": "#4D7C0F",
        "warning": "#B45309",
        "attention": "#C2410C",
        "error": "#B91C1C",
        "info": "#0369A1",
        "simulation": "#7C3AED",
        "magenta": "#A21CAF",
        "selection": "#CFFAFE",
        "selection_text": "#083344",
        "field": "#FFFFFF",
        "field_text": "#142033",
        "tree": "#FBFDFF",
        "disabled": "#94A3B8",
        "canvas_2d": "#F8FAFC",
        "canvas_3d": "#101827",
        "plot": "#FFFFFF",
        "grid": "#CBD5E1",
    },
    "dark": {
        "background": "#0B1220",
        "surface": "#111B2E",
        "surface_alt": "#142034",
        "panel": "#17243A",
        "elevated": "#1D2C45",
        "text": "#F1F5F9",
        "secondary_text": "#CBD5E1",
        "muted": "#94A3B8",
        "border": "#263750",
        "strong_border": "#334A68",
        "accent": "#22D3EE",
        "accent_hover": "#38BDF8",
        "accent_text": "#07111F",
        "blue": "#2563EB",
        "success": "#22C55E",
        "lime": "#84CC16",
        "warning": "#F59E0B",
        "attention": "#F97316",
        "error": "#EF4444",
        "info": "#38BDF8",
        "simulation": "#A78BFA",
        "magenta": "#E879F9",
        "selection": "#164E63",
        "selection_text": "#ECFEFF",
        "field": "#0F192A",
        "field_text": "#F1F5F9",
        "tree": "#0F192A",
        "disabled": "#64748B",
        "canvas_2d": "#0E1726",
        "canvas_3d": "#09101C",
        "plot": "#0E1726",
        "grid": "#263750",
    },
}


def normalize_theme_name(value: Any) -> str:
    name = str(value or "").strip().lower()
    return name if name in _THEME_PALETTES else "light"


def theme_palette(value: Any) -> dict[str, str]:
    return deepcopy(_THEME_PALETTES[normalize_theme_name(value)])


def normalize_density_name(value: Any) -> str:
    name = str(value or "").strip().lower()
    return name if name in _DENSITY_PROFILES else "comfortable"


def density_profile(value: Any) -> dict[str, int | tuple[int, int]]:
    return deepcopy(_DENSITY_PROFILES[normalize_density_name(value)])


def _configure_badge(
    style: ttk.Style,
    name: str,
    *,
    foreground: str,
    background: str,
) -> None:
    style.configure(
        name,
        foreground=foreground,
        background=background,
        padding=(7, 2),
        font=("TkDefaultFont", 8, "bold"),
        anchor="center",
    )


def configure_ttk_theme(
    root: tk.Misc,
    value: Any,
    *,
    density: Any = "comfortable",
) -> dict[str, str]:
    """Apply the centralized CleanroomX engineering workstation design system."""
    theme_name = normalize_theme_name(value)
    density_name = normalize_density_name(density)
    metrics = density_profile(density_name)
    palette = theme_palette(theme_name)
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    root.configure(background=palette["background"])

    style.configure(
        ".",
        background=palette["background"],
        foreground=palette["text"],
    )
    style.configure("TFrame", background=palette["background"])
    style.configure(
        "TLabel",
        background=palette["background"],
        foreground=palette["text"],
    )
    style.configure(
        "TLabelframe",
        background=palette["background"],
        foreground=palette["text"],
        bordercolor=palette["border"],
        lightcolor=palette["border"],
        darkcolor=palette["border"],
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
        padding=metrics["button_padding"],
    )
    style.map(
        "TButton",
        background=[
            ("active", palette["elevated"]),
            ("pressed", palette["selection"]),
            ("disabled", palette["surface_alt"]),
        ],
        foreground=[
            ("disabled", palette["disabled"]),
            ("!disabled", palette["text"]),
        ],
    )

    for widget_style in ("TCheckbutton", "TRadiobutton"):
        style.configure(
            widget_style,
            background=palette["background"],
            foreground=palette["text"],
        )
        style.map(
            widget_style,
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
        padding=metrics["entry_padding"],
    )
    style.map(
        "TEntry",
        fieldbackground=[
            ("disabled", palette["surface_alt"]),
            ("readonly", palette["surface_alt"]),
        ],
        foreground=[("disabled", palette["disabled"])],
    )
    style.configure(
        "TCombobox",
        fieldbackground=palette["field"],
        background=palette["surface_alt"],
        foreground=palette["field_text"],
        arrowcolor=palette["text"],
        bordercolor=palette["border"],
        lightcolor=palette["border"],
        darkcolor=palette["border"],
        padding=metrics["combo_padding"],
    )
    style.map(
        "TCombobox",
        fieldbackground=[
            ("readonly", palette["field"]),
            ("disabled", palette["surface_alt"]),
        ],
        foreground=[("disabled", palette["disabled"])],
        selectbackground=[("readonly", palette["selection"])],
        selectforeground=[("readonly", palette["selection_text"])],
    )
    style.configure(
        "TSpinbox",
        fieldbackground=palette["field"],
        foreground=palette["field_text"],
        arrowcolor=palette["text"],
        bordercolor=palette["border"],
        lightcolor=palette["border"],
        darkcolor=palette["border"],
    )

    style.configure(
        "TNotebook",
        background=palette["background"],
        bordercolor=palette["border"],
        tabmargins=(2, 2, 2, 0),
    )
    style.configure(
        "TNotebook.Tab",
        background=palette["surface_alt"],
        foreground=palette["muted"],
        padding=metrics["tab_padding"],
        bordercolor=palette["border"],
        font=("TkDefaultFont", 9, "bold"),
    )
    style.map(
        "TNotebook.Tab",
        background=[
            ("selected", palette["panel"]),
            ("active", palette["elevated"]),
        ],
        foreground=[
            ("selected", palette["accent"]),
            ("active", palette["text"]),
        ],
    )

    style.configure(
        "Treeview",
        background=palette["tree"],
        fieldbackground=palette["tree"],
        foreground=palette["text"],
        bordercolor=palette["border"],
        rowheight=metrics["tree_rowheight"],
    )
    style.map(
        "Treeview",
        background=[("selected", palette["selection"])],
        foreground=[("selected", palette["selection_text"])],
    )
    style.configure(
        "Treeview.Heading",
        background=palette["surface_alt"],
        foreground=palette["secondary_text"],
        bordercolor=palette["border"],
        font=("TkDefaultFont", 9, "bold"),
        padding=metrics["heading_padding"],
    )
    style.map(
        "Treeview.Heading",
        background=[("active", palette["elevated"])],
        foreground=[("active", palette["text"])],
    )

    style.configure("TPanedwindow", background=palette["strong_border"])
    style.configure("TSeparator", background=palette["border"])
    style.configure(
        "TMenubutton",
        background=palette["surface_alt"],
        foreground=palette["text"],
        bordercolor=palette["border"],
        arrowcolor=palette["text"],
        padding=metrics["menubutton_padding"],
    )
    style.map(
        "TMenubutton",
        background=[("active", palette["elevated"])],
        foreground=[("disabled", palette["disabled"])],
    )
    style.configure(
        "Horizontal.TProgressbar",
        troughcolor=palette["surface_alt"],
        background=palette["accent"],
        bordercolor=palette["border"],
        lightcolor=palette["accent"],
        darkcolor=palette["accent"],
        thickness=9,
    )

    # Brand and application chrome.
    style.configure(
        "CX.AppBar.TFrame",
        background=palette["surface"],
        padding=metrics["appbar_padding"],
    )
    style.configure(
        "CX.Brand.TLabel",
        background=palette["surface"],
        foreground=palette["accent"],
        font=("TkDefaultFont", 15, "bold"),
    )
    style.configure(
        "CX.AppBarMeta.TLabel",
        background=palette["surface"],
        foreground=palette["secondary_text"],
        font=("TkDefaultFont", 9),
    )
    style.configure(
        "CX.Section.TLabel",
        background=palette["background"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 9, "bold"),
    )
    style.configure(
        "CX.ViewTitle.TLabel",
        background=palette["background"],
        foreground=palette["text"],
        font=("TkDefaultFont", 10, "bold"),
    )

    # Panels and instrumentation cards.
    style.configure(
        "CX.Card.TFrame",
        background=palette["panel"],
        relief="solid",
        borderwidth=1,
    )
    style.configure(
        "CX.CardHeader.TLabel",
        background=palette["panel"],
        foreground=palette["secondary_text"],
        font=("TkDefaultFont", 8, "bold"),
    )
    style.configure(
        "CX.CardValue.TLabel",
        background=palette["panel"],
        foreground=palette["text"],
        font=("TkDefaultFont", 17, "bold"),
    )
    style.configure(
        "CX.CardHint.TLabel",
        background=palette["panel"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 8),
    )
    style.configure(
        "CX.PanelHeader.TFrame",
        background=palette["surface_alt"],
        padding=metrics["panel_header_padding"],
    )
    style.configure(
        "CX.PanelHeader.TLabel",
        background=palette["surface_alt"],
        foreground=palette["secondary_text"],
        font=("TkDefaultFont", 9, "bold"),
    )
    style.configure(
        "CX.Tooltip.TLabel",
        background=palette["elevated"],
        foreground=palette["text"],
        relief="solid",
        borderwidth=1,
        font=("TkDefaultFont", 8),
    )
    style.configure(
        "CX.Toolbar.TFrame",
        background=palette["surface"],
        padding=metrics["toolbar_padding"],
    )
    style.configure(
        "CX.ToolbarGroup.TLabel",
        background=palette["surface"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 8, "bold"),
    )

    style.configure(
        "CX.Navigator.Treeview",
        background=palette["tree"],
        fieldbackground=palette["tree"],
        foreground=palette["secondary_text"],
        rowheight=metrics["tree_rowheight"],
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
        padding=metrics["primary_padding"],
        font=("TkDefaultFont", 9, "bold"),
    )
    style.map(
        "CX.Primary.TButton",
        background=[
            ("active", palette["accent_hover"]),
            ("pressed", palette["info"]),
            ("disabled", palette["surface_alt"]),
        ],
        foreground=[
            ("disabled", palette["disabled"]),
            ("!disabled", palette["accent_text"]),
        ],
    )
    style.configure(
        "CX.Danger.TButton",
        background=palette["error"],
        foreground="#FFFFFF",
        bordercolor=palette["error"],
        padding=metrics["danger_padding"],
    )
    style.map(
        "CX.Danger.TButton",
        background=[
            ("active", palette["attention"]),
            ("disabled", palette["surface_alt"]),
        ],
        foreground=[("disabled", palette["disabled"])],
    )
    style.configure(
        "CX.Compact.TButton",
        background=palette["surface_alt"],
        foreground=palette["secondary_text"],
        bordercolor=palette["border"],
        padding=metrics["compact_padding"],
    )
    style.map(
        "CX.Compact.TButton",
        background=[
            ("active", palette["elevated"]),
            ("pressed", palette["selection"]),
            ("disabled", palette["surface_alt"]),
        ],
        foreground=[
            ("active", palette["text"]),
            ("disabled", palette["disabled"]),
        ],
    )

    # Compact engineering status language reused across the application.
    _configure_badge(
        style,
        "CX.Status.Pass.TLabel",
        foreground="#052E16" if theme_name == "dark" else "#FFFFFF",
        background=palette["success"],
    )
    _configure_badge(
        style,
        "CX.Status.Fail.TLabel",
        foreground="#FFFFFF",
        background=palette["error"],
    )
    _configure_badge(
        style,
        "CX.Status.Warning.TLabel",
        foreground="#1C1202",
        background=palette["warning"],
    )
    _configure_badge(
        style,
        "CX.Status.Running.TLabel",
        foreground=palette["accent_text"],
        background=palette["accent"],
    )
    _configure_badge(
        style,
        "CX.Status.Info.TLabel",
        foreground="#061B2A",
        background=palette["info"],
    )
    _configure_badge(
        style,
        "CX.Status.Stale.TLabel",
        foreground="#FFFFFF",
        background=palette["attention"],
    )
    _configure_badge(
        style,
        "CX.Status.Unknown.TLabel",
        foreground=palette["secondary_text"],
        background=palette["surface_alt"],
    )
    _configure_badge(
        style,
        "CX.Status.Verified.TLabel",
        foreground="#052E16" if theme_name == "dark" else "#FFFFFF",
        background=palette["success"],
    )

    # Defaults for Tk-native widgets created after this call.
    root.option_add("*Text.background", palette["field"])
    root.option_add("*Text.foreground", palette["field_text"])
    root.option_add("*Text.insertBackground", palette["text"])
    root.option_add("*Text.selectBackground", palette["selection"])
    root.option_add("*Text.selectForeground", palette["selection_text"])
    root.option_add("*Menu.background", palette["surface"])
    root.option_add("*Menu.foreground", palette["text"])
    root.option_add("*Menu.activeBackground", palette["selection"])
    root.option_add("*Menu.activeForeground", palette["selection_text"])
    root.option_add("*Menu.disabledForeground", palette["disabled"])

    return palette
