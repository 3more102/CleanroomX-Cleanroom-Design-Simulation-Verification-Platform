"""Dependency-free SVG visualization for selected-time CFD audit reports.

The shaded band is the spatial p05–p95 distribution within each snapshot;
it is not a confidence interval or a measure of uncertainty.
"""
from __future__ import annotations

import math
from statistics import fmean
from xml.sax.saxutils import escape


def _finite_number(value, label: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"plot report {label} must be a finite number")
    return float(value)


def _short_text(value, label: str, *, limit: int = 120) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"plot report {label} must be nonempty text")
    value = value.strip()
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _svg_text(x: float, y: float, value: str, *, size: int = 12,
              color: str = "#172b36", anchor: str = "start",
              weight: str = "normal") -> str:
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" '
        f'font-weight="{weight}" text-anchor="{anchor}" fill="{color}">'
        f"{escape(value)}</text>"
    )


def render_time_study_svg(report: dict) -> str:
    """Render selected-time means and spatial percentile bands as SVG text."""
    if type(report) is not dict or report.get("status") != "DIAGNOSTIC_ONLY":
        raise ValueError("plot report must retain DIAGNOSTIC_ONLY status")
    samples = report.get("samples")
    if type(samples) is not list or not 2 <= len(samples) <= 100:
        raise ValueError("plot report requires 2..100 selected samples")

    rows = []
    for index, sample in enumerate(samples):
        if type(sample) is not dict or type(sample.get("field_summary")) is not dict:
            raise ValueError(f"plot report sample {index} is malformed")
        label = _short_text(sample.get("solver_time_name"), f"samples[{index}].solver_time_name", limit=32)
        time_value = _finite_number(sample.get("solver_time_value"), f"samples[{index}].solver_time_value")
        summary = sample["field_summary"]
        mean = _finite_number(summary.get("volume_weighted_mean"), f"samples[{index}].volume_weighted_mean")
        p05 = _finite_number(summary.get("volume_weighted_p05"), f"samples[{index}].volume_weighted_p05")
        p95 = _finite_number(summary.get("volume_weighted_p95"), f"samples[{index}].volume_weighted_p95")
        if p05 > p95:
            raise ValueError(f"plot report sample {index} has reversed spatial percentiles")
        rows.append({"label": label, "time": time_value, "mean": mean, "p05": p05, "p95": p95})

    times = [row["time"] for row in rows]
    time_span = times[-1] - times[0]
    if (
        not math.isfinite(time_span)
        or time_span <= 0
        or any(later <= earlier for earlier, later in zip(times, times[1:]))
    ):
        raise ValueError("plot report solver-time values must be strictly increasing")
    xs = [(value - times[0]) / time_span for value in times]

    value_scale = max(abs(value) for row in rows for value in (row["mean"], row["p05"], row["p95"]))
    if value_scale == 0:
        ys = [{"mean": 0.0, "p05": 0.0, "p95": 0.0} for _ in rows]
    else:
        ys = [{key: row[key] / value_scale for key in ("mean", "p05", "p95")} for row in rows]

    # Fit a descriptive line in normalized coordinates to avoid overflow at
    # large field magnitudes. The fit is a visual summary, not a convergence test.
    mean_y = [row["mean"] for row in ys]
    center_x = fmean(xs)
    center_y = fmean(mean_y)
    x_variance = math.fsum((value - center_x) ** 2 for value in xs)
    if x_variance > 0:
        slope = math.fsum((x - center_x) * (y - center_y) for x, y in zip(xs, mean_y)) / x_variance
        trend_y = [center_y + slope * (x - center_x) for x in (0.0, 1.0)]
    else:
        trend_y = [center_y, center_y]

    y_values = [value for row in ys for value in row.values()] + trend_y
    y_min, y_max = min(y_values), max(y_values)
    if y_min == y_max:
        padding = max(abs(y_min) * 0.05, 1e-9)
    else:
        padding = (y_max - y_min) * 0.08
    y_min -= padding
    y_max += padding

    width, height = 1000, 570
    left, right, top, bottom = 92.0, 950.0, 142.0, 420.0
    plot_width, plot_height = right - left, bottom - top

    def px(x: float) -> float:
        return left + x * plot_width

    def py(y: float) -> float:
        return bottom - (y - y_min) / (y_max - y_min) * plot_height

    study = _short_text(report.get("study_name"), "study_name", limit=100)
    solver = _short_text(report.get("solver"), "solver", limit=80)
    run_id = _short_text(report.get("run_id"), "run_id", limit=50)
    quantity = _short_text(report.get("quantity"), "quantity", limit=50)
    unit = _short_text(report.get("unit"), "unit", limit=24)
    review = report.get("engineering_review")
    if review not in ("BLOCKED", "READY_FOR_ENGINEERING_REVIEW"):
        raise ValueError("plot report engineering_review has an unsupported value")
    review_badge = "BLOCKED" if review == "BLOCKED" else "REVIEW READY"
    series = report.get("series_analysis")
    if type(series) is not dict:
        raise ValueError("plot report series_analysis is malformed")
    relative_range = series.get("relative_range_over_mean_absolute_value")
    range_label = (
        "not computed" if relative_range is None
        else f"{_finite_number(relative_range, 'relative range') * 100:.4g}%"
    )
    screening = _short_text(series.get("screening_status"), "series_analysis.screening_status", limit=64)

    upper = " ".join(f"{px(x):.2f},{py(row['p95']):.2f}" for x, row in zip(xs, ys))
    lower = " ".join(f"{px(x):.2f},{py(row['p05']):.2f}" for x, row in reversed(list(zip(xs, ys))))
    mean_path = " ".join(
        ("M" if index == 0 else "L") + f" {px(x):.2f} {py(row['mean']):.2f}"
        for index, (x, row) in enumerate(zip(xs, ys))
    )
    trend_path = f"M {px(0.0):.2f} {py(trend_y[0]):.2f} L {px(1.0):.2f} {py(trend_y[1]):.2f}"

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="plot-title plot-description">',
        f"<title id=\"plot-title\">Selected-time CFD field analysis: {escape(study)}</title>",
        "<desc id=\"plot-description\">Volume-weighted field means across selected OpenFOAM time labels. The shaded p05 to p95 band shows within-snapshot spatial variation, not uncertainty.</desc>",
        '<rect width="100%" height="100%" fill="#edf2f5"/>',
        '<rect x="24" y="20" width="952" height="526" rx="12" fill="#ffffff" stroke="#c9d5dd"/>',
        _svg_text(52, 54, "Selected-time CFD field analysis", size=22, color="#172b36", weight="bold"),
        _svg_text(52, 78, f"{study} · Configuration {report.get('configuration')} · {solver} · run {run_id}", size=12, color="#627481"),
        '<rect x="725" y="35" width="220" height="29" rx="14" fill="#f7efd9" stroke="#e6d6ad"/>',
        _svg_text(835, 54, "DIAGNOSTIC ONLY · " + review_badge, size=10, color="#755607", anchor="middle", weight="bold"),
        _svg_text(52, 105, "OpenFOAM labels are not assumed to represent physical seconds. Percentile band is spatial variation within each snapshot.", size=11, color="#627481"),
        _svg_text(52, 128, f"Quantity: {quantity} ({unit})  ·  Relative range: {range_label}  ·  Screen: {screening}", size=11, color="#172b36", weight="bold"),
        f'<defs><clipPath id="plot-area"><rect x="{left}" y="{top}" width="{plot_width}" height="{plot_height}"/></clipPath></defs>',
        f'<rect x="{left}" y="{top}" width="{plot_width}" height="{plot_height}" fill="#fbfdfe" stroke="#c9d5dd"/>',
    ]

    if value_scale == 0:
        tick_values = [0.0]
    else:
        tick_values = [y_min + (y_max - y_min) * index / 4 for index in range(5)]
    for value in tick_values:
        coordinate = py(value)
        displayed = value * value_scale
        parts.extend([
            f'<line x1="{left}" y1="{coordinate:.2f}" x2="{right}" y2="{coordinate:.2f}" stroke="#d8e1e7" stroke-width="1"/>',
            _svg_text(left - 10, coordinate + 4, f"{displayed:.5g}", size=10, color="#627481", anchor="end"),
        ])

    parts.append(
        f'<text x="31" y="{(top + bottom) / 2:.2f}" '
        f'transform="rotate(-90 31 {(top + bottom) / 2:.2f})" '
        f'font-size="11" font-weight="bold" text-anchor="middle" fill="#172b36">'
        f"{escape('Volume-weighted ' + quantity + ' (' + unit + ')')}</text>"
    )

    parts.append(f'<g clip-path="url(#plot-area)"><polygon points="{upper} {lower}" fill="#087f78" fill-opacity="0.16"/>')
    parts.append(f'<path d="{trend_path}" fill="none" stroke="#7050a7" stroke-width="2" stroke-dasharray="7 6"/>')
    parts.append(f'<path d="{mean_path}" fill="none" stroke="#087f78" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>')
    for x, row, plotted in zip(xs, rows, ys):
        parts.append(
            f'<circle cx="{px(x):.2f}" cy="{py(plotted["mean"]):.2f}" r="4.5" fill="#087f78" stroke="#ffffff" stroke-width="2">'
            f'<title>Solver time label {escape(row["label"])}; volume-weighted mean {row["mean"]:.6g} {escape(unit)}</title></circle>'
        )
    parts.append("</g>")

    label_indices = sorted({round(index * (len(rows) - 1) / 5) for index in range(6)})
    for index in label_indices:
        parts.append(_svg_text(px(xs[index]), bottom + 23, rows[index]["label"], size=10, color="#627481", anchor="middle"))
    parts.append(_svg_text((left + right) / 2, bottom + 51, "OpenFOAM solver time label (not interpreted as seconds)", size=11, color="#172b36", anchor="middle", weight="bold"))

    legend_y = 502
    parts.extend([
        '<line x1="88" y1="492" x2="122" y2="492" stroke="#087f78" stroke-width="3"/>',
        '<circle cx="105" cy="492" r="4" fill="#087f78" stroke="#ffffff" stroke-width="1"/>',
        _svg_text(130, legend_y, "volume-weighted mean", size=11, color="#172b36"),
        '<rect x="330" y="484" width="26" height="15" rx="3" fill="#087f78" fill-opacity="0.16" stroke="#087f78" stroke-opacity="0.4"/>',
        _svg_text(365, legend_y, "spatial p05–p95", size=11, color="#172b36"),
        '<line x1="535" y1="492" x2="570" y2="492" stroke="#7050a7" stroke-width="2" stroke-dasharray="7 6"/>',
        _svg_text(580, legend_y, "descriptive linear trend", size=11, color="#172b36"),
        _svg_text(52, 525, "Scientific validation: BLOCKED. This plot does not establish convergence, mesh independence, or cleanroom performance.", size=10, color="#627481"),
        "</svg>",
    ])
    return "\n".join(parts) + "\n"
