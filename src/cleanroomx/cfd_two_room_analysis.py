"""Receipt-bound two-room diagnostic charts from real Foundation v10 outputs.

The analysis is descriptive and diagnostic only. Validating source hashes does
not validate the solver physics, mesh independence, or measured performance.
"""
from __future__ import annotations

import hashlib
from html import escape
import json
import math
from pathlib import Path, PurePosixPath
from typing import Any

from .cfd_proofgraph import _hash_regular_file, _read_json, proofgraph_from_two_room_receipt
from .cfd_audit import _RESIDUAL, _CONTINUITY, _FATAL, MAX_LOG_BYTES
from .cfd_two_room import compute_pressure_difference_pa, parse_pressure_probe_data
from .cfd_vtk import import_vtk_case, _read_vtk, MAX_VTK_BYTES


def _finite(value: Any, label: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return float(value)


def _probe_series(text: str, density: float, expected: dict[str, Any]) -> list[dict[str, float]]:
    verified = parse_pressure_probe_data(text)
    if verified["sample_count"] != expected.get("sample_count"):
        raise ValueError("Probe sample count disagrees with the receipt")
    if verified["last_time"] != expected.get("last_solver_time"):
        raise ValueError("Probe final solver index disagrees with the receipt")
    samples: list[dict[str, float]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        index, room1, room2 = map(float, line.split())
        result = compute_pressure_difference_pa(
            {"kinematic_pressure_m2_s2": [room1, room2]}, density
        )
        if not all(math.isfinite(value) for value in result.values()):
            raise ValueError("Probe pressure conversion overflowed the declared density")
        samples.append({
            "solver_index": index,
            "room_1_pressure_pa_gauge": result["room_1_pressure_pa_gauge"],
            "room_2_pressure_pa_gauge": result["room_2_pressure_pa_gauge"],
            "delta_pressure_pa": result["delta_pressure_pa_room_1_minus_room_2"],
        })
    final = samples[-1]
    for key, actual in (
        ("room_1_pressure_pa_gauge", final["room_1_pressure_pa_gauge"]),
        ("room_2_pressure_pa_gauge", final["room_2_pressure_pa_gauge"]),
        ("delta_pressure_pa_room_1_minus_room_2", final["delta_pressure_pa"]),
    ):
        recorded = _finite(expected.get(key), key)
        if not math.isclose(actual, recorded, rel_tol=1e-12, abs_tol=1e-10):
            raise ValueError(f"Recomputed probe value differs from receipt: {key}")
    return samples


def _weighted_distribution(samples: list[tuple[float, float]], unit: str) -> dict[str, Any]:
    if not samples:
        raise ValueError("Cannot summarize an empty cell field")
    ordered = sorted((_finite(x, "field"), _finite(w, "cell_volume")) for x, w in samples)
    if any(w <= 0 for _, w in ordered):
        raise ValueError("Distribution requires positive cell volumes")
    total = math.fsum(w for _, w in ordered)
    mean = math.fsum(x * w for x, w in ordered) / total
    if not all(map(math.isfinite, (total, mean))):
        raise ValueError("Distribution numeric overflow")
    def percentile(fraction: float) -> float:
        threshold = total * fraction
        cumulative = 0.0
        for value, weight in ordered:
            cumulative += weight
            if cumulative >= threshold:
                return value
        return ordered[-1][0]
    low, high = ordered[0][0], ordered[-1][0]
    bins = [0.0] * 12
    for value, weight in ordered:
        slot = min(11, int((value - low) / (high - low) * 12)) if high > low else 0
        bins[slot] += weight
    return {
        "units": unit,
        "cell_count": len(samples),
        "sampled_volume_m3": total,
        "minimum": low,
        "maximum": high,
        "volume_weighted_mean": mean,
        "volume_weighted_p05": percentile(0.05),
        "volume_weighted_median": percentile(0.5),
        "volume_weighted_p95": percentile(0.95),
        "bin_edges": [low + (high - low) * i / 12 for i in range(13)],
        "bin_volume_percent": [100.0 * w / total for w in bins],
        "weighting": "vtk_cell_volume",
    }


def _vtk_room_fields(case: Path, vtk_assets: dict[str, str], room_length: float, density: float) -> dict[str, Any]:
    # Boundary-patch surface datasets are deliberately excluded.
    volume_paths = sorted(
        name for name in vtk_assets
        if len(PurePosixPath(name).parts) == 2 and name.lower().endswith((".vtk", ".vtu"))
    )
    if not volume_paths:
        return {"status": "UNAVAILABLE", "reason": "no_receipt_bound_volume_vtk"}
    if len(volume_paths) != 1:
        raise ValueError("Expected exactly one final-time receipt-bound volume VTK dataset")
    relative = volume_paths[0]
    path = case.joinpath(*PurePosixPath(relative).parts)
    digest, _ = _hash_regular_file(path, max_bytes=MAX_VTK_BYTES)
    if digest != vtk_assets[relative]:
        raise ValueError("VTK input changed after ProofGraph verification")
    imported = import_vtk_case(
        path,
        field_map={
            "schema_version": "cleanroomx.cfd-vtk-field-map.v1",
            "fields": {"p": {"semantic": "kinematic_pressure", "units": "m2/s2"}},
        },
    )
    grid = _read_vtk(path)
    try:
        import vtk
    except ImportError as error:
        raise RuntimeError("VTK field diagnostics require pip install vtk") from error
    centers = vtk.vtkCellCenters()
    centers.SetInputData(grid)
    centers.Update()
    points = centers.GetOutput().GetPoints()
    if points is None or points.GetNumberOfPoints() != len(imported["cells"]):
        raise ValueError("VTK cell centers do not match imported field cells")
    p_data = imported.get("field_data", {}).get("kinematic_pressure")
    p_values = p_data["values"] if p_data is not None else None
    grouped: dict[str, dict[str, list[tuple[float, float]]]] = {
        "room_1": {"speed": [], "pressure": []},
        "room_2": {"speed": [], "pressure": []},
    }
    for i, cell in enumerate(imported["cells"]):
        x = _finite(points.GetPoint(i)[0], "cell_center_x")
        if x < 0 or x > 2 * room_length or x == room_length:
            raise ValueError("VTK cell is outside the two-room center partition")
        room = "room_1" if x < room_length else "room_2"
        volume = cell["volume_m3"]
        speed = math.sqrt(math.fsum(component * component for component in cell["velocity_m_s"]))
        grouped[room]["speed"].append((speed, volume))
        if p_values is not None:
            grouped[room]["pressure"].append((_finite(p_values[i], "kinematic_pressure") * density, volume))
    if not grouped["room_1"]["speed"] or not grouped["room_2"]["speed"]:
        raise ValueError("VTK does not contain volume cells from both rooms")
    digest_after, _ = _hash_regular_file(path, max_bytes=MAX_VTK_BYTES)
    if digest_after != digest or imported["source_sha256"] != digest:
        raise ValueError("VTK content changed during analysis")
    return {
        "status": "MEASURED_DIAGNOSTIC_ONLY",
        "source_path": relative,
        "source_sha256": digest,
        "pressure_availability": "measured_kinematic_pressure_converted_with_declared_density" if p_values is not None else "NOT_AVAILABLE_IN_VTK",
        "rooms": {
            name: {
                "velocity_magnitude": _weighted_distribution(fields["speed"], "m/s"),
                "pressure_gauge": _weighted_distribution(fields["pressure"], "Pa") if fields["pressure"] else {
                    "status": "UNAVAILABLE", "reason": "p_not_present_in_cell_data"
                },
            }
            for name, fields in grouped.items()
        },
    }



def _solver_residual_history(case: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    """Read actual simpleFoam linear-solver residuals; do not assert convergence."""
    logs = [stage for stage in receipt["stages"] if stage.get("command") == "simpleFoam"]
    if len(logs) != 1 or logs[0].get("log_path") != "simpleFoam.log":
        raise ValueError("Receipt does not bind a unique simpleFoam log")
    log_path = case / "simpleFoam.log"
    digest, size = _hash_regular_file(log_path, max_bytes=MAX_LOG_BYTES)
    if digest != logs[0]["log_sha256"]:
        raise ValueError("simpleFoam log changed after evidence verification")
    raw = log_path.read_bytes()
    if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("simpleFoam log changed during residual ingestion")
    content = raw.decode("utf-8", errors="strict")
    fields: dict[str, dict[str, list[float]]] = {}
    count = 0
    for match in _RESIDUAL.finditer(content):
        name = match.group(1)
        initial = float(match.group(2))
        final = float(match.group(3))
        if not all(math.isfinite(v) and v >= 0 for v in (initial, final)):
            raise ValueError("Solver log contains non-finite or negative residual")
        values = fields.setdefault(name, {"initial": [], "final": []})
        values["initial"].append(initial)
        values["final"].append(final)
        count += 1
        if count > 16000 or len(fields) > 24:
            raise ValueError("Solver residual history exceeds bounded chart capacity")
    continuity = []
    for match in _CONTINUITY.finditer(content):
        local, global_error = map(float, match.groups())
        if not all(math.isfinite(v) for v in (local, global_error)):
            raise ValueError("Solver log has nonfinite reported continuity")
        continuity.append({"sum_local": local, "global": global_error})
        if len(continuity) > 16000:
            raise ValueError("Continuity history exceeds bounded chart capacity")
    return {
        "status": "DIAGNOSTIC_ONLY" if fields else "UNAVAILABLE",
        "solver_log_sha256": digest,
        "fatal_or_nonfinite_marker": bool(_FATAL.search(content)),
        "fields": fields,
        "continuity": continuity,
        "sequence_axis": "per-field linear solve sequence, not physical time or coupled convergence proof",
        "solver_convergence": "NOT_ASSESSED",
        "criteria": "NOT_SUPPLIED",
    }



def analyze_two_room_evidence(case_directory: str | Path, receipt_path: str | Path) -> dict[str, Any]:
    """Analyze only artifacts checked by the existing ProofGraph receipt gate."""
    # Performs strict input, receipt, stage-log, phi, probe, and entire VTK-set hash verification.
    proofgraph_from_two_room_receipt(case_directory, receipt_path)
    case = Path(case_directory).resolve(strict=True)
    receipt, _ = _read_json(Path(receipt_path), max_bytes=2 * 1024 * 1024)
    manifest, _ = _read_json(case / "manifest.json", max_bytes=2 * 1024 * 1024)
    spec = manifest["spec"]
    density = _finite(spec["density_kg_m3"], "density_kg_m3")
    probe = receipt["pressure_probe"]
    relative = PurePosixPath(probe["path"])
    probe_path = case.joinpath(*relative.parts)
    probe_digest, probe_size = _hash_regular_file(probe_path, max_bytes=4 * 1024 * 1024)
    if probe_digest != probe["sha256"]:
        raise ValueError("Probe changed after evidence verification")
    raw = probe_path.read_bytes()
    if len(raw) != probe_size or hashlib.sha256(raw).hexdigest() != probe_digest:
        raise ValueError("Probe changed during analysis")
    samples = _probe_series(raw.decode("utf-8"), density, probe)
    flow = receipt["engineering_screens"]
    inlet = _finite(flow["actual_inlet_flow_m3_s"], "actual_inlet_flow_m3_s")
    outlet = _finite(flow["actual_outlet_flow_m3_s"], "actual_outlet_flow_m3_s")
    if inlet < 0 or outlet < 0:
        raise ValueError("Measured inlet or outlet flow cannot be negative")
    recorded_flux = receipt["solver_flux"]
    for label, nested, recorded in (
        ("inlet", "net_inward_m3_s", inlet),
        ("outlet", "net_outward_m3_s", outlet),
    ):
        source = recorded_flux.get(label)
        if type(source) is not dict or not math.isclose(
            _finite(source.get(nested), f"solver_flux.{label}"), recorded,
            rel_tol=1e-10, abs_tol=1e-12,
        ):
            raise ValueError(f"Solver phi flow and engineering screen disagree at {label}")
    mean_flow = (inlet + outlet) / 2
    if mean_flow <= 0:
        raise ValueError("Cannot calculate balance with zero inlet and outlet flow")
    expected_imbalance = 100 * abs(inlet - outlet) / mean_flow
    recorded_imbalance = _finite(
        flow["relative_inlet_outlet_difference_percent"], "relative_inlet_outlet_difference_percent"
    )
    if not math.isclose(expected_imbalance, recorded_imbalance, rel_tol=1e-9, abs_tol=1e-8):
        raise ValueError("Inlet/outlet relative difference disagrees with measured solver flux")
    target = _finite(flow["pressure_target_pa"], "pressure_target_pa")
    tolerance = _finite(flow["pressure_tolerance_pa"], "pressure_tolerance_pa")
    if tolerance <= 0 or target <= 0:
        raise ValueError("Pressure screen target and tolerance must be positive")
    expected_screen = (
        "within_declared_band"
        if abs(samples[-1]["delta_pressure_pa"] - target) <= tolerance
        else "outside_declared_band"
    )
    if flow["pressure_target_screen"] != expected_screen:
        raise ValueError("Pressure target screen disagrees with final verified probe values")
    result = {
        "schema_version": "cleanroomx.cfd-two-room-analysis.v1",
        "status": "DIAGNOSTIC_ONLY",
        "scientific_validation": "BLOCKED",
        "solver_convergence": "NOT_ASSESSED",
        "receipt_sha256": receipt["receipt_sha256"],
        "case_manifest_sha256": receipt["manifest_sha256"],
        "probe_sha256": probe_digest,
        "vtk_assets_sha256": receipt["vtk_assets_sha256"],
        "pressure": {
            "units": "Pa",
            "time_axis": "OpenFOAM solver indices; not physical seconds",
            "density_kg_m3": density,
            "series": samples,
            "target_pa": target,
            "tolerance_pa": tolerance,
            "screen": flow["pressure_target_screen"],
            "meaning": "two probe locations only; not spatial room-average pressure",
        },
        "flow": {
            "inlet_m3_s": inlet,
            "outlet_m3_s": outlet,
            "relative_difference_percent": _finite(
                flow["relative_inlet_outlet_difference_percent"], "relative_difference_percent"
            ),
            "acceptance_criterion": "NOT_SET",
            "meaning": "solver phi patch flux diagnostics; no independent acceptance screen",
        },
        "residual_history": _solver_residual_history(case, receipt),
        "vtk_fields": _vtk_room_fields(
            case, receipt["vtk_assets_sha256"], _finite(spec["room_m"][0], "room_length"), density
        ),
        "not_derived": {
            "air_change_rate": "No room-specific verified supply/extract flux allocation",
            "temperature": "Not solved in the pinned two-room airflow fixture",
            "particle_transport": "Not solved in the pinned two-room airflow fixture",
            "cleanroom_compliance": "Requires independent measurements and engineering criteria",
        },
    }
    return result


def _line_svg(series: list[dict[str, float]], target: float, tolerance: float) -> str:
    series = series[::max(1, math.ceil(len(series) / 1000))]
    xs = [row["solver_index"] for row in series]
    ys = [row["delta_pressure_pa"] for row in series]
    x0, x1 = min(xs), max(xs)
    y0 = min(min(ys), target - tolerance)
    y1 = max(max(ys), target + tolerance)
    if y1 == y0:
        y1 = y0 + 1.0
    if x1 == x0:
        x1 = x0 + 1.0
    xp = lambda x: 70 + 600 * (x - x0) / (x1 - x0)
    yp = lambda y: 240 - 190 * (y - y0) / (y1 - y0)
    polygon = " ".join(f"{xp(x):.2f},{yp(y):.2f}" for x, y in zip(xs, ys))
    band_y = yp(target + tolerance)
    band_h = yp(target - tolerance) - band_y
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="720" height="300" viewBox="0 0 720 300">'
        '<rect width="720" height="300" fill="#fff"/>'
        '<text x="30" y="24" font-size="17">Room 1 - Room 2 probe pressure (Pa)</text>'
        f'<rect x="70" y="{band_y:.2f}" width="600" height="{band_h:.2f}" fill="#dcefe1"/>'
        f'<polyline points="{polygon}" fill="none" stroke="#1464b4" stroke-width="2"/>'
        '<line x1="70" y1="240" x2="670" y2="240" stroke="#333"/>'
        f'<text x="70" y="267" font-size="12">{x0:g}</text>'
        f'<text x="640" y="267" font-size="12">{x1:g}</text>'
        '<text x="255" y="290" font-size="13">OpenFOAM solver index (not seconds)</text>'
        f'<text x="10" y="52" font-size="12">{y1:.3g}</text>'
        f'<text x="10" y="240" font-size="12">{y0:.3g}</text>'
        '<text x="470" y="42" font-size="12">Green: declared target band</text>'
        '</svg>'
    )


def _bars_svg(title: str, labels: list[str], values: list[float], units: str) -> str:
    if len(labels) != len(values) or not 1 <= len(values) <= 3:
        raise ValueError("Graph requires one to three aligned values")
    values = [_finite(x, "bar_value") for x in values]
    low = min(0.0, *values)
    high = max(0.0, *values)
    extent = high - low or 1.0
    margin = extent * 0.1
    low -= margin
    high += margin
    scale = high - low
    yp = lambda value: 235 - 170 * (value - low) / scale
    baseline = yp(0.0)
    bars = []
    for i, (label, value) in enumerate(zip(labels, values)):
        x = 100 + 180 * i
        value_y = yp(value)
        y = min(value_y, baseline)
        height = abs(value_y - baseline)
        text_y = max(40, min(225, value_y - 6 if value >= 0 else value_y + 16))
        bars.append(
            f'<rect x="{x}" y="{y:.2f}" width="85" height="{height:.2f}" fill="#1464b4"/>'
            f'<text x="{x}" y="{text_y:.2f}" font-size="12">{value:.5g}</text>'
            f'<text x="{x}" y="256" font-size="12">{escape(label)}</text>'
        )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="720" height="295" viewBox="0 0 720 295">'
        '<rect width="720" height="295" fill="#fff"/>'
        f'<text x="30" y="24" font-size="17">{escape(title)} ({escape(units)})</text>'
        f'<line x1="70" y1="{baseline:.2f}" x2="670" y2="{baseline:.2f}" stroke="#333"/>'
        + "".join(bars)
        + '</svg>'
    )




def _residual_svg(field: str, records: dict[str, list[float]]) -> str:
    """Plot logarithmic per-field linear-solver residual sequence, without thresholds."""
    initial, final = records["initial"], records["final"]
    if not initial or len(initial) != len(final):
        raise ValueError("Residual chart requires aligned nonempty initial and final values")
    values = [math.log10(max(1e-16, value)) for value in initial + final]
    minimum, maximum = min(values), max(values)
    if maximum <= minimum:
        maximum = minimum + 1.0
    n = len(initial)
    step = max(1, math.ceil(n / 1000))
    xscale = lambda i: 75.0 + 585.0 * i / max(1, n - 1)
    yscale = lambda value: 235.0 - 175.0 * (value - minimum) / (maximum - minimum)
    segments = []
    for key, color in (("initial", "#1464b4"), ("final", "#d96b27")):
        points = " ".join(
            f"{xscale(i):.2f},{yscale(math.log10(max(1e-16, records[key][i]))):.2f}"
            for i in range(0, n, step)
        )
        segments.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="1.8"/>')
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="720" height="305" viewBox="0 0 720 305">'
        '<rect width="720" height="305" fill="#fff"/>'
        f'<text x="28" y="24" font-size="17">simpleFoam residual: {escape(field)}</text>'
        + "".join(segments)
        + '<line x1="70" y1="235" x2="670" y2="235" stroke="#333"/>'
        + '<text x="75" y="260" font-size="12">1</text>'
        + f'<text x="635" y="260" font-size="12">{n}</text>'
        + f'<text x="12" y="60" font-size="12">{maximum:.3g}</text>'
        + f'<text x="12" y="236" font-size="12">{minimum:.3g}</text>'
        + '<text x="225" y="288" font-size="12">Per-field solve number | log10 residual (floor 1e-16)</text>'
        + '<text x="460" y="44" font-size="12">Blue: initial  Orange: final</text>'
        + '</svg>'
    )



