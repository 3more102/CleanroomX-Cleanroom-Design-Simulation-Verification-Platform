from __future__ import annotations

from copy import deepcopy
from typing import Any

import tkinter as tk
from tkinter import ttk


_THEME_PALETTES: dict[str, dict[str, str]] = {
    "light": {
        "background": "#e7edf4",
        "surface": "#f3f7fb",
        "surface_alt": "#dfe8f1",
        "panel": "#ffffff",
        "text": "#102033",
        "muted": "#52657a",
        "border": "#aebdcb",
        "accent": "#087ea4",
        "accent_hover": "#036685",
        "accent_text": "#ffffff",
        "selection": "#bdefff",
        "selection_text": "#082f49",
        "field": "#f9fbfd",
        "field_text": "#102033",
        "tree": "#f7fafc",
        "disabled": "#8191a3",
        "canvas_2d": "#eef4f8",
        "canvas_3d": "#0b1220",
        "plot": "#f8fbfd",
        "grid": "#c6d3df",
    },
    "dark": {
        "background": "#0B1220",
        "surface": "#111B2E",
        "surface_alt": "#17243A",
        "panel": "#111B2E",
        "text": "#F1F5F9",
        "muted": "#94A3B8",
        "border": "#263750",
        "accent": "#22D3EE",
        "accent_hover": "#38BDF8",
        "accent_text": "#06202A",
        "selection": "#164E63",
        "selection_text": "#F0FDFA",
        "field": "#0E1728",
        "field_text": "#F1F5F9",
        "tree": "#0F192A",
        "disabled": "#64748B",
        "canvas_2d": "#101B2D",
        "canvas_3d": "#07101D",
        "plot": "#0D1727",
        "grid": "#2A3D56",
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
        "CX.Surface.TFrame",
        background=palette["surface"],
    )
    style.configure(
        "CX.Panel.TFrame",
        background=palette["panel"],
        relief="flat",
        borderwidth=1,
    )
    style.configure(
        "CX.Sidebar.TFrame",
        background=palette["surface"],
        relief="flat",
        borderwidth=1,
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
        bordercolor=[("focus", palette["accent"])],
        lightcolor=[("focus", palette["accent"])],
        darkcolor=[("focus", palette["accent"])],
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
        bordercolor=[("focus", palette["accent"])],
        lightcolor=[("focus", palette["accent"])],
        darkcolor=[("focus", palette["accent"])],
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
    style.map(
        "TSpinbox",
        bordercolor=[("focus", palette["accent"])],
        lightcolor=[("focus", palette["accent"])],
        darkcolor=[("focus", palette["accent"])],
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
        lightcolor=palette["border"],
        darkcolor=palette["border"],
    )
    style.map(
        "TNotebook.Tab",
        background=[
            ("selected", palette["surface"]),
            ("active", palette["panel"]),
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
        lightcolor=palette["border"],
        darkcolor=palette["border"],
        padding=(6, 5),
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
        "TScrollbar",
        background=palette["surface_alt"],
        troughcolor=palette["surface"],
        arrowcolor=palette["muted"],
        bordercolor=palette["border"],
        lightcolor=palette["border"],
        darkcolor=palette["border"],
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

    # Restrained industrial semantic colors communicate engineering state
    # without competing with the design canvas.
    semantic = {
        "success": "#22C55E",
        "warning": "#F59E0B",
        "danger": "#DC2626",
        "info": "#38BDF8",
        "violet": "#7C3AED",
    }

    style.configure(
        "CX.Workbench.TFrame",
        background=palette["surface"],
    )
    style.configure(
        "CX.Topbar.TFrame",
        background=palette["panel"],
        bordercolor=palette["border"],
        lightcolor=palette["border"],
        darkcolor=palette["border"],
        relief="flat",
        borderwidth=1,
    )
    style.configure(
        "CX.Topbar.TLabel",
        background=palette["panel"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 9, "bold"),
    )
    style.configure(
        "CX.TopbarBrand.TLabel",
        background=palette["panel"],
        foreground=palette["accent"],
        font=("TkDefaultFont", 16, "bold"),
    )
    style.configure(
        "CX.Sidebar.TLabel",
        background=palette["surface"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 9, "bold"),
    )
    style.configure(
        "CX.Panel.TFrame",
        background=palette["panel"],
    )
    style.configure(
        "CX.PanelHint.TLabel",
        background=palette["panel"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 8),
    )
    style.configure(
        "CX.Statusbar.TFrame",
        background=palette["surface_alt"],
        padding=(8, 4),
    )
    style.configure(
        "CX.Status.TLabel",
        background=palette["surface_alt"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 8),
    )
    style.configure(
        "CX.Workflow.TFrame",
        background=palette["surface"],
        padding=(5, 4),
    )
    style.configure(
        "CX.WorkflowLabel.TLabel",
        background=palette["surface"],
        foreground=palette["accent"],
        font=("TkDefaultFont", 8, "bold"),
    )
    style.configure(
        "CX.Muted.TLabel",
        background=palette["background"],
        foreground=palette["muted"],
    )
    for style_name, color in (
        ("CX.Success.TLabel", semantic["success"]),
        ("CX.Warning.TLabel", semantic["warning"]),
        ("CX.Error.TLabel", semantic["danger"]),
        ("CX.Info.TLabel", semantic["info"]),
    ):
        style.configure(
            style_name,
            background=palette["background"],
            foreground=color,
            font=("TkDefaultFont", 9, "bold"),
        )

    for style_name, color, text_color in (
        ("CX.Success.TButton", semantic["success"], "#07131E"),
        ("CX.Warning.TButton", semantic["warning"], "#07131E"),
        ("CX.Danger.TButton", semantic["danger"], "#ffffff"),
        ("CX.Info.TButton", semantic["info"], "#07131E"),
        ("CX.Violet.TButton", semantic["violet"], "#ffffff"),
    ):
        style.configure(
            style_name,
            background=color,
            foreground=text_color,
            bordercolor=color,
            lightcolor=color,
            darkcolor=color,
            padding=(9, 5),
        )
        style.map(
            style_name,
            background=[
                ("active", color),
                ("pressed", color),
                ("disabled", palette["surface_alt"]),
            ],
            foreground=[
                ("disabled", palette["disabled"]),
                ("!disabled", text_color),
            ],
        )

    style.configure(
        "CX.Brand.TLabel",
        background=palette["background"],
        foreground=palette["accent"],
        font=("TkDefaultFont", 16, "bold"),
    )
    style.configure(
        "CX.Accent.TLabel",
        background=palette["background"],
        foreground=palette["accent"],
        font=("TkDefaultFont", 9, "bold"),
    )
    style.configure(
        "CX.Muted.TLabel",
        background=palette["background"],
        foreground=palette["muted"],
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
        relief="flat",
        borderwidth=1,
    )
    style.configure(
        "CX.PanelHeader.TFrame",
        background=palette["surface_alt"],
        padding=(8, 5),
        relief="flat",
        borderwidth=1,
    )
    style.configure(
        "CX.PanelHeader.TLabel",
        background=palette["surface_alt"],
        foreground=palette["accent"],
        font=("TkDefaultFont", 9, "bold"),
    )
    style.configure(
        "CX.Tool.TButton",
        background=palette["surface"],
        foreground=palette["text"],
        bordercolor=palette["border"],
        lightcolor=palette["border"],
        darkcolor=palette["border"],
        padding=(7, 4),
    )
    style.map(
        "CX.Tool.TButton",
        background=[
            ("active", palette["surface_alt"]),
            ("pressed", palette["selection"]),
        ],
        foreground=[
            ("active", palette["accent"]),
            ("disabled", palette["disabled"]),
        ],
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
