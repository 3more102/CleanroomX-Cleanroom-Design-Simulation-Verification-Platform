"""Three-grid CFD discretization-error screening using external VTK fields.

Based on Richardson extrapolation and Roache's GCI as described by NASA
Glenn. This is NOT a CFD solver, independent validation, or proof that a
simulation is in the asymptotic convergence range.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re

from .cfd_audit import audit_openfoam_log
from .cfd_vtk import import_vtk_case

SCHEMA = "cleanroomx.cfd-grid-study.v1"
LEVELS = ("fine", "medium", "coarse")
QUANTITIES = {"velocity_mean_m_s": "m/s", "contaminant_mean": None}
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def _mapping(value, keys, context):
    if type(value) is not dict or set(value) != keys:
        raise ValueError(f"{context} requires exactly {sorted(keys)}")
    return value


def _number(value, name, *, positive=False, nonnegative=False):
    if type(value) not in (float, int) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite, non-boolean number")
    if positive and value <= 0:
        raise ValueError(f"{name} must be positive")
    if nonnegative and value < 0:
        raise ValueError(f"{name} must be nonnegative")
    return float(value)


def _nonempty(value, name):
    if type(value) is not str or not value.strip():
        raise ValueError(f"{name} must be nonempty text")
    return value


def validate_grid_spec(data):
    _mapping(data, {"schema_version", "name", "configuration",
                    "room_volume_m3", "quantity", "unit", "criteria",
                    "log_audit", "runs"}, "grid study")
    if data["schema_version"] != SCHEMA:
        raise ValueError("Unsupported CFD grid-study schema")
    _nonempty(data["name"], "name")
    if type(data["configuration"]) is not int or data["configuration"] not in (1, 2, 3):
        raise ValueError("configuration must be integer 1, 2, or 3")
    _number(data["room_volume_m3"], "room_volume_m3", positive=True)
    quantity = data["quantity"]
    if quantity not in QUANTITIES or type(quantity) is not str:
        raise ValueError("quantity must be velocity_mean_m_s or contaminant_mean")
    _nonempty(data["unit"], "unit")
    if QUANTITIES[quantity] is not None and data["unit"] != QUANTITIES[quantity]:
        raise ValueError("Velocity mean must have unit m/s")
    criteria = _mapping(data["criteria"], {
        "min_refinement_ratio", "max_relative_volume_error",
        "min_observed_order", "max_observed_order", "max_fine_gci_percent",
        "safety_factor", "max_axis_ratio_spread",
    }, "criteria")
    if _number(criteria["min_refinement_ratio"], "min_refinement_ratio") < 1.1:
        raise ValueError("min_refinement_ratio must be >= 1.1")
    for name in ("max_relative_volume_error", "max_fine_gci_percent",
                 "max_axis_ratio_spread"):
        _number(criteria[name], name, nonnegative=True)
    if criteria["max_relative_volume_error"] > 1 or criteria["max_axis_ratio_spread"] > 1:
        raise ValueError("Relative volume error and axis ratio spread must be <= 1")
    pmin = _number(criteria["min_observed_order"], "min_observed_order", positive=True)
    pmax = _number(criteria["max_observed_order"], "max_observed_order", positive=True)
    if pmin >= pmax or pmax > 12:
        raise ValueError("Require min_observed_order < max_observed_order <= 12")
    if _number(criteria["safety_factor"], "safety_factor") < 1.25:
        raise ValueError("safety_factor must be >= 1.25")
    audit = _mapping(data["log_audit"], {
        "fields", "window", "max_initial_residual", "max_final_residual",
        "max_global_continuity",
    }, "log_audit")
    if type(audit["fields"]) is not list or not audit["fields"]:
        raise ValueError("log_audit.fields must be a nonempty list")
    if type(audit["window"]) is not int or not 1 <= audit["window"] <= 100:
        raise ValueError("log_audit.window must be an integer 1..100")
    for name in ("max_initial_residual", "max_final_residual"):
        _number(audit[name], name, positive=True)
    if audit["max_global_continuity"] is not None:
        _number(audit["max_global_continuity"], "max_global_continuity", positive=True)
    runs = data["runs"]
    if type(runs) is not list or len(runs) != 3:
        raise ValueError("Exactly three grid resolutions are required")
    indexed = {}
    for run in runs:
        _mapping(run, {"level", "mesh_cells", "vtk_file",
                       "solver_log", "run_id", "conditions_sha256"}, "grid run")
        level = run["level"]
        if type(level) is not str or level not in LEVELS or level in indexed:
            raise ValueError("levels must be unique fine, medium, coarse")
        indexed[level] = run
        dims = run["mesh_cells"]
        if type(dims) is not list or len(dims) != 3 or any(
            type(n) is not int or n <= 0 for n in dims
        ):
            raise ValueError("mesh_cells requires three positive integers")
        for key in ("vtk_file", "solver_log", "run_id"):
            _nonempty(run[key], key)
        if not HEX64.fullmatch(run["conditions_sha256"] or ""):
            raise ValueError("conditions_sha256 must be lowercase SHA-256 hex")
    if set(indexed) != set(LEVELS):
        raise ValueError("levels must contain fine, medium and coarse")
    if len({v["run_id"] for v in runs}) != 3:
        raise ValueError("run_id must differ across resolutions")
    if len({v["vtk_file"] for v in runs}) != 3:
        raise ValueError("VTK sources must differ across resolutions")
    if len({v["solver_log"] for v in runs}) != 3:
        raise ValueError("Solver logs must differ across resolutions")
    return indexed


def _observed_order(h1, h2, h3, f1, f2, f3):
    """Return positive p for monotone three-grid power-law behavior or None."""
    d21=f2-f1
    d32=f3-f2
    if d21 == 0 or d32 == 0 or d21*d32 <= 0:
        return None
    r21=h2/h1
    r32=h3/h2
    ratio=abs(d32/d21)
    def theoretical(p):
        # Stable for small positive p and moderate refinement ratios.
        a=p*math.log(r21)
        b=p*math.log(r32)
        return math.exp(a)*math.expm1(b)/math.expm1(a)
    lo,hi=1e-5,12.0
    if ratio <= theoretical(lo) or ratio >= theoretical(hi):
        return None
    for _ in range(100):
        mid=(lo+hi)/2
        if theoretical(mid) < ratio:
            lo=mid
        else:
            hi=mid
    return (lo+hi)/2


def _analysis(rows, criteria):
    """Rows are fine/medium/coarse finite metric samples with verified cell counts."""
    f1,f2,f3=(r["value"] for r in rows)
    h1,h2,h3=(r["characteristic_h_m"] for r in rows)
    r21=h2/h1
    r32=h3/h2
    blockers=[]
    if r21 < criteria["min_refinement_ratio"] or r32 < criteria["min_refinement_ratio"]:
        blockers.append("Insufficient grid refinement ratio")
    p=_observed_order(h1,h2,h3,f1,f2,f3)
    if p is None:
        blockers.append("No positive three-grid monotonic observed order; oscillation, stagnation or divergence")
    elif not criteria["min_observed_order"] <= p <= criteria["max_observed_order"]:
        blockers.append("Observed order outside project-selected admissible range")
    zero_grid=None
    gci_fine=None
    if p is not None:
        denom=math.expm1(p*math.log(r21))
        if denom>0 and math.isfinite(denom):
            zero_grid=f1+(f1-f2)/denom
            if f1 != 0:
                gci_fine=100*criteria["safety_factor"]*abs(f2-f1)/(abs(f1)*denom)
        if zero_grid is None or not math.isfinite(zero_grid):
            zero_grid=None
            blockers.append("Non-finite Richardson zero-grid estimate")
    if gci_fine is None or not math.isfinite(gci_fine):
        gci_fine=None
        blockers.append("Relative fine-grid GCI unavailable (e.g. fine-grid value is zero)")
    elif gci_fine > criteria["max_fine_gci_percent"]:
        blockers.append("Fine-grid GCI exceeds project threshold")
    return {
        "observed_order":p,
        "richardson_zero_spacing_estimate":zero_grid,
        "fine_grid_gci_percent":gci_fine,
        "refinement_ratios":{"medium_over_fine":r21,"coarse_over_medium":r32},
        "screening_status":"eligible_for_engineering_review" if not blockers else "indeterminate_or_failed",
        "screening_blockers":blockers,
    }


def analyze_vtk_grid_study(data, *, base_directory="."):
    """Compute volume-weighted QoI from REAL VTK cell fields and screen grids.

    External solver data & logs are treated as UNTRUSTED evidence. Identical
    conditions digests are explicit analyst assertions, not independently
    proven equivalent CFD boundary conditions.
    """
    indexed=validate_grid_spec(data)
    settings=data["criteria"]
    base=Path(base_directory).resolve()
    conditions={r["conditions_sha256"] for r in indexed.values()}
    blockers=[]
    if len(conditions)!=1:
        blockers.append("Mesh runs declare different physics/boundary-condition fingerprints")
    rows=[]
    for level in LEVELS:
        run=indexed[level]
        vtk_path=(base/run["vtk_file"]).resolve(strict=True)
        log_path=(base/run["solver_log"]).resolve(strict=True)
        imported=import_vtk_case(vtk_path)
        cell_count=math.prod(run["mesh_cells"])
        if imported["mesh_cells"]!=cell_count:
            blockers.append(f"{level}: VTK cell count does not match specified grid")
        volume=sum(cell["volume_m3"] for cell in imported["cells"])
        rel_volume=abs(volume-data["room_volume_m3"])/data["room_volume_m3"]
        if rel_volume > settings["max_relative_volume_error"]:
            blockers.append(f"{level}: VTK sample volumes inconsistent with room volume")
        values=[]
        for cell in imported["cells"]:
            if data["quantity"]=="velocity_mean_m_s":
                val=math.sqrt(sum(component**2 for component in cell["velocity_m_s"]))
            else:
                val=cell.get("contaminant_concentration")
                if val is None:
                    blockers.append(f"{level}: missing contaminant field")
                    values=[]
                    break
            values.append((cell["volume_m3"],val))
        value=sum(weight*val for weight,val in values)/volume if values and volume>0 else None
        audit=audit_openfoam_log(log_path,**data["log_audit"])
        if audit["status"]!="numerically_screened":
            blockers.append(f"{level}: solver residual audit did not pass")
        rows.append({
            "level":level,
            "mesh_cells":run["mesh_cells"],
            "reported_cell_count":imported["mesh_cells"],
            "characteristic_h_m":(data["room_volume_m3"]/cell_count)**(1/3),
            "sampled_volume_m3":volume,
            "relative_volume_error":rel_volume,
            "value":value,
            "run_id":run["run_id"],
            "vtk_sha256":imported["source_sha256"],
            "log_sha256":audit["log_sha256"],
            "log_screening_status":audit["status"],
        })
    for a,b in zip(rows,rows[1:]):
        if math.prod(a["mesh_cells"]) <= math.prod(b["mesh_cells"]):
            blockers.append("Grid cell counts are not strictly decreasing fine to coarse")
        ratios=[x/y for x,y in zip(a["mesh_cells"],b["mesh_cells"])]
        if any(r<=1 for r in ratios):
            blockers.append("Each mesh axis must be successively refined")
        elif max(ratios)/min(ratios)-1>settings["max_axis_ratio_spread"]:
            blockers.append("Anisotropic refinement ratios exceed project spread tolerance")
    if all(r["value"] is not None for r in rows):
        metrics=_analysis(rows,settings)
    else:
        metrics={
            "observed_order":None, "richardson_zero_spacing_estimate":None,
            "fine_grid_gci_percent":None, "refinement_ratios":None,
            "screening_status":"indeterminate_or_failed",
            "screening_blockers":["Missing comparable field samples"],
        }
    blockers.extend(metrics.pop("screening_blockers"))
    status="eligible_for_engineering_review" if not blockers else "indeterminate_or_failed"
    canonical=json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)
    return {
        "schema_version":SCHEMA,
        "study_name":data["name"],
        "configuration":data["configuration"],
        "quantity":data["quantity"],
        "unit":data["unit"],
        "declared_conditions_sha256":next(iter(conditions)) if len(conditions)==1 else None,
        "input_spec_sha256":hashlib.sha256(canonical.encode()).hexdigest(),
        "grids":rows,
        **metrics,
        "status":status,
        "blockers":blockers,
        "engineering_boundary":"GCI screens grid sensitivity of one selected quantity; it does not prove asymptotic range, correct physics, calibrated contamination, mesh independence, measurements or certification",
    }
