"""Per-path leakage what-if experiments for the independent closed-door network.

Only ONE explicitly sourced pressure-network path is varied per experiment.
The unchanged all-doors-open CFD case is a provenance reference, never a source
of leakage coefficients or closed-door pressure results. Always release HOLD.
"""
from __future__ import annotations

from dataclasses import asdict, replace
import json
import math
from pathlib import Path
import re

from .cfd_closed_door_comparison import compare_closed_network_with_open_cfd
from .cfd_leakage_replay import network_inputs_sha256
from .cfd_leakage_priority import compute_sampled_path_rankings
from .pressure_network import RoomPressureNetwork, solve_room_pressure_network
from .pressure_network_io import pressure_network_from_dict

SCHEMA = "cleanroomx.closed-door-local-leakage-sensitivity.v1"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
DEFAULT_FACTORS = (0.5, 1.0, 2.0)
MAX_PATHS = 16


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _finite(value, name):
    _require(type(value) in (int, float) and math.isfinite(value),
             f"{name} must be a finite numeric value")
    return float(value)


def _factors(values):
    _require(type(values) in (tuple, list) and 2 <= len(values) <= 8,
             "Supply two to eight leakage factors")
    values = tuple(_finite(value, "leakage factor") for value in values)
    _require(all(0.25 <= value <= 4.0 for value in values),
             "Leakage factors must lie in [0.25,4.0]")
    _require(all(a < b for a, b in zip(values, values[1:])),
             "Leakage factors must increase strictly")
    _require(1.0 in values, "Leakage factors must include the unchanged 1.0 baseline")
    return values


def _modify_one(network, path_name, factor):
    _require(isinstance(network, RoomPressureNetwork), "Expected pressure network")
    _require(any(path.name == path_name for path in network.paths),
             "Requested leakage path is not part of the network")
    modified = []
    for path in network.paths:
        if path.name != path_name:
            modified.append(path)
        elif path.model == "power_law":
            modified.append(replace(
                path, coefficient_m3_s_pa_n=path.coefficient_m3_s_pa_n * factor))
        elif path.model == "orifice":
            modified.append(replace(path, area_m2=path.area_m2 * factor))
        else:
            raise ValueError("Unsupported leakage path flow model")
    return replace(network, paths=tuple(modified))


def _door_mapping(comparison):
    return [{
        "door": row["door"],
        "from_room": row["from_room"],
        "to_room": row["to_room"],
        "design_target_pa": row["design_target_pa"],
    } for row in comparison["door_comparison"]]


def _model_result(network, mapping):
    solved = solve_room_pressure_network(network)
    nodes = {item["name"]: item for item in solved["nodes"]}
    paths = {item["name"]: item for item in solved["paths"]}
    targets = {
        (target.high_node, target.low_node): target.name
        for target in network.targets
    }
    verdicts = {item["name"]: item for item in solved["targets"]}
    door_rows = []
    for mapping_row in mapping:
        name, high, low = (mapping_row[k] for k in ("door", "from_room", "to_room"))
        path = next(path for path in network.paths if path.name == name)
        _require((high, low) in targets, f"Door {name} has no pressure target")
        target_name = targets[(high, low)]
        status = verdicts[target_name]["status"] == "pass"
        sign = 1.0 if path.start_node == high else -1.0
        door_rows.append({
            "door": name,
            "delta_pa": nodes[high]["pressure_pa"] - nodes[low]["pressure_pa"],
            "leakage_m3_h": sign * paths[name]["airflow_m3_h"],
            "nominal_design_delta_pa": mapping_row["design_target_pa"],
            "nominal_target_met": status,
        })
    return {
        "node_pressures_pa": {
            name: nodes[name]["pressure_pa"] for name in sorted(nodes)
        },
        "door_results": door_rows,
        "all_door_targets_met": all(row["nominal_target_met"] for row in door_rows),
    }


