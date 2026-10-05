from __future__ import annotations

from copy import deepcopy
from typing import Any

import tkinter as tk
from tkinter import ttk


_THEME_PALETTES: dict[str, dict[str, str]] = {
    "light": {
        "background": "#E9EEF5",
        "surface": "#F4F7FA",
        "surface_alt": "#E8EEF5",
        "surface_elevated": "#FFFFFF",
        "panel": "#FFFFFF",
        "navigation": "#F7F9FC",
        "text": "#172033",
        "secondary_text": "#334155",
        "muted": "#64748B",
        "disabled": "#94A3B8",
        "border": "#C9D5E3",
        "border_strong": "#9FB2C8",
        "accent": "#0891B2",
        "accent_hover": "#0E7490",
        "accent_text": "#FFFFFF",
        "selection": "#CFFAFE",
        "selection_text": "#0C4A6E",
        "field": "#FFFFFF",
        "field_text": "#172033",
        "tree": "#FBFDFF",
        "canvas_2d": "#F8FAFC",
        "canvas_3d": "#182333",
        "plot": "#FFFFFF",
        "grid": "#D8E1EC",
        "success": "#15803D",
        "success_surface": "#DCFCE7",
        "warning": "#B45309",
        "warning_surface": "#FEF3C7",
        "error": "#DC2626",
        "error_surface": "#FEE2E2",
        "info": "#0284C7",
        "requirement": "#2563EB",
        "info_surface": "#E0F2FE",
        "simulation": "#7C3AED",
        "evidence": "#16A34A",
        "attention": "#EA580C",
        "magenta": "#C026D3",
    },
    "dark": {
        "background": "#0B1220",
        "surface": "#111B2E",
        "surface_alt": "#142034",
        "surface_elevated": "#1D2C45",
        "panel": "#17243A",
        "navigation": "#111B2E",
        "text": "#F1F5F9",
        "secondary_text": "#CBD5E1",
        "muted": "#94A3B8",
        "disabled": "#64748B",
        "border": "#263750",
        "border_strong": "#334A68",
        "accent": "#22D3EE",
        "accent_hover": "#38BDF8",
        "accent_text": "#082F49",
        "selection": "#164E63",
        "selection_text": "#ECFEFF",
        "field": "#0F1A2B",
        "field_text": "#F1F5F9",
        "tree": "#101B2D",
        "canvas_2d": "#0E1828",
        "canvas_3d": "#09111E",
        "plot": "#101A2A",
        "grid": "#263750",
        "success": "#22C55E",
        "success_surface": "#123524",
        "warning": "#F59E0B",
        "warning_surface": "#3B2A10",
        "error": "#EF4444",
        "error_surface": "#3B171C",
        "info": "#38BDF8",
        "requirement": "#2563EB",
        "info_surface": "#102D42",
        "simulation": "#A78BFA",
        "evidence": "#22C55E",
        "attention": "#F97316",
        "magenta": "#E879F9",
    },
}


def normalize_theme_name(value: Any) -> str:
    name = str(value or "").strip().lower()
    return name if name in _THEME_PALETTES else "light"


def theme_palette(value: Any) -> dict[str, str]:
    return deepcopy(_THEME_PALETTES[normalize_theme_name(value)])


def status_style_name(value: Any) -> str:
    """Return the canonical semantic badge style for an engineering state."""
    token = str(value or "").strip().lower().replace(" ", "_")
    if token in {"pass", "passed", "ok", "ready", "current", "healthy", "verified"}:
        return "CX.Status.Pass.TLabel"
    if token in {"fail", "failed", "error", "critical", "blocked"}:
        return "CX.Status.Fail.TLabel"
    if token in {"warning", "warn", "stale", "incomplete", "degraded", "attention"}:
        return "CX.Status.Warning.TLabel"
    if token in {"running", "simulation", "calculating", "queued"}:
        return "CX.Status.Simulation.TLabel"
    if token in {"info", "informational", "available"}:
        return "CX.Status.Info.TLabel"
    return "CX.Status.Neutral.TLabel"


