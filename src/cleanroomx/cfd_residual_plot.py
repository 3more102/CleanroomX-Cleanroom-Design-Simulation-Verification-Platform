"""Native inspection of recorded SIMPLE residuals; no solver state is inferred."""
from __future__ import annotations

import math
import re
import tkinter as tk
from tkinter import ttk

from .cfd_live_monitor import PREVIEW_SCHEMA


_COLORS = ("#ffbf69", "#22c5d6", "#98d36b", "#d990ed", "#f789a4")
_KINDS = {"Initial": "initial", "Final linear": "final"}
_WINDOWS = {"All": None, "Last 100": 100, "Last 500": 500}


def residual_plot_data(report, *, field="All", kind="Initial", window="All"):
    """Copy actual entries, preserving repeated solves and gaps in iterations.

    The window counts distinct recorded SIMPLE iterations, never seconds or
    linear-solver entries. Configured limits apply only to initial residuals.
    """
    if kind not in _KINDS or window not in _WINDOWS:
        raise ValueError("Unknown residual kind or recorded-iteration window")
    history = report.get("residual_history")
    if type(history) is not list or not history:
        raise ValueError("Recorded residual history is required")
    preview = report.get("schema") == PREVIEW_SCHEMA
    offset = report.get("residual_log_offset", 0) if preview else 0
    if type(offset) is not int or offset < 0:
        raise ValueError("Invalid preview log offset")
    rows, occurrences = [], {}
    for index, row in enumerate(history, offset + 1):
        if type(row) is not dict:
            raise ValueError("Invalid recorded residual entry")
        name, iteration = row.get("field"), row.get("iteration")
        if (type(name) is not str or re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name) is None
            or type(iteration) not in (int, float) or not math.isfinite(iteration)
            or iteration < 0):
            raise ValueError("Invalid residual field or recorded SIMPLE iteration")
        for key in ("initial", "final"):
            value = row.get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError("Residual values must be finite and nonnegative")
        identity = (name, iteration)
        occurrences[identity] = occurrences.get(identity, 0) + 1
        rows.append({"field": name, "iteration": iteration,
                     "value": row[_KINDS[kind]], "log_index": index,
                     "solve_index": occurrences[identity]})
    names = tuple(dict.fromkeys(row["field"] for row in rows))
    if field != "All" and field not in names:
        raise ValueError("Selected field has no recorded residual entries")
    selected = None
    if not preview:
        try:
            selected = float(report.get("time_name"))
        except (ValueError, TypeError) as exc:
            raise ValueError("Selected saved iteration must be finite") from exc
        if not math.isfinite(selected) or selected < 0:
            raise ValueError("Selected saved iteration must be finite")
    iterations = sorted({row["iteration"] for row in rows})
    count = _WINDOWS[window]
    first = iterations[-count] if count and len(iterations) > count else iterations[0]
    visible = [row for row in rows if row["iteration"] >= first
               and (field == "All" or row["field"] == field)]
    limits = {}
    if kind == "Initial" and not preview:
        for name, row in report.get("numerics", {}).get("fields", {}).items():
            if name not in {item["field"] for item in visible}:
                continue
            limit = row.get("configured_initial_residual_limit")
            if limit is None:
                continue
            if type(limit) not in (int, float) or not math.isfinite(limit) or limit <= 0:
                raise ValueError("Configured initial residual limits must be positive")
            limits[name] = limit
    return {"fields": names, "samples": visible, "limits": limits,
            "first_iteration": first, "last_iteration": iterations[-1],
            "selected_iteration": selected, "total_samples": len(rows)}


