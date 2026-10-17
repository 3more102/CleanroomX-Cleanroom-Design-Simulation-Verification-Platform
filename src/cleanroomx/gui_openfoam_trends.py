"""Read-only plots for hash-verified OpenFOAM field summaries in ProofGraph."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import math
import re
from typing import Any

import tkinter as tk
from tkinter import ttk

from .gui_theme import theme_palette
from .proofgraph_io import proofgraph_from_dict


_METRICS = ("mean", "minimum", "maximum")
_METRIC_LABELS = {"minimum": "Minimum", "mean": "Mean", "maximum": "Maximum"}
_SERIES_LIMIT = 5_000
_TIME_LABEL = re.compile(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")


def openfoam_field_series_from_proofgraph(
    document: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return validated descriptive field series from one canonical graph.

    Invalid individual series are ignored. The stored ProofGraph remains the
    authority for provenance and SHA-256 validation; this function validates
    only the data shape and numeric values needed to draw a safe plot.
    """
    if not isinstance(document, dict):
        return []
    canonical = proofgraph_from_dict(document).to_dict()
    snapshots_by_id = {
        evidence["id"]: evidence["value"].get("snapshot_sha256")
        for evidence in canonical.get("evidence", [])
        if evidence.get("property_name") == "openfoam_vtk_snapshot"
        and isinstance(evidence.get("value"), dict)
    }
    series_items: list[dict[str, Any]] = []
    for evidence in canonical.get("evidence", []):
        if evidence.get("property_name") != "openfoam_field_time_series":
            continue
        value = evidence.get("value")
        if not isinstance(value, dict):
            continue
        upstream_ids = {
            upstream_id
            for provenance in evidence.get("provenance", [])
            if isinstance(provenance, dict)
            for upstream_id in provenance.get("upstream_evidence_ids", [])
            if isinstance(upstream_id, str)
        }
        try:
            normalized = _validate_series(value, snapshots_by_id, upstream_ids)
        except (TypeError, ValueError, OverflowError):
            continue
        normalized["evidence_id"] = evidence["id"]
        series_items.append(normalized)
    series_items.sort(
        key=lambda item: (
            item["case_id"].casefold(),
            item["semantic"].casefold(),
            item["evidence_id"],
        )
    )
    return series_items


