from __future__ import annotations

from copy import deepcopy
from typing import Any

import tkinter as tk
from tkinter import ttk


_THEME_PALETTES: dict[str, dict[str, str]] = {
    "light": {
        "background": "#E8EEF5",
        "surface": "#F5F8FC",
        "surface_alt": "#DCE6F2",
        "panel": "#FFFFFF",
        "text": "#142033",
        "muted": "#5C6B7D",
        "border": "#AFC0D2",
        "accent": "#087EA4",
        "accent_hover": "#075F7D",
        "accent_text": "#FFFFFF",
        "selection": "#C9EDF5",
        "selection_text": "#0A3340",
        "field": "#FFFFFF",
        "field_text": "#142033",
        "tree": "#F8FBFE",
        "disabled": "#8493A5",
        "canvas_2d": "#EEF4F9",
        "canvas_3d": "#142033",
        "plot": "#FFFFFF",
        "grid": "#C7D5E3",
    },
    "dark": {
        "background": "#0B1220",
        "surface": "#111B2E",
        "surface_alt": "#17243A",
        "panel": "#132033",
        "text": "#F1F5F9",
        "muted": "#94A3B8",
        "border": "#263750",
        "accent": "#22D3EE",
        "accent_hover": "#38BDF8",
        "accent_text": "#07111E",
        "selection": "#164E63",
        "selection_text": "#ECFEFF",
        "field": "#0E1828",
        "field_text": "#F1F5F9",
        "tree": "#0F1A2A",
        "disabled": "#64748B",
        "canvas_2d": "#0F1A2A",
        "canvas_3d": "#070D16",
        "plot": "#0D1726",
        "grid": "#2B425F",
    },
}


def normalize_theme_name(value: Any) -> str:
    name = str(value or "").strip().lower()
    return name if name in _THEME_PALETTES else "light"


def theme_palette(value: Any) -> dict[str, str]:
    return deepcopy(_THEME_PALETTES[normalize_theme_name(value)])


def configure_ttk_theme(root: tk.Misc, value: Any) -> dict[str, str]:
    """Apply the CleanroomX presentation palette to ttk without model side effects."""
    palette = theme_palette(value)
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
        padding=(9, 5),
        borderwidth=1,
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
        padding=(12, 7),
        bordercolor=palette["border"],
    )
    style.map(
        "TNotebook.Tab",
        background=[
            ("selected", palette["panel"]),
            ("active", palette["surface"]),
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
        rowheight=26,
        font=("TkDefaultFont", 9),
    )
    style.map(
        "Treeview",
        background=[("selected", palette["selection"])],
        foreground=[("selected", palette["selection_text"])],
    )
    style.configure(
        "Treeview.Heading",
        background=palette["surface"],
        foreground=palette["accent"],
        bordercolor=palette["border"],
        font=("TkDefaultFont", 9, "bold"),
        padding=(6, 5),
    )
    style.map(
        "Treeview.Heading",
        background=[("active", palette["surface_alt"])],
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
        "TScrollbar",
        background=palette["surface_alt"],
        troughcolor=palette["background"],
        bordercolor=palette["border"],
        arrowcolor=palette["muted"],
        lightcolor=palette["surface_alt"],
        darkcolor=palette["surface_alt"],
    )
    style.map(
        "TScrollbar",
        background=[
            ("active", palette["accent"]),
            ("pressed", palette["accent_hover"]),
        ],
        arrowcolor=[
            ("active", palette["accent_text"]),
            ("pressed", palette["accent_text"]),
        ],
    )
    style.configure(
        "TProgressbar",
        background=palette["accent"],
        troughcolor=palette["surface_alt"],
        bordercolor=palette["border"],
        lightcolor=palette["accent"],
        darkcolor=palette["accent"],
    )
    style.configure(
        "CX.Status.TLabel",
        background=palette["surface"],
        foreground=palette["muted"],
        padding=(7, 3),
    )
    style.configure(
        "CX.StatusAccent.TLabel",
        background=palette["surface"],
        foreground=palette["accent"],
        padding=(7, 3),
        font=("TkDefaultFont", 9, "bold"),
    )
    style.configure(
        "CX.Toolbar.TLabel",
        background=palette["surface"],
        foreground=palette["text"],
    )
    style.configure(
        "CX.ToolbarSection.TLabel",
        background=palette["surface"],
        foreground=palette["accent"],
        font=("TkDefaultFont", 9, "bold"),
    )
    style.configure(
        "CX.Accent.TLabel",
        background=palette["background"],
        foreground=palette["accent"],
        font=("TkDefaultFont", 9, "bold"),
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
        foreground=palette["accent"],
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
        rowheight=24,
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
        padding=(6, 4),
        relief="solid",
        borderwidth=1,
    )
    style.configure(
        "CX.PanelHeader.TFrame",
        background=palette["surface_alt"],
        padding=(8, 5),
        relief="solid",
        borderwidth=1,
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
        padding=(6, 3),
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
