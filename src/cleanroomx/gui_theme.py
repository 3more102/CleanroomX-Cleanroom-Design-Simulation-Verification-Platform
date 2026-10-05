from __future__ import annotations

from copy import deepcopy
from typing import Any

import tkinter as tk
from tkinter import ttk


_THEME_PALETTES: dict[str, dict[str, str]] = {
    "light": {
        "background": "#E8EEF5",
        "surface": "#F4F7FA",
        "surface_alt": "#EAF0F6",
        "panel": "#FFFFFF",
        "elevated": "#F8FAFC",
        "text": "#172033",
        "muted": "#66758A",
        "disabled": "#94A3B8",
        "border": "#C4D0DE",
        "strong_border": "#8EA2BA",
        "accent": "#0284C7",
        "accent_hover": "#0369A1",
        "accent_text": "#FFFFFF",
        "selection": "#BAE6FD",
        "selection_text": "#0C4A6E",
        "field": "#FFFFFF",
        "field_text": "#172033",
        "tree": "#FBFDFF",
        "canvas_2d": "#F3F7FB",
        "canvas_3d": "#101827",
        "plot": "#F8FAFC",
        "grid": "#D5DFEA",
        "success": "#15803D",
        "warning": "#D97706",
        "error": "#DC2626",
        "running": "#0284C7",
        "unknown": "#64748B",
        "stale": "#EA580C",
        "verified": "#059669",
        "unverified": "#7C3AED",
        "geometry": "#0891B2",
        "hvac": "#2563EB",
        "airflow": "#0891B2",
        "pressure": "#7C3AED",
        "electrical": "#CA8A04",
        "utilities": "#EA580C",
        "safety": "#DC2626",
        "evidence": "#16A34A",
        "verification": "#059669",
        "simulation": "#7C3AED",
    },
    "dark": {
        "background": "#0B1220",
        "surface": "#111B2E",
        "surface_alt": "#142034",
        "panel": "#17243A",
        "elevated": "#1D2C45",
        "text": "#F1F5F9",
        "muted": "#94A3B8",
        "disabled": "#64748B",
        "border": "#263750",
        "strong_border": "#334A68",
        "accent": "#22D3EE",
        "accent_hover": "#38BDF8",
        "accent_text": "#07111E",
        "selection": "#164E63",
        "selection_text": "#ECFEFF",
        "field": "#0F192A",
        "field_text": "#F1F5F9",
        "tree": "#101A2B",
        "canvas_2d": "#0D1726",
        "canvas_3d": "#08101C",
        "plot": "#0D1726",
        "grid": "#223149",
        "success": "#22C55E",
        "warning": "#F59E0B",
        "error": "#EF4444",
        "running": "#38BDF8",
        "unknown": "#94A3B8",
        "stale": "#F97316",
        "verified": "#22C55E",
        "unverified": "#A78BFA",
        "geometry": "#22D3EE",
        "hvac": "#38BDF8",
        "airflow": "#2DD4BF",
        "pressure": "#A78BFA",
        "electrical": "#FACC15",
        "utilities": "#F97316",
        "safety": "#EF4444",
        "evidence": "#22C55E",
        "verification": "#34D399",
        "simulation": "#A78BFA",
    },
}


def normalize_theme_name(value: Any) -> str:
    name = str(value or "").strip().lower()
    return name if name in _THEME_PALETTES else "dark"


def theme_palette(value: Any) -> dict[str, str]:
    return deepcopy(_THEME_PALETTES[normalize_theme_name(value)])


def engineering_status_style(value: Any) -> str:
    """Return a consistent compact-badge ttk style for an engineering state."""
    key = str(value or "").strip().casefold().replace("_", " ").replace("-", " ")
    if key in {"pass", "passed", "ok", "healthy", "valid"}:
        return "CX.Badge.Pass.TLabel"
    if key in {"fail", "failed", "error", "critical", "invalid"}:
        return "CX.Badge.Fail.TLabel"
    if key in {"warning", "warn"}:
        return "CX.Badge.Warning.TLabel"
    if key in {"running", "busy", "working", "in progress"}:
        return "CX.Badge.Running.TLabel"
    if key in {"verified", "current"}:
        return "CX.Badge.Verified.TLabel"
    if key in {"stale"}:
        return "CX.Badge.Stale.TLabel"
    if key in {"unverified", "not verified", "incomplete", "not checked"}:
        return "CX.Badge.Unverified.TLabel"
    return "CX.Badge.Unknown.TLabel"


