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
        "raised": "#ffffff",
        "elevated": "#f5f8fb",
        "text": "#18212b",
        "text_secondary": "#344454",
        "muted": "#5f6b78",
        "disabled": "#9aa5b1",
        "border": "#c8d1dc",
        "divider_strong": "#9fb0c2",
        "accent": "#0b6aa8",
        "accent_hover": "#095786",
        "accent_text": "#ffffff",
        "selection": "#cfe8ff",
        "selection_text": "#102a43",
        "field": "#ffffff",
        "field_text": "#18212b",
        "tree": "#fbfcfd",
        "canvas_2d": "#f7f9fb",
        "canvas_3d": "#111820",
        "plot": "#ffffff",
        "grid": "#d7dee7",
        "info": "#0b6aa8",
        "success": "#15803d",
        "healthy": "#65a30d",
        "warning": "#b45309",
        "attention": "#c2410c",
        "error": "#b91c1c",
        "simulation": "#7c3aed",
        "special": "#a21caf",
        "geometry": "#0891b2",
        "hvac": "#2563eb",
        "airflow": "#0891b2",
        "pressure": "#7c3aed",
        "electrical": "#ca8a04",
        "utilities": "#ea580c",
        "evidence": "#15803d",
        "verification": "#059669",
    },
    "dark": {
        "background": "#0B1220",
        "surface": "#111B2E",
        "surface_alt": "#142034",
        "panel": "#17243A",
        "raised": "#17243A",
        "elevated": "#1D2C45",
        "text": "#F1F5F9",
        "text_secondary": "#CBD5E1",
        "muted": "#94A3B8",
        "disabled": "#64748B",
        "border": "#263750",
        "divider_strong": "#334A68",
        "accent": "#22D3EE",
        "accent_hover": "#38BDF8",
        "accent_text": "#07131F",
        "selection": "#164E63",
        "selection_text": "#ECFEFF",
        "field": "#0E1726",
        "field_text": "#F1F5F9",
        "tree": "#0D1727",
        "canvas_2d": "#0C1626",
        "canvas_3d": "#08111F",
        "plot": "#0C1626",
        "grid": "#223550",
        "info": "#38BDF8",
        "success": "#22C55E",
        "healthy": "#84CC16",
        "warning": "#F59E0B",
        "attention": "#F97316",
        "error": "#EF4444",
        "simulation": "#A78BFA",
        "special": "#E879F9",
        "geometry": "#22D3EE",
        "hvac": "#38BDF8",
        "airflow": "#2DD4BF",
        "pressure": "#A78BFA",
        "electrical": "#FACC15",
        "utilities": "#F97316",
        "evidence": "#22C55E",
        "verification": "#34D399",
    },
}


_STATUS_STYLE_KEYS = {
    "PASS": "success",
    "VERIFIED": "verification",
    "HEALTHY": "healthy",
    "FAIL": "error",
    "ERROR": "error",
    "CRITICAL": "error",
    "WARNING": "warning",
    "WARN": "warning",
    "RUNNING": "info",
    "INFO": "info",
    "STALE": "attention",
    "UNVERIFIED": "simulation",
    "UNKNOWN": "muted",
    "NOT CHECKED": "muted",
    "INCOMPLETE": "warning",
}


def normalize_theme_name(value: Any) -> str:
    name = str(value or "").strip().lower()
    return name if name in _THEME_PALETTES else "light"


def theme_palette(value: Any) -> dict[str, str]:
    return deepcopy(_THEME_PALETTES[normalize_theme_name(value)])


def status_style_name(status: Any) -> str:
    """Return the shared ttk label style for an engineering status."""
    normalized = str(status or "").strip().upper().replace("_", " ")
    key = _STATUS_STYLE_KEYS.get(normalized, "muted")
    return {
        "success": "CX.Pass.TLabel",
        "verification": "CX.Verified.TLabel",
        "healthy": "CX.Healthy.TLabel",
        "error": "CX.Error.TLabel",
        "warning": "CX.Warning.TLabel",
        "info": "CX.Info.TLabel",
        "attention": "CX.Stale.TLabel",
        "simulation": "CX.Simulation.TLabel",
        "muted": "CX.MutedBadge.TLabel",
    }[key]


