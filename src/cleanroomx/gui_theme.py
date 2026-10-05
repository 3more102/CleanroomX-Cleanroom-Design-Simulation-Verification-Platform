from __future__ import annotations

from copy import deepcopy
from typing import Any

import tkinter as tk
from tkinter import ttk


_DEFAULT_THEME = "dark"

_THEME_PALETTES: dict[str, dict[str, str]] = {
    "light": {
        "background": "#eef3f8",
        "surface": "#f8fafc",
        "surface_alt": "#e8eef5",
        "panel": "#ffffff",
        "text": "#172033",
        "muted": "#5f6f84",
        "border": "#c7d2df",
        "accent": "#0284c7",
        "accent_hover": "#0369a1",
        "accent_text": "#ffffff",
        "selection": "#dbeafe",
        "selection_text": "#0f2742",
        "field": "#ffffff",
        "field_text": "#172033",
        "tree": "#fbfdff",
        "disabled": "#8a98aa",
        "canvas_2d": "#f8fafc",
        "canvas_3d": "#111827",
        "plot": "#ffffff",
        "grid": "#d6dee8",
        "success": "#15803d",
        "warning": "#b45309",
        "error": "#dc2626",
        "info": "#0284c7",
        "mode_design": "#0F766E",
        "mode_analyze": "#0369A1",
        "mode_verify": "#B45309",
        "mode_evidence": "#7C3AED",
        "mode_release": "#15803D",
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
        "accent_text": "#07111F",
        "selection": "#164E63",
        "selection_text": "#F1F5F9",
        "field": "#0F172A",
        "field_text": "#F1F5F9",
        "tree": "#0F172A",
        "disabled": "#64748B",
        "canvas_2d": "#0D1728",
        "canvas_3d": "#08111F",
        "plot": "#0D1728",
        "grid": "#263750",
        "success": "#22C55E",
        "warning": "#F59E0B",
        "error": "#EF4444",
        "info": "#38BDF8",
        "mode_design": "#2DD4BF",
        "mode_analyze": "#38BDF8",
        "mode_verify": "#F59E0B",
        "mode_evidence": "#A78BFA",
        "mode_release": "#22C55E",
    },
}


