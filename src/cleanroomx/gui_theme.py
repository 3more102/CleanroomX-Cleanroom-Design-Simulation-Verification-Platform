from __future__ import annotations

from copy import deepcopy
from typing import Any

import tkinter as tk
from tkinter import ttk


_THEME_PALETTES: dict[str, dict[str, str]] = {
    "light": {
        "background": "#e8eef5",
        "surface": "#f3f7fb",
        "surface_alt": "#e5edf6",
        "surface_raised": "#ffffff",
        "panel": "#f8fbfe",
        "text": "#162335",
        "muted": "#5f7186",
        "border": "#b9c8d8",
        "accent": "#007d9c",
        "accent_secondary": "#1677c8",
        "accent_hover": "#006780",
        "accent_text": "#ffffff",
        "success": "#15803d",
        "warning": "#b45309",
        "danger": "#c62828",
        "info": "#1677c8",
        "selection": "#c8edf5",
        "selection_text": "#102a43",
        "field": "#ffffff",
        "field_text": "#162335",
        "tree": "#f8fbfe",
        "disabled": "#8b99a8",
        "canvas_2d": "#f4f8fb",
        "canvas_3d": "#111b28",
        "plot": "#ffffff",
        "grid": "#cfdae6",
    },
    "dark": {
        "background": "#0B1220",
        "surface": "#111B2E",
        "surface_alt": "#17243A",
        "surface_raised": "#1C2C45",
        "panel": "#101A2B",
        "text": "#F1F5F9",
        "muted": "#94A3B8",
        "border": "#263750",
        "accent": "#22D3EE",
        "accent_secondary": "#38BDF8",
        "accent_hover": "#67E8F9",
        "accent_text": "#06202A",
        "success": "#22C55E",
        "warning": "#F59E0B",
        "danger": "#EF4444",
        "info": "#38BDF8",
        "selection": "#164E63",
        "selection_text": "#ECFEFF",
        "field": "#0E192A",
        "field_text": "#F1F5F9",
        "tree": "#0F1A2C",
        "disabled": "#64748B",
        "canvas_2d": "#101B2D",
        "canvas_3d": "#08111E",
        "plot": "#0D1727",
        "grid": "#2A3B52",
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
        padding=(8, 5),
    )
    style.map(
        "TButton",
        background=[
            ("active", palette["surface_raised"]),
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
        padding=(6, 4),
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
        arrowcolor=palette["text"],
        bordercolor=palette["border"],
        lightcolor=palette["border"],
        darkcolor=palette["border"],
        padding=(5, 3),
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
        arrowcolor=palette["text"],
        bordercolor=palette["border"],
        lightcolor=palette["border"],
        darkcolor=palette["border"],
        padding=(5, 3),
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
            ("selected", palette["surface_raised"]),
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
        background=[("active", palette["surface_raised"])],
        foreground=[("active", palette["accent"])],
    )

    style.configure("TPanedwindow", background=palette["border"])
    style.configure("TSeparator", background=palette["border"])
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
        background=[("active", palette["surface_raised"])],
        arrowcolor=[("active", palette["text"])],
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
        background=[("active", palette["surface_raised"])],
        foreground=[("disabled", palette["disabled"])],
    )

    style.configure(
        "CX.Topbar.TFrame",
        background=palette["panel"],
        borderwidth=1,
        relief="flat",
    )
    style.configure(
        "CX.Topbar.TLabel",
        background=palette["panel"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 9, "bold"),
    )
    style.configure(
        "CX.Brand.TLabel",
        background=palette["panel"],
        foreground=palette["accent"],
        font=("TkDefaultFont", 16, "bold"),
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
        rowheight=26,
        bordercolor=palette["border"],
    )
    style.map(
        "CX.Navigator.Treeview",
        background=[("selected", palette["selection"])],
        foreground=[("selected", palette["selection_text"])],
    )

    def configure_action_button(
        style_name: str,
        *,
        background: str,
        foreground: str,
        hover: str,
    ) -> None:
        style.configure(
            style_name,
            background=background,
            foreground=foreground,
            bordercolor=background,
            lightcolor=background,
            darkcolor=background,
            padding=(11, 6),
            font=("TkDefaultFont", 9, "bold"),
        )
        style.map(
            style_name,
            background=[
                ("active", hover),
                ("pressed", hover),
                ("disabled", palette["surface_alt"]),
            ],
            foreground=[
                ("disabled", palette["disabled"]),
                ("!disabled", foreground),
            ],
        )

    configure_action_button(
        "CX.Primary.TButton",
        background=palette["accent"],
        foreground=palette["accent_text"],
        hover=palette["accent_hover"],
    )
    configure_action_button(
        "CX.Info.TButton",
        background=palette["info"],
        foreground=palette["accent_text"],
        hover=palette["accent_secondary"],
    )
    configure_action_button(
        "CX.Success.TButton",
        background=palette["success"],
        foreground="#ffffff",
        hover=palette["success"],
    )
    configure_action_button(
        "CX.Warning.TButton",
        background=palette["warning"],
        foreground="#ffffff",
        hover=palette["warning"],
    )
    configure_action_button(
        "CX.Danger.TButton",
        background=palette["danger"],
        foreground="#ffffff",
        hover=palette["danger"],
    )

    style.configure(
        "CX.Toolbar.TFrame",
        background=palette["surface"],
        borderwidth=1,
        relief="flat",
        padding=(4, 3),
    )
    style.configure(
        "CX.Workflow.TFrame",
        background=palette["surface_alt"],
        borderwidth=1,
        relief="flat",
        padding=(4, 3),
    )
    style.configure(
        "CX.Workflow.TLabel",
        background=palette["surface_alt"],
        foreground=palette["accent"],
        font=("TkDefaultFont", 9, "bold"),
    )
    style.configure(
        "CX.PanelHeader.TFrame",
        background=palette["surface_raised"],
        padding=(7, 5),
    )
    style.configure(
        "CX.PanelHeader.TLabel",
        background=palette["surface_raised"],
        foreground=palette["accent_secondary"],
        font=("TkDefaultFont", 9, "bold"),
    )
    style.configure(
        "CX.Compact.TButton",
        background=palette["surface_alt"],
        foreground=palette["text"],
        bordercolor=palette["border"],
        lightcolor=palette["border"],
        darkcolor=palette["border"],
        padding=(7, 4),
    )
    style.map(
        "CX.Compact.TButton",
        background=[
            ("active", palette["surface_raised"]),
            ("pressed", palette["selection"]),
            ("disabled", palette["surface_alt"]),
        ],
        foreground=[
            ("active", palette["accent"]),
            ("disabled", palette["disabled"]),
        ],
        bordercolor=[("focus", palette["accent"])],
    )
    style.configure(
        "CX.StatusBar.TFrame",
        background=palette["panel"],
        borderwidth=1,
        relief="flat",
    )
    style.configure(
        "CX.Status.TLabel",
        background=palette["panel"],
        foreground=palette["text"],
    )
    style.configure(
        "CX.StatusMuted.TLabel",
        background=palette["panel"],
        foreground=palette["muted"],
    )
    style.configure(
        "CX.StatusAccent.TLabel",
        background=palette["panel"],
        foreground=palette["accent"],
        font=("TkDefaultFont", 9, "bold"),
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
