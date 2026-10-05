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
        "border_strong": "#94a3b8",
        "info": "#0284c7",
        "success": "#15803d",
        "warning": "#b45309",
        "error": "#b91c1c",
        "purple": "#7c3aed",
        "orange": "#c2410c",
        "magenta": "#be185d",
        "blue_surface": "#dbeafe",
        "cyan_surface": "#cffafe",
        "green_surface": "#dcfce7",
        "success_surface": "#dcfce7",
        "warning_surface": "#fef3c7",
        "error_surface": "#fee2e2",
        "purple_surface": "#ede9fe",
        "orange_surface": "#ffedd5",
        "magenta_surface": "#fce7f3",
    },
    "dark": {
        "background": "#0B1220",
        "surface": "#111B2E",
        "surface_alt": "#142034",
        "panel": "#17243A",
        "text": "#F1F5F9",
        "muted": "#94A3B8",
        "border": "#263750",
        "accent": "#22D3EE",
        "accent_hover": "#38BDF8",
        "accent_text": "#07131F",
        "selection": "#164E63",
        "selection_text": "#F1F5F9",
        "field": "#0E1728",
        "field_text": "#F1F5F9",
        "tree": "#101A2B",
        "disabled": "#64748B",
        "canvas_2d": "#0B1526",
        "canvas_3d": "#08101D",
        "plot": "#0D1728",
        "grid": "#20314A",
        "border_strong": "#334A68",
        "info": "#38BDF8",
        "success": "#22C55E",
        "warning": "#F59E0B",
        "error": "#EF4444",
        "purple": "#A78BFA",
        "orange": "#F97316",
        "magenta": "#E879F9",
        "blue_surface": "#102A4A",
        "cyan_surface": "#0D3340",
        "green_surface": "#12351F",
        "success_surface": "#12351F",
        "warning_surface": "#3A2A0D",
        "error_surface": "#3A161B",
        "purple_surface": "#2C214A",
        "orange_surface": "#3A2112",
        "magenta_surface": "#3A1738",
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
        padding=(8, 5),
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
        padding=(10, 6),
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
        rowheight=25,
        borderwidth=0,
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
        "CX.Muted.TLabel",
        background=palette["background"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 8),
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
        padding=(4, 3),
    )
    style.configure(
        "CX.PanelHeader.TFrame",
        background=palette["surface_alt"],
        padding=(6, 4),
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
            ("active", palette["panel"]),
            ("pressed", palette["selection"]),
            ("disabled", palette["surface_alt"]),
        ],
        foreground=[("disabled", palette["disabled"])],
    )

    style.configure(
        "CX.Topbar.TFrame",
        background=palette["surface"],
        padding=(2, 1),
    )
    style.configure(
        "CX.Topbar.TLabel",
        background=palette["surface"],
        foreground=palette["text"],
    )
    style.configure(
        "CX.TopbarBrand.TLabel",
        background=palette["surface"],
        foreground=palette["accent"],
        font=("TkDefaultFont", 15, "bold"),
    )
    style.configure(
        "CX.TopbarMuted.TLabel",
        background=palette["surface"],
        foreground=palette["muted"],
    )
    style.configure(
        "CX.Healthbar.TFrame",
        background=palette["surface"],
        padding=(0, 2),
    )
    style.configure(
        "CX.StatusBar.TFrame",
        background=palette["surface"],
        padding=(8, 4),
    )
    style.configure(
        "CX.StatusBar.TLabel",
        background=palette["surface"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 8),
    )
    style.configure(
        "CX.Card.TFrame",
        background=palette["panel"],
        relief="flat",
        borderwidth=1,
    )
    style.configure(
        "CX.CardTitle.TLabel",
        background=palette["panel"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 8, "bold"),
    )
    style.configure(
        "CX.CardValue.TLabel",
        background=palette["panel"],
        foreground=palette["text"],
        font=("TkDefaultFont", 11, "bold"),
    )
    style.configure(
        "CX.CardBody.TLabel",
        background=palette["panel"],
        foreground=palette["text"],
        font=("TkDefaultFont", 9),
    )

    status_styles = {
        "Success": ("success_surface", "success"),
        "Warning": ("warning_surface", "warning"),
        "Error": ("error_surface", "error"),
        "Info": ("cyan_surface", "info"),
        "Purple": ("purple_surface", "purple"),
        "Orange": ("orange_surface", "orange"),
        "Neutral": ("surface_alt", "muted"),
    }
    for name, (background_key, foreground_key) in status_styles.items():
        style.configure(
            f"CX.Status.{name}.TLabel",
            background=palette[background_key],
            foreground=palette[foreground_key],
            padding=(7, 3),
            font=("TkDefaultFont", 8, "bold"),
        )

    domain_styles = {
        "Geometry": "accent",
        "HVAC": "info",
        "Airflow": "accent",
        "Pressure": "purple",
        "Electrical": "warning",
        "Utilities": "orange",
        "Safety": "error",
        "Evidence": "success",
        "Verification": "success",
        "Simulation": "purple",
    }
    for name, foreground_key in domain_styles.items():
        style.configure(
            f"CX.Domain.{name}.TLabel",
            background=palette["surface_alt"],
            foreground=palette[foreground_key],
            padding=(6, 2),
            font=("TkDefaultFont", 8, "bold"),
        )

    readiness_progress_styles = {
        "Success": "success",
        "Warning": "warning",
        "Neutral": "accent",
    }
    for name, color_key in readiness_progress_styles.items():
        style.configure(
            f"CX.Readiness.{name}.Horizontal.TProgressbar",
            background=palette[color_key],
            troughcolor=palette["surface_alt"],
            bordercolor=palette["border"],
            lightcolor=palette[color_key],
            darkcolor=palette[color_key],
            thickness=7,
        )

    style.configure(
        "Vertical.TScrollbar",
        background=palette["surface_alt"],
        troughcolor=palette["background"],
        bordercolor=palette["background"],
        arrowcolor=palette["muted"],
    )
    style.configure(
        "Horizontal.TScrollbar",
        background=palette["surface_alt"],
        troughcolor=palette["background"],
        bordercolor=palette["background"],
        arrowcolor=palette["muted"],
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
