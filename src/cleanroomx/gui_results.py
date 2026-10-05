from __future__ import annotations

import math
from typing import Any

import tkinter as tk
from tkinter import ttk

from .gui_theme import attach_tooltip, status_style_name, theme_palette


_UNIT_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("_m3_h", "m³/h"),
    ("_m3_s", "m³/s"),
    ("_kg_m3", "kg/m³"),
    ("_m2_s", "m²/s"),
    ("_m2", "m²"),
    ("_m3", "m³"),
    ("_pa", "Pa"),
    ("_kw", "kW"),
    ("_w", "W"),
    ("_c", "°C"),
    ("_percent", "%"),
    ("_minutes", "min"),
    ("_um", "µm"),
    ("_m", "m"),
)


def _unit_hint(path: str) -> str:
    """Infer a display unit only from an explicit field-name suffix."""
    key = str(path or "").rsplit(".", 1)[-1].split("[", 1)[0].lower()
    for suffix, unit in _UNIT_SUFFIXES:
        if key.endswith(suffix):
            return unit
    if key.endswith("_1_h") or key == "ach":
        return "1/h"
    return ""


def _humanize(value: Any) -> str:
    text = str(value or "").replace("_", " ").replace(".", " / ").strip()
    return " ".join(part.capitalize() for part in text.split())