class _Tooltip:
    """Small dependency-free workstation tooltip for compact engineering controls."""

    def __init__(self, widget: tk.Misc, text: str, *, delay_ms: int = 450) -> None:
        self.widget = widget
        self.text = str(text).strip()
        self.delay_ms = max(0, int(delay_ms))
        self._after_id: str | None = None
        self._window: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")
        widget.bind("<FocusOut>", self._hide, add="+")

    def _schedule(self, _event=None) -> None:
        self._cancel()
        if self.text:
            self._after_id = self.widget.after(self.delay_ms, self._show)

    def _cancel(self) -> None:
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _show(self) -> None:
        self._after_id = None
        if self._window is not None or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 7
        except tk.TclError:
            return
        window = tk.Toplevel(self.widget)
        self._window = window
        window.wm_overrideredirect(True)
        try:
            window.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        style = ttk.Style(self.widget)
        background = (
            style.lookup("CX.Panel.TFrame", "background")
            or style.lookup("TFrame", "background")
            or "#17243A"
        )
        foreground = style.lookup("TLabel", "foreground") or "#F1F5F9"
        label = tk.Label(
            window,
            text=self.text,
            justify="left",
            wraplength=340,
            background=background,
            foreground=foreground,
            relief="solid",
            borderwidth=1,
            padx=7,
            pady=4,
        )
        label.pack()
        window.wm_geometry(f"+{x}+{y}")

    def _hide(self, _event=None) -> None:
        self._cancel()
        if self._window is not None:
            try:
                self._window.destroy()
            except tk.TclError:
                pass
            self._window = None


def attach_tooltip(widget: tk.Misc, text: str, *, delay_ms: int = 450) -> None:
    """Attach a restrained tooltip while keeping widget APIs untouched."""
    tooltip = _Tooltip(widget, text, delay_ms=delay_ms)
    setattr(widget, "_cleanroomx_tooltip", tooltip)


def _configure_status_style(
    style: ttk.Style,
    name: str,
    *,
    foreground: str,
    background: str,
) -> None:
    style.configure(
        name,
        foreground=foreground,
        background=background,
        bordercolor=foreground,
        lightcolor=foreground,
        darkcolor=foreground,
        relief="flat",
        padding=(7, 2),
        font=("TkDefaultFont", 8, "bold"),
    )