def _validate_series(
    value: dict[str, Any],
    snapshots_by_id: dict[str, Any],
    upstream_ids: set[str],
) -> dict[str, Any]:
    case_id = value.get("case_id")
    semantic = value.get("semantic")
    units = value.get("units")
    components = value.get("components")
    samples = value.get("samples")
    if type(case_id) is not str or not case_id.strip():
        raise ValueError("OpenFOAM field series has no case ID")
    if type(semantic) is not str or not semantic.strip():
        raise ValueError("OpenFOAM field series has no semantic name")
    if type(units) is not str or not units.strip():
        raise ValueError("OpenFOAM field series has no units")
    if type(components) is not int or components not in (1, 3):
        raise ValueError("OpenFOAM field series has an unsupported component count")
    if value.get("mean_weighting") != "cell_volume":
        raise ValueError("OpenFOAM field series does not identify its mean weighting")
    if value.get("scientific_validation") != "BLOCKED":
        raise ValueError("OpenFOAM field series must preserve the BLOCKED validation state")
    case_snapshot_count = value.get("case_snapshot_count")
    available_sample_count = value.get("available_sample_count")
    coverage_status = value.get("coverage_status")
    if (
        type(case_snapshot_count) is not int
        or case_snapshot_count < 1
        or type(available_sample_count) is not int
        or not 1 <= available_sample_count <= case_snapshot_count
        or coverage_status
        != ("complete" if available_sample_count == case_snapshot_count else "partial")
    ):
        raise ValueError("OpenFOAM field series has invalid snapshot coverage metadata")
    if (
        type(samples) is not list
        or len(samples) != available_sample_count
        or len(samples) > _SERIES_LIMIT
        or not upstream_ids
    ):
        raise ValueError("OpenFOAM field series has an invalid sample count or provenance")

    snapshot_ids_by_hash: dict[str, list[str]] = {}
    for evidence_id, digest in snapshots_by_id.items():
        if type(digest) is str:
            snapshot_ids_by_hash.setdefault(digest, []).append(evidence_id)

    parsed: list[tuple[Decimal, dict[str, Any]]] = []
    for sample in samples:
        if type(sample) is not dict:
            raise ValueError("OpenFOAM field series sample must be an object")
        raw_time = sample.get("solver_time_label")
        snapshot_hash = sample.get("snapshot_sha256")
        mesh_cells = sample.get("mesh_cells")
        if type(mesh_cells) is not int or mesh_cells < 1:
            raise ValueError("OpenFOAM field series sample has an invalid mesh-cell count")
        if type(raw_time) is not str or _TIME_LABEL.fullmatch(raw_time) is None:
            raise ValueError("OpenFOAM field series contains an invalid solver-time label")
        try:
            decimal_time = Decimal(raw_time)
            numeric_time = float(decimal_time)
        except (InvalidOperation, OverflowError, TypeError, ValueError) as exc:
            raise ValueError("OpenFOAM field series contains invalid solver time") from exc
        if (
            not decimal_time.is_finite()
            or decimal_time < 0
            or not math.isfinite(numeric_time)
            or type(snapshot_hash) is not str
            or re.fullmatch(r"[0-9a-f]{64}", snapshot_hash) is None
        ):
            raise ValueError("OpenFOAM field series contains invalid sample provenance")
        snapshot_id = next(
            (
                evidence_id
                for evidence_id in snapshot_ids_by_hash.get(snapshot_hash, [])
                if evidence_id in upstream_ids
            ),
            None,
        )
        if snapshot_id is None:
            raise ValueError("OpenFOAM field series sample is not linked to its retained snapshot")
        point_values: dict[str, list[float]] = {}
        for metric, sample_key in (
            ("minimum", "minimum"),
            ("mean", "volume_weighted_mean"),
            ("maximum", "maximum"),
        ):
            vector = sample.get(sample_key)
            if type(vector) is not list or len(vector) != components:
                raise ValueError(f"OpenFOAM field series {metric} has an invalid shape")
            numbers = []
            for raw_number in vector:
                if isinstance(raw_number, bool) or not isinstance(raw_number, (int, float)):
                    raise ValueError(f"OpenFOAM field series {metric} must be numeric")
                number = float(raw_number)
                if not math.isfinite(number):
                    raise ValueError(f"OpenFOAM field series {metric} must be finite")
                numbers.append(number)
            point_values[metric] = numbers
        for minimum, mean, maximum in zip(
            point_values["minimum"], point_values["mean"], point_values["maximum"]
        ):
            if minimum > mean or mean > maximum:
                raise ValueError("OpenFOAM field series point summaries are inconsistent")
        parsed.append(
            (
                decimal_time,
                {
                    "solver_time": raw_time,
                    "solver_time_value": numeric_time,
                    "snapshot_evidence_id": snapshot_id,
                    "snapshot_sha256": snapshot_hash,
                    "mesh_cells": mesh_cells,
                    **point_values,
                },
            )
        )

    parsed.sort(key=lambda item: (item[0], item[1]["snapshot_evidence_id"]))
    if any(left[0] == right[0] for left, right in zip(parsed, parsed[1:])):
        raise ValueError("OpenFOAM field series repeats a numeric solver time")
    if any(
        left[1]["solver_time_value"] >= right[1]["solver_time_value"]
        for left, right in zip(parsed, parsed[1:])
    ):
        raise ValueError("OpenFOAM field series times cannot be represented distinctly on a plot axis")
    return {
        "case_id": case_id,
        "semantic": semantic,
        "array_name": str(value.get("array_name") or semantic),
        "units": units,
        "components": components,
        "mean_weighting": value.get("mean_weighting"),
        "time_axis": str(value.get("solver_time_semantics") or "OpenFOAM solver time"),
        "case_snapshot_count": case_snapshot_count,
        "available_sample_count": available_sample_count,
        "coverage_status": coverage_status,
        "same_mesh_verified": value.get("same_mesh_verified") is True,
        "interpretation": str(value.get("interpretation") or "diagnostic field summaries"),
        "scientific_validation": value.get("scientific_validation", "BLOCKED"),
        "points": [point for _time, point in parsed],
    }


