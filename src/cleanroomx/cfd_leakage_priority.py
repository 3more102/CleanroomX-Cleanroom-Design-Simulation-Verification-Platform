"""Rank only sampled steady pressure-NETWORK leakage what-if cases.

No CFD field is generated; ranks are not failure probabilities, physical
uncertainty intervals, or cleanroom acceptance and cannot authorize release.
"""
from __future__ import annotations
import math

SCHEMA="cleanroomx.sampled-local-leakage-pressure-margin-ranking.v1"

def _finite(value,name):
    if type(value) not in (float,int) or not math.isfinite(value):
        raise ValueError(f"Sampled network ranking {name} must be finite")
    return float(value)

def compute_sampled_path_rankings(baseline, experiments, factors):
    """Order one-path model studies by greatest sampled door target-margin LOSS."""
    if not isinstance(baseline,dict) or not baseline.get("door_results"):
        raise ValueError("Sampled ranking requires baseline network door results")
    baseline_margins={
        row["door"]:_finite(row["delta_pa"],"baseline pressure")-
                    _finite(row["nominal_design_delta_pa"],"baseline target")
        for row in baseline["door_results"]}
    if len(baseline_margins)!=len(baseline["door_results"]):
        raise ValueError("Sampled ranking requires unique baseline doors")
    baseline_rooms=baseline["node_pressures_pa"]
    if not isinstance(baseline_rooms,dict) or not baseline_rooms:
        raise ValueError("Sampled ranking requires baseline room pressures")
    result=[]
    for path in experiments:
        loss=0.
        worst_factor=1.
        worst_door=baseline["door_results"][0]["door"]
        min_margin=min(baseline_margins.values())
        max_room_shift=0.
        max_door_shift=0.
        failing_count=0
        for sample in path["factor_results"]:
            factor=_finite(sample["multiplier"],"factor")
            trial=sample["result"]
            if not trial["all_door_targets_met"]:
                failing_count+=1
            rooms=trial["node_pressures_pa"]
            if set(rooms)!=set(baseline_rooms):
                raise ValueError("Sampled ranking room inventory changed")
            for room in baseline_rooms:
                max_room_shift=max(max_room_shift,abs(
                    _finite(rooms[room],"room pressure")-
                    _finite(baseline_rooms[room],"baseline room pressure")))
            if len(trial["door_results"])!=len(baseline_margins):
                raise ValueError("Sampled ranking door inventory changed")
            for door in trial["door_results"]:
                name=door["door"]
                if name not in baseline_margins:
                    raise ValueError("Sampled ranking door inventory changed")
                delta=_finite(door["delta_pa"],"door pressure")
                target=_finite(door["nominal_design_delta_pa"],"target")
                margin=delta-target
                min_margin=min(min_margin,margin)
                margin_loss=baseline_margins[name]-margin
                if margin_loss>loss:
                    loss=margin_loss
                    worst_factor=factor
                    worst_door=name
                max_door_shift=max(max_door_shift,abs(
                    delta-(baseline_margins[name]+target)))
        result.append({
            "path":path["path"],"leakage_model":path["model"],
            "max_sampled_target_margin_loss_pa":loss,
            "max_margin_loss_factor":worst_factor,
            "max_margin_loss_door":worst_door,
            "min_sampled_nominal_margin_pa":min_margin,
            "max_abs_room_pressure_shift_pa":max_room_shift,
            "max_abs_door_delta_shift_pa":max_door_shift,
            "sampled_scenarios_with_any_target_failure":failing_count,
            "sampled_scenario_count":len(path["factor_results"]),
        })
    result.sort(key=lambda r:(-r["max_sampled_target_margin_loss_pa"],r["path"]))
    for rank,row in enumerate(result,1):
        row["rank"]=rank
    return {
        "schema":SCHEMA,
        "ranking_basis":"maximum_nominal_door_pressure_margin_loss_pa_in_sampled_factors",
        "sampled_factors":[_finite(value,"factor") for value in factors],
        "sampled_path_count":len(result),
        "ranked_paths":result,
        "rank_is_not_failure_probability":True,
        "rank_does_not_establish_uncertainty_bounds":True,
        "engineering_release":"HOLD",
    }
