from __future__ import annotations

import math
from typing import Any

import tkinter as tk
from tkinter import ttk

from .gui_theme import theme_palette


def _humanize(value: Any) -> str:
    text = str(value or "").replace("_", " ").replace(".", " / ").strip()
    return " ".join(part.capitalize() for part in text.split())


def _format_scalar(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "YES" if value else "NO"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        if not math.isfinite(value):
            return str(value)
        magnitude = abs(value)
        if magnitude >= 1000:
            return f"{value:,.2f}".rstrip("0").rstrip(".")
        if magnitude >= 1:
            return f"{value:.4f}".rstrip("0").rstrip(".")
        if magnitude == 0:
            return "0"
        return f"{value:.5g}"
    if isinstance(value, str):
        return value if len(value) <= 160 else value[:157] + "…"
    return str(value)


def _flatten_result(value: Any, *, limit: int = 120) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []

    def visit(node: Any, path: str, depth: int) -> None:
        if len(rows) >= limit:
            return
        if isinstance(node, dict):
            if depth > 4:
                rows.append((path or "Result", f"{len(node)} fields"))
                return
            if set(node).issuperset({"value", "unit"}) and not isinstance(
                node.get("value"), (dict, list, tuple)
            ):
                rendered = _format_scalar(node.get("value"))
                unit = str(node.get("unit") or "").strip()
                rows.append((path or "Result", f"{rendered} {unit}".strip()))
                return
            for key, child in node.items():
                child_path = f"{path}.{key}" if path else str(key)
                visit(child, child_path, depth + 1)
            return
        if isinstance(node, (list, tuple)):
            if not node:
                rows.append((path or "Result", "Empty collection"))
                return
            primitive = all(
                not isinstance(item, (dict, list, tuple)) for item in node
            )
            if primitive and len(node) <= 8:
                rows.append(
                    (
                        path or "Result",
                        ", ".join(_format_scalar(item) for item in node),
                    )
                )
            else:
                rows.append(
                    (
                        path or "Result",
                        f"{len(node)} item{'s' if len(node) != 1 else ''}",
                    )
                )
            return
        rows.append((path or "Result", _format_scalar(node)))

    visit(value, "", 0)
    return rows


class AnalysisResultPanel(ttk.Frame):
    """Structured, read-only presentation of the canonical analysis result."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, padding=(10, 8))
        self.title_var = tk.StringVar(value="No completed analysis")
        self.status_var = tk.StringVar(value="NOT RUN")
        self.summary_var = tk.StringVar(
            value="Run an analysis to populate calculated engineering results."
        )
        self.count_var = tk.StringVar(value="0 result fields")

        header = ttk.Frame(self, style="CX.PanelHeader.TFrame")
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(
            header,
            text="ANALYSIS RESULT",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        self.status_label = ttk.Label(
            header,
            textvariable=self.status_var,
            style="CX.Status.Neutral.TLabel",
        )
        self.status_label.pack(side="right")

        title_row = ttk.Frame(self)
        title_row.pack(fill="x", pady=(0, 8))
        ttk.Label(
            title_row,
            textvariable=self.title_var,
            style="CX.ViewTitle.TLabel",
        ).pack(side="left")
        ttk.Label(
            title_row,
            textvariable=self.count_var,
            style="CX.Muted.TLabel",
        ).pack(side="right")
        ttk.Label(
            self,
            textvariable=self.summary_var,
            style="CX.Muted.TLabel",
            wraplength=900,
            justify="left",
        ).pack(fill="x", pady=(0, 8))

        columns = ("field", "value")
        self.tree = ttk.Treeview(
            self,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("field", text="Calculated field")
        self.tree.heading("value", text="Value")
        self.tree.column("field", width=430, minwidth=180, stretch=True)
        self.tree.column("value", width=360, minwidth=160, stretch=True)
        yscroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")
        self.apply_theme("dark")

    def apply_theme(self, value: Any) -> None:
        palette = theme_palette(value)
        self.tree.tag_configure("row_even", background=palette["tree"])
        self.tree.tag_configure("row_odd", background=palette["surface_alt"])

    def clear(self) -> None:
        self.refresh(None)

    def refresh(self, run: Any | None) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

        if run is None:
            self.title_var.set("No completed analysis")
            self.status_var.set("NOT RUN")
            self.summary_var.set(
                "Run an analysis to populate calculated engineering results. "
                "Configured requirements and compliance verdicts remain separate."
            )
            self.count_var.set("0 result fields")
            self.status_label.configure(style="CX.Status.Neutral.TLabel")
            return

        title = str(getattr(run, "title", None) or "Analysis result")
        status = str(getattr(run, "status", None) or "unknown").strip().lower()
        result = getattr(run, "result", None)
        diagnostics = getattr(run, "diagnostics", None)
        rows = _flatten_result(result if result is not None else {})

        self.title_var.set(title)
        self.status_var.set(status.upper().replace("_", " "))
        diagnostic_count = len(diagnostics) if isinstance(diagnostics, list) else 0
        self.summary_var.set(
            f"Calculated result snapshot · {diagnostic_count} diagnostic"
            f"{'s' if diagnostic_count != 1 else ''}. "
            "This view presents canonical run output; verification verdicts are shown separately."
        )
        self.count_var.set(
            f"{len(rows)} displayed field{'s' if len(rows) != 1 else ''}"
        )
        self.status_label.configure(
            style=(
                "CX.Status.Fail.TLabel"
                if status in {"fail", "failed", "error"}
                else "CX.Status.Warning.TLabel"
                if status in {"warning", "warn"}
                else "CX.Status.Pass.TLabel"
                if status in {"pass", "passed", "ok", "success", "completed"}
                else "CX.Status.Info.TLabel"
            )
        )

        for index, (path, rendered) in enumerate(rows):
            self.tree.insert(
                "",
                "end",
                iid=f"result-{index}",
                values=(_humanize(path), rendered),
                tags=("row_even" if index % 2 == 0 else "row_odd",),
            )