def _configure_badge(
    style: ttk.Style,
    name: str,
    *,
    foreground: str,
    background: str,
    border: str,
) -> None:
    style.configure(
        name,
        background=background,
        foreground=foreground,
        bordercolor=border,
        lightcolor=border,
        darkcolor=border,
        relief="solid",
        padding=(6, 2),
        font=("TkDefaultFont", 8, "bold"),
        anchor="center",
    )


def configure_ttk_theme(root: tk.Misc, value: Any) -> dict[str, str]:
    """Apply the CleanroomX industrial presentation system without model side effects."""
    palette = theme_palette(value)
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    root.configure(background=palette["background"])

    style.configure(
        ".",
        background=palette["background"],
        foreground=palette["text"],
        troughcolor=palette["surface_alt"],
        bordercolor=palette["border"],
        lightcolor=palette["border"],
        darkcolor=palette["border"],
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
        relief="solid",
    )
    style.configure(
        "TLabelframe.Label",
        background=palette["background"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 8, "bold"),
    )
    style.configure(
        "TButton",
        background=palette["surface_alt"],
        foreground=palette["text"],
        bordercolor=palette["border"],
        lightcolor=palette["border"],
        darkcolor=palette["border"],
        padding=(8, 4),
        relief="solid",
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
            ("active", palette["strong_border"]),
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
        padding=(5, 3),
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
        tabmargins=(0, 2, 0, 0),
    )
    style.configure(
        "TNotebook.Tab",
        background=palette["surface_alt"],
        foreground=palette["muted"],
        padding=(10, 5),
        bordercolor=palette["border"],
        font=("TkDefaultFont", 8, "bold"),
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
    )
    style.configure(
        "Treeview",
        background=palette["tree"],
        fieldbackground=palette["tree"],
        foreground=palette["text"],
        bordercolor=palette["border"],
        rowheight=23,
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
        foreground=palette["muted"],
        bordercolor=palette["border"],
        font=("TkDefaultFont", 8, "bold"),
        padding=(6, 4),
        relief="flat",
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
        padding=(7, 4),
    )
    style.map(
        "TMenubutton",
        background=[("active", palette["elevated"])],
        foreground=[("disabled", palette["disabled"])],
        bordercolor=[("focus", palette["accent"])],
    )

    style.configure(
        "CX.AppBar.TFrame",
        background=palette["surface"],
        bordercolor=palette["strong_border"],
        relief="solid",
    )
    style.configure(
        "CX.Toolbar.TFrame",
        background=palette["surface_alt"],
        bordercolor=palette["border"],
        relief="solid",
    )
    style.configure(
        "CX.Panel.TFrame",
        background=palette["panel"],
        bordercolor=palette["border"],
        relief="solid",
    )
    style.configure(
        "CX.PanelHeader.TFrame",
        background=palette["surface_alt"],
        bordercolor=palette["border"],
        relief="solid",
        padding=(7, 4),
    )
    style.configure(
        "CX.StatusBar.TFrame",
        background=palette["surface"],
        bordercolor=palette["strong_border"],
        relief="solid",
    )
    style.configure(
        "CX.Brand.TLabel",
        background=palette["surface"],
        foreground=palette["accent"],
        font=("TkDefaultFont", 14, "bold"),
    )
    style.configure(
        "CX.ProductMeta.TLabel",
        background=palette["surface"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 8),
    )
    style.configure(
        "CX.Section.TLabel",
        background=palette["background"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 8, "bold"),
    )
    style.configure(
        "CX.PanelHeader.TLabel",
        background=palette["surface_alt"],
        foreground=palette["text"],
        font=("TkDefaultFont", 8, "bold"),
    )
    style.configure(
        "CX.ViewTitle.TLabel",
        background=palette["background"],
        foreground=palette["text"],
        font=("TkDefaultFont", 9, "bold"),
    )
    style.configure(
        "CX.Muted.TLabel",
        background=palette["background"],
        foreground=palette["muted"],
    )
    style.configure(
        "CX.Panel.TLabel",
        background=palette["panel"],
        foreground=palette["text"],
    )
    style.configure(
        "CX.PanelMuted.TLabel",
        background=palette["panel"],
        foreground=palette["muted"],
    )
    style.configure(
        "CX.PanelSection.TLabel",
        background=palette["panel"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 8, "bold"),
    )
    style.configure(
        "CX.PanelTitle.TLabel",
        background=palette["panel"],
        foreground=palette["text"],
        font=("TkDefaultFont", 9, "bold"),
    )
    style.configure(
        "CX.Status.TLabel",
        background=palette["surface"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 8),
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
        padding=(11, 5),
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
        background=palette["surface_alt"],
        foreground=palette["error"],
        bordercolor=palette["error"],
        padding=(8, 4),
    )
    style.map(
        "CX.Danger.TButton",
        background=[("active", palette["elevated"]), ("pressed", palette["selection"])],
        foreground=[("disabled", palette["disabled"])],
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
        bordercolor=[("focus", palette["accent"]), ("active", palette["strong_border"])],
    )
    style.configure(
        "CX.ToolActive.TButton",
        background=palette["selection"],
        foreground=palette["selection_text"],
        bordercolor=palette["accent"],
        padding=(6, 3),
    )
    style.configure(
        "CX.Nav.TButton",
        background=palette["surface"],
        foreground=palette["muted"],
        bordercolor=palette["surface"],
        padding=(8, 5),
        anchor="w",
        font=("TkDefaultFont", 8, "bold"),
    )
    style.map(
        "CX.Nav.TButton",
        background=[
            ("active", palette["elevated"]),
            ("pressed", palette["selection"]),
        ],
        foreground=[
            ("active", palette["text"]),
            ("pressed", palette["selection_text"]),
        ],
        bordercolor=[
            ("focus", palette["accent"]),
            ("active", palette["strong_border"]),
        ],
    )
    style.configure(
        "CX.NavActive.TButton",
        background=palette["selection"],
        foreground=palette["selection_text"],
        bordercolor=palette["accent"],
        padding=(8, 5),
        anchor="w",
        font=("TkDefaultFont", 8, "bold"),
    )
    style.map(
        "CX.NavActive.TButton",
        background=[
            ("active", palette["selection"]),
            ("pressed", palette["selection"]),
        ],
        foreground=[("!disabled", palette["selection_text"])],
        bordercolor=[("focus", palette["accent"])],
    )
    style.configure(
        "CX.Engineering.Horizontal.TProgressbar",
        troughcolor=palette["surface_alt"],
        background=palette["accent"],
        bordercolor=palette["border"],
        lightcolor=palette["accent"],
        darkcolor=palette["accent"],
        thickness=7,
    )
    style.configure(
        "CX.Card.TLabelframe",
        background=palette["panel"],
        bordercolor=palette["border"],
        lightcolor=palette["border"],
        darkcolor=palette["border"],
        relief="solid",
    )
    style.configure(
        "CX.Card.TLabelframe.Label",
        background=palette["panel"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 8, "bold"),
    )

    badge_specs = {
        "Pass": ("#ECFDF5", palette["success"]),
        "Fail": ("#FEF2F2", palette["error"]),
        "Warning": ("#FFFBEB", palette["warning"]),
        "Running": ("#ECFEFF", palette["running"]),
        "Verified": ("#ECFDF5", palette["verified"]),
        "Stale": ("#FFF7ED", palette["stale"]),
        "Unverified": ("#F5F3FF", palette["unverified"]),
        "Unknown": ("#F1F5F9", palette["unknown"]),
    }
    if normalize_theme_name(value) == "dark":
        badge_specs = {
            "Pass": ("#10351F", palette["success"]),
            "Fail": ("#3B171C", palette["error"]),
            "Warning": ("#3A2A0E", palette["warning"]),
            "Running": ("#0D3240", palette["running"]),
            "Verified": ("#10351F", palette["verified"]),
            "Stale": ("#3A210F", palette["stale"]),
            "Unverified": ("#2D2147", palette["unverified"]),
            "Unknown": ("#233047", palette["unknown"]),
        }
    for suffix, (background, foreground) in badge_specs.items():
        _configure_badge(
            style,
            f"CX.Badge.{suffix}.TLabel",
            foreground=foreground,
            background=background,
            border=foreground,
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
