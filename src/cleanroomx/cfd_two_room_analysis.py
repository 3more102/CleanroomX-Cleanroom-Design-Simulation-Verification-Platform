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
            "target_pa": _finite(flow["pressure_target_pa"], "pressure_target_pa"),
            "tolerance_pa": _finite(flow["pressure_tolerance_pa"], "pressure_tolerance_pa"),
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
    report["graphs"] = sorted(graphs)
    destination.mkdir(exist_ok=False)
    (destination / "analysis.json").write_text(
        json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    for filename, svg in graphs.items():
        (destination / filename).write_text(svg + "\n", encoding="utf-8")
    return {"status": "DIAGNOSTIC_ONLY", "directory": str(destination), "graphs": report["graphs"],
            "scientific_validation": "BLOCKED", "receipt_sha256": report["receipt_sha256"]}