def _result_class(path: Any) -> str:
    """Classify result rows without changing or inventing engineering meaning."""
    text = str(path or "").strip().lower()
    leaf = text.rsplit(".", 1)[-1].split("[", 1)[0]
    tokens = {
        part
        for part in text.replace("[", ".").replace("]", "").replace("_", ".").split(".")
        if part
    }
    if any(
        token.startswith("require")
        or token in {"target", "limit", "criterion", "criteria", "minimum", "maximum"}
        for token in tokens
    ):
        return "REQUIREMENT"
    if (
        leaf in {"status", "verdict", "compliance", "result_status"}
        or any(token in {"verdict", "compliance"} for token in tokens)
        or leaf.endswith("_status")
    ):
        return "VERDICT"
    if any(
        token in {"metadata", "meta", "provenance", "source", "version", "timestamp"}
        for token in tokens
    ):
        return "METADATA"
    return "CALCULATED"


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
        rendered = _format_scalar(node)
        unit = _unit_hint(path)
        if unit and isinstance(node, (int, float)) and not isinstance(node, bool):
            rendered = f"{rendered} {unit}"
        rows.append((path or "Result", rendered))

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
        self.calculated_count_var = tk.StringVar(value="0")
        self.requirement_count_var = tk.StringVar(value="0")
        self.verdict_count_var = tk.StringVar(value="0")
        self.diagnostic_count_var = tk.StringVar(value="0")
        self.search_var = tk.StringVar()
        self.class_filter_var = tk.StringVar(value="All")
        self._rows: list[tuple[str, str]] = []

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

        instruments = ttk.Frame(self)
        instruments.pack(fill="x", pady=(0, 8))
        for column in range(4):
            instruments.columnconfigure(column, weight=1)

        for column, title, variable in (
            (0, "CALCULATED", self.calculated_count_var),
            (1, "REQUIREMENTS", self.requirement_count_var),
            (2, "VERDICTS", self.verdict_count_var),
            (3, "DIAGNOSTICS", self.diagnostic_count_var),
        ):
            card = ttk.Frame(
                instruments,
                style="CX.Instrument.TFrame",
                padding=(8, 6),
            )
            card.grid(
                row=0,
                column=column,
                sticky="ew",
                padx=(0, 3) if column == 0 else (3, 3) if column < 3 else (3, 0),
            )
            ttk.Label(
                card,
                text=title,
                style="CX.InstrumentName.TLabel",
            ).pack(anchor="w")
            ttk.Label(
                card,
                textvariable=variable,
                style="CX.InstrumentValue.TLabel",
            ).pack(anchor="w", pady=(2, 0))

        filterbar = ttk.Frame(self, style="CX.SubtlePanel.TFrame", padding=(8, 5))
        filterbar.pack(fill="x", pady=(0, 7))
        ttk.Label(
            filterbar,
            text="RESULT FILTER",
            style="CX.SurfaceSection.TLabel",
        ).pack(side="left", padx=(0, 8))
        ttk.Label(filterbar, text="Search", style="CX.SurfaceMuted.TLabel").pack(side="left")
        search = ttk.Entry(filterbar, textvariable=self.search_var, width=28)
        search.pack(side="left", padx=(5, 10))
        ttk.Label(filterbar, text="Class", style="CX.SurfaceMuted.TLabel").pack(side="left")
        class_picker = ttk.Combobox(
            filterbar,
            textvariable=self.class_filter_var,
            values=("All", "Calculated", "Requirement", "Verdict", "Metadata"),
            state="readonly",
            width=13,
        )
        class_picker.pack(side="left", padx=(5, 0))
        attach_tooltip(
            class_picker,
            "Result classes separate calculated values, requirement-like fields, verdict fields, and metadata. Classification does not alter solver output.",
        )
        self.search_var.trace_add("write", lambda *_: self._populate())
        class_picker.bind("<<ComboboxSelected>>", lambda _event: self._populate())

        columns = ("class", "field", "value")
        self.tree = ttk.Treeview(
            self,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("class", text="Class")
        self.tree.heading("field", text="Engineering field")
        self.tree.heading("value", text="Value")
        self.tree.column("class", width=112, minwidth=96, stretch=False, anchor="center")
        self.tree.column("field", width=410, minwidth=180, stretch=True)
        self.tree.column("value", width=330, minwidth=160, stretch=True)
        yscroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")
        self.apply_theme("dark")

    def apply_theme(self, value: Any) -> None:
        palette = theme_palette(value)
        self.tree.tag_configure("row_even", background=palette["tree"])
        self.tree.tag_configure("row_odd", background=palette["surface_alt"])
        self.tree.tag_configure("calculated", foreground=palette["text"])
        self.tree.tag_configure("requirement", foreground=palette["requirement"])
        self.tree.tag_configure("metadata", foreground=palette["muted"])
        self.tree.tag_configure("verdict_pass", foreground=palette["success"])
        self.tree.tag_configure("verdict_warning", foreground=palette["warning"])
        self.tree.tag_configure(
            "verdict_fail",
            foreground=palette["error"],
            font=("TkDefaultFont", 9, "bold"),
        )

    def clear(self) -> None:
        self.refresh(None)

    def _visible_rows(self) -> list[tuple[str, str]]:
        query = self.search_var.get().strip().casefold()
        selected_class = self.class_filter_var.get().strip().upper()
        visible: list[tuple[str, str]] = []
        for path, rendered in self._rows:
            semantic = _result_class(path)
            if selected_class and selected_class != "ALL" and semantic != selected_class:
                continue
            if query and query not in f"{path} {rendered} {semantic}".casefold():
                continue
            visible.append((path, rendered))
        return visible

    @staticmethod
    def _semantic_tag(semantic: str, rendered: str) -> str:
        if semantic != "VERDICT":
            return semantic.lower()
        token = str(rendered).strip().lower()
        if token in {"fail", "failed", "error", "critical", "no", "false"}:
            return "verdict_fail"
        if token in {"warning", "warn", "stale", "incomplete"}:
            return "verdict_warning"
        if token in {"pass", "passed", "ok", "success", "completed", "yes", "true"}:
            return "verdict_pass"
        return "metadata"

    def _populate(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        visible = self._visible_rows()
        for index, (path, rendered) in enumerate(visible):
            semantic = _result_class(path)
            self.tree.insert(
                "",
                "end",
                iid=f"result-{index}",
                values=(semantic, _humanize(path), rendered),
                tags=(
                    "row_even" if index % 2 == 0 else "row_odd",
                    self._semantic_tag(semantic, rendered),
                ),
            )
        total = len(self._rows)
        shown = len(visible)
        classes = [_result_class(path) for path, _rendered in self._rows]
        calc = classes.count("CALCULATED")
        req = classes.count("REQUIREMENT")
        verdict = classes.count("VERDICT")
        self.calculated_count_var.set(str(calc))
        self.requirement_count_var.set(str(req))
        self.verdict_count_var.set(str(verdict))
        details = [f"{shown}/{total} fields" if shown != total else f"{total} fields"]
        if calc:
            details.append(f"{calc} calc")
        if req:
            details.append(f"{req} req")
        if verdict:
            details.append(f"{verdict} verdict")
        self.count_var.set(" · ".join(details))

    def refresh(self, run: Any | None) -> None:
        self._rows = []
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
            self.calculated_count_var.set("0")
            self.requirement_count_var.set("0")
            self.verdict_count_var.set("0")
            self.diagnostic_count_var.set("0")
            self.status_label.configure(style="CX.Status.Neutral.TLabel")
            return

        title = str(getattr(run, "title", None) or "Analysis result")
        status = str(getattr(run, "status", None) or "unknown").strip().lower()
        result = getattr(run, "result", None)
        diagnostics = getattr(run, "diagnostics", None)
        rows = _flatten_result(result if result is not None else {})
        self._rows = rows

        self.title_var.set(title)
        self.status_var.set(status.upper().replace("_", " "))
        diagnostic_count = (
            len(diagnostics)
            if isinstance(diagnostics, (dict, list, tuple))
            else 0
        )
        self.diagnostic_count_var.set(str(diagnostic_count))
        self.summary_var.set(
            f"Calculated result snapshot · {diagnostic_count} diagnostic"
            f"{'s' if diagnostic_count != 1 else ''}. "
            "This view presents canonical run output; verification verdicts are shown separately."
        )
        self.status_label.configure(style=status_style_name(status))
        self._populate()