def normalize_theme_name(value: Any) -> str:
    name = str(value or "").strip().lower()
    return name if name in _THEME_PALETTES else _DEFAULT_THEME


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
        bordercolor=palette["border"],
        lightcolor=palette["border"],
        darkcolor=palette["border"],
        troughcolor=palette["background"],
    )
    style.configure("TFrame", background=palette["background"])
    style.configure("CX.Surface.TFrame", background=palette["surface"])
    style.configure("CX.Panel.TFrame", background=palette["panel"])
    style.configure("CX.Card.TFrame", background=palette["surface_alt"])
    style.configure(
        "CX.Topbar.TFrame",
        background=palette["surface"],
        bordercolor=palette["border"],
        relief="flat",
    )
    style.configure(
        "CX.Workflow.TFrame",
        background=palette["surface_alt"],
        bordercolor=palette["border"],
        relief="flat",
    )

    style.configure(
        "TLabel",
        background=palette["background"],
        foreground=palette["text"],
    )
    style.configure(
        "TLabelframe",
        background=palette["panel"],
        foreground=palette["text"],
        bordercolor=palette["border"],
        lightcolor=palette["border"],
        darkcolor=palette["border"],
        relief="solid",
    )
    style.configure(
        "TLabelframe.Label",
        background=palette["panel"],
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
        relief="flat",
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
        bordercolor=[
            ("focus", palette["accent"]),
            ("active", palette["accent"]),
        ],
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
        bordercolor=[
            ("focus", palette["accent_hover"]),
            ("!disabled", palette["accent"]),
        ],
    )
    style.configure(
        "CX.Secondary.TButton",
        background=palette["surface_alt"],
        foreground=palette["text"],
        bordercolor=palette["border"],
        padding=(10, 5),
    )
    style.map(
        "CX.Secondary.TButton",
        background=[
            ("active", palette["surface"]),
            ("pressed", palette["selection"]),
        ],
        bordercolor=[
            ("focus", palette["accent"]),
            ("active", palette["accent"]),
        ],
    )
    style.configure(
        "CX.Destructive.TButton",
        background=palette["surface_alt"],
        foreground=palette["error"],
        bordercolor=palette["error"],
        padding=(10, 5),
    )
    style.map(
        "CX.Destructive.TButton",
        background=[
            ("active", palette["error"]),
            ("pressed", palette["error"]),
            ("disabled", palette["surface_alt"]),
        ],
        foreground=[
            ("active", "#ffffff"),
            ("pressed", "#ffffff"),
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
        bordercolor=[("focus", palette["accent"])],
    )
    # Workstation modes use semantic industrial colors. Text remains explicit,
    # so color reinforces hierarchy without becoming the only status signal.
    mode_accents = {
        "Design": palette["mode_design"],
        "Analyze": palette["mode_analyze"],
        "Verify": palette["mode_verify"],
        "Evidence": palette["mode_evidence"],
        "Release": palette["mode_release"],
    }
    for mode_name, mode_color in mode_accents.items():
        style.configure(
            f"CX.Mode{mode_name}.TButton",
            background=palette["background"],
            foreground=mode_color,
            bordercolor=palette["surface_alt"],
            padding=(11, 5),
            font=("TkDefaultFont", 9, "bold"),
            relief="flat",
        )
        style.map(
            f"CX.Mode{mode_name}.TButton",
            background=[
                ("active", palette["surface_alt"]),
                ("pressed", palette["surface_alt"]),
            ],
            foreground=[
                ("active", mode_color),
                ("pressed", mode_color),
            ],
            bordercolor=[
                ("focus", mode_color),
                ("active", mode_color),
            ],
        )
        style.configure(
            f"CX.Mode{mode_name}Active.TButton",
            background=mode_color,
            foreground=palette["accent_text"],
            bordercolor=mode_color,
            padding=(11, 5),
            font=("TkDefaultFont", 9, "bold"),
            relief="solid",
        )
        style.map(
            f"CX.Mode{mode_name}Active.TButton",
            background=[
                ("active", mode_color),
                ("pressed", palette["surface_alt"]),
            ],
            foreground=[
                ("active", palette["accent_text"]),
                ("pressed", mode_color),
            ],
            bordercolor=[
                ("focus", mode_color),
                ("active", mode_color),
            ],
        )

    # Generic aliases remain for compatibility with extensions that use the
    # pre-semantic style names directly.
    style.configure(
        "CX.Mode.TButton",
        background=palette["background"],
        foreground=palette["muted"],
        bordercolor=palette["surface_alt"],
        padding=(11, 5),
        font=("TkDefaultFont", 9, "bold"),
    )
    style.configure(
        "CX.ModeActive.TButton",
        background=palette["selection"],
        foreground=palette["accent"],
        bordercolor=palette["accent"],
        padding=(11, 5),
        font=("TkDefaultFont", 9, "bold"),
    )
    style.map(
        "CX.Mode.TButton",
        background=[
            ("active", palette["surface_alt"]),
            ("pressed", palette["selection"]),
        ],
        foreground=[
            ("active", palette["text"]),
            ("pressed", palette["text"]),
        ],
        bordercolor=[("focus", palette["accent"])],
    )
    style.map(
        "CX.ModeActive.TButton",
        background=[
            ("active", palette["selection"]),
            ("pressed", palette["selection"]),
        ],
        foreground=[
            ("active", palette["accent_hover"]),
            ("pressed", palette["accent"]),
        ],
        bordercolor=[
            ("focus", palette["accent_hover"]),
            ("active", palette["accent"]),
        ],
    )

    style.configure(
        "CX.Step.TButton",
        background=palette["surface"],
        foreground=palette["muted"],
        bordercolor=palette["border"],
        padding=(9, 4),
        font=("TkDefaultFont", 8, "bold"),
    )
    style.map(
        "CX.Step.TButton",
        background=[
            ("active", palette["panel"]),
            ("pressed", palette["selection"]),
            ("disabled", palette["surface"]),
        ],
        foreground=[
            ("active", palette["text"]),
            ("pressed", palette["accent"]),
            ("disabled", palette["disabled"]),
        ],
        bordercolor=[
            ("focus", palette["accent"]),
            ("active", palette["accent"]),
        ],
    )
    for step_name, step_color in mode_accents.items():
        style.configure(
            f"CX.Step{step_name}.TButton",
            background=palette["surface"],
            foreground=step_color,
            bordercolor=palette["border"],
            padding=(9, 4),
            font=("TkDefaultFont", 8, "bold"),
            relief="flat",
        )
        style.map(
            f"CX.Step{step_name}.TButton",
            background=[
                ("active", palette["surface_alt"]),
                ("pressed", step_color),
                ("disabled", palette["surface"]),
            ],
            foreground=[
                ("active", step_color),
                ("pressed", palette["accent_text"]),
                ("disabled", palette["disabled"]),
            ],
            bordercolor=[
                ("focus", step_color),
                ("active", step_color),
            ],
        )

    style.configure(
        "CX.NavigatorAction.TButton",
        background=palette["surface_alt"],
        foreground=palette["accent"],
        bordercolor=palette["border"],
        padding=(7, 4),
        font=("TkDefaultFont", 8, "bold"),
    )
    style.map(
        "CX.NavigatorAction.TButton",
        background=[
            ("active", palette["selection"]),
            ("pressed", palette["selection"]),
        ],
        foreground=[
            ("active", palette["accent_hover"]),
            ("pressed", palette["accent"]),
        ],
        bordercolor=[
            ("focus", palette["accent"]),
            ("active", palette["accent"]),
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
    style.map("TSpinbox", bordercolor=[("focus", palette["accent"])])

    style.configure(
        "TNotebook",
        background=palette["background"],
        bordercolor=palette["border"],
        tabmargins=(2, 2, 2, 0),
    )
    style.configure(
        "TNotebook.Tab",
        background=palette["surface"],
        foreground=palette["muted"],
        padding=(11, 6),
        bordercolor=palette["border"],
        font=("TkDefaultFont", 9),
    )
    style.map(
        "TNotebook.Tab",
        background=[
            ("selected", palette["surface_alt"]),
            ("active", palette["panel"]),
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
        foreground=palette["text"],
        bordercolor=palette["border"],
        rowheight=26,
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
        font=("TkDefaultFont", 9, "bold"),
        padding=(7, 5),
        relief="flat",
    )
    style.map(
        "Treeview.Heading",
        background=[("active", palette["surface"])],
        foreground=[("active", palette["accent"])],
    )
    style.configure(
        "CX.Navigator.Treeview",
        background=palette["tree"],
        fieldbackground=palette["tree"],
        foreground=palette["text"],
        rowheight=27,
        bordercolor=palette["border"],
        relief="flat",
    )
    style.map(
        "CX.Navigator.Treeview",
        background=[("selected", palette["selection"])],
        foreground=[("selected", palette["selection_text"])],
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
        background=[("active", palette["surface"])],
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
        background=[("active", palette["surface"])],
        foreground=[("disabled", palette["disabled"])],
        bordercolor=[("focus", palette["accent"])],
    )

    style.configure(
        "CX.Brand.TLabel",
        background=palette["surface"],
        foreground=palette["accent"],
        font=("TkDefaultFont", 15, "bold"),
    )
    style.configure(
        "CX.Meta.TLabel",
        background=palette["surface"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 8, "bold"),
    )
    style.configure(
        "CX.ToolbarLabel.TLabel",
        background=palette["surface"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 8, "bold"),
    )
    style.configure(
        "CX.WorkflowLabel.TLabel",
        background=palette["surface_alt"],
        foreground=palette["accent"],
        font=("TkDefaultFont", 8, "bold"),
    )
    style.configure(
        "CX.Helper.TLabel",
        background=palette["panel"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 8),
    )
    style.configure(
        "CX.Section.TLabel",
        background=palette["panel"],
        foreground=palette["accent_hover"],
        font=("TkDefaultFont", 8, "bold"),
    )
    style.configure(
        "CX.ViewTitle.TLabel",
        background=palette["background"],
        foreground=palette["text"],
        font=("TkDefaultFont", 10, "bold"),
    )
    style.configure(
        "CX.Toolbar.TFrame",
        background=palette["surface"],
        padding=(4, 3),
    )
    style.configure(
        "CX.PanelHeader.TFrame",
        background=palette["surface_alt"],
        padding=(7, 5),
    )
    style.configure(
        "CX.PanelHeader.TLabel",
        background=palette["surface_alt"],
        foreground=palette["accent"],
        font=("TkDefaultFont", 9, "bold"),
    )
    style.configure(
        "CX.StatusBar.TFrame",
        background=palette["surface"],
        bordercolor=palette["border"],
    )
    style.configure(
        "CX.StatusBar.TLabel",
        background=palette["surface"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 8),
    )
    style.configure(
        "CX.StatusPrimary.TLabel",
        background=palette["surface"],
        foreground=palette["text"],
        font=("TkDefaultFont", 8, "bold"),
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
            f"CX.{name}Badge.TLabel",
            background=palette["surface_alt"],
            foreground=color,
            padding=(6, 2),
            font=("TkDefaultFont", 8, "bold"),
        )

    # Defaults for Tk-native widgets created after this call.
    root.option_add("*Text.background", palette["field"])
    root.option_add("*Text.foreground", palette["field_text"])
    root.option_add("*Text.insertBackground", palette["text"])
    root.option_add("*Text.selectBackground", palette["selection"])
    root.option_add("*Text.selectForeground", palette["selection_text"])
    root.option_add("*Listbox.background", palette["field"])
    root.option_add("*Listbox.foreground", palette["field_text"])
    root.option_add("*Listbox.selectBackground", palette["selection"])
    root.option_add("*Listbox.selectForeground", palette["selection_text"])
    root.option_add("*Menu.background", palette["surface"])
    root.option_add("*Menu.foreground", palette["text"])
    root.option_add("*Menu.activeBackground", palette["selection"])
    root.option_add("*Menu.activeForeground", palette["selection_text"])
    root.option_add("*Menu.disabledForeground", palette["disabled"])

    return palette
