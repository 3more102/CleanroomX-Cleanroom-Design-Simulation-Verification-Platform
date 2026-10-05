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
        "accent_text": "#07111F",
        "selection": "#153B5B",
        "selection_text": "#F1F5F9",
        "field": "#0F1A2B",
        "field_text": "#F1F5F9",
        "tree": "#0F1A2B",
        "disabled": "#64748B",
        "canvas_2d": "#0D1728",
        "canvas_3d": "#08101D",
        "plot": "#0D1728",
        "grid": "#263750",
    },
}


_STATUS_TOKENS: dict[str, tuple[str, str, str]] = {
    "pass": ("#123224", "#BBF7D0", "#22C55E"),
    "verified": ("#10352F", "#A7F3D0", "#10B981"),
    "fail": ("#3B171B", "#FECACA", "#EF4444"),
    "warning": ("#3B2B12", "#FDE68A", "#F59E0B"),
    "running": ("#103449", "#BAE6FD", "#38BDF8"),
    "stale": ("#3A2514", "#FED7AA", "#F97316"),
    "unverified": ("#2A2443", "#DDD6FE", "#A78BFA"),
    "unknown": ("#202A3A", "#CBD5E1", "#64748B"),
    "not_checked": ("#202A3A", "#CBD5E1", "#64748B"),
    "incomplete": ("#2A2443", "#DDD6FE", "#A78BFA"),
}

_DOMAIN_TOKENS: dict[str, str] = {
    "geometry": "#22D3EE",
    "bim": "#38BDF8",
    "ifc": "#38BDF8",
    "hvac": "#2563EB",
    "airflow": "#22D3EE",
    "pressure": "#A78BFA",
    "contamination": "#E879F9",
    "electrical": "#F59E0B",
    "utilities": "#F97316",
    "safety": "#EF4444",
    "evidence": "#22C55E",
    "verification": "#10B981",
    "simulation": "#A78BFA",
    "requirements": "#38BDF8",
}


def canonical_status(value: Any) -> str:
    raw = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "ok": "pass",
        "success": "pass",
        "passed": "pass",
        "valid": "pass",
        "ready": "pass",
        "error": "fail",
        "failed": "fail",
        "critical": "fail",
        "warn": "warning",
        "active": "running",
        "pending": "running",
        "unchecked": "not_checked",
        "notchecked": "not_checked",
    }
    normalized = aliases.get(raw, raw)
    return normalized if normalized in _STATUS_TOKENS else "unknown"


def status_tokens(value: Any, theme: Any = "dark") -> dict[str, str]:
    """Return stable semantic colors for compact engineering state indicators."""
    status = canonical_status(value)
    background, foreground, accent = _STATUS_TOKENS[status]
    if normalize_theme_name(theme) == "light":
        light_background = {
            "pass": "#DCFCE7",
            "verified": "#D1FAE5",
            "fail": "#FEE2E2",
            "warning": "#FEF3C7",
            "running": "#E0F2FE",
            "stale": "#FFEDD5",
            "unverified": "#EDE9FE",
            "unknown": "#E2E8F0",
            "not_checked": "#E2E8F0",
            "incomplete": "#EDE9FE",
        }[status]
        foreground = {
            "pass": "#166534",
            "verified": "#065F46",
            "fail": "#991B1B",
            "warning": "#92400E",
            "running": "#075985",
            "stale": "#9A3412",
            "unverified": "#5B21B6",
            "unknown": "#475569",
            "not_checked": "#475569",
            "incomplete": "#5B21B6",
        }[status]
        background = light_background
    return {
        "status": status,
        "background": background,
        "foreground": foreground,
        "accent": accent,
    }


def domain_accent(value: Any) -> str:
    key = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    return _DOMAIN_TOKENS.get(key, "#38BDF8")


def format_engineering_value(
    value: Any,
    unit: str = "",
    *,
    precision: int | None = None,
    signed: bool = False,
) -> str:
    """Format finite engineering values compactly without changing model data."""
    if isinstance(value, bool):
        return str(value)
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        text = str(value if value is not None else "—")
        return f"{text} {unit}".strip()
    if number != number or number in (float("inf"), float("-inf")):
        return "—"
    if precision is None:
        magnitude = abs(number)
        precision = 0 if magnitude >= 100 else 1 if magnitude >= 10 else 2
    prefix = "+" if signed and number > 0 else ""
    text = f"{prefix}{number:,.{precision}f}"
    return f"{text} {unit}".strip()


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
        rowheight=24,
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
    style.configure(
        "CX.Topbar.TFrame",
        background=palette["surface"],
        padding=(10, 6),
    )
    style.configure(
        "CX.Topbar.Brand.TLabel",
        background=palette["surface"],
        foreground=palette["accent"],
        font=("TkDefaultFont", 14, "bold"),
    )
    style.configure(
        "CX.Topbar.Meta.TLabel",
        background=palette["surface"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 8),
    )
    style.configure(
        "CX.Muted.TLabel",
        foreground=palette["muted"],
    )
    style.configure(
        "CX.Card.TFrame",
        background=palette["panel"],
        bordercolor=palette["border"],
        relief="solid",
        borderwidth=1,
        padding=(10, 8),
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
        font=("TkDefaultFont", 13, "bold"),
    )
    style.configure(
        "CX.Sidebar.TFrame",
        background=palette["surface"],
    )
    style.configure(
        "CX.Sidebar.Section.TLabel",
        background=palette["surface"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 8, "bold"),
    )
    style.configure(
        "CX.Danger.TButton",
        background="#7F1D1D" if normalize_theme_name(value) == "dark" else "#FEE2E2",
        foreground="#FEE2E2" if normalize_theme_name(value) == "dark" else "#991B1B",
        bordercolor="#EF4444",
        padding=(8, 5),
    )
    style.map(
        "CX.Danger.TButton",
        background=[("active", "#991B1B"), ("pressed", "#7F1D1D")],
        foreground=[("disabled", palette["disabled"])],
    )
    for status_name in _STATUS_TOKENS:
        tokens = status_tokens(status_name, value)
        style.configure(
            f"CX.Status.{status_name}.TLabel",
            background=tokens["background"],
            foreground=tokens["foreground"],
            bordercolor=tokens["accent"],
            relief="solid",
            borderwidth=1,
            padding=(6, 2),
            font=("TkDefaultFont", 8, "bold"),
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
