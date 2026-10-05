from __future__ import annotations

import math
from typing import Any

import tkinter as tk
from tkinter import ttk

from .gui_theme import status_style_name


def format_engineering_number(
    value: Any,
    *,
    precision: int = 1,
    signed: bool = False,
    fallback: str = "—",
) -> str:
    """Format finite engineering scalars without leaking machine precision."""
    if isinstance(value, bool):
        return fallback
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(number):
        return fallback

    digits = max(0, min(int(precision), 6))
    sign = "+" if signed else ""
    return f"{number:{sign},.{digits}f}"


def format_engineering_measurement(
    value: Any,
    unit: str,
    *,
    precision: int = 1,
    signed: bool = False,
    fallback: str = "—",
) -> str:
    """Render an engineering measurement with consistent units and spacing."""
    rendered = format_engineering_number(
        value,
        precision=precision,
        signed=signed,
        fallback=fallback,
    )
    if rendered == fallback:
        return fallback
    normalized_unit = str(unit or "").strip()
    if not normalized_unit:
        return rendered
    separator = "" if normalized_unit in {"%", "°"} else " "
    return f"{rendered}{separator}{normalized_unit}"


def canonical_status_text(value: Any, *, fallback: str = "NOT CHECKED") -> str:
    """Normalize engineering state text while preserving explicit semantics."""
    token = str(value or "").strip().replace("-", "_").replace(" ", "_").lower()
    aliases = {
        "ok": "PASS",
        "passed": "PASS",
        "pass": "PASS",
        "success": "PASS",
        "valid": "PASS",
        "verified": "VERIFIED",
        "fail": "FAIL",
        "failed": "FAIL",
        "error": "FAIL",
        "invalid": "FAIL",
        "warning": "WARNING",
        "warn": "WARNING",
        "running": "RUNNING",
        "queued": "RUNNING",
        "calculating": "RUNNING",
        "stale": "STALE",
        "unknown": "UNKNOWN",
        "unverified": "UNVERIFIED",
        "incomplete": "INCOMPLETE",
        "not_checked": "NOT CHECKED",
        "unchecked": "NOT CHECKED",
        "": fallback,
    }
    if token in aliases:
        return aliases[token]
    return token.replace("_", " ").upper()


class EngineeringMetricRow(ttk.Frame):
    """Dense reusable label/value row for inspector-style engineering panels."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        label: str,
        value_var: tk.Variable,
        unit: str = "",
        status: bool = False,
    ) -> None:
        super().__init__(master, style="CX.MetricRow.TFrame", padding=(0, 1))
        self.value_var = value_var
        self._status_enabled = bool(status)

        ttk.Label(
            self,
            text=label,
            style="CX.MetricLabel.TLabel",
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        self.value_label = ttk.Label(
            self,
            textvariable=value_var,
            style="CX.MetricValue.TLabel",
            anchor="e",
        )
        self.value_label.grid(row=0, column=1, sticky="e", padx=(8, 0))

        if unit:
            ttk.Label(
                self,
                text=unit,
                style="CX.MetricUnit.TLabel",
                anchor="w",
            ).grid(row=0, column=2, sticky="w", padx=(4, 0))

        self.columnconfigure(0, weight=1)

    def set_status(self, value: Any) -> None:
        if self._status_enabled:
            self.value_label.configure(style=status_style_name(value))
