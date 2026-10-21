"""Explicit illustrative uncertainty sweep for closed-door leakage NETWORK.

This does not model variations in actual CFD geometry, fan operation,
turbulence, door transients or physical leakage uncertainty distributions.
Only individually supplied pressure-flow coefficient / orifice area is
multiplied by a visibly hypothetical factor in a NEW network solve.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, replace
import json
import math
from pathlib import Path

from .cfd_closed_door_comparison import compare_closed_network_with_open_cfd
from .pressure_network import RoomPressureNetwork
from .cfd_leakage_replay import (
    network_inputs_sha256, validate_closed_door_sensitivity_replay,
    varied_network,
)

SCHEMA="cleanroomx.closed-door-leakage-sensitivity.v1"


def sweep_closed_door_leakage(
    report, network, path_evidence, *, factors=(0.5,1.0,2.0),
    scenario_sha256=None,
):
    """Re-solve with a bounded explicit set of ALL-path coefficient multipliers.

    This is only a scenario stress test, not a statistical confidence band.
    It is deliberately impossible to return a verified 'PASS' decision.
    """
    if type(factors) not in (list,tuple) or not 2<=len(factors)<=8:
        raise ValueError("Specify 2 to 8 hypothetical leakage scale factors")
    factors=tuple(factors)
    if any(type(f) not in (int,float) or not math.isfinite(f) or
           not 0.25<=f<=4.0 for f in factors):
        raise ValueError("Leakage factors must be finite numerical scalars in [0.25,4.0]")
    if any(float(a)>=float(b) for a,b in zip(factors,factors[1:])):
        raise ValueError("Leakage factors must increase strictly")
    if 1.0 not in factors:
        raise ValueError("A 1.0 baseline factor must be included")
    # Independent model and all physical target/provenance invariants are
    # verified in the baseline prior to varying any coefficients.
    base=compare_closed_network_with_open_cfd(
        report,network,path_evidence,scenario_sha256=scenario_sha256)
    rows=[]
    for factor in factors:
        changed_network=varied_network(network,factor)
        try:
            comparison=(base if factor==1 else
                compare_closed_network_with_open_cfd(
                    report,changed_network,path_evidence,
                    scenario_sha256=scenario_sha256))
        except RuntimeError as exc:
            raise ValueError(
                f"Leakage sensitivity factor {factor:g} did not solve; "
                "no values can be inferred"
            ) from exc
        rows.append({
            "leakage_multiplier":factor,
            "network_nominal_targets_met":comparison["network_nominal_targets_met"],
            "door_results":[{
                "door":door["door"],
                "computed_closed_network_delta_pa":door["closed_door_network_delta_pa"],
                "nominal_design_delta_pa":door["design_target_pa"],
                "nominal_target_met":door["closed_network_meets_nominal_target"],
                "computed_network_leakage_m3_h":door["closed_door_network_flow_m3_h"],
            } for door in comparison["door_comparison"]],
        })
    base_result=next(row for row in rows if row["leakage_multiplier"]==1)
    source=base["open_cfd_provenance"]
    return {
        "schema":SCHEMA,
        "source_open_cfd_provenance":source,
        "source_closed_input_sha256":scenario_sha256,
        "physical_model":"steady pressure/leakage NETWORK only; OPEN CFD is reference",
        "basis":"hypothetical uniform simultaneous path coefficient/orifice-area multipliers",
        "baseline_factor":1.0,
        "baseline_closed_network_inputs":json.loads(
            json.dumps(asdict(network),allow_nan=False)),
        "baseline_closed_network_sha256":network_inputs_sha256(network),
        "baseline_door_connectivity":[{
            "door":row["door"],
            "from_room":row["from_room"],
            "to_room":row["to_room"],
            "design_target_pa":row["design_target_pa"],
        } for row in base["door_comparison"]],
        "baseline_result":deepcopy(base_result),
        "factor_results":rows,
        "hypothesis_not_uncertainty_interval":True,
        "engineering_release":"HOLD",
        "closed_door_cfd_demonstrated":False,
        "conclusions":[
            "Sensitivity is NOT a statistical confidence interval, calibrated pressure controller, or site measurement",
            "Actual leakage uncertainty may vary door by door, with pressure, temperature and workmanship",
            "A model-predicted nominal 5 Pa target does NOT certify closed-door CFD, cleanroom performance or commissioning",
            "Mechanical airflow inputs are assumed fixed while path leakage coefficients/orifice areas change",
        ],
    }


def export_closed_door_sensitivity(sweep,destination):
    """Write source-linked noncertifying JSON; refuse file overwrites."""
    if (not isinstance(sweep,dict) or sweep.get("schema")!=SCHEMA
        or sweep.get("engineering_release")!="HOLD"
        or sweep.get("closed_door_cfd_demonstrated") is not False
        or sweep.get("hypothesis_not_uncertainty_interval") is not True):
        raise ValueError("Only hypothetical noncertifying HOLD sensitivity may be exported")
    validate_closed_door_sensitivity_replay(sweep)
    path=Path(destination)
    data=json.dumps(sweep,indent=2,allow_nan=False)+"\n"
    with path.open("x",encoding="utf-8") as stream:
        stream.write(data)
    return path
