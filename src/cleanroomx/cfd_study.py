"""Evidence-gated post-processing of externally computed cleanroom CFD fields.

This module DOES NOT solve the Navier-Stokes or species-transport equations.
It never substitutes observations from a teaching document for solver results.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any

SCHEMA = "cleanroomx.cfd-study.v1"
CONFIGURATIONS = {
    1: {"inlet": "central_ceiling", "exhaust": "low_level_wall", "raised_floor": False},
    2: {"inlet": "distributed_ceiling", "exhaust": "low_level_wall", "raised_floor": False},
    3: {"inlet": "distributed_ceiling", "exhaust": "perforated_raised_floor", "raised_floor": True},
}
METRICS_TO_MINIMIZE = (
    "contaminant_exceedance_volume_fraction",
    "recirculation_volume_fraction",
    "velocity_nonuniformity_cv",
)


def _obj(value: Any, allowed: set[str], context: str) -> dict:
    if type(value) is not dict:
        raise ValueError(f"{context} must be an object")
    bad = sorted(set(value) - allowed)
    if bad:
        raise ValueError(f"{context} has unsupported field(s): {', '.join(bad)}")
    return value


def _number(value: Any, context: str, *, positive: bool = False, nonnegative: bool = False) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{context} must be a finite number")
    if positive and value <= 0:
        raise ValueError(f"{context} must be positive")
    if nonnegative and value < 0:
        raise ValueError(f"{context} must be nonnegative")
    return float(value)


def _string(value: Any, context: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{context} must be nonempty text")
    return value


def _position(value: Any, context: str, dimensions: list[float] | None) -> list[float]:
    if type(value) is not list or len(value) != 3:
        raise ValueError(f"{context} must contain three coordinates in metres")
    pos = [_number(v, context, nonnegative=True) for v in value]
    if dimensions is not None and any(v > lim for v, lim in zip(pos, dimensions)):
        raise ValueError(f"{context} is outside the cleanroom")
    return pos


def validate_study(data: Any) -> dict:
    study = _obj(data, {"schema_version", "name", "room", "analysis", "cases"}, "study")
    if study.get("schema_version") != SCHEMA:
        raise ValueError(f"schema_version must equal {SCHEMA}")
    _string(study.get("name"), "name")
    dimensions = None
    if study.get("room") is not None:
        room = _obj(study["room"], {"length_m", "width_m", "height_m"}, "room")
        dimensions = [_number(room[k], f"room.{k}", positive=True) for k in ("length_m", "width_m", "height_m")]
    settings = _obj(study.get("analysis", {}), {
        "contaminant_limit", "contaminant_unit", "max_unrepresented_volume_fraction",
        "max_flow_imbalance_fraction",
    }, "analysis")
    limit = settings.get("contaminant_limit")
    if limit is not None:
        _number(limit, "analysis.contaminant_limit", nonnegative=True)
        _string(settings.get("contaminant_unit"), "analysis.contaminant_unit")
    elif settings.get("contaminant_unit") is not None:
        raise ValueError("contaminant_unit requires contaminant_limit")
    for key in ("max_unrepresented_volume_fraction", "max_flow_imbalance_fraction"):
        if settings.get(key) is not None:
            value = _number(settings[key], "analysis." + key, nonnegative=True)
            if value > 1:
                raise ValueError(f"analysis.{key} must not exceed 1")
    cases = study.get("cases")
    if type(cases) is not list or not 1 <= len(cases) <= 3:
        raise ValueError("cases must be a list containing one to three configurations")
    seen = set()
    for case in cases:
        case = _obj(case, {
            "configuration", "source_location_m", "inlet_flow_m3_s", "outlet_flow_m3_s",
            "solver", "cells", "exhaust_capture_fraction",
        }, "case")
        cid = case.get("configuration")
        if type(cid) is not int or cid not in CONFIGURATIONS or cid in seen:
            raise ValueError("case configuration must be unique and one of 1, 2, 3")
        seen.add(cid)
        if case.get("source_location_m") is not None:
            _position(case["source_location_m"], f"case {cid} source_location_m", dimensions)
        for key in ("inlet_flow_m3_s", "outlet_flow_m3_s"):
            if case.get(key) is not None:
                _number(case[key], f"case {cid} {key}", positive=True)
        if case.get("exhaust_capture_fraction") is not None:
            capture = _number(case["exhaust_capture_fraction"], "exhaust_capture_fraction", nonnegative=True)
            if capture > 1:
                raise ValueError("exhaust_capture_fraction must not exceed 1")
        solver = case.get("solver")
        if solver is not None:
            solver = _obj(solver, {"name", "run_id", "mesh_cells", "source_reference"}, "solver")
            for key in ("name", "run_id", "source_reference"):
                _string(solver.get(key), "solver." + key)
            mesh = solver.get("mesh_cells")
            if type(mesh) is not int or mesh <= 0:
                raise ValueError("solver.mesh_cells must be a positive integer")
        cells = case.get("cells", [])
        if type(cells) is not list or len(cells) > 100_000:
            raise ValueError("cells must be a list of at most 100000 sampled cells")
        if cells and (dimensions is None or solver is None):
            raise ValueError("sampled cells require room geometry and solver provenance")
        for cell in cells:
            cell = _obj(cell, {"volume_m3", "velocity_m_s", "contaminant_concentration", "recirculating"}, "cell")
            _number(cell.get("volume_m3"), "cell.volume_m3", positive=True)
            velocity = cell.get("velocity_m_s")
            if type(velocity) is not list or len(velocity) != 3:
                raise ValueError("cell.velocity_m_s must contain three components")
            for component in velocity:
                _number(component, "cell.velocity_m_s")
            if cell.get("contaminant_concentration") is not None:
                _number(cell["contaminant_concentration"], "cell.contaminant_concentration", nonnegative=True)
                if limit is None:
                    raise ValueError("contaminant samples require an explicit project contaminant_limit and unit")
            if cell.get("recirculating") is not None and type(cell["recirculating"]) is not bool:
                raise ValueError("cell.recirculating must be a Boolean solver classification")
        if cells and sum(cell["volume_m3"] for cell in cells) > math.prod(dimensions) * (1 + 1e-9):
            raise ValueError("sampled CFD cell volumes exceed cleanroom volume")
    return study


def _metrics(case: dict, room_volume: float | None, settings: dict) -> dict:
    cells = case.get("cells", [])
    supplied = sum(cell["volume_m3"] for cell in cells)
    covered = supplied / room_volume if room_volume and cells else None
    result = {
        "sampled_cell_count": len(cells),
        "sampled_volume_m3": supplied,
        "volume_coverage_fraction": covered,
        "velocity_mean_m_s": None,
        "velocity_nonuniformity_cv": None,
        "recirculation_volume_fraction": None,
        "contaminant_mean": None,
        "contaminant_max": None,
        "contaminant_exceedance_volume_fraction": None,
        "exhaust_capture_fraction": case.get("exhaust_capture_fraction"),
        "flow_imbalance_fraction": None,
        "volume_coverage_status": "not_checked",
        "flow_balance_status": "not_checked",
    }
    inlet, outlet = case.get("inlet_flow_m3_s"), case.get("outlet_flow_m3_s")
    if inlet is not None and outlet is not None:
        imbalance = abs(inlet - outlet) / inlet
        result["flow_imbalance_fraction"] = imbalance
        if settings.get("max_flow_imbalance_fraction") is not None:
            result["flow_balance_status"] = (
                "pass" if imbalance <= settings["max_flow_imbalance_fraction"] + 1e-12 else "fail"
            )
    if not cells:
        return result
    tolerance = settings.get("max_unrepresented_volume_fraction")
    if tolerance is not None:
        result["volume_coverage_status"] = "pass" if covered >= 1 - tolerance - 1e-12 else "fail"
    speeds = [math.sqrt(sum(v * v for v in cell["velocity_m_s"])) for cell in cells]
    mean = sum(c["volume_m3"] * v for c, v in zip(cells, speeds)) / supplied
    variance = sum(c["volume_m3"] * (v - mean)**2 for c, v in zip(cells, speeds)) / supplied
    result["velocity_mean_m_s"] = mean
    result["velocity_nonuniformity_cv"] = math.sqrt(variance) / mean if mean > 0 else None
    if all(type(c.get("recirculating")) is bool for c in cells):
        result["recirculation_volume_fraction"] = sum(
            c["volume_m3"] for c in cells if c["recirculating"]
        ) / supplied
    if all(c.get("contaminant_concentration") is not None for c in cells):
        concentrations = [c["contaminant_concentration"] for c in cells]
        result["contaminant_mean"] = sum(c["volume_m3"] * conc for c, conc in zip(cells, concentrations)) / supplied
        result["contaminant_max"] = max(concentrations)
        limit = settings["contaminant_limit"]
        result["contaminant_exceedance_volume_fraction"] = sum(
            c["volume_m3"] for c in cells if c["contaminant_concentration"] > limit
        ) / supplied
    return result


def analyze_cfd_study(data: dict) -> dict:
    """Compare external CFD runs, never claiming certification or solving CFD."""
    validate_study(data)
    settings = data.get("analysis", {})
    room = data.get("room")
    room_volume = room["length_m"] * room["width_m"] * room["height_m"] if room else None
    results = []
    for case in sorted(data["cases"], key=lambda x: x["configuration"]):
        results.append({"configuration": case["configuration"], "layout": CONFIGURATIONS[case["configuration"]],
                        "solver": case.get("solver"), "metrics": _metrics(case, room_volume, settings)})
    blockers = []
    if len(results) != 3:
        blockers.append("All three ventilation configurations are required for comparison")
    if room_volume is None:
        blockers.append("Room dimensions were not supplied")
    if settings.get("contaminant_limit") is None:
        blockers.append("Project-specific contaminant limit/unit were not supplied")
    if settings.get("max_unrepresented_volume_fraction") is None:
        blockers.append("Project-specific CFD sampled-volume coverage tolerance was not supplied")
    if settings.get("max_flow_imbalance_fraction") is None:
        blockers.append("Project-specific supply/exhaust flow balance tolerance was not supplied")
    solver_names = set()
    source_positions = set()
    inlet_flows, outlet_flows = set(), set()
    for case, result in zip(sorted(data["cases"], key=lambda x:x["configuration"]), results):
        cid = case["configuration"]
        m = result["metrics"]
        if case.get("solver") is None:
            blockers.append(f"Configuration {cid}: missing external solver run/provenance")
        else:
            solver_names.add(case["solver"]["name"])
        if case.get("source_location_m") is None:
            blockers.append(f"Configuration {cid}: missing contamination source location")
        else:
            source_positions.add(tuple(case["source_location_m"]))
        if case.get("inlet_flow_m3_s") is None or case.get("outlet_flow_m3_s") is None:
            blockers.append(f"Configuration {cid}: missing inlet/outlet airflow boundary conditions")
        else:
            inlet_flows.add(case["inlet_flow_m3_s"])
            outlet_flows.add(case["outlet_flow_m3_s"])
        if m["volume_coverage_status"] != "pass" or m["flow_balance_status"] != "pass":
            blockers.append(f"Configuration {cid}: missing or failed coverage/flow-balance gates")
        for key in METRICS_TO_MINIMIZE:
            if m[key] is None:
                blockers.append(f"Configuration {cid}: missing {key} solver evidence")
    if len(solver_names) > 1:
        blockers.append("Solver names differ across runs; harmonize provenance before comparison")
    if len(source_positions) > 1:
        blockers.append("Contamination source positions differ across runs")
    if len(inlet_flows) > 1 or len(outlet_flows) > 1:
        blockers.append("Airflow boundary conditions differ across runs")
    winner = None
    if not blockers:
        for candidate in results:
            competitors = [r for r in results if r is not candidate]
            cm = candidate["metrics"]
            if all(
                all(cm[k] <= other["metrics"][k] + 1e-12 for k in METRICS_TO_MINIMIZE)
                and any(cm[k] < other["metrics"][k] - 1e-12 for k in METRICS_TO_MINIMIZE)
                for other in competitors
            ):
                winner = candidate["configuration"]
                break
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return {
        "schema_version": SCHEMA,
        "study_name": data["name"],
        "analysis_kind": "external_cfd_field_postprocessing_not_a_cfd_solver",
        "assumed_ventilation_mode": "single_pass_fresh_air",
        "room_volume_m3": room_volume,
        "contaminant_unit": settings.get("contaminant_unit"),
        "cases": results,
        "comparison_status": "comparable" if not blockers else "insufficient_evidence",
        "comparison_blockers": blockers,
        "unique_pareto_dominant_configuration": winner,
        "source_document_observation": "The teaching PDF qualitatively preferred Configuration 3; not treated as computed evidence.",
        "input_canonical_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "engineering_boundary": "Not CFD simulation, cleanroom certification, or design/commissioning approval",
    }