def _verify_source(payload):
    _require(type(payload) is dict and payload.get("schema") == SCHEMA and
             payload.get("engineering_release") == "HOLD" and
             payload.get("closed_door_cfd_demonstrated") is False and
             payload.get("not_physical_uncertainty_or_acceptance") is True and
             payload.get("variation_scope") == "one_pressure_network_path_at_a_time" and
             payload.get("unchanged_mechanical_airflow") is True,
             "Only noncertifying, one-path-at-a-time HOLD results can be verified")
    prov = payload.get("source_open_cfd_provenance")
    _require(type(prov) is dict, "Original open CFD provenance is required")
    for key in ("manifest_sha256", "run_receipt_sha256"):
        value = prov.get(key)
        _require(type(value) is str and _SHA.fullmatch(value) is not None,
                 f"Source open CFD {key} must be a SHA-256 reference")
    _require(type(prov.get("selected_iteration")) is str and
             bool(prov["selected_iteration"].strip()),
             "Original CFD SIMPLE iteration must be identified")
    scenario_sha = payload.get("source_closed_input_sha256")
    _require(scenario_sha is None or
             (type(scenario_sha) is str and _SHA.fullmatch(scenario_sha) is not None),
             "Closed-door input source identity must be a valid SHA-256")
    config = payload.get("baseline_closed_network_inputs")
    _require(type(config) is dict and
             all(type(config.get(field)) is list
                 for field in ("nodes", "paths", "targets")),
             "Baseline pressure-network inputs must contain JSON arrays")
    network = pressure_network_from_dict(config)
    _require(network_inputs_sha256(network) ==
             payload.get("baseline_closed_network_sha256"),
             "Baseline pressure-network source fingerprint mismatch")
    _require(len(network.paths) <= MAX_PATHS,
             "Per-path sensitivity exceeds supported leakage path count")
    mapping = payload.get("cfd_door_mapping")
    _require(type(mapping) is list and bool(mapping),
             "Original CFD door mapping is missing")
    _require(all(type(item) is dict and
                 set(item) == {"door", "from_room", "to_room", "design_target_pa"}
                 for item in mapping),
             "Original CFD door mapping is malformed")
    _require([item["door"] for item in mapping] ==
             sorted(item["door"] for item in mapping),
             "Original CFD door mapping must be canonically ordered")
    _require(len(set(item["door"] for item in mapping)) == len(mapping),
             "Original CFD door mapping must have unique names")
    paths = {path.name: path for path in network.paths}
    nodes = {node.name for node in network.nodes}
    targets = list(network.targets)
    _require(len(targets) == len(mapping), "Network pressure-target count differs from CFD door count")
    _require(sum(n.fixed_pressure_pa is not None for n in network.nodes) == 1,
             "Only one explicit pressure reference node is supported")
    for entry in mapping:
        name, high, low = (entry[k] for k in ("door", "from_room", "to_room"))
        _require(type(name) is str and name in paths and
                 type(high) is str and type(low) is str and high in nodes and
                 low in nodes and high != low, "CFD door missing from network")
        path = paths[name]
        _require(path.kind in ("door", "undercut") and
                 {path.start_node, path.end_node} == {high, low},
                 f"CFD door {name} endpoint or path-kind mismatch")
        target = _finite(entry["design_target_pa"], "door pressure target")
        _require(target > 0, "CFD door design target must be positive")
        matched = [t for t in targets if t.high_node == high and t.low_node == low]
        _require(len(matched) == 1 and math.isclose(
            matched[0].minimum_delta_pa, target, rel_tol=0, abs_tol=1e-9),
            f"CFD door {name} target mismatch")
    return network, mapping


def _compare_results(stored, calculated, path_name, factor):
    _require(type(stored) is dict and set(stored) == set(calculated),
             "Local leakage experiment result fields are incomplete")
    a, b = stored["node_pressures_pa"], calculated["node_pressures_pa"]
    _require(type(a) is dict and set(a) == set(b),
             "Local experiment room pressure inventory changed")
    for node in b:
        _equal(a[node], b[node], f"{path_name} ({factor:g}) room {node} pressure")
    x, y = stored["door_results"], calculated["door_results"]
    _require(type(x) is list and len(x) == len(y),
             "Local experiment door results are missing")
    for left, right in zip(x, y):
        _require(type(left) is dict and set(left) == set(right) and
                 left.get("door") == right["door"],
                 "Local leakage door result identity changed")
        for field in ("delta_pa", "leakage_m3_h", "nominal_design_delta_pa"):
            _equal(left[field], right[field],
                   f"{path_name} ({factor:g}) {right['door']} {field}")
        _require(type(left["nominal_target_met"]) is bool and
                 left["nominal_target_met"] is right["nominal_target_met"],
                 "Local leakage nominal pressure target verdict changed")
    _require(type(stored["all_door_targets_met"]) is bool and
             stored["all_door_targets_met"] is calculated["all_door_targets_met"],
             "Local leakage aggregate pressure-target verdict changed")


def _equal(actual, expected, label):
    value = _finite(actual, label)
    _require(math.isclose(value, expected, rel_tol=1e-9, abs_tol=1e-8),
             f"{label} disagrees with independently solved leakage network")