class OpenFOAMFieldTrendWindow:
    """Small theme-aware line plot for one field metric/component at a time."""

    def __init__(
        self,
        master: tk.Misc,
        document: dict[str, Any] | None = None,
        *,
        series: list[dict[str, Any]] | None = None,
        theme: str = "light",
    ) -> None:
        self.window = tk.Toplevel(master)
        self.window.title("OpenFOAM field trends · ProofGraph")
        self.window.geometry("900x570")
        self.window.minsize(640, 400)
        self._theme_name = theme
        self._palette = theme_palette(theme)
        self._series: list[dict[str, Any]] = []
        self._metric_options: dict[str, tuple[str, int]] = {}
        self._screen_points: list[tuple[float, float, dict[str, Any], float]] = []

        controls = ttk.Frame(self.window, padding=(10, 8, 10, 4))
        controls.pack(fill="x")
        ttk.Label(controls, text="Field series").pack(side="left")
        self.series_var = tk.StringVar()
        self.series_picker = ttk.Combobox(
            controls,
            textvariable=self.series_var,
            state="readonly",
            width=42,
        )
        self.series_picker.pack(side="left", padx=(6, 14))
        self.series_picker.bind("<<ComboboxSelected>>", self._on_series_changed)
        ttk.Label(controls, text="Measure").pack(side="left")
        self.metric_var = tk.StringVar()
        self.metric_picker = ttk.Combobox(
            controls,
            textvariable=self.metric_var,
            state="readonly",
            width=24,
        )
        self.metric_picker.pack(side="left", padx=(6, 0))
        self.metric_picker.bind("<<ComboboxSelected>>", lambda _event: self.draw())

        self.canvas = tk.Canvas(self.window, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=(3, 0))
        self.canvas.bind("<Configure>", lambda _event: self.draw())
        self.canvas.bind("<Motion>", self._on_motion)
        self.hover_var = tk.StringVar(value="Move over a point to inspect its exact summary.")
        ttk.Label(self.window, textvariable=self.hover_var, padding=(10, 4)).pack(
            fill="x"
        )
        self.note_var = tk.StringVar()
        ttk.Label(
            self.window,
            textvariable=self.note_var,
            style="CX.Section.TLabel",
            padding=(10, 3, 10, 8),
        ).pack(fill="x")
        if series is None:
            self.set_document(document)
        else:
            self.set_series(series)
        self.apply_theme(theme)

    def set_document(self, document: dict[str, Any] | None) -> None:
        self.set_series(openfoam_field_series_from_proofgraph(document))

    def set_series(self, series: list[dict[str, Any]]) -> None:
        self._series = list(series)
        labels = [
            self._series_label(item)
            for item in self._series
        ]
        self.series_picker.configure(values=labels)
        if labels:
            if self.series_var.get() not in labels:
                self.series_var.set(labels[0])
            self._set_metric_options()
        else:
            self.series_var.set("")
            self.metric_var.set("")
            self.metric_picker.configure(values=())
        self.draw()

    def apply_theme(self, theme: str) -> None:
        self._theme_name = theme
        self._palette = theme_palette(theme)
        self.canvas.configure(
            background=self._palette["plot"],
            highlightthickness=1,
            highlightbackground=self._palette["border"],
        )
        self.draw()

    def _active_series(self) -> dict[str, Any] | None:
        label = self.series_var.get()
        for item in self._series:
            if self._series_label(item) == label:
                return item
        return self._series[0] if self._series else None

    @staticmethod
    def _series_label(item: dict[str, Any]) -> str:
        identity = str(item.get("evidence_id", ""))[-8:]
        suffix = f" · {identity}" if identity else ""
        return (
            f"{item['case_id']} · {item['semantic']} "
            f"({len(item['points'])} times){suffix}"
        )

    def _set_metric_options(self) -> None:
        item = self._active_series()
        if item is None:
            self._metric_options = {}
            self.metric_picker.configure(values=())
            self.metric_var.set("")
            return
        options: dict[str, tuple[str, int]] = {}
        for metric in _METRICS:
            for component in range(item["components"]):
                component_label = (
                    f" · component {component + 1}" if item["components"] > 1 else ""
                )
                label = f"{_METRIC_LABELS[metric]}{component_label}"
                options[label] = (metric, component)
        self._metric_options = options
        labels = list(options)
        self.metric_picker.configure(values=labels)
        if self.metric_var.get() not in labels:
            self.metric_var.set(next(iter(options)))

    def _on_series_changed(self, _event=None) -> None:
        self._set_metric_options()
        self.draw()

    def _active_measure(self) -> tuple[str, int] | None:
        return self._metric_options.get(self.metric_var.get())

    def draw(self) -> None:
        if not self.window.winfo_exists():
            return
        self.canvas.delete("all")
        self._screen_points = []
        item = self._active_series()
        measure = self._active_measure()
        width = max(self.canvas.winfo_width(), 640)
        height = max(self.canvas.winfo_height(), 380)
        if item is None or measure is None:
            self.canvas.create_text(
                width / 2,
                height / 2,
                text="No verified OpenFOAM field time series in this ProofGraph.",
                fill=self._palette["muted"],
            )
            self.note_var.set("Scientific validation remains BLOCKED.")
            return

        metric, component = measure
        points = item["points"]
        xs = [point["solver_time_value"] for point in points]
        ys = [point[metric][component] for point in points]
        x_min, x_max = min(xs), max(xs)
        if x_min == x_max:
            half = max(abs(x_min) * 0.05, 0.5)
            x_min, x_max = x_min - half, x_max + half
        y_min, y_max = min(ys), max(ys)
        if y_min == y_max:
            pad = max(abs(y_min) * 0.05, 1e-9)
            y_min, y_max = y_min - pad, y_max + pad
        else:
            pad = (y_max - y_min) * 0.08
            y_min, y_max = y_min - pad, y_max + pad

        left, right, top, bottom = 76.0, width - 24.0, 34.0, height - 64.0
        if right <= left + 40 or bottom <= top + 40:
            return

        def px(value: float) -> float:
            return left + (value - x_min) / (x_max - x_min) * (right - left)

        def py(value: float) -> float:
            return bottom - (value - y_min) / (y_max - y_min) * (bottom - top)

        title = f"{item['case_id']} · {item['semantic']}"
        self.canvas.create_text(
            (left + right) / 2,
            15,
            text=title,
            fill=self._palette["text"],
            font=("TkDefaultFont", 11, "bold"),
        )
        for tick in range(5):
            fraction = tick / 4
            y_value = y_min + fraction * (y_max - y_min)
            y = py(y_value)
            self.canvas.create_line(left, y, right, y, fill=self._palette["grid"])
            self.canvas.create_text(
                left - 8,
                y,
                text=f"{y_value:.5g}",
                anchor="e",
                fill=self._palette["muted"],
            )
            x_value = x_min + fraction * (x_max - x_min)
            x = px(x_value)
            self.canvas.create_line(x, top, x, bottom, fill=self._palette["grid"])
            self.canvas.create_text(
                x,
                bottom + 14,
                text=f"{x_value:.5g}",
                anchor="n",
                fill=self._palette["muted"],
            )
        self.canvas.create_line(left, top, left, bottom, fill=self._palette["text"])
        self.canvas.create_line(left, bottom, right, bottom, fill=self._palette["text"])
        self.canvas.create_text(
            17,
            (top + bottom) / 2,
            text=f"{_METRIC_LABELS[metric]} ({item['units']})",
            angle=90,
            fill=self._palette["text"],
        )
        self.canvas.create_text(
            (left + right) / 2,
            height - 12,
            text="OpenFOAM solver time · physical units not inferred",
            fill=self._palette["text"],
        )

        color = self._palette["accent"]
        screen = [(px(x), py(y)) for x, y in zip(xs, ys)]
        if len(screen) > 1:
            coordinates = [coordinate for point in screen for coordinate in point]
            self.canvas.create_line(*coordinates, fill=color, width=2, smooth=False)
        for point, (screen_x, screen_y) in zip(points, screen):
            radius = 4
            self.canvas.create_oval(
                screen_x - radius,
                screen_y - radius,
                screen_x + radius,
                screen_y + radius,
                fill=color,
                outline=self._palette["plot"],
                width=1,
            )
            self._screen_points.append((screen_x, screen_y, point, point[metric][component]))

        coverage = (
            f"{item['available_sample_count']}/{item['case_snapshot_count']} snapshots · "
            f"{item['coverage_status']} field coverage"
        )
        if not item["same_mesh_verified"]:
            coverage += " · same mesh not verified"
        self.note_var.set(
            f"{coverage} · summaries use cell-volume weighting · descriptive only · "
            "scientific validation BLOCKED"
        )

    def _on_motion(self, event: tk.Event) -> None:
        nearest = None
        nearest_distance = 15.0**2
        for x, y, point, value in self._screen_points:
            distance = (event.x - x) ** 2 + (event.y - y) ** 2
            if distance < nearest_distance:
                nearest = (point, value)
                nearest_distance = distance
        measure = self._active_measure()
        item = self._active_series()
        if nearest is None or measure is None or item is None:
            self.hover_var.set("Move over a point to inspect its exact summary.")
            return
        point, value = nearest
        metric, component = measure
        component_text = f", component {component + 1}" if item["components"] > 1 else ""
        self.hover_var.set(
            f"t = {point['solver_time']} · {_METRIC_LABELS[metric].lower()}"
            f"{component_text} = {value:.17g} {item['units']} · "
            f"{point['mesh_cells']} cells · snapshot "
            f"{point['snapshot_evidence_id'].rsplit(':', 1)[-1]}"
        )


__all__ = ["OpenFOAMFieldTrendWindow", "openfoam_field_series_from_proofgraph"]