def configure_ttk_theme(root: tk.Misc, value: Any) -> dict[str, str]:
    """Apply the CleanroomX industrial presentation palette without model side effects."""
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
    style.configure("TLabel", background=palette["background"], foreground=palette["text"])
    style.configure(
        "TLabelframe",
        background=palette["background"],
        foreground=palette["text"],
        bordercolor=palette["border"],
        lightcolor=palette["border"],
        darkcolor=palette["border"],
        relief="solid",
    )
    style.configure(
        "TLabelframe.Label",
        background=palette["background"],
        foreground=palette["text_secondary"],
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
            ("active", palette["elevated"]),
            ("pressed", palette["selection"]),
            ("disabled", palette["surface_alt"]),
        ],
        foreground=[
            ("disabled", palette["disabled"]),
            ("!disabled", palette["text"]),
        ],
        bordercolor=[
            ("focus", palette["accent"]),
            ("active", palette["divider_strong"]),
        ],
    )
    style.configure("TCheckbutton", background=palette["background"], foreground=palette["text"])
    style.map(
        "TCheckbutton",
        background=[("active", palette["background"])],
        foreground=[("disabled", palette["disabled"])],
    )
    style.configure("TRadiobutton", background=palette["background"], foreground=palette["text"])
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
        padding=(5, 4),
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
        font=("TkDefaultFont", 9),
    )
    style.map(
        "TNotebook.Tab",
        background=[
            ("selected", palette["panel"]),
            ("active", palette["elevated"]),
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
        foreground=palette["text_secondary"],
        bordercolor=palette["border"],
        font=("TkDefaultFont", 9, "bold"),
        padding=(6, 5),
        relief="flat",
    )
    style.map(
        "Treeview.Heading",
        background=[("active", palette["elevated"])],
        foreground=[("active", palette["text"])],
    )
    style.configure("TPanedwindow", background=palette["border"])
    style.configure("TSeparator", background=palette["border"])
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
        background=[("active", palette["elevated"])],
        foreground=[("disabled", palette["disabled"])],
    )

    style.configure(
        "CX.Topbar.TFrame",
        background=palette["surface"],
        padding=(8, 5),
    )
    style.configure(
        "CX.Brand.TLabel",
        background=palette["background"],
        foreground=palette["accent"],
        font=("TkDefaultFont", 15, "bold"),
    )
    style.configure(
        "CX.TopbarBrand.TLabel",
        background=palette["surface"],
        foreground=palette["accent"],
        font=("TkDefaultFont", 15, "bold"),
    )
    style.configure(
        "CX.ProductSub.TLabel",
        background=palette["surface"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 8, "bold"),
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
        font=("TkDefaultFont", 10, "bold"),
    )
    style.configure(
        "CX.Panel.TFrame",
        background=palette["panel"],
    )
    style.configure(
        "CX.Panel.TLabel",
        background=palette["panel"],
        foreground=palette["text_secondary"],
    )
    style.configure(
        "CX.PanelTitle.TLabel",
        background=palette["panel"],
        foreground=palette["text"],
        font=("TkDefaultFont", 10, "bold"),
    )
    style.configure(
        "CX.Metric.TLabel",
        background=palette["panel"],
        foreground=palette["accent"],
        font=("TkDefaultFont", 13, "bold"),
    )
    style.configure(
        "CX.Raised.TFrame",
        background=palette["raised"],
    )
    style.configure(
        "CX.Navigator.Treeview",
        background=palette["tree"],
        fieldbackground=palette["tree"],
        foreground=palette["text"],
        rowheight=25,
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
        background=palette["error"],
        foreground="#ffffff",
        bordercolor=palette["error"],
        padding=(9, 5),
    )
    style.map(
        "CX.Danger.TButton",
        background=[("active", palette["attention"]), ("pressed", palette["error"])],
        foreground=[("disabled", palette["disabled"])],
    )
    style.configure(
        "CX.Toolbar.TFrame",
        background=palette["surface"],
        padding=(4, 3),
    )
    style.configure(
        "CX.ToolbarLabel.TLabel",
        background=palette["surface"],
        foreground=palette["text_secondary"],
        font=("TkDefaultFont", 8, "bold"),
    )
    style.configure(
        "CX.PanelHeader.TFrame",
        background=palette["surface_alt"],
        padding=(7, 5),
    )
    style.configure(
        "CX.PanelHeader.TLabel",
        background=palette["surface_alt"],
        foreground=palette["text_secondary"],
        font=("TkDefaultFont", 8, "bold"),
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
            ("active", palette["elevated"]),
            ("pressed", palette["selection"]),
            ("disabled", palette["surface_alt"]),
        ],
        foreground=[("disabled", palette["disabled"])],
        bordercolor=[("focus", palette["accent"]), ("active", palette["divider_strong"])],
    )
    style.configure(
        "CX.StatusBar.TFrame",
        background=palette["surface"],
        padding=(7, 3),
    )
    style.configure(
        "CX.StatusBar.TLabel",
        background=palette["surface"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 8),
    )
    style.configure(
        "CX.Project.TLabel",
        background=palette["surface"],
        foreground=palette["text"],
        font=("TkDefaultFont", 9, "bold"),
        padding=(6, 3),
    )

    badge_specs = {
        "CX.Pass.TLabel": palette["success"],
        "CX.Verified.TLabel": palette["verification"],
        "CX.Healthy.TLabel": palette["healthy"],
        "CX.Error.TLabel": palette["error"],
        "CX.Warning.TLabel": palette["warning"],
        "CX.Info.TLabel": palette["info"],
        "CX.Stale.TLabel": palette["attention"],
        "CX.Simulation.TLabel": palette["simulation"],
        "CX.MutedBadge.TLabel": palette["divider_strong"],
    }
    for style_name, background in badge_specs.items():
        foreground = "#07131F" if style_name not in {"CX.Error.TLabel", "CX.Simulation.TLabel", "CX.MutedBadge.TLabel"} else "#ffffff"
        style.configure(
            style_name,
            background=background,
            foreground=foreground,
            padding=(6, 2),
            font=("TkDefaultFont", 8, "bold"),
            relief="flat",
        )

    domain_specs = {
        "CX.Geometry.TLabel": palette["geometry"],
        "CX.HVAC.TLabel": palette["hvac"],
        "CX.Airflow.TLabel": palette["airflow"],
        "CX.Pressure.TLabel": palette["pressure"],
        "CX.Electrical.TLabel": palette["electrical"],
        "CX.Utilities.TLabel": palette["utilities"],
        "CX.Evidence.TLabel": palette["evidence"],
        "CX.Verification.TLabel": palette["verification"],
        "CX.SimulationDomain.TLabel": palette["simulation"],
    }
    for style_name, foreground in domain_specs.items():
        style.configure(
            style_name,
            background=palette["background"],
            foreground=foreground,
            font=("TkDefaultFont", 8, "bold"),
        )

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