class RecordedResidualPlot(ttk.Frame):
    """Filtering, honest axes, and mouse/keyboard probes on the actual Tk canvas."""

    def __init__(self, master):
        super().__init__(master)
        self.report = None
        self.model = None
        self.points = []
        self._probe_index = None
        self.field = tk.StringVar(self, value="All")
        self.kind = tk.StringVar(self, value="Initial")
        self.scale = tk.StringVar(self, value="log10")
        self.window = tk.StringVar(self, value="All")
        self.detail = tk.StringVar(self, value="Import recorded fields to inspect residuals.")
        controls = ttk.Frame(self)
        controls.pack(fill="x", pady=(0, 5))
        self.pickers = {}
        for column, (label, var, values, width) in enumerate((
            ("Field", self.field, ("All",), 10),
            ("Residual", self.kind, tuple(_KINDS), 12),
            ("Y scale", self.scale, ("log10", "linear"), 8),
            ("Iterations", self.window, tuple(_WINDOWS), 11),
        )):
            group = ttk.Frame(controls)
            group.grid(row=0, column=column, sticky="w", padx=(0, 12))
            ttk.Label(group, text=label).pack(anchor="w")
            picker = ttk.Combobox(group, textvariable=var, values=values,
                                  state="readonly", width=width)
            picker.pack(anchor="w")
            picker.bind("<<ComboboxSelected>>", lambda _event: self.redraw())
            self.pickers[label] = picker
        self.canvas = tk.Canvas(self, background="#101b2b", highlightthickness=1,
                                highlightbackground="#425d76", takefocus=1,
                                width=650, height=350)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self.redraw())
        self.canvas.bind("<Motion>", self._hover)
        self.canvas.bind("<Leave>", lambda _event: self._clear_probe())
        self.canvas.bind("<Button-1>", lambda _event: self.canvas.focus_set())
        self.canvas.bind("<Left>", lambda _event: self._step_probe(-1))
        self.canvas.bind("<Right>", lambda _event: self._step_probe(1))
        ttk.Label(self, textvariable=self.detail, wraplength=850).pack(anchor="w", pady=5)
        ttk.Label(self, wraplength=850, text=(
            "Hover to inspect; click the chart then use Left/Right for recorded entries. "
            "X: recorded SIMPLE iteration, not physical time. Dashed limits apply only "
            "to initial residuals; final linear residuals do not establish convergence. "
            "log10 uses a display floor of 1e-30; probes retain exact recorded values."
        )).pack(anchor="w")

    def set_report(self, report):
        self.report = report
        if report is not None:
            self.pickers["Field"].configure(values=("All", *dict.fromkeys(
                row["field"] for row in report["residual_history"])))
            if self.field.get() not in self.pickers["Field"].cget("values"):
                self.field.set("All")
        self.redraw()

    def redraw(self):
        c = self.canvas
        c.delete("all")
        self.points = []
        self._probe_index = None
        self.model = None
        if self.report is None:
            self.detail.set("Import recorded fields to inspect residuals.")
            return
        try:
            if self.scale.get() not in ("log10", "linear"):
                raise ValueError("Choose log10 or linear residual scale")
            model = residual_plot_data(self.report, field=self.field.get(),
                                       kind=self.kind.get(), window=self.window.get())
        except ValueError as exc:
            self.detail.set("Residual view rejected: " + str(exc))
            return
        self.model = model
        if not model["samples"]:
            self.detail.set("No entries for this field in the selected recorded-iteration window.")
            return
        width, height = max(c.winfo_width(), 400), max(c.winfo_height(), 200)
        left, right, top, bottom = 80, width - 20, 40, height - 65
        first, last = model["first_iteration"], model["last_iteration"]
        def xx(iteration):
            return (left + right) / 2 if first == last else left + (right-left) * ((iteration-first)/(last-first))
        def transform(value):
            return math.log10(max(value, 1e-30)) if self.scale.get() == "log10" else value
        ys = [transform(row["value"]) for row in model["samples"]]
        ys.extend(transform(value) for value in model["limits"].values())
        low, high = min(ys), max(ys)
        if low == high:
            if self.scale.get() == "log10":
                low, high = low - .5, high + .5
            else:
                low, high = (0., high) if high else (0., 1.)
        def yy(value):
            return bottom - ((transform(value)-low)/(high-low)) * (bottom-top)
        for n in range(5):
            y = top + n * (bottom-top)/4
            v = high - n * (high-low)/4
            text = f"10^{v:.1f}" if self.scale.get() == "log10" else f"{v:.3g}"
            c.create_line(left, y, right, y, fill="#24374e")
            c.create_text(left-8, y, anchor="e", text=text, fill="#b6cddd")
            x = left + n * (right-left)/4
            c.create_text(x, bottom+16, text=f"{first+n*(last-first)/4:g}", fill="#b6cddd")
        colors = {name: _COLORS[i % len(_COLORS)] for i, name in enumerate(model["fields"])}
        for name in model["fields"]:
            entries = [row for row in model["samples"] if row["field"] == name]
            if not entries:
                continue
            coords = []
            for row in entries:
                x, y = xx(row["iteration"]), yy(row["value"])
                coords.extend((x, y))
            if len(coords) >= 4:
                c.create_line(*coords, fill=colors[name], width=1.5, tags="computed-residual")
            else:
                x, y = coords
                c.create_oval(x-2, y-2, x+2, y+2, fill=colors[name], tags="computed-residual")
            if name in model["limits"]:
                y = yy(model["limits"][name])
                c.create_line(left, y, right, y, fill=colors[name], dash=(5, 4), tags="residual-limit")
        # Probe order is the original global log order, including repeated solves.
        self.points = [(xx(row["iteration"]), yy(row["value"]), row) for row in model["samples"]]
        selected = model["selected_iteration"]
        if selected is not None and first <= selected <= last:
            x = xx(selected)
            c.create_line(x, top, x, bottom, fill="white", dash=(4, 3), tags="selected-iteration")
        if selected is None:
            caption = f"{self.kind.get()} residuals | UNVERIFIED log preview; no saved fields imported"
        else:
            caption = f"{self.kind.get()} residuals | saved fields: iteration {selected:g}"
            if not first <= selected <= last:
                caption += " (outside visible range)"
        c.create_text(left, 17, anchor="w", text=caption, fill="white", tags="residual-caption")
        visible_fields = tuple(dict.fromkeys(row["field"] for row in model["samples"]))
        for i, name in enumerate(visible_fields):
            label = name + (f" (limit {model['limits'][name]:g})" if name in model["limits"] else "")
            c.create_text(left + (i % 2) * (right-left)/2, height-31 + (i//2)*18,
                          anchor="w", text=label, fill=colors[name], tags="residual-legend")
        self._summary = (f"Showing {len(self.points)} of {model['total_samples']} recorded linear solves; "
                         f"SIMPLE iterations {first:g} to {last:g}.")
        self.detail.set(self._summary)

    def _show_probe(self, index):
        self.canvas.delete("residual-probe")
        self._probe_index = index
        x, y, row = self.points[index]
        self.canvas.create_oval(x-4, y-4, x+4, y+4, fill="white", outline="#101b2b", tags="residual-probe")
        self.detail.set(f"{row['field']} | SIMPLE iteration {row['iteration']:g} | "
                        f"field solve {row['solve_index']} in this iteration | "
                        f"log entry {row['log_index']} | {self.kind.get()} residual = {row['value']!r}")

    def _hover(self, event):
        if self.points:
            nearest = min(range(len(self.points)), key=lambda i: (
                (self.points[i][0]-event.x)**2 + (self.points[i][1]-event.y)**2))
            self._show_probe(nearest)

    def _clear_probe(self):
        self.canvas.delete("residual-probe")
        self._probe_index = None
        if self.points:
            self.detail.set(self._summary)

    def _step_probe(self, step):
        if self.points:
            index = (0 if step > 0 else len(self.points)-1) if self._probe_index is None else max(
                0, min(len(self.points)-1, self._probe_index+step))
            self._show_probe(index)
        return "break"