def _histogram_svg(title: str, distribution: dict[str, Any]) -> str:
    """Volume-weighted histogram; bins describe samples, not an interpolated contour."""
    fractions = distribution["bin_volume_percent"]
    bounds = distribution["bin_edges"]
    if len(fractions) != 12 or len(bounds) != 13:
        raise ValueError("Invalid binned CFD distribution")
    maximum = max(1.0, *(float(value) for value in fractions))
    bars = []
    for index, fraction in enumerate(fractions):
        amount = _finite(fraction, "bin_volume_percent")
        if not 0 <= amount <= 100:
            raise ValueError("Histogram percentage must be between 0 and 100")
        height = 170 * amount / maximum
        bars.append(
            f'<rect x="{75 + 49 * index}" y="{235-height:.2f}" width="43" '
            f'height="{height:.2f}" fill="#1464b4"/>'
        )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="720" height="300" viewBox="0 0 720 300">'
        '<rect width="720" height="300" fill="#fff"/>'
        f'<text x="28" y="24" font-size="16">{escape(title)}</text>'
        '<line x1="70" y1="235" x2="675" y2="235" stroke="#333"/>'
        + "".join(bars)
        + f'<text x="72" y="258" font-size="12">{bounds[0]:.4g}</text>'
        + f'<text x="619" y="258" font-size="12">{bounds[-1]:.4g}</text>'
        + f'<text x="240" y="285" font-size="12">{escape(distribution["units"])} | % sampled cell volume</text>'
        + '</svg>'
    )




