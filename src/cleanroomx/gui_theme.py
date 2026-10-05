from __future__ import annotations

from copy import deepcopy
from typing import Any

import tkinter as tk
from tkinter import ttk


_THEME_PALETTES: dict[str, dict[str, str]] = {
    "light": {
        "background": "#e9edf2",
        "surface": "#f6f8fa",
        "surface_alt": "#eef2f6",
        "panel": "#ffffff",
        "text": "#18212b",
        "muted": "#5f6b78",
        "border": "#c8d1dc",
        "accent": "#0b6aa8",
        "accent_hover": "#095786",
        "accent_text": "#ffffff",
        "selection": "#cfe8ff",
        "selection_text": "#102a43",
        "field": "#ffffff",
        "field_text": "#18212b",
        "tree": "#fbfcfd",
        "disabled": "#9aa5b1",
        "canvas_2d": "#f7f9fb",
        "canvas_3d": "#111820",
        "plot": "#ffffff",
        "grid": "#d7dee7",
        "info": "#0b6aa8",
        "simulation": "#6d28d9",
        "evidence": "#7c3aed",
        "pass": "#15803d",
        "warning": "#b45309",
        "error": "#b91c1c",
        "stale": "#64748b",
        "suppressed": "#78716c",
        "pass_surface": "#dcfce7",
        "warning_surface": "#fef3c7",
        "error_surface": "#fee2e2",
        "stale_surface": "#e2e8f0",
    },
    "dark": {
        "background": "#14191f",
        "surface": "#1b2129",
        "surface_alt": "#232a33",
        "panel": "#1e252d",
        "text": "#e6edf3",
        "muted": "#9aa7b4",
        "border": "#394451",
        "accent": "#2f81f7",
        "accent_hover": "#58a6ff",
        "accent_text": "#ffffff",
        "selection": "#264f78",
        "selection_text": "#ffffff",
        "field": "#11161c",
        "field_text": "#e6edf3",
        "tree": "#171d24",
        "disabled": "#6f7b87",
        "canvas_2d": "#1b222a",
        "canvas_3d": "#0d1117",
        "plot": "#131920",
        "grid": "#33404c",
        "info": "#58a6ff",
        "simulation": "#c4b5fd",
        "evidence": "#d8b4fe",
        "pass": "#6ee7a2",
        "warning": "#fbbf24",
        "error": "#fb7185",
        "stale": "#94a3b8",
        "suppressed": "#a8a29e",
        "pass_surface": "#183b2b",
        "warning_surface": "#4b3b18",
        "error_surface": "#4a2026",
        "stale_surface": "#303844",
    },
}

_DENSITY_PROFILES: dict[str, dict[str, Any]] = {
    "comfortable": {
        "button_padding": (8, 5),
        "primary_button_padding": (12, 6),
        "compact_button_padding": (6, 3),
        "tab_padding": (10, 6),
        "tree_rowheight": 24,
        "toolbar_padding": (4, 3),
        "panel_header_padding": (6, 4),
    },
    "compact": {
        "button_padding": (7, 3),
        "primary_button_padding": (10, 4),
        "compact_button_padding": (5, 2),
        "tab_padding": (8, 4),
        "tree_rowheight": 20,
        "toolbar_padding": (3, 2),
        "panel_header_padding": (5, 3),
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


def configure_ttk_theme(
    root: tk.Misc,
    value: Any,
    density: Any = "comfortable",
) -> dict[str, str]:
    """Apply CleanroomX theme and density tokens without model side effects."""
    palette = theme_palette(value)
    density_profile = _DENSITY_PROFILES[normalize_density_name(density)]
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    root.configure(background=palette["background"])

    style.configure(
        ".",
        background=palette["background"],
        foreground=palette["text"],
    )
    style.configure(
        "TFrame",
        background=palette["background"],
    )
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
        foreground=palette["text"],
        font=("TkDefaultFont", 9, "bold"),
    )
    style.configure(
        "TButton",
        background=palette["surface_alt"],
        foreground=palette["text"],
        bordercolor=palette["border"],
        lightcolor=palette["border"],
        darkcolor=palette["border"],
        padding=density_profile["button_padding"],
    )
    style.map(
        "TButton",
        background=[
            ("active", palette["surface"]),
            ("pressed", palette["selection"]),
            ("disabled", palette["surface_alt"]),
        ],
        foreground=[
            ("disabled", palette["disabled"]),
            ("!disabled", palette["text"]),
        ],
    )
    style.configure(
        "TCheckbutton",
        background=palette["background"],
        foreground=palette["text"],
    )
    style.map(
        "TCheckbutton",
        background=[("active", palette["background"])],
        foreground=[("disabled", palette["disabled"])],
    )
    style.configure(
        "TRadiobutton",
        background=palette["background"],
        foreground=palette["text"],
    )
    style.map(
        "TRadiobutton",
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
        padding=density_profile["tab_padding"],
        bordercolor=palette["border"],
    )
    style.map(
        "TNotebook.Tab",
        background=[
            ("selected", palette["panel"]),
            ("active", palette["surface"]),
        ],
        foreground=[
            ("selected", palette["text"]),
            ("active", palette["text"]),
        ],
    )
    style.configure(
        "Treeview",
        background=palette["tree"],
        fieldbackground=palette["tree"],
        foreground=palette["text"],
        bordercolor=palette["border"],
        rowheight=density_profile["tree_rowheight"],
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
        font=("TkDefaultFont", 9, "bold"),
    )
    style.map(
        "Treeview.Heading",
        background=[("active", palette["surface"])],
    )
    style.configure(
        "TPanedwindow",
        background=palette["border"],
    )
    style.configure(
        "TSeparator",
        background=palette["border"],
    )
    style.configure(
        "TMenubutton",
        background=palette["surface_alt"],
        foreground=palette["text"],
        bordercolor=palette["border"],
        arrowcolor=palette["text"],
        padding=(7, 4),
    )
    style.map(
        "TMenubutton",
        background=[("active", palette["surface"])],
        foreground=[("disabled", palette["disabled"])],
    )

    style.configure(
        "CX.Brand.TLabel",
        background=palette["background"],
        foreground=palette["accent"],
        font=("TkDefaultFont", 15, "bold"),
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
    style.configure(
        "CX.Navigator.Treeview",
        background=palette["tree"],
        fieldbackground=palette["tree"],
        foreground=palette["text"],
        rowheight=density_profile["tree_rowheight"],
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
        padding=density_profile["primary_button_padding"],
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
        "CX.Toolbar.TFrame",
        background=palette["surface"],
        padding=density_profile["toolbar_padding"],
    )
    style.configure(
        "CX.PanelHeader.TFrame",
        background=palette["surface_alt"],
        padding=density_profile["panel_header_padding"],
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
        foreground=palette["text"],
        bordercolor=palette["border"],
        padding=density_profile["compact_button_padding"],
    )
    style.map(
        "CX.Compact.TButton",
        background=[
            ("active", palette["surface"]),
            ("pressed", palette["selection"]),
            ("disabled", palette["surface_alt"]),
        ],
        foreground=[("disabled", palette["disabled"])],
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
