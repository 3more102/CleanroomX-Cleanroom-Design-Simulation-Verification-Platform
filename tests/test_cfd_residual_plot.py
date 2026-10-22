"""Numerical/GUI contracts use synthetic logs, not physical CFD evidence."""
from __future__ import annotations

import copy
import os
import tkinter as tk

import pytest

from cleanroomx.cfd_multizone_results import solver_iteration_diagnostics
from cleanroomx.cfd_residual_plot import RecordedResidualPlot, residual_plot_data


def _report(iterations=(1, 2, 3), *, selected=None):
    log = []
    for iteration in iterations:
        log.append(f"Time = {iteration}")
        for field in ("p", "Ux", "Uy", "Uz", "p"):
            # Includes two pressure solves at each iteration, and true zero.
            initial = .1/iteration if field == "p" else 0.
            log.append(f"Solving for {field}, Initial residual = {initial}, Final residual = 1e-12")
    history, numerics = solver_iteration_diagnostics(
        "\n".join(log), "SIMPLE { residualControl { p 1e-5; U 1e-6; } }",
        str(iterations[-1] if selected is None else selected))
    return {"residual_history": history, "numerics": numerics,
            "time_name": str(iterations[-1] if selected is None else selected),
            "solver_reported_convergence": False, "engineering_release": "HOLD"}


def test_repeated_linear_solves_gaps_and_exact_values_are_preserved():
    report = _report((1, 8, 25))
    before = copy.deepcopy(report)
    model = residual_plot_data(report)
    assert [row["log_index"] for row in model["samples"]] == list(range(1, 16))
    assert {row["iteration"] for row in model["samples"]} == {1, 8, 25}
    pressure = [row for row in model["samples"] if row["field"] == "p"]
    assert [row["solve_index"] for row in pressure] == [1, 2]*3
    assert pressure[0]["value"] == .1
    assert any(row["value"] == 0. for row in model["samples"])
    assert model["limits"] == {"p": 1e-5, "Ux": 1e-6, "Uy": 1e-6, "Uz": 1e-6}
    assert report == before


def test_window_counts_distinct_recorded_iterations_and_never_linear_entries():
    model = residual_plot_data(_report(tuple(2*i for i in range(1, 121)), selected=2),
                               field="p", window="Last 100")
    assert model["first_iteration"] == 42
    assert model["last_iteration"] == 240
    assert model["selected_iteration"] == 2
    assert len(model["samples"]) == 200
    assert model["samples"][0]["log_index"] == 101
    assert model["samples"][1]["solve_index"] == 2


def test_final_linear_residuals_do_not_inherit_initial_convergence_limits():
    model = residual_plot_data(_report(), field="Ux", kind="Final linear")
    assert model["limits"] == {}
    assert [row["value"] for row in model["samples"]] == [1e-12]*3
    model = residual_plot_data(_report(), field="p", window="Last 500")
    assert len(model["samples"]) == 6


@pytest.mark.parametrize("change", [
    lambda r: r["residual_history"][0].update(initial=float("nan")),
    lambda r: r["residual_history"][0].update(final=-1),
    lambda r: r["residual_history"][0].update(initial=True),
    lambda r: r["residual_history"][0].update(iteration=None),
    lambda r: r["residual_history"][0].update(iteration=float("inf")),
    lambda r: r["residual_history"][0].update(field="<invalid>"),
    lambda r: r["numerics"]["fields"]["p"].update(configured_initial_residual_limit=0),
    lambda r: r.update(time_name="nan"),
    lambda r: r.update(residual_history=[]),
])
def test_invalid_chart_data_is_rejected(change):
    report = _report()
    change(report)
    with pytest.raises(ValueError):
        residual_plot_data(report)


@pytest.fixture
def desktop():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.name == "nt" or os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    root.geometry("950x650")
    try:
        yield root
    finally:
        root.destroy()


def test_real_canvas_filters_probes_and_keeps_solver_verdict(desktop):
    errors = []
    desktop.report_callback_exception = lambda *args: errors.append(args)
    plot = RecordedResidualPlot(desktop)
    plot.pack(fill="both", expand=True)
    report = _report()
    before = copy.deepcopy(report)
    plot.set_report(report)
    desktop.update()
    assert len(plot.canvas.find_withtag("computed-residual")) == 4
    assert len(plot.canvas.find_withtag("residual-limit")) == 4
    assert len(plot.canvas.find_withtag("selected-iteration")) == 1
    plot.field.set("p")
    plot.pickers["Field"].event_generate("<<ComboboxSelected>>")
    desktop.update()
    assert len(plot.canvas.find_withtag("computed-residual")) == 1
    assert len(plot.points) == 6  # both pressure solves survive
    plot.canvas.focus_force()
    plot.canvas.event_generate("<Right>")
    desktop.update()
    assert "field solve 1" in plot.detail.get()
    plot.canvas.event_generate("<Right>")
    desktop.update()
    assert "field solve 2" in plot.detail.get()
    plot.kind.set("Final linear")
    plot.pickers["Residual"].event_generate("<<ComboboxSelected>>")
    desktop.update()
    assert not plot.canvas.find_withtag("residual-limit")
    assert all(row[2]["value"] == 1e-12 for row in plot.points)
    plot.field.set("Ux")
    plot.kind.set("Initial")
    plot.scale.set("linear")
    plot.redraw()
    desktop.update()
    x, y, _ = plot.points[0]
    plot.canvas.event_generate("<Motion>", x=round(x), y=round(y))
    desktop.update()
    assert "Initial residual = 0.0" in plot.detail.get()
    assert plot.canvas.find_withtag("residual-probe")
    assert report == before
    assert not errors


def test_real_canvas_marks_offscreen_saved_iteration_and_clears_stale_probes(desktop):
    plot = RecordedResidualPlot(desktop)
    plot.pack(fill="both", expand=True)
    plot.set_report(_report(tuple(range(1, 121)), selected=1))
    plot.window.set("Last 100")
    plot.redraw()
    desktop.update()
    assert not plot.canvas.find_withtag("selected-iteration")
    assert "outside visible range" in plot.canvas.itemcget(
        plot.canvas.find_withtag("residual-caption")[0], "text")
    plot._step_probe(1)
    assert plot.canvas.find_withtag("residual-probe")
    plot.set_report(None)
    assert plot.points == []
    assert plot.model is None
    assert not plot.canvas.find_all()
    assert "Import recorded" in plot.detail.get()
    # A single recorded iteration remains visible without invented states.
    plot.set_report(_report((7,)))
    desktop.update()
    assert len(plot.points) == 5
    assert len(plot.canvas.find_withtag("selected-iteration")) == 1


def test_existing_workspace_uses_native_residual_controls(desktop):
    from cleanroomx.cfd_multizone_gui import MultizoneCFDWindow
    window = MultizoneCFDWindow(desktop)
    try:
        window.report = _report()
        window.draw_residuals()
        window.tabs.select(2)
        desktop.update()
        assert window.residual_canvas is window.residual_plot.canvas
        assert window.residual_plot.model["selected_iteration"] == 3
        assert len(window.residual_canvas.find_withtag("computed-residual")) == 4
    finally:
        window.close()