def _offline_dashboard(report: dict[str, Any]) -> str:
    """Self-contained, script-free graph index with explicit evidence boundaries."""
    pressure = report["pressure"]
    last = pressure["series"][-1]
    flow = report["flow"]
    title = "CleanroomX | Two-room CFD diagnostic review"
    figures = []
    for filename in report["graphs"]:
        if not filename.endswith(".svg") or "/" in filename or "\\" in filename:
            raise ValueError("Dashboard graph path must be a local SVG basename")
        label = escape(filename.removesuffix(".svg").replace("_", " ").title())
        figures.append(
            '<figure class="panel">'
            f'<figcaption>{label}</figcaption>'
            f'<a href="{escape(filename, quote=True)}" title="Open source SVG">'
            f'<img loading="lazy" src="{escape(filename, quote=True)}" alt="{label}"/></a>'
            '</figure>'
        )
    cards = (
        ("Final probe Δp", f'{last["delta_pressure_pa"]:.5g} Pa'),
        ("Target band", f'{pressure["target_pa"]:.5g} ± {pressure["tolerance_pa"]:.5g} Pa'),
        ("Inlet / outlet", f'{flow["inlet_m3_s"]:.5g} / {flow["outlet_m3_s"]:.5g} m³/s'),
        ("Flow imbalance", f'{flow["relative_difference_percent"]:.5g}%'),
        ("VTK room fields", report["vtk_fields"]["status"]),
    )
    metrics = "".join(
        f'<div class="metric"><small>{escape(label)}</small><strong>{escape(value)}</strong></div>'
        for label, value in cards
    )
    missing = "".join(
        f'<li><strong>{escape(k.replace("_", " ").title())}:</strong> {escape(v)}</li>'
        for k, v in report["not_derived"].items()
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{escape(title)}</title>
<style>
:root {{color-scheme:dark;font:15px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif}}
* {{box-sizing:border-box}}
body {{margin:0;background:#0b1220;color:#e4ebf5}}
header,main,footer {{max-width:1380px;margin:auto;padding:26px 26px}}
header {{border-bottom:1px solid #293a52}}
h1 {{font-size:clamp(1.4rem,3vw,2.3rem);line-height:1.2;margin:9px 0}}
h2 {{font-size:1.15rem;margin-top:32px}}
.eyebrow {{color:#90b9eb;font-weight:700;letter-spacing:.08em;text-transform:uppercase}}
.notice {{padding:14px 18px;border-left:4px solid #f5ae54;background:#252132;border-radius:6px}}
.metrics {{display:grid;grid-template-columns:repeat(auto-fit,minmax(205px,1fr));gap:12px;margin:23px 0}}
.metric,.panel {{border:1px solid #2c3e54;border-radius:12px;background:#152237}}
.metric {{padding:17px;min-height:110px}}
small {{display:block;color:#a6b9cc}}
strong {{display:block;font-weight:650;margin-top:6px;overflow-wrap:anywhere}}
.metric strong {{font-size:1.25rem}}
.plots {{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,450px),1fr));gap:16px}}
figure {{margin:0;overflow:hidden}}
figcaption {{padding:14px 17px;font-weight:650}}
img {{display:block;width:100%;height:auto;background:white}}
a {{color:#a6d0ff}}
li {{margin:.5rem 0}}
footer {{font-size:.9rem;color:#a6b9cc;border-top:1px solid #293a52}}
</style></head>
<body><header><div class="eyebrow">CleanroomX · solver-backed evidence</div>
<h1>Two-room CFD diagnostic review</h1>
<p>Offline report based on a locally verified OpenFOAM Foundation v10 run.</p></header>
<main><div class="notice"><strong>Scientific validation: BLOCKED · Solver convergence: NOT ASSESSED</strong>
<p>Graphs describe synthetic-case CFD diagnostics. Hash consistency is not solver
authenticity, physical measurement correlation, cleanroom compliance, or certification.
Pressure probes are not spatial room-average measurements.</p></div>
<section aria-label="Run diagnostics"><div class="metrics">{metrics}</div></section>
<h2>Verified CFD charts</h2><section class="plots" aria-label="Graphs">
{''.join(figures)}</section>
<h2>Unavailable or unsupported metrics</h2><ul>{missing}</ul>
<p>Numerical provenance and complete datasets: <a href="analysis.json">analysis.json</a>.</p>
</main><footer>Receipt SHA-256: {escape(report["receipt_sha256"])} ·
Case manifest SHA-256: {escape(report["case_manifest_sha256"])}</footer></body></html>
"""



def export_two_room_analysis(
    case_directory: str | Path, receipt_path: str | Path, output_directory: str | Path
) -> dict[str, Any]:
    """Write reproducible diagnostic JSON and SVG files; never overwrite outputs."""
    report = analyze_two_room_evidence(case_directory, receipt_path)
    destination = Path(output_directory).expanduser()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("refusing to overwrite an existing CFD analysis directory")
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        raise ValueError("Analysis output parent must be an existing regular directory")
    graphs = {
        "pressure_probe_history.svg": _line_svg(
            report["pressure"]["series"], report["pressure"]["target_pa"], report["pressure"]["tolerance_pa"]
        ),
        "inlet_outlet_flux.svg": _bars_svg(
            "Final-time solver patch flow", ["Inlet", "Outlet"],
            [report["flow"]["inlet_m3_s"], report["flow"]["outlet_m3_s"]], "m3/s"
        ),
    }
    vtk = report["vtk_fields"]
    if vtk["status"] == "MEASURED_DIAGNOSTIC_ONLY":
        rooms = vtk["rooms"]
        graphs["room_velocity_comparison.svg"] = _bars_svg(
            "Volume-weighted mean velocity magnitude", ["Room 1", "Room 2"],
            [rooms[name]["velocity_magnitude"]["volume_weighted_mean"] for name in ("room_1", "room_2")],
            "m/s",
        )
        if vtk["pressure_availability"] != "NOT_AVAILABLE_IN_VTK":
            graphs["room_pressure_comparison.svg"] = _bars_svg(
                "Volume-weighted mean gauge pressure", ["Room 1", "Room 2"],
                [rooms[name]["pressure_gauge"]["volume_weighted_mean"] for name in ("room_1", "room_2")],
                "Pa",
            )
    if vtk["status"] == "MEASURED_DIAGNOSTIC_ONLY":
        for room in ("room_1", "room_2"):
            dist = vtk["rooms"][room]
            graphs[f"{room}_speed_distribution.svg"] = _histogram_svg(
                f"{room.replace('_', ' ').title()}: velocity magnitude distribution", dist["velocity_magnitude"]
            )
            if dist["pressure_gauge"].get("status") != "UNAVAILABLE":
                graphs[f"{room}_pressure_distribution.svg"] = _histogram_svg(
                    f"{room.replace('_', ' ').title()}: gauge pressure distribution", dist["pressure_gauge"]
                )
    for field, samples in sorted(report["residual_history"]["fields"].items())[:8]:
        graphs[f"simplefoam_residual_{field}.svg"] = _residual_svg(field, samples)
    report["graphs"] = sorted(graphs)
    destination.mkdir(exist_ok=False)
    (destination / "analysis.json").write_text(
        json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    for filename, svg in graphs.items():
        (destination / filename).write_text(svg + "\n", encoding="utf-8")
    (destination / "index.html").write_text(_offline_dashboard(report), encoding="utf-8")
    return {"status": "DIAGNOSTIC_ONLY", "directory": str(destination), "graphs": report["graphs"],
            "scientific_validation": "BLOCKED", "receipt_sha256": report["receipt_sha256"]}
