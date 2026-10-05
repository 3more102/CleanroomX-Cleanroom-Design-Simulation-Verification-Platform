from __future__ import annotations

from copy import deepcopy
from typing import Any

import tkinter as tk
from tkinter import ttk


_THEME_PALETTES: dict[str, dict[str, str]] = {
    "light": {
        "background": "#e7edf4",
        "surface": "#f5f8fb",
        "surface_alt": "#dce6f0",
        "panel": "#ffffff",
        "text": "#0f172a",
        "muted": "#52647a",
        "border": "#b8c7d9",
        "accent": "#0891b2",
        "accent_hover": "#0e7490",
        "accent_secondary": "#0284c7",
        "accent_text": "#ffffff",
        "selection": "#bae6fd",
        "selection_text": "#082f49",
        "field": "#ffffff",
        "field_text": "#0f172a",
        "tree": "#f8fbfe",
        "disabled": "#8b9aab",
        "canvas_2d": "#edf4f8",
        "canvas_3d": "#111b2e",
        "plot": "#ffffff",
        "grid": "#c7d6e5",
        "success": "#15803d",
        "warning": "#b45309",
        "error": "#dc2626",
        "info": "#0284c7",
    },
    "dark": {
        "background": "#0b1220",
        "surface": "#111b2e",
        "surface_alt": "#17243a",
        "panel": "#111b2e",
        "text": "#f1f5f9",
        "muted": "#94a3b8",
        "border": "#263750",
        "accent": "#22d3ee",
        "accent_hover": "#67e8f9",
        "accent_secondary": "#38bdf8",
        "accent_text": "#07131f",
        "selection": "#164e63",
        "selection_text": "#ecfeff",
        "field": "#0f1a2c",
        "field_text": "#f1f5f9",
        "tree": "#0f1929",
        "disabled": "#64748b",
        "canvas_2d": "#101c2d",
        "canvas_3d": "#0b1220",
        "plot": "#0f1a2c",
        "grid": "#263750",
        "success": "#22c55e",
        "warning": "#f59e0b",
        "error": "#ef4444",
        "info": "#38bdf8",
    },
}


def normalize_theme_name(value: Any) -> str:
    name = str(value or "").strip().lower()
    return name if name in _THEME_PALETTES else "light"


def theme_palette(value: Any) -> dict[str, str]:
    return deepcopy(_THEME_PALETTES[normalize_theme_name(value)])


