from __future__ import annotations

from copy import deepcopy
from typing import Any

import tkinter as tk
from tkinter import ttk


_THEME_PALETTES: dict[str, dict[str, str]] = {
    "light": {
        "background": "#f3f6fa",
        "surface": "#ffffff",
        "surface_alt": "#eaf0f7",
        "panel": "#ffffff",
        "toolbar": "#e8eef7",
        "topbar": "#162033",
        "topbar_text": "#f8fafc",
        "statusbar": "#e5ebf3",
        "statusbar_text": "#334155",
        "text": "#172033",
        "muted": "#617086",
        "border": "#cbd5e1",
        "border_strong": "#9fb0c4",
        "accent": "#2563eb",
        "accent_hover": "#1d4ed8",
        "accent_soft": "#dbeafe",
        "accent_text": "#ffffff",
        "selection": "#dbeafe",
        "selection_text": "#102a43",
        "field": "#ffffff",
        "field_text": "#172033",
        "tree": "#fbfdff",
        "disabled": "#94a3b8",
        "success": "#15803d",
        "success_soft": "#dcfce7",
        "warning": "#b45309",
        "warning_soft": "#fef3c7",
        "danger": "#b91c1c",
        "danger_soft": "#fee2e2",
        "info": "#0369a1",
        "info_soft": "#e0f2fe",
        "canvas_2d": "#f8fafc",
        "canvas_3d": "#0b1220",
        "plot": "#ffffff",
        "grid": "#d8e1eb",
    },
    "dark": {
        "background": "#111827",
        "surface": "#182233",
        "surface_alt": "#202c3d",
        "panel": "#162131",
        "toolbar": "#1c293a",
        "topbar": "#0a101a",
        "topbar_text": "#f8fafc",
        "statusbar": "#151f2d",
        "statusbar_text": "#c7d2e0",
        "text": "#e8eef6",
        "muted": "#9aabc0",
        "border": "#34445a",
        "border_strong": "#50657f",
        "accent": "#60a5fa",
        "accent_hover": "#93c5fd",
        "accent_soft": "#173b66",
        "accent_text": "#07111f",
        "selection": "#1f4f7d",
        "selection_text": "#ffffff",
        "field": "#0f1724",
        "field_text": "#e8eef6",
        "tree": "#121c2a",
        "disabled": "#6f8094",
        "success": "#4ade80",
        "success_soft": "#153b29",
        "warning": "#fbbf24",
        "warning_soft": "#493615",
        "danger": "#fb7185",
        "danger_soft": "#4b1f2a",
        "info": "#38bdf8",
        "info_soft": "#12394b",
        "canvas_2d": "#172231",
        "canvas_3d": "#080d14",
        "plot": "#101925",
        "grid": "#324258",
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
        bordercolor=palette["border"],
        focuscolor=palette["accent"],
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
        focuscolor=palette["accent"],
        padding=(8, 5),
    )
    style.map(
        "TButton",
        background=[
            ("pressed", palette["selection"]),
            ("active", palette["surface"]),
            ("disabled", palette["surface_alt"]),
        ],
        foreground=[
            ("disabled", palette["disabled"]),
            ("!disabled", palette["text"]),
        ],
        bordercolor=[
            ("focus", palette["accent"]),
            ("active", palette["border_strong"]),
        ],
    )

    for control in ("TCheckbutton", "TRadiobutton"):
        style.configure(
            control,
            background=palette["background"],
            foreground=palette["text"],
            focuscolor=palette["accent"],
        )
        style.map(
            control,
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
            ("disabled", palette["surface_alt"]),
            ("readonly", palette["surface_alt"]),
        ],
        foreground=[("disabled", palette["disabled"])],
        bordercolor=[
            ("focus", palette["accent"]),
            ("!focus", palette["border"]),
        ],
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
        padding=(4, 3),
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
        padding=(4, 3),
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
        padding=(11, 7),
        bordercolor=palette["border"],
        font=("TkDefaultFont", 9),
    )
    style.map(
        "TNotebook.Tab",
        background=[
            ("selected", palette["accent_soft"]),
            ("active", palette["surface"]),
        ],
        foreground=[
            ("selected", palette["text"]),
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
        lightcolor=palette["border"],
        darkcolor=palette["border"],
        rowheight=26,
    )
    style.map(
        "Treeview",
        background=[("selected", palette["selection"])],
        foreground=[("selected", palette["selection_text"])],
        bordercolor=[("focus", palette["accent"])],
    )
    style.configure(
        "Treeview.Heading",
        background=palette["surface_alt"],
        foreground=palette["text"],
        bordercolor=palette["border"],
        lightcolor=palette["border"],
        darkcolor=palette["border"],
        relief="flat",
        padding=(6, 5),
        font=("TkDefaultFont", 9, "bold"),
    )
    style.map(
        "Treeview.Heading",
        background=[("active", palette["accent_soft"])],
        foreground=[("active", palette["text"])],
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
        background=[
            ("active", palette["border_strong"]),
            ("pressed", palette["accent"]),
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
        bordercolor=[("focus", palette["accent"])],
    )

    # Application chrome.
    style.configure(
        "CX.Topbar.TFrame",
        background=palette["topbar"],
        padding=(4, 2),
    )
    style.configure(
        "CX.Topbar.TLabel",
        background=palette["topbar"],
        foreground=palette["topbar_text"],
    )
    style.configure(
        "CX.Brand.TLabel",
        background=palette["topbar"],
        foreground=palette["accent"],
        font=("TkDefaultFont", 15, "bold"),
    )
    style.configure(
        "CX.Toolbar.TFrame",
        background=palette["toolbar"],
        bordercolor=palette["border"],
        relief="flat",
        padding=(4, 3),
    )
    style.configure(
        "CX.Toolbar.TLabel",
        background=palette["toolbar"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 9, "bold"),
    )
    style.configure(
        "CX.Statusbar.TFrame",
        background=palette["statusbar"],
        bordercolor=palette["border"],
    )
    style.configure(
        "CX.Statusbar.TLabel",
        background=palette["statusbar"],
        foreground=palette["statusbar_text"],
        font=("TkDefaultFont", 8),
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
        background=[("selected", palette["accent_soft"])],
        foreground=[("selected", palette["text"])],
    )

    # Primary and compact actions.
    style.configure(
        "CX.Primary.TButton",
        background=palette["accent"],
        foreground=palette["accent_text"],
        bordercolor=palette["accent"],
        lightcolor=palette["accent"],
        darkcolor=palette["accent"],
        focuscolor=palette["accent_hover"],
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
            ("selected", palette["accent_soft"]),
            ("pressed", palette["accent_soft"]),
            ("active", palette["surface"]),
            ("disabled", palette["surface_alt"]),
        ],
        foreground=[
            ("selected", palette["accent"]),
            ("disabled", palette["disabled"]),
        ],
        bordercolor=[
            ("selected", palette["accent"]),
            ("focus", palette["accent"]),
            ("active", palette["border_strong"]),
        ],
    )
    # Defined here so the pending workspace-mode usability branch can use the
    # same visual language without introducing another independent palette.
    style.configure(
        "CX.WorkspaceMode.TButton",
        background=palette["surface_alt"],
        foreground=palette["text"],
        bordercolor=palette["border"],
        padding=(7, 4),
    )
    style.map(
        "CX.WorkspaceMode.TButton",
        background=[
            ("selected", palette["accent"]),
            ("pressed", palette["accent_soft"]),
            ("active", palette["surface"]),
        ],
        foreground=[
            ("selected", palette["accent_text"]),
            ("!selected", palette["text"]),
        ],
        bordercolor=[
            ("selected", palette["accent"]),
            ("focus", palette["accent"]),
        ],
    )

    style.configure(
        "CX.PanelHeader.TFrame",
        background=palette["surface_alt"],
        padding=(7, 5),
    )
    style.configure(
        "CX.PanelHeader.TLabel",
        background=palette["surface_alt"],
        foreground=palette["text"],
        font=("TkDefaultFont", 9, "bold"),
    )

    # Semantic styles are available to diagnostics/verification panels without
    # requiring those panels to know light-vs-dark color values.
    for name, foreground, background in (
        ("Success", palette["success"], palette["success_soft"]),
        ("Warning", palette["warning"], palette["warning_soft"]),
        ("Danger", palette["danger"], palette["danger_soft"]),
        ("Info", palette["info"], palette["info_soft"]),
    ):
        style.configure(
            f"CX.{name}.TLabel",
            foreground=foreground,
            background=background,
            padding=(6, 3),
            font=("TkDefaultFont", 8, "bold"),
        )

    # Defaults for Tk-native widgets created after this call.
    root.option_add("*Text.background", palette["field"])
    root.option_add("*Text.foreground", palette["field_text"])
    root.option_add("*Text.insertBackground", palette["text"])
    root.option_add("*Text.selectBackground", palette["selection"])
    root.option_add("*Text.selectForeground", palette["selection_text"])
    root.option_add("*Text.highlightBackground", palette["border"])
    root.option_add("*Text.highlightColor", palette["accent"])
    root.option_add("*Menu.background", palette["surface"])
    root.option_add("*Menu.foreground", palette["text"])
    root.option_add("*Menu.activeBackground", palette["accent_soft"])
    root.option_add("*Menu.activeForeground", palette["text"])
    root.option_add("*Menu.disabledForeground", palette["disabled"])

    return palette