def configure_ttk_theme(root: tk.Misc, value: Any) -> dict[str, str]:
    """Apply the CleanroomX workstation palette without engineering side effects."""
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
        font=("TkDefaultFont", 9),
    )
    style.configure("TFrame", background=palette["background"])
    style.configure("CX.App.TFrame", background=palette["background"])
    style.configure("CX.Topbar.TFrame", background=palette["surface"])
    style.configure("CX.Toolbar.TFrame", background=palette["surface"], padding=(4, 3))
    style.configure("CX.Statusbar.TFrame", background=palette["surface"], borderwidth=1, relief="solid")
    style.configure("CX.Statusbar.TLabel", background=palette["surface"], foreground=palette["secondary_text"], font=("TkDefaultFont", 8))
    style.configure("CX.StatusbarMuted.TLabel", background=palette["surface"], foreground=palette["muted"], font=("TkDefaultFont", 8))
    style.configure("CX.Navigator.TFrame", background=palette["navigation"])
    style.configure("CX.Panel.TFrame", background=palette["panel"])
    style.configure("CX.Surface.TFrame", background=palette["surface_alt"])
    style.configure("CX.Card.TFrame", background=palette["panel"])

    style.configure(
        "TLabel",
        background=palette["background"],
        foreground=palette["text"],
    )
    style.configure(
        "CX.Brand.TLabel",
        background=palette["surface"],
        foreground=palette["accent"],
        font=("TkDefaultFont", 15, "bold"),
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
        "CX.ViewTitle.TLabel",
        background=palette["background"],
        foreground=palette["text"],
        font=("TkDefaultFont", 11, "bold"),
    )
    style.configure(
        "CX.Secondary.TLabel",
        background=palette["background"],
        foreground=palette["secondary_text"],
    )
    style.configure(
        "CX.Muted.TLabel",
        background=palette["background"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 8),
    )
    style.configure(
        "CX.Topbar.TLabel",
        background=palette["surface"],
        foreground=palette["text"],
    )
    style.configure(
        "CX.TopbarMuted.TLabel",
        background=palette["surface"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 8),
    )
    style.configure(
        "CX.ToolbarSection.TLabel",
        background=palette["surface"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 8, "bold"),
    )
    style.configure(
        "CX.ToolbarMuted.TLabel",
        background=palette["surface"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 8),
    )

    # Surface-aware text styles prevent background seams inside dense
    # engineering cards/panels while keeping typography semantic and centralized.
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
        font=("TkDefaultFont", 11, "bold"),
    )
    style.configure(
        "CX.PanelSecondary.TLabel",
        background=palette["panel"],
        foreground=palette["secondary_text"],
    )
    style.configure(
        "CX.PanelMuted.TLabel",
        background=palette["panel"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 8),
    )
    style.configure(
        "CX.SurfaceSection.TLabel",
        background=palette["surface_alt"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 8, "bold"),
    )
    style.configure(
        "CX.SurfaceSecondary.TLabel",
        background=palette["surface_alt"],
        foreground=palette["secondary_text"],
    )
    style.configure(
        "CX.SurfaceMuted.TLabel",
        background=palette["surface_alt"],
        foreground=palette["muted"],
        font=("TkDefaultFont", 8),
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
        foreground=palette["secondary_text"],
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
            ("active", palette["surface_elevated"]),
            ("pressed", palette["selection"]),
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
    style.configure(
        "CX.Primary.TButton",
        background=palette["accent"],
        foreground=palette["accent_text"],
        bordercolor=palette["accent"],
        padding=(11, 5),
        font=("TkDefaultFont", 9, "bold"),
        relief="flat",
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
        "CX.Compact.TButton",
        background=palette["surface_alt"],
        foreground=palette["text"],
        bordercolor=palette["border"],
        padding=(6, 3),
        relief="flat",
    )
    style.map(
        "CX.Compact.TButton",
        background=[
            ("active", palette["surface_elevated"]),
            ("pressed", palette["selection"]),
            ("disabled", palette["surface_alt"]),
        ],
        foreground=[("disabled", palette["disabled"])],
        bordercolor=[("focus", palette["accent"]), ("active", palette["border_strong"])],
    )
    style.configure(
        "CX.Danger.TButton",
        background=palette["error_surface"],
        foreground=palette["error"],
        bordercolor=palette["error"],
        padding=(8, 4),
        relief="flat",
    )
    style.map(
        "CX.Danger.TButton",
        background=[("active", palette["surface_elevated"])],
        foreground=[("disabled", palette["disabled"])],
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

    for widget_style in ("TEntry", "TSpinbox"):
        style.configure(
            widget_style,
            fieldbackground=palette["field"],
            foreground=palette["field_text"],
            bordercolor=palette["border"],
            insertcolor=palette["text"],
            lightcolor=palette["border"],
            darkcolor=palette["border"],
            padding=(5, 4),
        )
        style.map(
            widget_style,
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
        arrowcolor=palette["secondary_text"],
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
        "TNotebook",
        background=palette["background"],
        bordercolor=palette["border"],
        tabmargins=(1, 2, 1, 0),
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
            ("active", palette["surface_elevated"]),
        ],
        foreground=[
            ("selected", palette["accent"]),
            ("active", palette["text"]),
        ],
        bordercolor=[
            ("selected", palette["accent"]),
            ("active", palette["border_strong"]),
        ],
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
        foreground=palette["secondary_text"],
        bordercolor=palette["border"],
        font=("TkDefaultFont", 8, "bold"),
        padding=(5, 5),
        relief="flat",
    )
    style.map(
        "Treeview.Heading",
        background=[("active", palette["surface_elevated"])],
        foreground=[("active", palette["text"])],
    )
    style.configure(
        "CX.Navigator.Treeview",
        background=palette["navigation"],
        fieldbackground=palette["navigation"],
        foreground=palette["secondary_text"],
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
        "TMenubutton",
        background=palette["surface_alt"],
        foreground=palette["text"],
        bordercolor=palette["border"],
        arrowcolor=palette["secondary_text"],
        padding=(7, 4),
        relief="flat",
    )
    style.map(
        "TMenubutton",
        background=[("active", palette["surface_elevated"])],
        foreground=[("disabled", palette["disabled"])],
    )
    style.configure(
        "TProgressbar",
        background=palette["accent"],
        troughcolor=palette["surface_alt"],
        bordercolor=palette["border"],
        lightcolor=palette["accent"],
        darkcolor=palette["accent"],
    )

    # Semantic progress variants keep project health, verification currency, and
    # solver activity visually consistent without encoding meaning in text alone.
    for progress_style, progress_color in (
        ("CX.Success.Horizontal.TProgressbar", palette["success"]),
        ("CX.Warning.Horizontal.TProgressbar", palette["warning"]),
        ("CX.Fail.Horizontal.TProgressbar", palette["error"]),
        ("CX.Simulation.Horizontal.TProgressbar", palette["simulation"]),
    ):
        style.configure(
            progress_style,
            background=progress_color,
            troughcolor=palette["surface_alt"],
            bordercolor=palette["border"],
            lightcolor=progress_color,
            darkcolor=progress_color,
        )

    style.configure(
        "CX.PanelHeader.TFrame",
        background=palette["surface_alt"],
        padding=(7, 5),
    )
    style.configure(
        "CX.PanelHeader.TLabel",
        background=palette["surface_alt"],
        foreground=palette["secondary_text"],
        font=("TkDefaultFont", 8, "bold"),
    )
    style.configure(
        "CX.SubtlePanel.TFrame",
        background=palette["surface_alt"],
        borderwidth=1,
        relief="solid",
    )

    _configure_status_style(
        style,
        "CX.Status.Pass.TLabel",
        foreground=palette["success"],
        background=palette["success_surface"],
    )
    _configure_status_style(
        style,
        "CX.Status.Fail.TLabel",
        foreground=palette["error"],
        background=palette["error_surface"],
    )
    _configure_status_style(
        style,
        "CX.Status.Warning.TLabel",
        foreground=palette["warning"],
        background=palette["warning_surface"],
    )
    _configure_status_style(
        style,
        "CX.Status.Info.TLabel",
        foreground=palette["info"],
        background=palette["info_surface"],
    )
    _configure_status_style(
        style,
        "CX.Status.Simulation.TLabel",
        foreground=palette["simulation"],
        background=palette["surface_alt"],
    )
    _configure_status_style(
        style,
        "CX.Status.Neutral.TLabel",
        foreground=palette["muted"],
        background=palette["surface_alt"],
    )

    # Defaults for Tk-native widgets created after this call.
    root.option_add("*Text.background", palette["field"])
    root.option_add("*Text.foreground", palette["field_text"])
    root.option_add("*Text.insertBackground", palette["text"])
    root.option_add("*Text.selectBackground", palette["selection"])
    root.option_add("*Text.selectForeground", palette["selection_text"])
    root.option_add("*Listbox.background", palette["tree"])
    root.option_add("*Listbox.foreground", palette["text"])
    root.option_add("*Listbox.selectBackground", palette["selection"])
    root.option_add("*Listbox.selectForeground", palette["selection_text"])
    root.option_add("*Menu.background", palette["surface"])
    root.option_add("*Menu.foreground", palette["text"])
    root.option_add("*Menu.activeBackground", palette["selection"])
    root.option_add("*Menu.activeForeground", palette["selection_text"])
    root.option_add("*Menu.disabledForeground", palette["disabled"])

    return palette