def configure_ttk_theme(root: tk.Misc, value: Any) -> dict[str, str]:
    """Apply the CleanroomX industrial presentation palette without model effects."""
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
        borderwidth=1,
        padding=(9, 6),
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
        bordercolor=[("focus", palette["accent"])],
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
        padding=(7, 5),
    )
    style.map(
        "TEntry",
        fieldbackground=[
            ("disabled", palette["surface_alt"]),
            ("readonly", palette["surface_alt"]),
        ],
        foreground=[("disabled", palette["disabled"])],
        bordercolor=[("focus", palette["accent"])],
    )
    style.configure(
        "TCombobox",
        fieldbackground=palette["field"],
        background=palette["surface_alt"],
        foreground=palette["field_text"],
        arrowcolor=palette["accent_secondary"],
        bordercolor=palette["border"],
        lightcolor=palette["border"],
        darkcolor=palette["border"],
        padding=(5, 4),
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
        bordercolor=[("focus", palette["accent"])],
    )
    style.configure(
        "TSpinbox",
        fieldbackground=palette["field"],
        foreground=palette["field_text"],
        arrowcolor=palette["accent_secondary"],
        bordercolor=palette["border"],
        lightcolor=palette["border"],
        darkcolor=palette["border"],
    )
    style.configure(
        "TNotebook",
        background=palette["background"],
        bordercolor=palette["border"],
        tabmargins=(2, 3, 2, 0),
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
        padding=(7, 5),
    )
    style.map(
        "Treeview.Heading",
        background=[("active", palette["surface"])],
        foreground=[("active", palette["accent_secondary"])],
    )
    style.configure("TPanedwindow", background=palette["border"])
    style.configure("TSeparator", background=palette["border"])
    style.configure(
        "TMenubutton",
        background=palette["surface_alt"],
        foreground=palette["text"],
        bordercolor=palette["border"],
        arrowcolor=palette["accent_secondary"],
        padding=(8, 5),
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
        font=("TkDefaultFont", 16, "bold"),
    )
    style.configure(
        "CX.Section.TLabel",
        background=palette["background"],
        foreground=palette["accent_secondary"],
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
        rowheight=26,
        bordercolor=palette["border"],
    )
    style.map(
        "CX.Navigator.Treeview",
        background=[("selected", palette["selection"])],
        foreground=[("selected", palette["selection_text"])],
    )

    # Industrial hierarchy: instrument surfaces, cyan primary actions, blue secondary
    # actions, and restrained semantic engineering states.
    style.configure(
        "CX.Hero.TFrame",
        background=palette["surface"],
        bordercolor=palette["border"],
        relief="solid",
        borderwidth=1,
        padding=(20, 16),
    )
    style.configure(
        "CX.HeroBrand.TLabel",
        background=palette["surface"],
        foreground=palette["accent"],
        font=("TkDefaultFont", 18, "bold"),
    )
    style.configure(
        "CX.HeroTitle.TLabel",
        background=palette["surface"],
        foreground=palette["text"],
        font=("TkDefaultFont", 11, "bold"),
    )
    style.configure(
        "CX.HeroMuted.TLabel",
        background=palette["surface"],
        foreground=palette["muted"],
    )
    style.configure(
        "CX.Card.TLabelframe",
        background=palette["panel"],
        foreground=palette["text"],
        bordercolor=palette["border"],
        lightcolor=palette["border"],
        darkcolor=palette["border"],
        borderwidth=1,
        relief="solid",
    )
    style.configure(
        "CX.Card.TLabelframe.Label",
        background=palette["panel"],
        foreground=palette["accent_secondary"],
        font=("TkDefaultFont", 9, "bold"),
    )
    style.configure("CX.Card.TFrame", background=palette["panel"])
    style.configure(
        "CX.Card.TLabel",
        background=palette["panel"],
        foreground=palette["text"],
    )
    style.configure(
        "CX.CardMuted.TLabel",
        background=palette["panel"],
        foreground=palette["muted"],
    )
    style.configure(
        "CX.CardTitle.TLabel",
        background=palette["panel"],
        foreground=palette["text"],
        font=("TkDefaultFont", 10, "bold"),
    )
    style.configure(
        "CX.Card.Treeview",
        background=palette["tree"],
        fieldbackground=palette["tree"],
        foreground=palette["text"],
        rowheight=27,
        bordercolor=palette["border"],
    )
    style.map(
        "CX.Card.Treeview",
        background=[("selected", palette["selection"])],
        foreground=[("selected", palette["selection_text"])],
    )
    style.configure(
        "CX.Primary.TButton",
        background=palette["accent"],
        foreground=palette["accent_text"],
        bordercolor=palette["accent"],
        lightcolor=palette["accent"],
        darkcolor=palette["accent"],
        borderwidth=1,
        padding=(13, 7),
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
        "CX.Secondary.TButton",
        background=palette["accent_secondary"],
        foreground=palette["accent_text"],
        bordercolor=palette["accent_secondary"],
        lightcolor=palette["accent_secondary"],
        darkcolor=palette["accent_secondary"],
        borderwidth=1,
        padding=(13, 7),
        font=("TkDefaultFont", 9, "bold"),
    )
    style.map(
        "CX.Secondary.TButton",
        background=[
            ("active", palette["info"]),
            ("pressed", palette["selection"]),
            ("disabled", palette["surface_alt"]),
        ],
        foreground=[
            ("disabled", palette["disabled"]),
            ("!disabled", palette["accent_text"]),
        ],
    )
    for name, color in (
        ("Success", palette["success"]),
        ("Warning", palette["warning"]),
        ("Error", palette["error"]),
        ("Info", palette["info"]),
    ):
        style.configure(
            f"CX.{name}.TLabel",
            background=palette["background"],
            foreground=color,
            font=("TkDefaultFont", 9, "bold"),
        )
        style.configure(
            f"CX.{name}Card.TLabel",
            background=palette["panel"],
            foreground=color,
            font=("TkDefaultFont", 9, "bold"),
        )
        style.configure(
            f"CX.{name}Badge.TLabel",
            background=palette["surface_alt"],
            foreground=color,
            padding=(7, 3),
            font=("TkDefaultFont", 8, "bold"),
        )

    style.configure(
        "CX.Toolbar.TFrame",
        background=palette["surface"],
        padding=(5, 4),
    )
    style.configure(
        "CX.PanelHeader.TFrame",
        background=palette["surface_alt"],
        padding=(7, 5),
    )
    style.configure(
        "CX.PanelHeader.TLabel",
        background=palette["surface_alt"],
        foreground=palette["accent_secondary"],
        font=("TkDefaultFont", 9, "bold"),
    )
    style.configure(
        "CX.Compact.TButton",
        background=palette["surface_alt"],
        foreground=palette["text"],
        bordercolor=palette["border"],
        padding=(7, 4),
    )
    style.map(
        "CX.Compact.TButton",
        background=[
            ("active", palette["surface"]),
            ("pressed", palette["selection"]),
            ("disabled", palette["surface_alt"]),
        ],
        foreground=[("disabled", palette["disabled"])],
        bordercolor=[("focus", palette["accent"])],
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