def validate_individual_leakage_sensitivity(payload):
    """Replay each independent one-path change without trusting saved numbers.

    Only internal network numerical consistency is validated. CFD and leakage
    source identities are reported, not rehashed from original input files.
    """
    network, mapping = _verify_source(payload)
    factors = _factors(payload.get("factors"))
    experiments = payload.get("path_experiments")
    _require(type(experiments) is list and
             len(experiments) == len(network.paths),
             "Every explicitly supplied leakage path must have an experiment")
    names = sorted(p.name for p in network.paths)
    _require([item.get("path") if type(item) is dict else None
              for item in experiments] == names,
             "Experiments must include each leakage path once in name order")
    common = _model_result(network, mapping)
    for entry in experiments:
        name = entry["path"]
        path = next(p for p in network.paths if p.name == name)
        _require(set(entry) == {"path", "model", "factor_results"} and
                 entry["model"] == path.model,
                 "Local leakage experiment path/model is inconsistent")
        series = entry["factor_results"]
        _require(type(series) is list and len(series) == len(factors),
                 "Every leakage path needs the complete factor series")
        for row, factor in zip(series, factors):
            _require(type(row) is dict and set(row) ==
                     {"multiplier", "result"} and
                     type(row["multiplier"]) in (int, float) and
                     float(row["multiplier"]) == factor,
                     "Recorded local leakage factors changed")
            expected = (common if factor == 1.0 else
                        _model_result(_modify_one(network, name, factor), mapping))
            _compare_results(row["result"], expected, name, factor)
    _require(type(payload.get("baseline_result")) is dict,
             "Original unmodified network baseline result is required")
    _compare_results(payload["baseline_result"], common, "baseline", 1.0)
    # Independent recalculation follows full numerical replay of all model rows.
    expected_ranking=compute_sampled_path_rankings(common,experiments,factors)
    _require(payload.get("sampled_path_rankings")==expected_ranking,
             "Sampled path ranking disagrees with replayed network results")
    return True


def sweep_individual_leakage_sensitivity(
    open_cfd_report, network, path_evidence, *,
    factors=DEFAULT_FACTORS, scenario_sha256=None,
):
    """Compute pressure/airflow response to varying just one path per case."""
    factors = _factors(factors)
    _require(isinstance(network, RoomPressureNetwork),
             "Explicit baseline RoomPressureNetwork required")
    _require(1 <= len(network.paths) <= MAX_PATHS,
             "Only 1–16 explicitly sourced leakage paths are supported")
    comparison = compare_closed_network_with_open_cfd(
        open_cfd_report, network, path_evidence, scenario_sha256=scenario_sha256)
    mapping = _door_mapping(comparison)
    baseline = _model_result(network, mapping)
    experiments = []
    for path in sorted(network.paths, key=lambda item: item.name):
        series = []
        for factor in factors:
            result = baseline if factor == 1.0 else _model_result(
                _modify_one(network, path.name, factor), mapping)
            series.append({"multiplier": factor, "result": result})
        experiments.append({
            "path": path.name, "model": path.model, "factor_results": series})
    payload = {
        "schema": SCHEMA,
        "variation_scope": "one_pressure_network_path_at_a_time",
        "factors": list(factors),
        "source_open_cfd_provenance": comparison["open_cfd_provenance"],
        "source_closed_input_sha256": scenario_sha256,
        "baseline_closed_network_inputs": json.loads(
            json.dumps(asdict(network), allow_nan=False)),
        "baseline_closed_network_sha256": network_inputs_sha256(network),
        "cfd_door_mapping": mapping,
        "baseline_result": json.loads(json.dumps(baseline, allow_nan=False)),
        "path_experiments": experiments,
        "sampled_path_rankings": compute_sampled_path_rankings(
            baseline,experiments,factors),
        "unchanged_mechanical_airflow": True,
        "not_physical_uncertainty_or_acceptance": True,
        "engineering_release": "HOLD",
        "closed_door_cfd_demonstrated": False,
        "interpretation": (
            "One path varies while all other leakage and mechanical inputs stay "
            "fixed. Network model only; nominal target screens are NOT measured "
            "CFD pressure, validated leakage coefficients, or certification."),
    }
    validate_individual_leakage_sensitivity(payload)
    return payload


def export_individual_leakage_sensitivity(payload, destination):
    """Create one new replay-validated JSON report; never overwrite evidence."""
    validate_individual_leakage_sensitivity(payload)
    path = Path(destination)
    data = json.dumps(payload, indent=2, allow_nan=False) + "\n"
    with path.open("x", encoding="utf-8") as stream:
        stream.write(data)
    return path
