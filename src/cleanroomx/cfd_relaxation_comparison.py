"""Matched independent Foundation v10 SIMPLE relaxation experiment comparison.

Every input other than fvSolution MUST have the same recorded SHA-256, and
the two solver runs must have distinct provenanced receipts and matching saved
SIMPLE iteration labels. Observed numerical differences are not evidence of
physical model validity, mesh independence or closed-door cascade compliance.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from .cfd_multizone import verify_multizone_inputs
from .cfd_multizone_results import analyze_multizone_case

SCHEMA="cleanroomx.multizone-paired-relaxation-comparison.v1"
FIELDS=("p","Ux","Uy","Uz")


def _finite(value,label):
    if type(value) not in (int,float) or not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return float(value)


def compare_independent_relaxation_cases(
    baseline_directory, variant_directory, *,
    density_kg_m3=1.2, reference_room_id="corridor",
):
    """Analyze two truly executed, hash-verified, like-for-like solver cases.

    Enforce identical saved OpenFOAM fields' *iteration identities* and input
    meshes/physical BC/viscosity/controlDict. Alteration may only be to
    fvSolution, whose actual controls are tied to manifest metadata; no
    unsolved or unverified case can be interpreted as a numerical experiment.
    """
    ra,ma=verify_multizone_inputs(baseline_directory)
    rb,mb=verify_multizone_inputs(variant_directory)
    if ra==rb:
        raise ValueError("Compare two different independently generated run directories")
    for key in ("schema_version","project_source_sha256","input_mode","solver"):
        if ma.get(key)!=mb.get(key):
            raise ValueError(f"Numerical variants must share exact {key}")
    ca=ma.get("case",{})
    cb=mb.get("case",{})
    if (not isinstance(ca,dict) or not isinstance(cb,dict) or
        ca.get("door_mode")!="open" or cb.get("door_mode")!="open"):
        raise ValueError("Only independently generated open-door cases can be compared")
    controls_a=ca.get("numerical_controls")
    controls_b=cb.get("numerical_controls")
    if not isinstance(controls_a,dict) or not isinstance(controls_b,dict):
        raise ValueError("Numerical relaxation controls must be source recorded")
    unchanged_a={key:value for key,value in ca.items() if key!="numerical_controls"}
    unchanged_b={key:value for key,value in cb.items() if key!="numerical_controls"}
    if unchanged_a!=unchanged_b:
        raise ValueError("Geometry, boundary conditions, or scenario metadata differ")
    for key in ("pressure_field_relaxation","velocity_equation_relaxation"):
        a=_finite(controls_a.get(key),key)
        b=_finite(controls_b.get(key),key)
        if (key=="pressure_field_relaxation" and
            not 0.05<=a<=0.7 or not 0.05<=b<=0.7):
            raise ValueError("Invalid recorded pressure relaxation setting")
        if (key=="velocity_equation_relaxation" and
            not 0.1<=a<=0.95 or not 0.1<=b<=0.95):
            raise ValueError("Invalid recorded velocity relaxation setting")
    if controls_a==controls_b:
        raise ValueError("A numerical comparison requires different recorded relaxation settings")
    if any(controls_a.get(k)!=controls_b.get(k) for k in (
        "residual_control_p","residual_control_U")):
        raise ValueError("SIMPLE convergence limits changed between variants")
    files_a=ma.get("files",{})
    files_b=mb.get("files",{})
    if (not isinstance(files_a,dict) or set(files_a)!=set(files_b) or
        any(files_a[name]!=files_b[name] for name in files_a
            if name!="system/fvSolution") or
        files_a.get("system/fvSolution")==files_b.get("system/fvSolution")):
        raise ValueError("Only the hashed fvSolution input may change")
    # Check the actual dictionary, not merely the manifest text claim.
    for case_dir,controls in ((ra,controls_a),(rb,controls_b)):
        solution=(case_dir/"system/fvSolution").read_text(encoding="utf-8")
        p=controls["pressure_field_relaxation"]
        u=controls["velocity_equation_relaxation"]
        if (f"fields {{ p {p:.12g}; }}" not in solution or
            f"equations {{ U {u:.12g}; }}" not in solution):
            raise ValueError("fvSolution relaxation disagrees with source manifest")
    # Never let a generated-but-never-executed numerical case be mistaken
    # for a CFD result. The canonical importer independently verifies every
    # receipt stage/log/field hash, even when this first guard passes.
    for case_dir in (ra,rb):
        receipt=case_dir/"run-receipt.json"
        if receipt.is_symlink() or not receipt.is_file():
            raise ValueError(
                "Both numerical variants require successful recorded OpenFOAM execution receipts")
    density=_finite(density_kg_m3,"air density")
    if density<=0:
        raise ValueError("Air density must be positive")
    a=analyze_multizone_case(
        ra,density_kg_m3=density,reference_room_id=reference_room_id)
    b=analyze_multizone_case(
        rb,density_kg_m3=density,reference_room_id=reference_room_id)
    if (a.get("scenario")!="all_doors_open" or
        b.get("scenario")!="all_doors_open" or
        a.get("time_name")!=b.get("time_name") or
        a.get("available_times")!=b.get("available_times")):
        raise ValueError("Run iteration identities or CFD scenarios differ")
    if a.get("time_name") is None:
        raise ValueError("Both cases must have a real matching selected SIMPLE iteration")
    for key in ("manifest_sha256","run_receipt_sha256"):
        if a["provenance"].get(key)==b["provenance"].get(key):
            raise ValueError("Independent numerical variants must have distinct source identities")
    if (a["mesh"]!=b["mesh"] or len(a["cells"])!=len(b["cells"]) or
        any(left["center_m"]!=right["center_m"] or
            left["room_id"]!=right["room_id"]
            for left,right in zip(a["cells"],b["cells"]))):
        raise ValueError("Compared solved meshes and computed cell coordinates differ")
    rooms_a,rooms_b=a["rooms"],b["rooms"]
    doors_a,doors_b=a["doors"],b["doors"]
    if set(rooms_a)!=set(rooms_b) or set(doors_a)!=set(doors_b):
        raise ValueError("Computed room and door inventories are not identical")
    room_rows={}
    for name in sorted(rooms_a):
        left=_finite(rooms_a[name]["mean_pressure_pa_relative_to_reference"],"room pressure")
        right=_finite(rooms_b[name]["mean_pressure_pa_relative_to_reference"],"room pressure")
        ua=_finite(rooms_a[name]["mean_speed_m_s"],"room velocity")
        ub=_finite(rooms_b[name]["mean_speed_m_s"],"room velocity")
        room_rows[name]={
            "baseline_relative_mean_pressure_pa":left,
            "variant_relative_mean_pressure_pa":right,
            "variant_minus_baseline_pressure_pa":right-left,
            "baseline_mean_speed_m_s":ua,
            "variant_mean_speed_m_s":ub,
            "variant_minus_baseline_speed_m_s":ub-ua,
        }
    door_rows={}
    for name in sorted(doors_a):
        left,right=doors_a[name],doors_b[name]
        if any(left.get(k)!=right.get(k) for k in (
            "from_room","to_room","design_delta_pressure_target_pa")):
            raise ValueError("Recorded doors differ between solver variants")
        pa=_finite(left["computed_delta_pressure_pa"],"door delta")
        pb=_finite(right["computed_delta_pressure_pa"],"door delta")
        qa=_finite(left["computed_net_transfer_m3_s"],"door flux")
        qb=_finite(right["computed_net_transfer_m3_s"],"door flux")
        door_rows[name]={
            "from_room":left["from_room"],"to_room":left["to_room"],
            "baseline_computed_delta_pa":pa,"variant_computed_delta_pa":pb,
            "variant_minus_baseline_delta_pa":pb-pa,
            "baseline_net_transfer_m3_s":qa,"variant_net_transfer_m3_s":qb,
            "variant_minus_baseline_net_transfer_m3_s":qb-qa,
            "closed_door_5pa_verified":False,
        }
    numerical={}
    for name,report in (("baseline",a),("variant",b)):
        n=report["numerics"]
        if n["selected_iteration"]!=float(report["time_name"]):
            raise ValueError("Log residual identity conflicts with computed SIMPLE time")
        numerical[name]={
            "selected_iteration":n["selected_iteration"],
            "run_reported_convergence":n["run_reported_convergence"],
            "selected_iteration_reported_convergence":n[
                "selected_iteration_reported_convergence"],
            "selected_initial_residuals_below_limits":n[
                "selected_initial_residuals_below_limits"],
            "selected_fields":{
                key:{
                    "first_initial_residual":_finite(
                        n["fields"][key]["first_initial_residual"],"field residual"),
                    "last_final_linear_residual":_finite(
                        n["fields"][key]["last_final_linear_residual"],"field residual"),
                } for key in FIELDS
            },
            "sum_absolute_cell_imbalance_m3_s":_finite(
                report["flow_balance"]["sum_absolute_cell_imbalance_m3_s"],
                "cell imbalance"),
            "global_signed_boundary_imbalance_m3_s":_finite(
                report["global_net_outward_imbalance_m3_s"],"boundary imbalance"),
        }
    return {
        "schema":SCHEMA,
        "scenario":"all_doors_open",
        "source_project_sha256":ma["project_source_sha256"],
        "selected_simple_iteration":a["time_name"],
        "available_identical_saved_iterations":a["available_times"],
        "reference_room_id":reference_room_id,
        "air_density_kg_m3":density,
        "mesh_cells":len(a["cells"]),
        "baseline":{
            "directory":str(ra),
            "manifest_sha256":a["provenance"]["manifest_sha256"],
            "run_receipt_sha256":a["provenance"]["run_receipt_sha256"],
            "controls":controls_a,
        },
        "variant":{
            "directory":str(rb),
            "manifest_sha256":b["provenance"]["manifest_sha256"],
            "run_receipt_sha256":b["provenance"]["run_receipt_sha256"],
            "controls":controls_b,
        },
        "room_comparison":room_rows,
        "door_comparison":door_rows,
        "solver_numerical_evidence":numerical,
        "comparison_status":"two_real_runs_numerical_differences_only",
        "same_geometry_and_other_solver_inputs_verified":True,
        "iteration_comparable_but_not_physical_time":True,
        "numerical_convergence_or_improvement_proven":False,
        "closed_door_5pa_demonstrated":False,
        "engineering_release":"HOLD",
        "limitations":[
            "Relaxation sensitivity only: exactly equal input meshes, equipment, boundaries, viscosity, iteration IDs and output cadence",
            "Even lower residuals or smaller computed changes do not prove a physically correct model",
            "Neither run is a closed-door leakage CFD model or a 5 Pa pressure-cascade certification",
            "No mesh-convergence, turbulence, manufacturer-device, or commissioning validation",
        ],
    }


def export_independent_relaxation_comparison(comparison, destination):
    """Preserve original two execution receipts; never overwrite evidence."""
    if (type(comparison) is not dict or comparison.get("schema")!=SCHEMA or
        comparison.get("engineering_release")!="HOLD" or
        comparison.get("closed_door_5pa_demonstrated") is not False or
        comparison.get("numerical_convergence_or_improvement_proven") is not False or
        comparison.get("same_geometry_and_other_solver_inputs_verified") is not True or
        comparison.get("comparison_status")!="two_real_runs_numerical_differences_only" or
        not isinstance(comparison.get("door_comparison"),dict) or
        not isinstance(comparison.get("room_comparison"),dict)):
        raise ValueError("Only verified, noncertifying paired solver evidence may be exported")
    data=json.dumps(comparison,indent=2,allow_nan=False)+"\n"
    out=Path(destination)
    with out.open("x",encoding="utf-8") as file:
        file.write(data)
    return out
