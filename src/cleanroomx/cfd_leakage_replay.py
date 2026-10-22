"""Independent replay of bounded, hypothetical closed-door leakage NETWORK sweeps.

This is not CFD replay. It never infers coefficients from CFD, and cannot
validate any measured leakage coefficients, 5 Pa closed-door CFD or certification.
"""
from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json
import math
import re

from .pressure_network import RoomPressureNetwork, solve_room_pressure_network
from .pressure_network_io import pressure_network_from_dict

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SCHEMA = "cleanroomx.closed-door-leakage-sensitivity.v1"


def _check(ok, message):
    if not ok:
        raise ValueError(message)


def _finite(value, name):
    _check(type(value) in (int, float) and math.isfinite(value),
           f"{name} must be a finite number")
    return float(value)


def _equal_number(actual, expected, label):
    value = _finite(actual, label)
    _check(math.isclose(value, expected, rel_tol=1e-9, abs_tol=1e-8),
           f"{label} disagrees with replayed closed-door network")
    return value


def network_inputs_sha256(network: RoomPressureNetwork) -> str:
    """Deterministic engineering-model fingerprint, not a digital signature."""
    payload = json.dumps(asdict(network), sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def varied_network(network: RoomPressureNetwork, factor: float) -> RoomPressureNetwork:
    """Scale every explicitly supplied power-law C or orifice area by factor."""
    changed = []
    for path in network.paths:
        if path.model == "power_law":
            changed.append(replace(
                path, coefficient_m3_s_pa_n=path.coefficient_m3_s_pa_n * factor))
        elif path.model == "orifice":
            changed.append(replace(path, area_m2=path.area_m2 * factor))
        else:
            raise ValueError(f"Unsupported closed-door leakage path model: {path.model}")
    return replace(network, paths=tuple(changed))


def validate_closed_door_sensitivity_replay(sweep):
    """Re-solve every saved factor and reject contradictory pressure/flow claims.

    Does not verify original OpenFOAM bytes or the external evidence source
    behind an assumed/manufacturer/measured leakage coefficient.
    """
    _check(type(sweep) is dict and sweep.get("schema") == SCHEMA and
           sweep.get("engineering_release") == "HOLD" and
           sweep.get("closed_door_cfd_demonstrated") is False and
           sweep.get("hypothesis_not_uncertainty_interval") is True and
           sweep.get("baseline_factor") == 1.0 and
           sweep.get("physical_model") ==
               "steady pressure/leakage NETWORK only; OPEN CFD is reference" and
           sweep.get("basis") ==
               "hypothetical uniform simultaneous path coefficient/orifice-area multipliers",
           "Only hypothetical noncertifying HOLD network evidence can be replayed")
    source = sweep.get("source_open_cfd_provenance")
    _check(type(source) is dict, "Original CFD provenance reference is missing")
    for key in ("manifest_sha256", "run_receipt_sha256"):
        val = source.get(key)
        _check(type(val) is str and _SHA256.fullmatch(val) is not None,
               f"Original CFD {key} identity is malformed")
    _check(type(source.get("selected_iteration")) is str and
           bool(source["selected_iteration"].strip()),
           "Original CFD selected iteration is not identified")
    sha = sweep.get("source_closed_input_sha256")
    _check(sha is None or (type(sha) is str and _SHA256.fullmatch(sha) is not None),
           "Original closed-door scenario SHA-256 identity is malformed")

    params = sweep.get("baseline_closed_network_inputs")
    _check(type(params) is dict, "Explicit baseline network inputs are missing")
    network = pressure_network_from_dict(params)
    _check(network_inputs_sha256(network) ==
           sweep.get("baseline_closed_network_sha256"),
           "Baseline closed-door network fingerprint does not match its inputs")
    _check(sum(node.fixed_pressure_pa is not None for node in network.nodes) == 1,
           "Sensitivity replay requires one explicit pressure reference node")
    topology = sweep.get("baseline_door_connectivity")
    _check(type(topology) is list and len(topology) > 0,
           "Baseline CFD door linkage must be recorded")
    _check(all(type(item) is dict and
               set(item) == {"door", "from_room", "to_room", "design_target_pa"}
               for item in topology),
           "Recorded door linkage must contain exact door, endpoints and targets")
    paths = {item.name: item for item in network.paths}
    nodes = {node.name for node in network.nodes}
    _check(len({item["door"] for item in topology}) == len(topology),
           "Baseline door linkage has duplicate names")
    _check([item["door"] for item in topology] ==
           sorted(item["door"] for item in topology),
           "Baseline CFD door linkage must retain canonical order")
    targets = {}
    for item in topology:
        name, high, low = item["door"], item["from_room"], item["to_room"]
        _check(type(name) is str and name in paths and
               type(high) is str and type(low) is str and
               high in nodes and low in nodes and high != low,
               f"Recorded door {name!r} is not present in the baseline network")
        path = paths[name]
        _check(path.kind in ("door", "undercut") and
               {path.start_node, path.end_node} == {high, low},
               f"Baseline door {name!r} endpoints mismatch the modeled path")
        design = _finite(item["design_target_pa"], f"{name} design target")
        _check(design > 0, "Baseline door design targets must be positive")
        matched = [target for target in network.targets if
                   target.high_node == high and target.low_node == low]
        _check(len(matched) == 1 and
               math.isclose(matched[0].minimum_delta_pa, design,
                            rel_tol=0, abs_tol=1e-9),
               f"Baseline door {name!r} lacks its explicit matching target")
        targets[name] = matched[0].name
    _check(len(network.targets) == len(topology),
           "Unexpected additional or missing baseline pressure targets")
    factors = sweep.get("factor_results")
    _check(type(factors) is list and 2 <= len(factors) <= 8,
           "Sensitivity requires two to eight bounded network re-solves")
    seen_baseline = 0
    previous_factor = -math.inf
    for row in factors:
        _check(type(row) is dict and set(row) ==
               {"leakage_multiplier", "network_nominal_targets_met", "door_results"},
               "Malformed pressure sensitivity row")
        factor = _finite(row["leakage_multiplier"], "Leakage scale factor")
        _check(0.25 <= factor <= 4 and factor > previous_factor,
               "Leakage factors must increase strictly within [0.25, 4.0]")
        previous_factor = factor
        seen_baseline += factor == 1.0
        _check(type(row["network_nominal_targets_met"]) is bool,
               "Nominal aggregate target verdict must be boolean")
        result_rows = row["door_results"]
        _check(type(result_rows) is list and len(result_rows) == len(topology),
               "Door sensitivity results must cover every original CFD door")
        _check([item.get("door") if isinstance(item, dict) else None
                for item in result_rows] == [item["door"] for item in topology],
               "Sensitivity door results changed identities or ordering")
        try:
            solved = solve_room_pressure_network(varied_network(network, factor))
        except (RuntimeError, OverflowError) as exc:
            raise ValueError(f"Network sensitivity factor {factor} could not replay") from exc
        p_nodes = {item["name"]: item for item in solved["nodes"]}
        p_paths = {item["name"]: item for item in solved["paths"]}
        p_targets = {item["name"]: item for item in solved["targets"]}
        matches = []
        for mapping, item in zip(topology, result_rows):
            name, high, low = mapping["door"], mapping["from_room"], mapping["to_room"]
            _check(type(item) is dict and set(item) == {
                "door", "computed_closed_network_delta_pa", "nominal_design_delta_pa",
                "nominal_target_met", "computed_network_leakage_m3_h"},
                "Malformed door sensitivity evidence row")
            expected_delta = p_nodes[high]["pressure_pa"] - p_nodes[low]["pressure_pa"]
            path = paths[name]
            sign = 1 if path.start_node == high else -1
            expected_flux = sign * p_paths[name]["airflow_m3_h"]
            expected_status = p_targets[targets[name]]["status"] == "pass"
            _equal_number(item["nominal_design_delta_pa"],
                          mapping["design_target_pa"], f"{name} design target")
            _equal_number(item["computed_closed_network_delta_pa"],
                          expected_delta, f"{name} solved pressure")
            _equal_number(item["computed_network_leakage_m3_h"],
                          expected_flux, f"{name} solved leakage flow")
            _check(type(item["nominal_target_met"]) is bool and
                   item["nominal_target_met"] is expected_status,
                   f"{name} nominal pressure target verdict disagrees with replay")
            matches.append(expected_status)
        _check(row["network_nominal_targets_met"] is all(matches),
               "Aggregate nominal target verdict disagrees with replay")
    _check(seen_baseline == 1, "Leakage factors must include exactly one baseline 1.0")
    baseline = next(row for row in factors if row["leakage_multiplier"] == 1.0)
    _check(sweep.get("baseline_result") == baseline,
           "Baseline result disagrees with the 1.0-factor network re-solve")
    return True
