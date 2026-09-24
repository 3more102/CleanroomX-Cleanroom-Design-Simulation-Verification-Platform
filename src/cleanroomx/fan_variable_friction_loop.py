from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

from .fan_curve import FanCurve, FanCurvePoint
from .fan_loop_network import FanLoopNetworkStudy
from .loop_network import LoopedFlowNetwork
from .pressure_power import FanPowerEfficiencies, analyze_fan_pressure_power
from .variable_friction_loop import solve_variable_friction_looped_network


_NETWORK_STATE_CANONICALIZATION = (
    "network-result-projection-sort-named-collections-normalize-signed-zero-"
    "preserve-iteration-history-json-sort-keys-compact-utf8-v3"
)
_SOLVER_RESULT_INTEGRITY_CANONICALIZATION = (
    "fan-variable-friction-loop-result-sort-named-collections-"
    "normalize-signed-zero-json-sort-keys-compact-utf8-v1"
)
_SOLVER_RESULT_INTEGRITY_SCOPE = (
    "cleanroomx.fan_variable_friction_loop.result_without_result_integrity.v1"
)
_SOLVER_RESULT_NAMED_COLLECTION_KEYS = frozenset(
    {"nodes", "edges", "edge_closure"}
)


def _positive(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field_name} must be finite and > 0")
    return value


def _unit_interval(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0 or value > 1:
        raise ValueError(f"{field_name} must be finite and in (0, 1]")
    return value


def _nonnegative(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{field_name} must be finite and >= 0")
    return value


def _positive_integer(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be an integer > 0")
    return value


@dataclass(frozen=True)
class FanVariableFrictionLoopStudy:
    name: str
    fan_curve: FanCurve
    loop_network: LoopedFlowNetwork
    fan_discharge_node: str
    fan_suction_node: str
    fixed_pressure_pa: float = 0.0
    power_efficiencies: FanPowerEfficiencies | None = None
    resistance_relative_tolerance: float = 1e-6
    relaxation: float = 0.5
    near_zero_airflow_m3_h: float = 1e-6
    max_outer_iterations: int = 50
    mass_balance_tolerance_m3_h: float = 1e-6
    max_newton_iterations: int = 100
    operating_pressure_tolerance_pa: float = 1e-6
    max_operating_iterations: int = 80

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError(
                "fan/variable-friction loop study name cannot be empty"
            )
        object.__setattr__(
            self,
            "fixed_pressure_pa",
            _nonnegative(self.fixed_pressure_pa, "fixed_pressure_pa"),
        )
        if (
            self.power_efficiencies is not None
            and not isinstance(self.power_efficiencies, FanPowerEfficiencies)
        ):
            raise ValueError(
                "power_efficiencies must be FanPowerEfficiencies or None"
            )
        object.__setattr__(
            self,
            "resistance_relative_tolerance",
            _positive(
                self.resistance_relative_tolerance,
                "resistance_relative_tolerance",
            ),
        )
        object.__setattr__(
            self,
            "relaxation",
            _unit_interval(self.relaxation, "relaxation"),
        )
        object.__setattr__(
            self,
            "near_zero_airflow_m3_h",
            _nonnegative(
                self.near_zero_airflow_m3_h,
                "near_zero_airflow_m3_h",
            ),
        )
        object.__setattr__(
            self,
            "max_outer_iterations",
            _positive_integer(
                self.max_outer_iterations, "max_outer_iterations"
            ),
        )
        object.__setattr__(
            self,
            "mass_balance_tolerance_m3_h",
            _positive(
                self.mass_balance_tolerance_m3_h,
                "mass_balance_tolerance_m3_h",
            ),
        )
        object.__setattr__(
            self,
            "max_newton_iterations",
            _positive_integer(
                self.max_newton_iterations, "max_newton_iterations"
            ),
        )
        object.__setattr__(
            self,
            "operating_pressure_tolerance_pa",
            _positive(
                self.operating_pressure_tolerance_pa,
                "operating_pressure_tolerance_pa",
            ),
        )
        object.__setattr__(
            self,
            "max_operating_iterations",
            _positive_integer(
                self.max_operating_iterations, "max_operating_iterations"
            ),
        )

        # Reuse the established two-terminal fan/loop topology checks without
        # using the fixed-resistance equivalent-law solver.
        FanLoopNetworkStudy(
            name=self.name,
            fan_curve=self.fan_curve,
            loop_network=self.loop_network,
            fan_discharge_node=self.fan_discharge_node,
            fan_suction_node=self.fan_suction_node,
            fixed_pressure_pa=self.fixed_pressure_pa,
        )


def _network_at_airflow(
    study: FanVariableFrictionLoopStudy,
    airflow_m3_h: float,
) -> LoopedFlowNetwork:
    airflow = _nonnegative(airflow_m3_h, "airflow_m3_h")
    reference_airflow = study.loop_network.node_injections_m3_h[
        study.fan_discharge_node
    ]
    scale = airflow / reference_airflow
    return LoopedFlowNetwork(
        name=study.loop_network.name,
        node_injections_m3_h={
            node: injection * scale
            for node, injection in study.loop_network.node_injections_m3_h.items()
        },
        edges=study.loop_network.edges,
        reference_node=study.loop_network.reference_node,
    )


def _node_pressure(result: dict, node_name: str) -> float:
    for node in result["nodes"]:
        if node["name"] == node_name:
            return float(node["relative_pressure_pa"])
    raise RuntimeError(f"node {node_name!r} missing from loop-network result")


def _fan_pressure(
    left: FanCurvePoint,
    right: FanCurvePoint,
    airflow_m3_h: float,
) -> float:
    fraction = (
        (airflow_m3_h - left.airflow_m3_h)
        / (right.airflow_m3_h - left.airflow_m3_h)
    )
    return left.pressure_pa + fraction * (
        right.pressure_pa - left.pressure_pa
    )


def _solve_network_at_airflow(
    study: FanVariableFrictionLoopStudy,
    airflow_m3_h: float,
) -> tuple[dict, float]:
    network = _network_at_airflow(study, airflow_m3_h)
    solved = solve_variable_friction_looped_network(
        network,
        resistance_relative_tolerance=study.resistance_relative_tolerance,
        relaxation=study.relaxation,
        near_zero_airflow_m3_h=study.near_zero_airflow_m3_h,
        max_outer_iterations=study.max_outer_iterations,
        mass_balance_tolerance_m3_h=study.mass_balance_tolerance_m3_h,
        max_newton_iterations=study.max_newton_iterations,
    )
    discharge_pressure = _node_pressure(solved, study.fan_discharge_node)
    suction_pressure = _node_pressure(solved, study.fan_suction_node)
    network_pressure = discharge_pressure - suction_pressure
    if not math.isfinite(network_pressure) or network_pressure < -1e-9:
        raise RuntimeError(
            "variable-friction loop solution produced invalid fan-terminal "
            "pressure requirement"
        )
    return solved, max(network_pressure, 0.0)


def _normalize_signed_zero(value):
    if isinstance(value, float):
        return 0.0 if value == 0.0 else value
    if isinstance(value, dict):
        return {
            key: _normalize_signed_zero(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_normalize_signed_zero(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_signed_zero(item) for item in value]
    return value


def _canonical_solver_result_payload(result: dict) -> dict:
    payload = {
        key: value
        for key, value in result.items()
        if key != "result_integrity"
    }
    normalized = _normalize_signed_zero(payload)

    def canonicalize(value, *, collection_key: str | None = None):
        if isinstance(value, dict):
            return {
                key: canonicalize(item, collection_key=key)
                for key, item in value.items()
            }
        if isinstance(value, list):
            items = [canonicalize(item) for item in value]
            if (
                collection_key in _SOLVER_RESULT_NAMED_COLLECTION_KEYS
                and all(
                    isinstance(item, dict) and "name" in item
                    for item in items
                )
            ):
                return sorted(items, key=lambda item: str(item["name"]))
            return items
        return value

    return canonicalize(normalized)


def _solver_result_sha256(result: dict) -> str:
    encoded = json.dumps(
        _canonical_solver_result_payload(result),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _with_solver_result_integrity(result: dict) -> dict:
    result = dict(result)
    result.pop("result_integrity", None)
    result["result_integrity"] = {
        "algorithm": "sha256",
        "canonicalization": _SOLVER_RESULT_INTEGRITY_CANONICALIZATION,
        "scope": _SOLVER_RESULT_INTEGRITY_SCOPE,
        "sha256": _solver_result_sha256(result),
    }
    return result


def _solver_result_integrity_audit(result: dict) -> dict:
    retained = result.get("result_integrity")
    recomputed_sha256 = _solver_result_sha256(result)
    if not isinstance(retained, dict):
        return {
            "available": False,
            "metadata_matches_expected": False,
            "sha256_matches_recomputed": False,
            "consistent": False,
            "recorded_sha256": None,
            "recomputed_sha256": recomputed_sha256,
            "verdict": "solver_result_integrity_missing",
        }

    metadata_matches_expected = (
        retained.get("algorithm") == "sha256"
        and retained.get("canonicalization")
        == _SOLVER_RESULT_INTEGRITY_CANONICALIZATION
        and retained.get("scope") == _SOLVER_RESULT_INTEGRITY_SCOPE
    )
    recorded_sha256 = retained.get("sha256")
    sha256_matches_recomputed = (
        isinstance(recorded_sha256, str)
        and recorded_sha256 == recomputed_sha256
    )
    consistent = metadata_matches_expected and sha256_matches_recomputed
    return {
        "available": True,
        "metadata_matches_expected": metadata_matches_expected,
        "sha256_matches_recomputed": sha256_matches_recomputed,
        "consistent": consistent,
        "algorithm": retained.get("algorithm"),
        "canonicalization": retained.get("canonicalization"),
        "scope": retained.get("scope"),
        "recorded_sha256": recorded_sha256,
        "recomputed_sha256": recomputed_sha256,
        "verdict": (
            "solver_result_integrity_consistent"
            if consistent
            else "solver_result_integrity_inconsistent"
        ),
    }


def _network_state_projection(network: dict) -> dict:
    variable_friction = network.get("variable_friction", {})
    projection = {
        "network": network.get("network"),
        "status": network.get("status"),
        "reference_node": network.get("reference_node"),
        "iterations": network.get("iterations"),
        "mass_balance_tolerance_m3_h": network.get(
            "mass_balance_tolerance_m3_h"
        ),
        "nodes": sorted(
            [
                {
                    "name": row["name"],
                    "relative_pressure_pa": row["relative_pressure_pa"],
                    "specified_injection_m3_h": row["specified_injection_m3_h"],
                    "net_edge_outflow_m3_h": row["net_edge_outflow_m3_h"],
                    "mass_balance_residual_m3_h": row[
                        "mass_balance_residual_m3_h"
                    ],
                    "specified_pressure_power_w": row[
                        "specified_pressure_power_w"
                    ],
                }
                for row in network["nodes"]
            ],
            key=lambda row: str(row["name"]),
        ),
        "edges": sorted(
            [
                {
                    "name": row["name"],
                    "start_node": row["start_node"],
                    "end_node": row["end_node"],
                    "resistance_pa_per_m3_s_squared": row[
                        "resistance_pa_per_m3_s_squared"
                    ],
                    "airflow_m3_s": row["airflow_m3_s"],
                    "airflow_m3_h": row["airflow_m3_h"],
                    "flow_direction": row["flow_direction"],
                    "pressure_difference_pa": row["pressure_difference_pa"],
                    "constitutive_pressure_difference_pa": row[
                        "constitutive_pressure_difference_pa"
                    ],
                    "pressure_law_residual_pa": row["pressure_law_residual_pa"],
                    "dissipated_pressure_power_w": row[
                        "dissipated_pressure_power_w"
                    ],
                }
                for row in network["edges"]
            ],
            key=lambda row: str(row["name"]),
        ),
        "max_abs_mass_balance_residual_m3_h": network[
            "max_abs_mass_balance_residual_m3_h"
        ],
        "max_abs_pressure_law_residual_pa": network[
            "max_abs_pressure_law_residual_pa"
        ],
        "pressure_power": network["pressure_power"],
        "variable_friction": {
            "converged": variable_friction.get("converged"),
            "outer_iterations": variable_friction.get("outer_iterations"),
            "resistance_relative_tolerance": variable_friction.get(
                "resistance_relative_tolerance"
            ),
            "relaxation": variable_friction.get("relaxation"),
            "near_zero_airflow_m3_h": variable_friction.get(
                "near_zero_airflow_m3_h"
            ),
            "automatic_friction_edge_count": variable_friction.get(
                "automatic_friction_edge_count"
            ),
            "near_zero_frozen_edge_count": variable_friction.get(
                "near_zero_frozen_edge_count"
            ),
            "max_relative_resistance_closure_error": variable_friction.get(
                "max_relative_resistance_closure_error"
            ),
            "iteration_history": variable_friction.get(
                "iteration_history", []
            ),
            "edge_closure": sorted(
                variable_friction.get("edge_closure", []),
                key=lambda row: str(row["name"]),
            ),
        },
    }
    return _normalize_signed_zero(projection)

def _network_state_sha256(network: dict) -> str:
    canonical_state = _network_state_projection(network)
    encoded = json.dumps(
        canonical_state,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _network_state_projection_value_type(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return type(value).__name__


def _network_state_projection_mismatch(
    *,
    path: str,
    mismatch_kind: str,
    recorded_present: bool,
    recomputed_present: bool,
    recorded_value=None,
    recomputed_value=None,
) -> dict:
    absolute_error = None
    numeric_error_field = None
    if (
        recorded_present
        and recomputed_present
        and isinstance(recorded_value, (int, float))
        and not isinstance(recorded_value, bool)
        and isinstance(recomputed_value, (int, float))
        and not isinstance(recomputed_value, bool)
        and math.isfinite(float(recorded_value))
        and math.isfinite(float(recomputed_value))
    ):
        absolute_error = abs(
            float(recorded_value) - float(recomputed_value)
        )
        numeric_error_field = path.rsplit(".", 1)[-1]
    return {
        "path": path,
        "mismatch_kind": mismatch_kind,
        "recorded_present": recorded_present,
        "recomputed_present": recomputed_present,
        "recorded_type": (
            _network_state_projection_value_type(recorded_value)
            if recorded_present
            else None
        ),
        "recomputed_type": (
            _network_state_projection_value_type(recomputed_value)
            if recomputed_present
            else None
        ),
        "recorded_value": recorded_value if recorded_present else None,
        "recomputed_value": (
            recomputed_value if recomputed_present else None
        ),
        "absolute_error": absolute_error,
        "numeric_error_field": numeric_error_field,
    }


def _network_state_projection_differences(
    recorded,
    recomputed,
    *,
    path: str = "$",
) -> list[dict]:
    if type(recorded) is not type(recomputed):
        return [
            _network_state_projection_mismatch(
                path=path,
                mismatch_kind="type_mismatch",
                recorded_present=True,
                recomputed_present=True,
                recorded_value=recorded,
                recomputed_value=recomputed,
            )
        ]
    if isinstance(recorded, dict):
        differences = []
        for key in sorted(set(recorded) | set(recomputed)):
            child_path = f"{path}.{key}"
            if key not in recorded:
                differences.append(
                    _network_state_projection_mismatch(
                        path=child_path,
                        mismatch_kind="missing_recorded_key",
                        recorded_present=False,
                        recomputed_present=True,
                        recomputed_value=recomputed[key],
                    )
                )
                continue
            if key not in recomputed:
                differences.append(
                    _network_state_projection_mismatch(
                        path=child_path,
                        mismatch_kind="missing_recomputed_key",
                        recorded_present=True,
                        recomputed_present=False,
                        recorded_value=recorded[key],
                    )
                )
                continue
            differences.extend(
                _network_state_projection_differences(
                    recorded[key],
                    recomputed[key],
                    path=child_path,
                )
            )
        return differences
    if isinstance(recorded, list):
        differences = []
        if len(recorded) != len(recomputed):
            differences.append(
                _network_state_projection_mismatch(
                    path=f"{path}.length",
                    mismatch_kind="length_mismatch",
                    recorded_present=True,
                    recomputed_present=True,
                    recorded_value=len(recorded),
                    recomputed_value=len(recomputed),
                )
            )
        for index, (recorded_item, recomputed_item) in enumerate(
            zip(recorded, recomputed)
        ):
            differences.extend(
                _network_state_projection_differences(
                    recorded_item,
                    recomputed_item,
                    path=f"{path}[{index}]",
                )
            )
        return differences
    if recorded == recomputed:
        return []
    return [
        _network_state_projection_mismatch(
            path=path,
            mismatch_kind="value_mismatch",
            recorded_present=True,
            recomputed_present=True,
            recorded_value=recorded,
            recomputed_value=recomputed,
        )
    ]


def _network_state_projection_difference_paths(
    recorded,
    recomputed,
    *,
    path: str = "$",
) -> list[str]:
    return [
        mismatch["path"]
        for mismatch in _network_state_projection_differences(
            recorded,
            recomputed,
            path=path,
        )
    ]


def _maximum_network_state_projection_numeric_errors(
    mismatches: list[dict],
) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for mismatch in mismatches:
        field = mismatch.get("numeric_error_field")
        absolute_error = mismatch.get("absolute_error")
        if field is None or absolute_error is None:
            continue
        grouped.setdefault(str(field), []).append(mismatch)

    evidence = []
    for field in sorted(grouped):
        candidates = grouped[field]
        maximum = max(
            float(candidate["absolute_error"])
            for candidate in candidates
        )
        evidence.append(
            {
                "field": field,
                "comparison_basis": "same_canonical_leaf_field",
                "maximum_absolute_error": maximum,
                "witnesses": [
                    candidate
                    for candidate in candidates
                    if float(candidate["absolute_error"]) == maximum
                ],
            }
        )
    return evidence


def _fan_curve_supplied_point_network_state_replay_audit(
    study: FanVariableFrictionLoopStudy,
    curve_checks: list[dict],
) -> dict:
    expected_count = len(study.fan_curve.points)
    evaluated_count = len(curve_checks)
    replay_checks = []
    violations = []
    projection_mismatches = []
    coverage_gaps = []

    for missing_point_index in range(evaluated_count, expected_count):
        point = study.fan_curve.points[missing_point_index]
        coverage_gaps.append(
            {
                "point_index": missing_point_index,
                "airflow_m3_h": float(point.airflow_m3_h),
                "reason": "supplied_point_not_evaluated",
            }
        )

    for point_index, check in enumerate(curve_checks):
        point = study.fan_curve.points[point_index]
        recorded_sha256 = check.get("network_state_sha256")
        recorded_projection = check.get("network_state_projection")
        replay_error = None
        independent_replay_available = False
        recomputed_sha256 = None
        recomputed_projection = None
        hash_matches = None
        projection_matches = None
        mismatches = []

        if recorded_sha256 is None:
            coverage_gaps.append(
                {
                    "point_index": point_index,
                    "airflow_m3_h": float(point.airflow_m3_h),
                    "reason": "recorded_network_state_sha256_missing",
                }
            )
        if recorded_projection is None:
            coverage_gaps.append(
                {
                    "point_index": point_index,
                    "airflow_m3_h": float(point.airflow_m3_h),
                    "reason": "recorded_network_state_projection_missing",
                }
            )

        try:
            replayed_network, _ = _solve_network_at_airflow(
                study,
                point.airflow_m3_h,
            )
            independent_replay_available = True
            recomputed_sha256 = _network_state_sha256(replayed_network)
            recomputed_projection = _network_state_projection(
                replayed_network
            )
            if recorded_sha256 is not None:
                hash_matches = (
                    str(recorded_sha256) == recomputed_sha256
                )
            if recorded_projection is not None:
                mismatches = _network_state_projection_differences(
                    recorded_projection,
                    recomputed_projection,
                )
                projection_matches = not mismatches
                for mismatch in mismatches:
                    projection_mismatches.append(
                        {
                            "point_index": point_index,
                            "airflow_m3_h": float(point.airflow_m3_h),
                            **mismatch,
                        }
                    )
        except RuntimeError as exc:
            replay_error = str(exc)
            coverage_gaps.append(
                {
                    "point_index": point_index,
                    "airflow_m3_h": float(point.airflow_m3_h),
                    "reason": "independent_replay_failed",
                    "replay_error": replay_error,
                }
            )

        point_consistent = (
            independent_replay_available
            and hash_matches is True
            and projection_matches is True
        )
        evidence = {
            "point_index": point_index,
            "airflow_m3_h": float(point.airflow_m3_h),
            "independent_replay_available": (
                independent_replay_available
            ),
            "recorded_network_state_sha256": (
                None
                if recorded_sha256 is None
                else str(recorded_sha256)
            ),
            "recomputed_network_state_sha256": recomputed_sha256,
            "network_state_hash_matches_independent_replay": (
                hash_matches
            ),
            "network_state_projection_replay_available": (
                recorded_projection is not None
                and independent_replay_available
            ),
            "network_state_projection_matches_independent_replay": (
                projection_matches
            ),
            "network_state_projection_mismatch_count": len(mismatches),
            "network_state_projection_mismatch_paths": [
                mismatch["path"] for mismatch in mismatches
            ],
            "network_state_projection_mismatches": mismatches,
            "network_state_projection_maximum_numeric_errors": (
                _maximum_network_state_projection_numeric_errors(
                    mismatches
                )
            ),
            "point_replay_consistent": point_consistent,
            "replay_error": replay_error,
        }
        replay_checks.append(evidence)
        if (
            hash_matches is False
            or projection_matches is False
            or replay_error is not None
        ):
            violations.append(evidence)

    complete_coverage = not coverage_gaps
    inconsistent_point_indices = sorted(
        {
            check["point_index"]
            for check in replay_checks
            if check["network_state_hash_matches_independent_replay"]
            is False
            or check[
                "network_state_projection_matches_independent_replay"
            ]
            is False
        }
    )
    if not replay_checks:
        verdict = "supplied_point_network_state_replay_not_available"
    elif inconsistent_point_indices:
        verdict = "supplied_point_network_state_replay_inconsistent"
    elif not complete_coverage:
        verdict = (
            "supplied_point_network_state_replay_incomplete_coverage"
        )
    else:
        verdict = "supplied_point_network_state_replay_consistent"

    return {
        "applicable": expected_count > 0,
        "available": bool(replay_checks),
        "algorithm": "sha256",
        "canonicalization": (
            _NETWORK_STATE_CANONICALIZATION
        ),
        "expected_supplied_point_count": expected_count,
        "evaluated_supplied_point_count": evaluated_count,
        "replay_check_count": len(replay_checks),
        "independent_replay_success_count": sum(
            check["independent_replay_available"]
            for check in replay_checks
        ),
        "complete_supplied_point_coverage": (
            evaluated_count == expected_count
        ),
        "replay_evidence_complete": complete_coverage,
        "complete_replay_coverage": complete_coverage,
        "matching_hash_count": sum(
            check[
                "network_state_hash_matches_independent_replay"
            ]
            is True
            for check in replay_checks
        ),
        "matching_projection_count": sum(
            check[
                "network_state_projection_matches_independent_replay"
            ]
            is True
            for check in replay_checks
        ),
        "consistent_point_count": sum(
            check["point_replay_consistent"] is True
            for check in replay_checks
        ),
        "inconsistent_point_count": len(inconsistent_point_indices),
        "incomplete_point_count": len(
            {
                gap["point_index"] for gap in coverage_gaps
            }
        ),
        "all_evaluated_supplied_point_network_state_hashes_match_independent_replay": (
            all(
                check[
                    "network_state_hash_matches_independent_replay"
                ]
                is True
                for check in replay_checks
            )
            if replay_checks
            else None
        ),
        "all_evaluated_supplied_point_network_state_projections_match_independent_replay": (
            all(
                check[
                    "network_state_projection_matches_independent_replay"
                ]
                is True
                for check in replay_checks
            )
            if replay_checks
            else None
        ),
        "complete_supplied_point_network_state_replay": (
            complete_coverage
            and bool(replay_checks)
            and all(
                check["point_replay_consistent"] is True
                for check in replay_checks
            )
        ),
        "hash_violation_point_indices": [
            check["point_index"]
            for check in replay_checks
            if check[
                "network_state_hash_matches_independent_replay"
            ]
            is False
        ],
        "projection_violation_point_indices": [
            check["point_index"]
            for check in replay_checks
            if check[
                "network_state_projection_matches_independent_replay"
            ]
            is False
        ],
        "violation_point_indices": sorted(
            {
                check["point_index"] for check in violations
            }
        ),
        "coverage_gap_point_indices": sorted(
            {
                gap["point_index"] for gap in coverage_gaps
            }
        ),
        "coverage_gaps": coverage_gaps,
        "network_state_projection_mismatch_count": len(
            projection_mismatches
        ),
        "network_state_projection_mismatch_paths": [
            {
                "point_index": mismatch["point_index"],
                "path": mismatch["path"],
            }
            for mismatch in projection_mismatches
        ],
        "network_state_projection_unique_mismatch_paths": sorted(
            {
                mismatch["path"]
                for mismatch in projection_mismatches
            }
        ),
        "network_state_projection_mismatches": projection_mismatches,
        "network_state_projection_maximum_numeric_errors": (
            _maximum_network_state_projection_numeric_errors(
                projection_mismatches
            )
        ),
        "replay_verdict": verdict,
        "violation_count": len(violations),
        "violations": violations,
        "checks": replay_checks,
        "scope_note": (
            "This audit independently re-solves every successfully "
            "evaluated supplied fan-curve point at its exact supplied "
            "airflow and compares both the retained canonical network-state "
            "SHA-256 and full canonical projection with the fresh nonlinear "
            "solve. It reports corruption separately from incomplete point "
            "or replay coverage, including the successfully evaluated prefix "
            "before network-solver failure. It does not alter candidate "
            "discovery, root selection, solver tolerances, convergence, or "
            "engineering acceptance. This is deterministic numerical/"
            "provenance verification only, not physical uncertainty, fan "
            "stability, cleanroom certification, commissioning evidence, "
            "or equipment acceptance."
        ),
    }


def _point_check(
    study: FanVariableFrictionLoopStudy,
    point: FanCurvePoint,
) -> tuple[dict, dict]:
    network, network_pressure = _solve_network_at_airflow(
        study, point.airflow_m3_h
    )
    total_pressure = study.fixed_pressure_pa + network_pressure
    residual = point.pressure_pa - total_pressure
    vf = network["variable_friction"]
    return (
        {
            "airflow_m3_h": round(point.airflow_m3_h, 6),
            "fan_pressure_pa": round(point.pressure_pa, 9),
            "loop_network_pressure_pa": round(network_pressure, 9),
            "system_pressure_pa": round(total_pressure, 9),
            "pressure_margin_pa": round(residual, 9),
            "network_outer_iterations": vf["outer_iterations"],
            "network_newton_iterations": network["iterations"],
            "max_relative_resistance_closure_error": vf[
                "max_relative_resistance_closure_error"
            ],
            "network_state_sha256": _network_state_sha256(network),
            "network_state_projection": _network_state_projection(network),
        },
        network,
    )


def _fan_curve_supplied_point_residual_audit(
    study: FanVariableFrictionLoopStudy,
    curve_checks: list[dict],
) -> dict:
    tolerance = float(study.operating_pressure_tolerance_pa)
    expected_count = len(study.fan_curve.points)
    observed_count = len(curve_checks)
    residuals = [
        float(check["pressure_margin_pa"]) for check in curve_checks
    ]

    tolerance_contacts = [
        {
            "point_index": index,
            "airflow_m3_h": check["airflow_m3_h"],
            "fan_minus_system_pressure_pa": check["pressure_margin_pa"],
        }
        for index, check in enumerate(curve_checks)
        if abs(float(check["pressure_margin_pa"])) <= tolerance
    ]

    strict_sign_change_segments = []
    reverse_strict_sign_change_segments = []
    residual_transitions = []
    positive_increases = []
    for index, (left, right) in enumerate(
        zip(curve_checks, curve_checks[1:])
    ):
        left_residual = float(left["pressure_margin_pa"])
        right_residual = float(right["pressure_margin_pa"])
        delta = right_residual - left_residual
        if delta > tolerance:
            classification = "increase"
            positive_increases.append(delta)
        elif delta < -tolerance:
            classification = "decrease"
        else:
            classification = "within_tolerance"
        residual_transitions.append(
            {
                "low_point_index": index,
                "high_point_index": index + 1,
                "low_airflow_m3_h": left["airflow_m3_h"],
                "high_airflow_m3_h": right["airflow_m3_h"],
                "residual_change_pa": round(delta, 9),
                "classification": classification,
            }
        )
        if left_residual > 0.0 and right_residual < 0.0:
            strict_sign_change_segments.append(
                {
                    "low_point_index": index,
                    "high_point_index": index + 1,
                    "low_airflow_m3_h": left["airflow_m3_h"],
                    "high_airflow_m3_h": right["airflow_m3_h"],
                    "low_fan_minus_system_pressure_pa": left[
                        "pressure_margin_pa"
                    ],
                    "high_fan_minus_system_pressure_pa": right[
                        "pressure_margin_pa"
                    ],
                }
            )
        elif left_residual < 0.0 and right_residual > 0.0:
            reverse_strict_sign_change_segments.append(
                {
                    "low_point_index": index,
                    "high_point_index": index + 1,
                    "low_airflow_m3_h": left["airflow_m3_h"],
                    "high_airflow_m3_h": right["airflow_m3_h"],
                    "low_fan_minus_system_pressure_pa": left[
                        "pressure_margin_pa"
                    ],
                    "high_fan_minus_system_pressure_pa": right[
                        "pressure_margin_pa"
                    ],
                }
            )

    increase_count = sum(
        transition["classification"] == "increase"
        for transition in residual_transitions
    )
    candidate_features = [
        {
            "feature_kind": "supplied_point_tolerance_contact",
            "point_index": contact["point_index"],
            "supplied_point_index_interval_low": contact["point_index"],
            "supplied_point_index_interval_high": contact["point_index"],
            "airflow_m3_h": contact["airflow_m3_h"],
            "fan_minus_system_pressure_pa": contact[
                "fan_minus_system_pressure_pa"
            ],
        }
        for contact in tolerance_contacts
    ]
    candidate_features.extend(
        {
            "feature_kind": "strict_sign_change_segment",
            **segment,
            "supplied_point_index_interval_low": segment["low_point_index"],
            "supplied_point_index_interval_high": segment["high_point_index"],
        }
        for segment in strict_sign_change_segments
    )
    for priority_rank, feature in enumerate(candidate_features):
        feature["solver_priority_rank"] = priority_rank

    supplied_airflow_spacings_m3_h = [
        float(right.airflow_m3_h) - float(left.airflow_m3_h)
        for left, right in zip(study.fan_curve.points, study.fan_curve.points[1:])
    ]
    minimum_supplied_point_airflow_spacing_m3_h = min(
        supplied_airflow_spacings_m3_h
    )
    maximum_supplied_point_airflow_spacing_m3_h = max(
        supplied_airflow_spacings_m3_h
    )

    return {
        "expected_supplied_point_count": expected_count,
        "evaluated_supplied_point_count": observed_count,
        "complete_supplied_point_coverage": observed_count == expected_count,
        "operating_pressure_tolerance_pa": tolerance,
        "supplied_fan_curve_airflow_span_m3_h": round(
            study.fan_curve.points[-1].airflow_m3_h
            - study.fan_curve.points[0].airflow_m3_h,
            9,
        ),
        "minimum_supplied_point_airflow_spacing_m3_h": round(
            minimum_supplied_point_airflow_spacing_m3_h, 9
        ),
        "maximum_supplied_point_airflow_spacing_m3_h": round(
            maximum_supplied_point_airflow_spacing_m3_h, 9
        ),
        "supplied_point_airflow_spacing_ratio_max_to_min": round(
            maximum_supplied_point_airflow_spacing_m3_h
            / minimum_supplied_point_airflow_spacing_m3_h,
            12,
        ),
        "tolerance_contact_point_count": len(tolerance_contacts),
        "tolerance_contact_points": tolerance_contacts,
        "strict_sign_change_segment_count": len(strict_sign_change_segments),
        "strict_sign_change_segments": strict_sign_change_segments,
        "reverse_strict_sign_change_segment_count": len(
            reverse_strict_sign_change_segments
        ),
        "reverse_strict_sign_change_segments": reverse_strict_sign_change_segments,
        "all_strict_sign_change_segment_count": (
            len(strict_sign_change_segments)
            + len(reverse_strict_sign_change_segments)
        ),
        "candidate_crossing_feature_count": len(candidate_features),
        "candidate_crossing_features_in_solver_priority_order": (
            candidate_features
        ),
        "selected_candidate_feature": None,
        "selected_candidate_feature_rank": None,
        "additional_candidate_feature_count": None,
        "selected_candidate_is_only_discrete_feature": None,
        "alternative_candidate_features": None,
        "nearest_alternative_candidate_airflow_interval_gap_m3_h": None,
        "nearest_alternative_candidate_airflow_interval_gap_fraction_of_supplied_curve_span": None,
        "nearest_alternative_candidate_airflow_interval_gap_fraction_of_minimum_supplied_point_spacing": None,
        "nearest_alternative_candidate_feature_index_interval_gap": None,
        "nearest_alternative_candidate_features_by_index_interval_gap": None,
        "nearest_alternative_candidate_features": None,
        "selected_airflow_overlaps_alternative_candidate_interval": None,
        "selection_policy": (
            "first supplied-point tolerance contact in point order; otherwise "
            "first strict positive-to-negative sign-change segment in segment "
            "order"
        ),
        "residual_transition_count": len(residual_transitions),
        "residual_increase_transition_count": increase_count,
        "residual_monotonic_non_increasing_with_tolerance": (
            increase_count == 0
        ),
        "largest_positive_residual_increase_pa": round(
            max(positive_increases, default=0.0),
            9,
        ),
        "residual_transitions": residual_transitions,
        "scope_note": (
            "This is a discrete audit of fan-minus-system pressure residuals "
            "at the supplied fan-curve points already evaluated by the solver. "
            "It reports tolerance contacts, solver-eligible positive-to-negative "
            "strict sign-change segments, audit-only reverse negative-to-positive "
            "strict sign-change segments, and whether those sampled residuals are "
            "non-increasing within the configured pressure tolerance. Candidate "
            "features remain limited to the solver's actual positive-to-negative "
            "selection priority, while selected-"
            "candidate provenance is added only for solved results. For solved "
            "cases with additional candidates, airflow separation is measured "
            "only to each alternative discrete point or sign-change interval "
            "and normalized by both the supplied fan-curve airflow span and "
            "the minimum adjacent supplied-point airflow spacing. Candidate "
            "separation is also measured between exact supplied-point index "
            "intervals; that value is discrete sample-grid topology only, and "
            "no alternate continuous root location is inferred. Candidate "
            "crossing features are not a count or proof of continuous physical "
            "intersections, and sampled monotonicity is not a dynamic stability, stall/surge, "
            "manufacturer-region, or equipment-acceptance criterion."
        ),
    }


def _with_selected_crossing_feature(
    audit: dict,
    *,
    termination_reason: str,
    selected_airflow_m3_h: float,
    selected_segment_index: int,
) -> dict:
    enriched = dict(audit)
    candidates = audit["candidate_crossing_features_in_solver_priority_order"]
    selected = None

    if termination_reason == "fan_curve_point_residual":
        for feature in candidates:
            if feature["feature_kind"] != "supplied_point_tolerance_contact":
                continue
            if math.isclose(
                float(feature["airflow_m3_h"]),
                float(selected_airflow_m3_h),
                rel_tol=1e-12,
                abs_tol=1e-6,
            ):
                selected = feature
                break
    else:
        for feature in candidates:
            if feature["feature_kind"] != "strict_sign_change_segment":
                continue
            if int(feature["low_point_index"]) == int(selected_segment_index):
                selected = feature
                break

    selected_copy = None if selected is None else dict(selected)
    selected_rank = (
        None if selected_copy is None else selected_copy["solver_priority_rank"]
    )

    alternative_features = None
    nearest_alternative_gap = None
    nearest_alternative_gap_fraction = None
    nearest_alternative_gap_fraction_of_minimum_spacing = None
    nearest_alternative_index_gap = None
    nearest_alternative_features_by_index_gap = None
    nearest_alternative_features = None
    selected_overlaps_alternative_interval = None
    if selected_copy is not None:
        alternative_features = []
        airflow = float(selected_airflow_m3_h)
        supplied_curve_span = float(
            audit["supplied_fan_curve_airflow_span_m3_h"]
        )
        minimum_supplied_point_spacing = float(
            audit["minimum_supplied_point_airflow_spacing_m3_h"]
        )
        selected_index_low = int(
            selected_copy["supplied_point_index_interval_low"]
        )
        selected_index_high = int(
            selected_copy["supplied_point_index_interval_high"]
        )
        for feature in candidates:
            if feature["solver_priority_rank"] == selected_rank:
                continue
            alternative = dict(feature)
            if feature["feature_kind"] == "supplied_point_tolerance_contact":
                low_airflow = float(feature["airflow_m3_h"])
                high_airflow = low_airflow
            else:
                low_airflow = float(feature["low_airflow_m3_h"])
                high_airflow = float(feature["high_airflow_m3_h"])
            alternative_index_low = int(
                feature["supplied_point_index_interval_low"]
            )
            alternative_index_high = int(
                feature["supplied_point_index_interval_high"]
            )
            if selected_index_high < alternative_index_low:
                index_gap = alternative_index_low - selected_index_high
            elif selected_index_low > alternative_index_high:
                index_gap = selected_index_low - alternative_index_high
            else:
                index_gap = 0
            if airflow < low_airflow:
                gap = low_airflow - airflow
            elif airflow > high_airflow:
                gap = airflow - high_airflow
            else:
                gap = 0.0
            alternative.update(
                {
                    "airflow_interval_low_m3_h": round(low_airflow, 9),
                    "airflow_interval_high_m3_h": round(high_airflow, 9),
                    "selected_airflow_to_feature_interval_gap_m3_h": round(
                        gap,
                        9,
                    ),
                    "selected_airflow_to_feature_interval_gap_fraction_of_supplied_curve_span": round(
                        gap / supplied_curve_span,
                        12,
                    ),
                    "selected_airflow_to_feature_interval_gap_fraction_of_minimum_supplied_point_spacing": round(
                        gap / minimum_supplied_point_spacing,
                        12,
                    ),
                    "selected_feature_to_candidate_feature_index_interval_gap": (
                        index_gap
                    ),
                }
            )
            alternative_features.append(alternative)

        if alternative_features:
            nearest_alternative_gap = min(
                float(
                    feature[
                        "selected_airflow_to_feature_interval_gap_m3_h"
                    ]
                )
                for feature in alternative_features
            )
            nearest_alternative_features = [
                dict(feature)
                for feature in alternative_features
                if math.isclose(
                    float(
                        feature[
                            "selected_airflow_to_feature_interval_gap_m3_h"
                        ]
                    ),
                    nearest_alternative_gap,
                    rel_tol=1e-12,
                    abs_tol=1e-9,
                )
            ]
            nearest_alternative_index_gap = min(
                int(
                    feature[
                        "selected_feature_to_candidate_feature_index_interval_gap"
                    ]
                )
                for feature in alternative_features
            )
            nearest_alternative_features_by_index_gap = [
                dict(feature)
                for feature in alternative_features
                if int(
                    feature[
                        "selected_feature_to_candidate_feature_index_interval_gap"
                    ]
                )
                == nearest_alternative_index_gap
            ]
            selected_overlaps_alternative_interval = math.isclose(
                nearest_alternative_gap,
                0.0,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            nearest_alternative_gap_fraction = round(
                nearest_alternative_gap / supplied_curve_span,
                12,
            )
            nearest_alternative_gap_fraction_of_minimum_spacing = round(
                nearest_alternative_gap / minimum_supplied_point_spacing,
                12,
            )
            nearest_alternative_gap = round(nearest_alternative_gap, 9)
        else:
            nearest_alternative_features = []
            nearest_alternative_features_by_index_gap = []
            selected_overlaps_alternative_interval = False

    enriched.update(
        {
            "selected_candidate_feature": selected_copy,
            "selected_candidate_feature_rank": selected_rank,
            "additional_candidate_feature_count": (
                None
                if selected_copy is None
                else max(0, len(candidates) - 1)
            ),
            "selected_candidate_is_only_discrete_feature": (
                None if selected_copy is None else len(candidates) == 1
            ),
            "alternative_candidate_features": alternative_features,
            "nearest_alternative_candidate_airflow_interval_gap_m3_h": (
                nearest_alternative_gap
            ),
            "nearest_alternative_candidate_airflow_interval_gap_fraction_of_supplied_curve_span": (
                nearest_alternative_gap_fraction
            ),
            "nearest_alternative_candidate_airflow_interval_gap_fraction_of_minimum_supplied_point_spacing": (
                nearest_alternative_gap_fraction_of_minimum_spacing
            ),
            "nearest_alternative_candidate_feature_index_interval_gap": (
                nearest_alternative_index_gap
            ),
            "nearest_alternative_candidate_features_by_index_interval_gap": (
                nearest_alternative_features_by_index_gap
            ),
            "nearest_alternative_candidate_features": (
                nearest_alternative_features
            ),
            "selected_airflow_overlaps_alternative_candidate_interval": (
                selected_overlaps_alternative_interval
            ),
        }
    )
    return enriched


def _bisection_decision_trace_audit(
    trace: list[dict] | None,
    *,
    operating_iterations: int,
    termination_reason: str,
    operating_pressure_tolerance_pa: float,
    expected_fixed_pressure_pa: float | None = None,
    study: FanVariableFrictionLoopStudy | None = None,
    segment_left: FanCurvePoint | None = None,
    segment_right: FanCurvePoint | None = None,
    initial_bisection_bracket: dict | None = None,
    solved_terminal_bracket: dict | None = None,
    iteration_limit_terminal_bracket: dict | None = None,
) -> dict | None:
    if trace is None:
        return None

    termination_indices = [
        index
        for index, step in enumerate(trace)
        if step["decision"] == "accept_pressure_tolerance"
    ]
    legend = {
        "L": "replace_low_endpoint",
        "H": "replace_high_endpoint",
        "T": "accept_pressure_tolerance",
    }
    symbol_by_decision = {
        decision: symbol for symbol, decision in legend.items()
    }
    iteration_sequence = [int(step["iteration"]) for step in trace]
    raw_state_checks = []
    pressure_state_checks = []
    geometry_checks = []
    for step in trace:
        iteration = int(step["iteration"])
        low_airflow = float(step["low_airflow_m3_h"])
        high_airflow = float(step["high_airflow_m3_h"])
        midpoint_airflow = float(step["midpoint_airflow_m3_h"])
        low_residual = float(step["low_fan_minus_system_pressure_pa"])
        high_residual = float(step["high_fan_minus_system_pressure_pa"])
        recorded_sign_flag = bool(
            step["strict_sign_change_before_evaluation"]
        )
        recorded_midpoint_flag = bool(
            step["midpoint_is_arithmetic_bracket_midpoint"]
        )
        recorded_width = float(step["width_m3_h"])
        recorded_width_fraction = float(
            step["width_fraction_of_supplied_segment"]
        )
        pressure_fields = (
            "midpoint_fan_pressure_pa",
            "midpoint_loop_network_pressure_pa",
            "midpoint_fixed_pressure_pa",
            "midpoint_system_pressure_pa",
            "midpoint_fan_minus_system_pressure_pa",
        )
        if all(field in step for field in pressure_fields):
            recorded_fan_pressure = float(step["midpoint_fan_pressure_pa"])
            recorded_loop_pressure = float(
                step["midpoint_loop_network_pressure_pa"]
            )
            recorded_fixed_pressure = float(
                step["midpoint_fixed_pressure_pa"]
            )
            recorded_system_pressure = float(
                step["midpoint_system_pressure_pa"]
            )
            recorded_midpoint_residual = float(
                step["midpoint_fan_minus_system_pressure_pa"]
            )
            expected_system_pressure = (
                recorded_fixed_pressure + recorded_loop_pressure
            )
            expected_midpoint_residual = (
                recorded_fan_pressure - recorded_system_pressure
            )
            system_pressure_balance_error = abs(
                recorded_system_pressure - expected_system_pressure
            )
            residual_balance_error = abs(
                recorded_midpoint_residual - expected_midpoint_residual
            )
            fixed_pressure_matches_expected = (
                expected_fixed_pressure_pa is None
                or math.isclose(
                    recorded_fixed_pressure,
                    float(expected_fixed_pressure_pa),
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
            )
            pressure_state_checks.append(
                {
                    "iteration": iteration,
                    "recorded_midpoint_fan_pressure_pa": (
                        recorded_fan_pressure
                    ),
                    "recorded_midpoint_loop_network_pressure_pa": (
                        recorded_loop_pressure
                    ),
                    "recorded_midpoint_fixed_pressure_pa": (
                        recorded_fixed_pressure
                    ),
                    "recorded_midpoint_system_pressure_pa": (
                        recorded_system_pressure
                    ),
                    "expected_midpoint_system_pressure_pa": (
                        expected_system_pressure
                    ),
                    "absolute_system_pressure_balance_error_pa": (
                        system_pressure_balance_error
                    ),
                    "recorded_midpoint_fan_minus_system_pressure_pa": (
                        recorded_midpoint_residual
                    ),
                    "expected_midpoint_fan_minus_system_pressure_pa": (
                        expected_midpoint_residual
                    ),
                    "absolute_residual_balance_error_pa": (
                        residual_balance_error
                    ),
                    "recorded_fixed_pressure_matches_study": (
                        fixed_pressure_matches_expected
                    ),
                    "recorded_system_pressure_matches_fixed_plus_loop": (
                        math.isclose(
                            recorded_system_pressure,
                            expected_system_pressure,
                            rel_tol=0.0,
                            abs_tol=2e-9,
                        )
                    ),
                    "recorded_residual_matches_fan_minus_system": (
                        math.isclose(
                            recorded_midpoint_residual,
                            expected_midpoint_residual,
                            rel_tol=0.0,
                            abs_tol=2e-9,
                        )
                    ),
                }
            )
        expected_width = high_airflow - low_airflow
        expected_width_fraction = 0.5 ** (iteration - 1)
        absolute_width_error = abs(recorded_width - expected_width)
        absolute_width_fraction_error = abs(
            recorded_width_fraction - expected_width_fraction
        )
        expected_midpoint_airflow = 0.5 * (low_airflow + high_airflow)
        absolute_midpoint_error = abs(
            midpoint_airflow - expected_midpoint_airflow
        )
        numeric_sign_change = low_residual > 0.0 and high_residual < 0.0
        numeric_midpoint_centered = math.isclose(
            midpoint_airflow,
            expected_midpoint_airflow,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        raw_state_checks.append(
            {
                "iteration": iteration,
                "numeric_strict_sign_change_before_evaluation": (
                    numeric_sign_change
                ),
                "recorded_strict_sign_change_flag": recorded_sign_flag,
                "recorded_sign_flag_matches_numeric_residuals": (
                    recorded_sign_flag == numeric_sign_change
                ),
                "recorded_midpoint_airflow_m3_h": midpoint_airflow,
                "expected_midpoint_airflow_from_endpoints_m3_h": (
                    expected_midpoint_airflow
                ),
                "absolute_midpoint_error_m3_h": absolute_midpoint_error,
                "numeric_midpoint_is_arithmetic_bracket_midpoint": (
                    numeric_midpoint_centered
                ),
                "recorded_midpoint_flag": recorded_midpoint_flag,
                "recorded_midpoint_flag_matches_numeric_geometry": (
                    recorded_midpoint_flag == numeric_midpoint_centered
                ),
            }
        )
        geometry_checks.append(
            {
                "iteration": iteration,
                "recorded_width_m3_h": recorded_width,
                "expected_width_from_endpoints_m3_h": expected_width,
                "absolute_width_error_m3_h": absolute_width_error,
                "recorded_width_fraction_of_supplied_segment": (
                    recorded_width_fraction
                ),
                "expected_width_fraction_from_iteration": (
                    expected_width_fraction
                ),
                "absolute_width_fraction_error": (
                    absolute_width_fraction_error
                ),
                "recorded_width_matches_airflow_bracket": math.isclose(
                    recorded_width,
                    expected_width,
                    rel_tol=0.0,
                    abs_tol=2e-9,
                ),
                "recorded_width_fraction_matches_iteration_sequence": (
                    math.isclose(
                        recorded_width_fraction,
                        expected_width_fraction,
                        rel_tol=0.0,
                        abs_tol=1e-12,
                    )
                ),
            }
        )

    residual_replay_checks = []
    pressure_component_replay_checks = []
    network_state_replay_checks = []
    network_state_projection_replay_checks = []
    terminal_pressure_component_replay = None
    terminal_network_state_replay = None
    residual_replay_available = (
        study is not None
        and segment_left is not None
        and segment_right is not None
    )
    residual_replay_absolute_tolerance_pa = 1e-9
    pressure_component_replay_absolute_tolerance_pa = 1e-9
    if residual_replay_available:
        assert study is not None
        assert segment_left is not None
        assert segment_right is not None
        replay_low_airflow = float(segment_left.airflow_m3_h)
        replay_high_airflow = float(segment_right.airflow_m3_h)
        state_cache: dict[float, dict] = {}

        def _independent_state(airflow_m3_h: float) -> dict:
            airflow = float(airflow_m3_h)
            if airflow not in state_cache:
                _network, network_pressure = _solve_network_at_airflow(
                    study,
                    airflow,
                )
                fan_pressure = _fan_pressure(
                    segment_left,
                    segment_right,
                    airflow,
                )
                system_pressure = study.fixed_pressure_pa + network_pressure
                state_cache[airflow] = {
                    "fan_pressure_pa": fan_pressure,
                    "loop_network_pressure_pa": network_pressure,
                    "system_pressure_pa": system_pressure,
                    "residual_pa": fan_pressure - system_pressure,
                    "network_state_sha256": _network_state_sha256(_network),
                    "network_state_projection": _network_state_projection(
                        _network
                    ),
                }
            return state_cache[airflow]

        for step in trace:
            replay_midpoint_airflow = 0.5 * (
                replay_low_airflow + replay_high_airflow
            )
            low_state = _independent_state(replay_low_airflow)
            high_state = _independent_state(replay_high_airflow)
            midpoint_state = _independent_state(replay_midpoint_airflow)
            recomputed_low_residual = low_state["residual_pa"]
            recomputed_high_residual = high_state["residual_pa"]
            recomputed_midpoint_residual = midpoint_state["residual_pa"]
            recorded_low_residual = float(
                step["low_fan_minus_system_pressure_pa"]
            )
            recorded_high_residual = float(
                step["high_fan_minus_system_pressure_pa"]
            )
            recorded_midpoint_residual = float(
                step["midpoint_fan_minus_system_pressure_pa"]
            )
            low_error = abs(
                recorded_low_residual - recomputed_low_residual
            )
            high_error = abs(
                recorded_high_residual - recomputed_high_residual
            )
            midpoint_error = abs(
                recorded_midpoint_residual - recomputed_midpoint_residual
            )
            low_matches = math.isclose(
                recorded_low_residual,
                recomputed_low_residual,
                rel_tol=0.0,
                abs_tol=residual_replay_absolute_tolerance_pa,
            )
            high_matches = math.isclose(
                recorded_high_residual,
                recomputed_high_residual,
                rel_tol=0.0,
                abs_tol=residual_replay_absolute_tolerance_pa,
            )
            midpoint_matches = math.isclose(
                recorded_midpoint_residual,
                recomputed_midpoint_residual,
                rel_tol=0.0,
                abs_tol=residual_replay_absolute_tolerance_pa,
            )
            residual_replay_checks.append(
                {
                    "iteration": int(step["iteration"]),
                    "replayed_low_airflow_m3_h": round(
                        replay_low_airflow,
                        9,
                    ),
                    "replayed_high_airflow_m3_h": round(
                        replay_high_airflow,
                        9,
                    ),
                    "replayed_midpoint_airflow_m3_h": round(
                        replay_midpoint_airflow,
                        9,
                    ),
                    "recorded_low_fan_minus_system_pressure_pa": (
                        recorded_low_residual
                    ),
                    "recomputed_low_fan_minus_system_pressure_pa": round(
                        recomputed_low_residual,
                        9,
                    ),
                    "absolute_low_residual_replay_error_pa": low_error,
                    "recorded_high_fan_minus_system_pressure_pa": (
                        recorded_high_residual
                    ),
                    "recomputed_high_fan_minus_system_pressure_pa": round(
                        recomputed_high_residual,
                        9,
                    ),
                    "absolute_high_residual_replay_error_pa": high_error,
                    "recorded_midpoint_fan_minus_system_pressure_pa": (
                        recorded_midpoint_residual
                    ),
                    "recomputed_midpoint_fan_minus_system_pressure_pa": round(
                        recomputed_midpoint_residual,
                        9,
                    ),
                    "absolute_midpoint_residual_replay_error_pa": (
                        midpoint_error
                    ),
                    "low_residual_matches_independent_replay": low_matches,
                    "high_residual_matches_independent_replay": high_matches,
                    "midpoint_residual_matches_independent_replay": (
                        midpoint_matches
                    ),
                    "all_residuals_match_independent_replay": (
                        low_matches and high_matches and midpoint_matches
                    ),
                }
            )

            pressure_component_fields = tuple(
                f"{position}_{component}_pressure_pa"
                for position in ("low", "midpoint", "high")
                for component in (
                    "fan",
                    "loop_network",
                    "system",
                )
            )
            if all(field in step for field in pressure_component_fields):
                position_states = {
                    "low": (
                        replay_low_airflow,
                        low_state,
                    ),
                    "midpoint": (
                        replay_midpoint_airflow,
                        midpoint_state,
                    ),
                    "high": (
                        replay_high_airflow,
                        high_state,
                    ),
                }
                position_checks = {}
                for position, (
                    replayed_airflow,
                    recomputed_state,
                ) in position_states.items():
                    recorded_fan_pressure = float(
                        step[f"{position}_fan_pressure_pa"]
                    )
                    recorded_loop_pressure = float(
                        step[f"{position}_loop_network_pressure_pa"]
                    )
                    recorded_system_pressure = float(
                        step[f"{position}_system_pressure_pa"]
                    )
                    recomputed_fan_pressure = recomputed_state[
                        "fan_pressure_pa"
                    ]
                    recomputed_loop_pressure = recomputed_state[
                        "loop_network_pressure_pa"
                    ]
                    recomputed_system_pressure = recomputed_state[
                        "system_pressure_pa"
                    ]
                    fan_error = abs(
                        recorded_fan_pressure - recomputed_fan_pressure
                    )
                    loop_error = abs(
                        recorded_loop_pressure - recomputed_loop_pressure
                    )
                    system_error = abs(
                        recorded_system_pressure
                        - recomputed_system_pressure
                    )
                    fan_matches = math.isclose(
                        recorded_fan_pressure,
                        recomputed_fan_pressure,
                        rel_tol=0.0,
                        abs_tol=(
                            pressure_component_replay_absolute_tolerance_pa
                        ),
                    )
                    loop_matches = math.isclose(
                        recorded_loop_pressure,
                        recomputed_loop_pressure,
                        rel_tol=0.0,
                        abs_tol=(
                            pressure_component_replay_absolute_tolerance_pa
                        ),
                    )
                    system_matches = math.isclose(
                        recorded_system_pressure,
                        recomputed_system_pressure,
                        rel_tol=0.0,
                        abs_tol=(
                            pressure_component_replay_absolute_tolerance_pa
                        ),
                    )
                    position_checks[position] = {
                        "replayed_airflow_m3_h": round(
                            replayed_airflow,
                            9,
                        ),
                        "recorded_fan_pressure_pa": recorded_fan_pressure,
                        "recomputed_fan_pressure_pa": round(
                            recomputed_fan_pressure,
                            9,
                        ),
                        "absolute_fan_pressure_replay_error_pa": fan_error,
                        "recorded_loop_network_pressure_pa": (
                            recorded_loop_pressure
                        ),
                        "recomputed_loop_network_pressure_pa": round(
                            recomputed_loop_pressure,
                            9,
                        ),
                        "absolute_loop_pressure_replay_error_pa": loop_error,
                        "recorded_system_pressure_pa": recorded_system_pressure,
                        "recomputed_system_pressure_pa": round(
                            recomputed_system_pressure,
                            9,
                        ),
                        "absolute_system_pressure_replay_error_pa": (
                            system_error
                        ),
                        "fan_pressure_matches_independent_replay": (
                            fan_matches
                        ),
                        "loop_pressure_matches_independent_replay": (
                            loop_matches
                        ),
                        "system_pressure_matches_independent_replay": (
                            system_matches
                        ),
                        "all_pressure_components_match_independent_replay": (
                            fan_matches and loop_matches and system_matches
                        ),
                    }
                midpoint_check = position_checks["midpoint"]
                pressure_component_replay_checks.append(
                    {
                        "iteration": int(step["iteration"]),
                        "low": position_checks["low"],
                        "midpoint": midpoint_check,
                        "high": position_checks["high"],
                        "replayed_midpoint_airflow_m3_h": midpoint_check[
                            "replayed_airflow_m3_h"
                        ],
                        "recorded_midpoint_fan_pressure_pa": midpoint_check[
                            "recorded_fan_pressure_pa"
                        ],
                        "recomputed_midpoint_fan_pressure_pa": midpoint_check[
                            "recomputed_fan_pressure_pa"
                        ],
                        "absolute_midpoint_fan_pressure_replay_error_pa": (
                            midpoint_check[
                                "absolute_fan_pressure_replay_error_pa"
                            ]
                        ),
                        "recorded_midpoint_loop_network_pressure_pa": (
                            midpoint_check[
                                "recorded_loop_network_pressure_pa"
                            ]
                        ),
                        "recomputed_midpoint_loop_network_pressure_pa": (
                            midpoint_check[
                                "recomputed_loop_network_pressure_pa"
                            ]
                        ),
                        "absolute_midpoint_loop_pressure_replay_error_pa": (
                            midpoint_check[
                                "absolute_loop_pressure_replay_error_pa"
                            ]
                        ),
                        "recorded_midpoint_system_pressure_pa": (
                            midpoint_check["recorded_system_pressure_pa"]
                        ),
                        "recomputed_midpoint_system_pressure_pa": (
                            midpoint_check["recomputed_system_pressure_pa"]
                        ),
                        "absolute_midpoint_system_pressure_replay_error_pa": (
                            midpoint_check[
                                "absolute_system_pressure_replay_error_pa"
                            ]
                        ),
                        "fan_pressure_matches_independent_replay": (
                            midpoint_check[
                                "fan_pressure_matches_independent_replay"
                            ]
                        ),
                        "loop_pressure_matches_independent_replay": (
                            midpoint_check[
                                "loop_pressure_matches_independent_replay"
                            ]
                        ),
                        "system_pressure_matches_independent_replay": (
                            midpoint_check[
                                "system_pressure_matches_independent_replay"
                            ]
                        ),
                        "all_pressure_components_match_independent_replay": (
                            midpoint_check[
                                "all_pressure_components_match_independent_replay"
                            ]
                        ),
                        "all_low_pressure_components_match_independent_replay": (
                            position_checks["low"][
                                "all_pressure_components_match_independent_replay"
                            ]
                        ),
                        "all_high_pressure_components_match_independent_replay": (
                            position_checks["high"][
                                "all_pressure_components_match_independent_replay"
                            ]
                        ),
                        "all_bracket_pressure_components_match_independent_replay": (
                            all(
                                check[
                                    "all_pressure_components_match_independent_replay"
                                ]
                                for check in position_checks.values()
                            )
                        ),
                        "maximum_absolute_pressure_component_replay_error_pa": (
                            max(
                                max(
                                    check[
                                        "absolute_fan_pressure_replay_error_pa"
                                    ],
                                    check[
                                        "absolute_loop_pressure_replay_error_pa"
                                    ],
                                    check[
                                        "absolute_system_pressure_replay_error_pa"
                                    ],
                                )
                                for check in position_checks.values()
                            )
                        ),
                    }
                )

            network_position_states = {
                "low": low_state,
                "midpoint": midpoint_state,
                "high": high_state,
            }
            network_position_airflows = {
                "low": replay_low_airflow,
                "midpoint": replay_midpoint_airflow,
                "high": replay_high_airflow,
            }
            network_state_fields = tuple(
                f"{position}_network_state_sha256"
                for position in ("low", "midpoint", "high")
            )
            if all(field in step for field in network_state_fields):
                network_position_checks = {}
                for position, recomputed_state in (
                    network_position_states.items()
                ):
                    recorded_sha256 = str(
                        step[f"{position}_network_state_sha256"]
                    )
                    recomputed_sha256 = str(
                        recomputed_state["network_state_sha256"]
                    )
                    network_position_checks[position] = {
                        "recorded_network_state_sha256": recorded_sha256,
                        "recomputed_network_state_sha256": (
                            recomputed_sha256
                        ),
                        "network_state_matches_independent_replay": (
                            recorded_sha256 == recomputed_sha256
                        ),
                    }
                network_state_replay_checks.append(
                    {
                        "iteration": int(step["iteration"]),
                        "algorithm": "sha256",
                        "canonicalization": (
                            _NETWORK_STATE_CANONICALIZATION
                        ),
                        "low": network_position_checks["low"],
                        "midpoint": network_position_checks["midpoint"],
                        "high": network_position_checks["high"],
                        "all_network_states_match_independent_replay": all(
                            check[
                                "network_state_matches_independent_replay"
                            ]
                            for check in network_position_checks.values()
                        ),
                    }
                )

            projection_position_checks = {}
            for position in ("low", "midpoint", "high"):
                projection_field = (
                    f"{position}_network_state_projection"
                )
                if projection_field not in step:
                    continue
                recorded_projection = step[projection_field]
                recomputed_projection = network_position_states[position][
                    "network_state_projection"
                ]
                projection_mismatches = (
                    _network_state_projection_differences(
                        recorded_projection,
                        recomputed_projection,
                    )
                )
                projection_position_checks[position] = {
                    "replayed_airflow_m3_h": float(
                        network_position_airflows[position]
                    ),
                    "network_state_projection_matches_independent_replay": (
                        not projection_mismatches
                    ),
                    "network_state_projection_mismatch_count": len(
                        projection_mismatches
                    ),
                    "network_state_projection_mismatch_paths": [
                        mismatch["path"]
                        for mismatch in projection_mismatches
                    ],
                    "network_state_projection_mismatches": (
                        projection_mismatches
                    ),
                    "network_state_projection_maximum_numeric_errors": (
                        _maximum_network_state_projection_numeric_errors(
                            projection_mismatches
                        )
                    ),
                }
            checked_positions = [
                position
                for position in ("low", "midpoint", "high")
                if position in projection_position_checks
            ]
            network_state_projection_replay_checks.append(
                {
                    "iteration": int(step["iteration"]),
                    "expected_positions": ["low", "midpoint", "high"],
                    "checked_positions": checked_positions,
                    "checked_position_count": len(checked_positions),
                    "coverage_complete": len(checked_positions) == 3,
                    "low": projection_position_checks.get("low"),
                    "midpoint": projection_position_checks.get("midpoint"),
                    "high": projection_position_checks.get("high"),
                    "all_checked_projections_match_independent_replay": all(
                        check[
                            "network_state_projection_matches_independent_replay"
                        ]
                        for check in projection_position_checks.values()
                    ),
                }
            )

            decision = step["decision"]
            if decision == "replace_low_endpoint":
                replay_low_airflow = replay_midpoint_airflow
            elif decision == "replace_high_endpoint":
                replay_high_airflow = replay_midpoint_airflow

    network_state_projection_replay_mismatches = []
    network_state_projection_replay_violation_iteration_positions = []
    network_state_projection_replay_coverage_gaps = []
    for replay_check in network_state_projection_replay_checks:
        iteration = int(replay_check["iteration"])
        for position in ("low", "midpoint", "high"):
            position_check = replay_check.get(position)
            if position_check is None:
                network_state_projection_replay_coverage_gaps.append(
                    {
                        "iteration": iteration,
                        "position": position,
                    }
                )
                continue
            if position_check[
                "network_state_projection_matches_independent_replay"
            ]:
                continue
            network_state_projection_replay_violation_iteration_positions.append(
                {
                    "iteration": iteration,
                    "position": position,
                }
            )
            for mismatch in position_check[
                "network_state_projection_mismatches"
            ]:
                network_state_projection_replay_mismatches.append(
                    {
                        "iteration": iteration,
                        "position": position,
                        **mismatch,
                    }
                )

    projection_expected_iteration_count = (
        len(trace) if residual_replay_available else 0
    )
    projection_expected_state_position_count = (
        projection_expected_iteration_count * 3
    )
    projection_checked_iteration_count = sum(
        check["checked_position_count"] > 0
        for check in network_state_projection_replay_checks
    )
    projection_checked_state_position_count = sum(
        int(check["checked_position_count"])
        for check in network_state_projection_replay_checks
    )
    projection_inconsistent_state_position_count = len(
        network_state_projection_replay_violation_iteration_positions
    )
    projection_consistent_state_position_count = (
        projection_checked_state_position_count
        - projection_inconsistent_state_position_count
    )
    projection_inconsistent_iterations = sorted(
        {
            item["iteration"]
            for item in (
                network_state_projection_replay_violation_iteration_positions
            )
        }
    )
    projection_consistent_iteration_count = sum(
        check["coverage_complete"]
        and check["all_checked_projections_match_independent_replay"]
        for check in network_state_projection_replay_checks
    )
    projection_complete_coverage = (
        projection_checked_state_position_count
        == projection_expected_state_position_count
        and len(network_state_projection_replay_checks)
        == projection_expected_iteration_count
    )
    projection_replay_applicable = (
        residual_replay_available and projection_expected_iteration_count > 0
    )
    projection_replay_available = (
        projection_checked_state_position_count > 0
    )
    if not projection_replay_applicable:
        projection_replay_verdict = (
            "bisection_network_state_projection_replay_not_applicable"
        )
    elif network_state_projection_replay_mismatches:
        projection_replay_verdict = (
            "bisection_network_state_projection_replay_inconsistent"
        )
    elif not projection_complete_coverage:
        projection_replay_verdict = (
            "bisection_network_state_projection_replay_incomplete_coverage"
        )
    else:
        projection_replay_verdict = (
            "bisection_network_state_projection_replay_consistent"
        )

    pressure_component_replay_violations = []
    pressure_component_replay_candidates = []
    component_specs = (
        (
            "fan",
            "recorded_fan_pressure_pa",
            "recomputed_fan_pressure_pa",
            "absolute_fan_pressure_replay_error_pa",
            "fan_pressure_matches_independent_replay",
        ),
        (
            "loop_network",
            "recorded_loop_network_pressure_pa",
            "recomputed_loop_network_pressure_pa",
            "absolute_loop_pressure_replay_error_pa",
            "loop_pressure_matches_independent_replay",
        ),
        (
            "system",
            "recorded_system_pressure_pa",
            "recomputed_system_pressure_pa",
            "absolute_system_pressure_replay_error_pa",
            "system_pressure_matches_independent_replay",
        ),
    )
    for replay_check in pressure_component_replay_checks:
        iteration = int(replay_check["iteration"])
        for position in ("low", "midpoint", "high"):
            position_check = replay_check[position]
            for (
                component,
                recorded_key,
                recomputed_key,
                error_key,
                matches_key,
            ) in component_specs:
                witness = {
                    "iteration": iteration,
                    "position": position,
                    "component": component,
                    "recorded_pressure_pa": position_check[recorded_key],
                    "recomputed_pressure_pa": position_check[recomputed_key],
                    "absolute_error_pa": position_check[error_key],
                }
                pressure_component_replay_candidates.append(witness)
                if not position_check[matches_key]:
                    pressure_component_replay_violations.append(witness)

    maximum_pressure_component_replay_error = (
        max(
            witness["absolute_error_pa"]
            for witness in pressure_component_replay_candidates
        )
        if pressure_component_replay_candidates
        else None
    )
    maximum_pressure_component_replay_error_witnesses = (
        [
            witness
            for witness in pressure_component_replay_candidates
            if math.isclose(
                witness["absolute_error_pa"],
                maximum_pressure_component_replay_error,
                rel_tol=0.0,
                abs_tol=1e-15,
            )
        ]
        if maximum_pressure_component_replay_error is not None
        and maximum_pressure_component_replay_error > 0.0
        else []
    )

    terminal_bracket_for_pressure_component_replay = (
        iteration_limit_terminal_bracket
        if termination_reason == "bisection_iteration_limit"
        else solved_terminal_bracket
    )
    terminal_pressure_component_fields = tuple(
        f"{position}_{component}_pressure_pa"
        for position in ("low", "high")
        for component in ("fan", "loop_network", "system")
    )
    if (
        residual_replay_available
        and terminal_bracket_for_pressure_component_replay is not None
        and all(
            field in terminal_bracket_for_pressure_component_replay
            for field in terminal_pressure_component_fields
        )
    ):
        terminal_position_states = {
            "low": (replay_low_airflow, _independent_state(replay_low_airflow)),
            "high": (
                replay_high_airflow,
                _independent_state(replay_high_airflow),
            ),
        }
        terminal_position_checks = {}
        for position, (
            replayed_airflow,
            recomputed_state,
        ) in terminal_position_states.items():
            recorded_fan_pressure = float(
                terminal_bracket_for_pressure_component_replay[
                    f"{position}_fan_pressure_pa"
                ]
            )
            recorded_loop_pressure = float(
                terminal_bracket_for_pressure_component_replay[
                    f"{position}_loop_network_pressure_pa"
                ]
            )
            recorded_system_pressure = float(
                terminal_bracket_for_pressure_component_replay[
                    f"{position}_system_pressure_pa"
                ]
            )
            recomputed_fan_pressure = recomputed_state["fan_pressure_pa"]
            recomputed_loop_pressure = recomputed_state[
                "loop_network_pressure_pa"
            ]
            recomputed_system_pressure = recomputed_state[
                "system_pressure_pa"
            ]
            fan_error = abs(recorded_fan_pressure - recomputed_fan_pressure)
            loop_error = abs(
                recorded_loop_pressure - recomputed_loop_pressure
            )
            system_error = abs(
                recorded_system_pressure - recomputed_system_pressure
            )
            fan_matches = math.isclose(
                recorded_fan_pressure,
                recomputed_fan_pressure,
                rel_tol=0.0,
                abs_tol=pressure_component_replay_absolute_tolerance_pa,
            )
            loop_matches = math.isclose(
                recorded_loop_pressure,
                recomputed_loop_pressure,
                rel_tol=0.0,
                abs_tol=pressure_component_replay_absolute_tolerance_pa,
            )
            system_matches = math.isclose(
                recorded_system_pressure,
                recomputed_system_pressure,
                rel_tol=0.0,
                abs_tol=pressure_component_replay_absolute_tolerance_pa,
            )
            terminal_position_checks[position] = {
                "replayed_airflow_m3_h": round(replayed_airflow, 9),
                "recorded_fan_pressure_pa": recorded_fan_pressure,
                "recomputed_fan_pressure_pa": round(recomputed_fan_pressure, 9),
                "absolute_fan_pressure_replay_error_pa": fan_error,
                "recorded_loop_network_pressure_pa": recorded_loop_pressure,
                "recomputed_loop_network_pressure_pa": round(
                    recomputed_loop_pressure,
                    9,
                ),
                "absolute_loop_pressure_replay_error_pa": loop_error,
                "recorded_system_pressure_pa": recorded_system_pressure,
                "recomputed_system_pressure_pa": round(
                    recomputed_system_pressure,
                    9,
                ),
                "absolute_system_pressure_replay_error_pa": system_error,
                "fan_pressure_matches_independent_replay": fan_matches,
                "loop_pressure_matches_independent_replay": loop_matches,
                "system_pressure_matches_independent_replay": system_matches,
                "all_pressure_components_match_independent_replay": (
                    fan_matches and loop_matches and system_matches
                ),
            }

        terminal_pressure_component_replay_candidates = []
        terminal_pressure_component_replay_violations = []
        for position in ("low", "high"):
            position_check = terminal_position_checks[position]
            for (
                component,
                recorded_key,
                recomputed_key,
                error_key,
                matches_key,
            ) in component_specs:
                witness = {
                    "iteration": int(operating_iterations),
                    "position": position,
                    "component": component,
                    "recorded_pressure_pa": position_check[recorded_key],
                    "recomputed_pressure_pa": position_check[recomputed_key],
                    "absolute_error_pa": position_check[error_key],
                }
                terminal_pressure_component_replay_candidates.append(witness)
                if not position_check[matches_key]:
                    terminal_pressure_component_replay_violations.append(
                        witness
                    )
        maximum_terminal_pressure_component_replay_error = max(
            (
                witness["absolute_error_pa"]
                for witness in terminal_pressure_component_replay_candidates
            ),
            default=0.0,
        )
        maximum_terminal_pressure_component_replay_error_witnesses = (
            [
                witness
                for witness in terminal_pressure_component_replay_candidates
                if math.isclose(
                    witness["absolute_error_pa"],
                    maximum_terminal_pressure_component_replay_error,
                    rel_tol=0.0,
                    abs_tol=1e-15,
                )
            ]
            if maximum_terminal_pressure_component_replay_error > 0.0
            else []
        )
        terminal_pressure_component_replay = {
            "terminal_kind": (
                "iteration_limit_remaining_bracket"
                if termination_reason == "bisection_iteration_limit"
                else "solved_final_bracket"
            ),
            "termination_reason": termination_reason,
            "iteration": int(operating_iterations),
            "low": terminal_position_checks["low"],
            "high": terminal_position_checks["high"],
            "all_terminal_pressure_components_match_independent_replay": (
                all(
                    check[
                        "all_pressure_components_match_independent_replay"
                    ]
                    for check in terminal_position_checks.values()
                )
            ),
            "pressure_component_replay_violation_count": len(
                terminal_pressure_component_replay_violations
            ),
            "pressure_component_replay_violation_positions": [
                position
                for position in ("low", "high")
                if any(
                    witness["position"] == position
                    for witness in terminal_pressure_component_replay_violations
                )
            ],
            "pressure_component_replay_violation_components": [
                component
                for component in ("fan", "loop_network", "system")
                if any(
                    witness["component"] == component
                    for witness in terminal_pressure_component_replay_violations
                )
            ],
            "pressure_component_replay_violations": (
                terminal_pressure_component_replay_violations
            ),
            "maximum_absolute_terminal_pressure_component_replay_error_pa": (
                maximum_terminal_pressure_component_replay_error
            ),
            "maximum_terminal_pressure_component_replay_error_witnesses": (
                maximum_terminal_pressure_component_replay_error_witnesses
            ),
        }

    terminal_network_state_fields = tuple(
        f"{position}_network_state_sha256"
        for position in ("low", "high")
    )
    terminal_network_projection_fields = tuple(
        f"{position}_network_state_projection"
        for position in ("low", "high")
    )
    if (
        residual_replay_available
        and terminal_bracket_for_pressure_component_replay is not None
        and all(
            field in terminal_bracket_for_pressure_component_replay
            for field in terminal_network_state_fields
        )
    ):
        terminal_network_projection_replay_available = all(
            field in terminal_bracket_for_pressure_component_replay
            for field in terminal_network_projection_fields
        )
        terminal_network_position_checks = {}
        for position, replayed_airflow in (
            ("low", replay_low_airflow),
            ("high", replay_high_airflow),
        ):
            recorded_sha256 = str(
                terminal_bracket_for_pressure_component_replay[
                    f"{position}_network_state_sha256"
                ]
            )
            recomputed_state = _independent_state(replayed_airflow)
            recomputed_sha256 = str(
                recomputed_state["network_state_sha256"]
            )
            projection_mismatches = []
            projection_mismatch_paths = []
            projection_matches = None
            if terminal_network_projection_replay_available:
                recorded_projection = (
                    terminal_bracket_for_pressure_component_replay[
                        f"{position}_network_state_projection"
                    ]
                )
                recomputed_projection = recomputed_state[
                    "network_state_projection"
                ]
                projection_mismatches = (
                    _network_state_projection_differences(
                        recorded_projection,
                        recomputed_projection,
                    )
                )
                projection_mismatch_paths = [
                    mismatch["path"]
                    for mismatch in projection_mismatches
                ]
                projection_matches = not projection_mismatches
            terminal_network_position_checks[position] = {
                "replayed_airflow_m3_h": round(replayed_airflow, 9),
                "recorded_network_state_sha256": recorded_sha256,
                "recomputed_network_state_sha256": recomputed_sha256,
                "network_state_matches_independent_replay": (
                    recorded_sha256 == recomputed_sha256
                ),
                "network_state_projection_matches_independent_replay": (
                    projection_matches
                ),
                "network_state_projection_mismatch_paths": (
                    projection_mismatch_paths
                ),
                "network_state_projection_mismatches": (
                    projection_mismatches
                ),
                "network_state_projection_maximum_numeric_errors": (
                    _maximum_network_state_projection_numeric_errors(
                        projection_mismatches
                    )
                ),
            }
        terminal_network_state_replay_violations = [
            {
                "iteration": int(operating_iterations),
                "position": position,
                "recorded_network_state_sha256": (
                    terminal_network_position_checks[position][
                        "recorded_network_state_sha256"
                    ]
                ),
                "recomputed_network_state_sha256": (
                    terminal_network_position_checks[position][
                        "recomputed_network_state_sha256"
                    ]
                ),
            }
            for position in ("low", "high")
            if not terminal_network_position_checks[position][
                "network_state_matches_independent_replay"
            ]
        ]
        terminal_network_projection_mismatch_details = [
            {
                "iteration": int(operating_iterations),
                "position": position,
                "mismatch_paths": terminal_network_position_checks[position][
                    "network_state_projection_mismatch_paths"
                ],
                "mismatches": terminal_network_position_checks[position][
                    "network_state_projection_mismatches"
                ],
                "maximum_numeric_errors": (
                    terminal_network_position_checks[position][
                        "network_state_projection_maximum_numeric_errors"
                    ]
                ),
            }
            for position in ("low", "high")
            if terminal_network_projection_replay_available
            and not terminal_network_position_checks[position][
                "network_state_projection_matches_independent_replay"
            ]
        ]
        terminal_network_projection_mismatches = [
            {
                "iteration": detail["iteration"],
                "position": detail["position"],
                "mismatch_paths": detail["mismatch_paths"],
            }
            for detail in terminal_network_projection_mismatch_details
        ]
        terminal_network_state_replay = {
            "terminal_kind": (
                "iteration_limit_remaining_bracket"
                if termination_reason == "bisection_iteration_limit"
                else "solved_final_bracket"
            ),
            "termination_reason": termination_reason,
            "iteration": int(operating_iterations),
            "algorithm": "sha256",
            "canonicalization": (
                _NETWORK_STATE_CANONICALIZATION
            ),
            "low": terminal_network_position_checks["low"],
            "high": terminal_network_position_checks["high"],
            "all_terminal_network_states_match_independent_replay": (
                all(
                    check["network_state_matches_independent_replay"]
                    for check in terminal_network_position_checks.values()
                )
            ),
            "network_state_replay_violation_count": len(
                terminal_network_state_replay_violations
            ),
            "network_state_replay_violation_positions": [
                witness["position"]
                for witness in terminal_network_state_replay_violations
            ],
            "network_state_replay_violations": (
                terminal_network_state_replay_violations
            ),
            "network_state_projection_replay_available": (
                terminal_network_projection_replay_available
            ),
            "all_terminal_network_state_projections_match_independent_replay": (
                all(
                    check[
                        "network_state_projection_matches_independent_replay"
                    ]
                    for check in terminal_network_position_checks.values()
                )
                if terminal_network_projection_replay_available
                else None
            ),
            "network_state_projection_mismatch_count": len(
                terminal_network_projection_mismatches
            ),
            "network_state_projection_mismatch_positions": [
                witness["position"]
                for witness in terminal_network_projection_mismatches
            ],
            "network_state_projection_mismatches": (
                terminal_network_projection_mismatches
            ),
            "network_state_projection_mismatch_details": (
                terminal_network_projection_mismatch_details
            ),
        }

    decision_semantic_checks = []
    tolerance = float(operating_pressure_tolerance_pa)
    for step in trace:
        midpoint_residual = float(
            step["midpoint_fan_minus_system_pressure_pa"]
        )
        if abs(midpoint_residual) <= tolerance:
            expected_decision = "accept_pressure_tolerance"
        elif midpoint_residual > 0.0:
            expected_decision = "replace_low_endpoint"
        else:
            expected_decision = "replace_high_endpoint"
        recorded_decision = step["decision"]
        decision_semantic_checks.append(
            {
                "iteration": int(step["iteration"]),
                "midpoint_fan_minus_system_pressure_pa": midpoint_residual,
                "operating_pressure_tolerance_pa": tolerance,
                "midpoint_within_pressure_tolerance": (
                    abs(midpoint_residual) <= tolerance
                ),
                "recorded_decision": recorded_decision,
                "expected_decision_from_midpoint_residual": (
                    expected_decision
                ),
                "decision_matches_midpoint_residual_semantics": (
                    recorded_decision == expected_decision
                ),
            }
        )

    transition_checks = []
    for transition_index, (step, next_step) in enumerate(
        zip(trace, trace[1:]),
        start=1,
    ):
        decision = step["decision"]
        expected_low_airflow = float(step["low_airflow_m3_h"])
        expected_high_airflow = float(step["high_airflow_m3_h"])
        expected_low_residual = float(
            step["low_fan_minus_system_pressure_pa"]
        )
        expected_high_residual = float(
            step["high_fan_minus_system_pressure_pa"]
        )
        replayable_decision = decision in {
            "replace_low_endpoint",
            "replace_high_endpoint",
        }
        if decision == "replace_low_endpoint":
            expected_low_airflow = float(step["midpoint_airflow_m3_h"])
            expected_low_residual = float(
                step["midpoint_fan_minus_system_pressure_pa"]
            )
        elif decision == "replace_high_endpoint":
            expected_high_airflow = float(step["midpoint_airflow_m3_h"])
            expected_high_residual = float(
                step["midpoint_fan_minus_system_pressure_pa"]
            )

        next_iteration_is_contiguous = (
            int(next_step["iteration"]) == int(step["iteration"]) + 1
        )
        next_airflow_bracket_matches_decision = (
            replayable_decision
            and math.isclose(
                float(next_step["low_airflow_m3_h"]),
                expected_low_airflow,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            and math.isclose(
                float(next_step["high_airflow_m3_h"]),
                expected_high_airflow,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
        )
        next_residual_bracket_matches_decision = (
            replayable_decision
            and math.isclose(
                float(next_step["low_fan_minus_system_pressure_pa"]),
                expected_low_residual,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            and math.isclose(
                float(next_step["high_fan_minus_system_pressure_pa"]),
                expected_high_residual,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
        )
        transition_checks.append(
            {
                "transition_index": transition_index,
                "from_iteration": int(step["iteration"]),
                "to_iteration": int(next_step["iteration"]),
                "decision": decision,
                "next_iteration_is_contiguous": (
                    next_iteration_is_contiguous
                ),
                "next_airflow_bracket_matches_decision": (
                    next_airflow_bracket_matches_decision
                ),
                "next_residual_bracket_matches_decision": (
                    next_residual_bracket_matches_decision
                ),
                "state_transition_replays_recorded_decision": (
                    next_iteration_is_contiguous
                    and next_airflow_bracket_matches_decision
                    and next_residual_bracket_matches_decision
                ),
            }
        )

    origin_replay = None
    terminal_bracket_for_origin_replay = (
        iteration_limit_terminal_bracket
        if termination_reason == "bisection_iteration_limit"
        else solved_terminal_bracket
    )
    if trace and initial_bisection_bracket is not None:
        replay_low_airflow = float(
            initial_bisection_bracket["low_airflow_m3_h"]
        )
        replay_high_airflow = float(
            initial_bisection_bracket["high_airflow_m3_h"]
        )
        replay_low_residual = float(
            initial_bisection_bracket["low_fan_minus_system_pressure_pa"]
        )
        replay_high_residual = float(
            initial_bisection_bracket["high_fan_minus_system_pressure_pa"]
        )
        origin_step_checks = []
        for trace_index, step in enumerate(trace):
            airflow_matches = (
                math.isclose(
                    float(step["low_airflow_m3_h"]),
                    replay_low_airflow,
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
                and math.isclose(
                    float(step["high_airflow_m3_h"]),
                    replay_high_airflow,
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
            )
            residual_matches = (
                math.isclose(
                    float(step["low_fan_minus_system_pressure_pa"]),
                    replay_low_residual,
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
                and math.isclose(
                    float(step["high_fan_minus_system_pressure_pa"]),
                    replay_high_residual,
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
            )
            current_bracket_matches = airflow_matches and residual_matches
            decision = step["decision"]
            replayable_decision = decision in {
                "replace_low_endpoint",
                "replace_high_endpoint",
                "accept_pressure_tolerance",
            }
            if decision == "replace_low_endpoint":
                replay_low_airflow = float(step["midpoint_airflow_m3_h"])
                replay_low_residual = float(
                    step["midpoint_fan_minus_system_pressure_pa"]
                )
            elif decision == "replace_high_endpoint":
                replay_high_airflow = float(step["midpoint_airflow_m3_h"])
                replay_high_residual = float(
                    step["midpoint_fan_minus_system_pressure_pa"]
                )
            origin_step_checks.append(
                {
                    "trace_index": trace_index,
                    "iteration": int(step["iteration"]),
                    "decision": decision,
                    "airflow_bracket_matches_origin_replay": airflow_matches,
                    "residual_bracket_matches_origin_replay": residual_matches,
                    "current_bracket_matches_origin_replay": (
                        current_bracket_matches
                    ),
                    "decision_is_replayable": replayable_decision,
                }
            )

        terminal_matches = False
        if terminal_bracket_for_origin_replay is not None:
            terminal_matches = (
                math.isclose(
                    float(
                        terminal_bracket_for_origin_replay[
                            "low_airflow_m3_h"
                        ]
                    ),
                    replay_low_airflow,
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
                and math.isclose(
                    float(
                        terminal_bracket_for_origin_replay[
                            "high_airflow_m3_h"
                        ]
                    ),
                    replay_high_airflow,
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
                and math.isclose(
                    float(
                        terminal_bracket_for_origin_replay[
                            "low_fan_minus_system_pressure_pa"
                        ]
                    ),
                    replay_low_residual,
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
                and math.isclose(
                    float(
                        terminal_bracket_for_origin_replay[
                            "high_fan_minus_system_pressure_pa"
                        ]
                    ),
                    replay_high_residual,
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
            )
        all_steps_match = all(
            check["current_bracket_matches_origin_replay"]
            and check["decision_is_replayable"]
            for check in origin_step_checks
        )
        origin_replay = {
            "initial_bracket_matches_first_trace_step": (
                bool(origin_step_checks)
                and origin_step_checks[0][
                    "current_bracket_matches_origin_replay"
                ]
            ),
            "all_trace_steps_match_origin_replay": all_steps_match,
            "terminal_bracket_matches_origin_replay": terminal_matches,
            "trace_origin_to_terminal_replay_consistent": (
                all_steps_match and terminal_matches
            ),
            "replayed_terminal_bracket": {
                "low_airflow_m3_h": round(replay_low_airflow, 9),
                "high_airflow_m3_h": round(replay_high_airflow, 9),
                "low_fan_minus_system_pressure_pa": round(
                    replay_low_residual,
                    9,
                ),
                "high_fan_minus_system_pressure_pa": round(
                    replay_high_residual,
                    9,
                ),
            },
            "step_checks": origin_step_checks,
        }

    terminal_limit_replay = None
    if (
        termination_reason == "bisection_iteration_limit"
        and trace
        and iteration_limit_terminal_bracket is not None
    ):
        last_step = trace[-1]
        last_decision = last_step["decision"]
        expected_low_airflow = float(last_step["low_airflow_m3_h"])
        expected_high_airflow = float(last_step["high_airflow_m3_h"])
        expected_low_residual = float(
            last_step["low_fan_minus_system_pressure_pa"]
        )
        expected_high_residual = float(
            last_step["high_fan_minus_system_pressure_pa"]
        )
        replayable_decision = last_decision in {
            "replace_low_endpoint",
            "replace_high_endpoint",
        }
        if last_decision == "replace_low_endpoint":
            expected_low_airflow = float(
                last_step["midpoint_airflow_m3_h"]
            )
            expected_low_residual = float(
                last_step["midpoint_fan_minus_system_pressure_pa"]
            )
        elif last_decision == "replace_high_endpoint":
            expected_high_airflow = float(
                last_step["midpoint_airflow_m3_h"]
            )
            expected_high_residual = float(
                last_step["midpoint_fan_minus_system_pressure_pa"]
            )

        airflow_matches = (
            replayable_decision
            and math.isclose(
                float(iteration_limit_terminal_bracket["low_airflow_m3_h"]),
                expected_low_airflow,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            and math.isclose(
                float(iteration_limit_terminal_bracket["high_airflow_m3_h"]),
                expected_high_airflow,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
        )
        residual_matches = (
            replayable_decision
            and math.isclose(
                float(
                    iteration_limit_terminal_bracket[
                        "low_fan_minus_system_pressure_pa"
                    ]
                ),
                expected_low_residual,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            and math.isclose(
                float(
                    iteration_limit_terminal_bracket[
                        "high_fan_minus_system_pressure_pa"
                    ]
                ),
                expected_high_residual,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
        )
        terminal_limit_replay = {
            "from_iteration": int(last_step["iteration"]),
            "decision": last_decision,
            "terminal_airflow_bracket_matches_decision": airflow_matches,
            "terminal_residual_bracket_matches_decision": residual_matches,
            "terminal_bracket_replays_recorded_decision": (
                airflow_matches and residual_matches
            ),
        }

    if termination_reason == "pressure_residual":
        terminal_outcome_consistent = (
            bool(trace)
            and termination_indices == [len(trace) - 1]
        )
    elif termination_reason == "bisection_iteration_limit":
        terminal_outcome_consistent = (
            bool(trace)
            and not termination_indices
            and terminal_limit_replay is not None
            and terminal_limit_replay[
                "terminal_bracket_replays_recorded_decision"
            ]
        )
    else:
        terminal_outcome_consistent = False

    return {
        "step_count": len(trace),
        "termination_reason": termination_reason,
        "trace_matches_operating_iterations": (
            len(trace) == operating_iterations
        ),
        "iteration_sequence": iteration_sequence,
        "iterations_are_contiguous_from_one": (
            iteration_sequence == list(range(1, len(trace) + 1))
        ),
        "raw_state_check_count": len(raw_state_checks),
        "all_numeric_brackets_preserve_strict_sign_change": all(
            check["numeric_strict_sign_change_before_evaluation"]
            for check in raw_state_checks
        ),
        "all_recorded_sign_flags_match_numeric_residuals": all(
            check["recorded_sign_flag_matches_numeric_residuals"]
            for check in raw_state_checks
        ),
        "all_numeric_midpoints_are_arithmetic_bracket_midpoints": all(
            check["numeric_midpoint_is_arithmetic_bracket_midpoint"]
            for check in raw_state_checks
        ),
        "all_recorded_midpoint_flags_match_numeric_geometry": all(
            check["recorded_midpoint_flag_matches_numeric_geometry"]
            for check in raw_state_checks
        ),
        "all_trace_raw_state_consistent": all(
            check["numeric_strict_sign_change_before_evaluation"]
            and check["recorded_sign_flag_matches_numeric_residuals"]
            and check["numeric_midpoint_is_arithmetic_bracket_midpoint"]
            and check["recorded_midpoint_flag_matches_numeric_geometry"]
            for check in raw_state_checks
        ),
        "maximum_absolute_trace_midpoint_error_m3_h": max(
            (
                check["absolute_midpoint_error_m3_h"]
                for check in raw_state_checks
            ),
            default=0.0,
        ),
        "raw_state_checks": raw_state_checks,
        "pressure_state_check_count": len(pressure_state_checks),
        "pressure_state_evidence_complete": (
            len(pressure_state_checks) == len(trace)
        ),
        "all_recorded_fixed_pressure_values_match_study": (
            len(pressure_state_checks) == len(trace)
            and all(
                check["recorded_fixed_pressure_matches_study"]
                for check in pressure_state_checks
            )
        ),
        "all_recorded_system_pressures_match_fixed_plus_loop": (
            len(pressure_state_checks) == len(trace)
            and all(
                check["recorded_system_pressure_matches_fixed_plus_loop"]
                for check in pressure_state_checks
            )
        ),
        "all_recorded_residuals_match_fan_minus_system": (
            len(pressure_state_checks) == len(trace)
            and all(
                check["recorded_residual_matches_fan_minus_system"]
                for check in pressure_state_checks
            )
        ),
        "all_trace_pressure_state_consistent": (
            len(pressure_state_checks) == len(trace)
            and all(
                check["recorded_fixed_pressure_matches_study"]
                and check[
                    "recorded_system_pressure_matches_fixed_plus_loop"
                ]
                and check["recorded_residual_matches_fan_minus_system"]
                for check in pressure_state_checks
            )
        ),
        "maximum_absolute_trace_system_pressure_balance_error_pa": max(
            (
                check["absolute_system_pressure_balance_error_pa"]
                for check in pressure_state_checks
            ),
            default=0.0,
        ),
        "maximum_absolute_trace_residual_balance_error_pa": max(
            (
                check["absolute_residual_balance_error_pa"]
                for check in pressure_state_checks
            ),
            default=0.0,
        ),
        "pressure_state_checks": pressure_state_checks,
        "residual_replay_available": residual_replay_available,
        "residual_replay_check_count": len(residual_replay_checks),
        "residual_replay_absolute_tolerance_pa": (
            residual_replay_absolute_tolerance_pa
            if residual_replay_available
            else None
        ),
        "all_recorded_low_residuals_match_independent_replay": (
            all(
                check["low_residual_matches_independent_replay"]
                for check in residual_replay_checks
            )
            if residual_replay_available
            else None
        ),
        "all_recorded_high_residuals_match_independent_replay": (
            all(
                check["high_residual_matches_independent_replay"]
                for check in residual_replay_checks
            )
            if residual_replay_available
            else None
        ),
        "all_recorded_midpoint_residuals_match_independent_replay": (
            all(
                check["midpoint_residual_matches_independent_replay"]
                for check in residual_replay_checks
            )
            if residual_replay_available
            else None
        ),
        "all_trace_residuals_match_independent_replay": (
            all(
                check["all_residuals_match_independent_replay"]
                for check in residual_replay_checks
            )
            if residual_replay_available
            else None
        ),
        "maximum_absolute_trace_residual_replay_error_pa": (
            max(
                max(
                    check["absolute_low_residual_replay_error_pa"],
                    check["absolute_high_residual_replay_error_pa"],
                    check["absolute_midpoint_residual_replay_error_pa"],
                )
                for check in residual_replay_checks
            )
            if residual_replay_checks
            else None
        ),
        "residual_replay_checks": residual_replay_checks,
        "pressure_component_replay_available": residual_replay_available,
        "pressure_component_replay_check_count": len(
            pressure_component_replay_checks
        ),
        "pressure_component_replay_evidence_complete": (
            len(pressure_component_replay_checks) == len(trace)
            if residual_replay_available
            else None
        ),
        "pressure_component_replay_absolute_tolerance_pa": (
            pressure_component_replay_absolute_tolerance_pa
            if residual_replay_available
            else None
        ),
        "all_recorded_midpoint_fan_pressures_match_independent_replay": (
            len(pressure_component_replay_checks) == len(trace)
            and all(
                check["fan_pressure_matches_independent_replay"]
                for check in pressure_component_replay_checks
            )
            if residual_replay_available
            else None
        ),
        "all_recorded_midpoint_loop_pressures_match_independent_replay": (
            len(pressure_component_replay_checks) == len(trace)
            and all(
                check["loop_pressure_matches_independent_replay"]
                for check in pressure_component_replay_checks
            )
            if residual_replay_available
            else None
        ),
        "all_recorded_midpoint_system_pressures_match_independent_replay": (
            len(pressure_component_replay_checks) == len(trace)
            and all(
                check["system_pressure_matches_independent_replay"]
                for check in pressure_component_replay_checks
            )
            if residual_replay_available
            else None
        ),
        "all_midpoint_pressure_components_match_independent_replay": (
            len(pressure_component_replay_checks) == len(trace)
            and all(
                check["all_pressure_components_match_independent_replay"]
                for check in pressure_component_replay_checks
            )
            if residual_replay_available
            else None
        ),
        "all_low_pressure_components_match_independent_replay": (
            len(pressure_component_replay_checks) == len(trace)
            and all(
                check[
                    "all_low_pressure_components_match_independent_replay"
                ]
                for check in pressure_component_replay_checks
            )
            if residual_replay_available
            else None
        ),
        "all_high_pressure_components_match_independent_replay": (
            len(pressure_component_replay_checks) == len(trace)
            and all(
                check[
                    "all_high_pressure_components_match_independent_replay"
                ]
                for check in pressure_component_replay_checks
            )
            if residual_replay_available
            else None
        ),
        "all_trace_pressure_components_match_independent_replay": (
            len(pressure_component_replay_checks) == len(trace)
            and all(
                check[
                    "all_bracket_pressure_components_match_independent_replay"
                ]
                for check in pressure_component_replay_checks
            )
            if residual_replay_available
            else None
        ),
        "maximum_absolute_trace_pressure_component_replay_error_pa": (
            maximum_pressure_component_replay_error
        ),
        "pressure_component_replay_violation_count": len(
            pressure_component_replay_violations
        ),
        "pressure_component_replay_violation_iterations": sorted(
            {
                witness["iteration"]
                for witness in pressure_component_replay_violations
            }
        ),
        "pressure_component_replay_violation_positions": [
            position
            for position in ("low", "midpoint", "high")
            if any(
                witness["position"] == position
                for witness in pressure_component_replay_violations
            )
        ],
        "pressure_component_replay_violation_components": [
            component
            for component in ("fan", "loop_network", "system")
            if any(
                witness["component"] == component
                for witness in pressure_component_replay_violations
            )
        ],
        "pressure_component_replay_violations": (
            pressure_component_replay_violations
        ),
        "maximum_trace_pressure_component_replay_error_witnesses": (
            maximum_pressure_component_replay_error_witnesses
        ),
        "pressure_component_replay_checks": (
            pressure_component_replay_checks
        ),
        "network_state_replay_available": residual_replay_available,
        "network_state_replay_algorithm": (
            "sha256" if residual_replay_available else None
        ),
        "network_state_replay_canonicalization": (
            _NETWORK_STATE_CANONICALIZATION
            if residual_replay_available
            else None
        ),
        "network_state_replay_check_count": len(
            network_state_replay_checks
        ),
        "network_state_replay_evidence_complete": (
            len(network_state_replay_checks) == len(trace)
            if residual_replay_available
            else None
        ),
        "all_low_network_states_match_independent_replay": (
            len(network_state_replay_checks) == len(trace)
            and all(
                check["low"][
                    "network_state_matches_independent_replay"
                ]
                for check in network_state_replay_checks
            )
            if residual_replay_available
            else None
        ),
        "all_midpoint_network_states_match_independent_replay": (
            len(network_state_replay_checks) == len(trace)
            and all(
                check["midpoint"][
                    "network_state_matches_independent_replay"
                ]
                for check in network_state_replay_checks
            )
            if residual_replay_available
            else None
        ),
        "all_high_network_states_match_independent_replay": (
            len(network_state_replay_checks) == len(trace)
            and all(
                check["high"][
                    "network_state_matches_independent_replay"
                ]
                for check in network_state_replay_checks
            )
            if residual_replay_available
            else None
        ),
        "all_trace_network_states_match_independent_replay": (
            len(network_state_replay_checks) == len(trace)
            and all(
                check["all_network_states_match_independent_replay"]
                for check in network_state_replay_checks
            )
            if residual_replay_available
            else None
        ),
        "network_state_replay_violation_iterations": [
            check["iteration"]
            for check in network_state_replay_checks
            if not check["all_network_states_match_independent_replay"]
        ],
        "network_state_replay_checks": network_state_replay_checks,
        "network_state_projection_replay_applicable": (
            projection_replay_applicable
        ),
        "network_state_projection_replay_available": (
            projection_replay_available
        ),
        "network_state_projection_replay_expected_iteration_count": (
            projection_expected_iteration_count
        ),
        "network_state_projection_replay_checked_iteration_count": (
            projection_checked_iteration_count
        ),
        "network_state_projection_replay_expected_state_position_count": (
            projection_expected_state_position_count
        ),
        "network_state_projection_replay_checked_state_position_count": (
            projection_checked_state_position_count
        ),
        "network_state_projection_replay_complete_coverage": (
            projection_complete_coverage
            if projection_replay_applicable
            else None
        ),
        "network_state_projection_replay_consistent_iteration_count": (
            projection_consistent_iteration_count
        ),
        "network_state_projection_replay_inconsistent_iteration_count": len(
            projection_inconsistent_iterations
        ),
        "network_state_projection_replay_consistent_state_position_count": (
            projection_consistent_state_position_count
        ),
        "network_state_projection_replay_inconsistent_state_position_count": (
            projection_inconsistent_state_position_count
        ),
        "network_state_projection_replay_violation_iterations": (
            projection_inconsistent_iterations
        ),
        "network_state_projection_replay_violation_iteration_positions": (
            network_state_projection_replay_violation_iteration_positions
        ),
        "network_state_projection_replay_coverage_gaps": (
            network_state_projection_replay_coverage_gaps
        ),
        "network_state_projection_replay_mismatch_count": len(
            network_state_projection_replay_mismatches
        ),
        "network_state_projection_replay_mismatch_paths": [
            {
                "iteration": mismatch["iteration"],
                "position": mismatch["position"],
                "path": mismatch["path"],
            }
            for mismatch in network_state_projection_replay_mismatches
        ],
        "network_state_projection_replay_unique_mismatch_paths": sorted(
            {
                mismatch["path"]
                for mismatch in network_state_projection_replay_mismatches
            }
        ),
        "network_state_projection_replay_mismatches": (
            network_state_projection_replay_mismatches
        ),
        "network_state_projection_replay_maximum_numeric_errors": (
            _maximum_network_state_projection_numeric_errors(
                network_state_projection_replay_mismatches
            )
        ),
        "network_state_projection_replay_verdict": (
            projection_replay_verdict
        ),
        "all_trace_network_state_projections_match_independent_replay": (
            projection_complete_coverage
            and not network_state_projection_replay_mismatches
            if projection_replay_applicable
            else None
        ),
        "network_state_projection_replay_checks": (
            network_state_projection_replay_checks
        ),
        "terminal_pressure_component_replay_available": (
            terminal_pressure_component_replay is not None
        ),
        "all_terminal_pressure_components_match_independent_replay": (
            terminal_pressure_component_replay[
                "all_terminal_pressure_components_match_independent_replay"
            ]
            if terminal_pressure_component_replay is not None
            else None
        ),
        "terminal_pressure_component_replay_violation_count": (
            terminal_pressure_component_replay[
                "pressure_component_replay_violation_count"
            ]
            if terminal_pressure_component_replay is not None
            else None
        ),
        "terminal_pressure_component_replay_violations": (
            terminal_pressure_component_replay[
                "pressure_component_replay_violations"
            ]
            if terminal_pressure_component_replay is not None
            else []
        ),
        "maximum_absolute_terminal_pressure_component_replay_error_pa": (
            terminal_pressure_component_replay[
                "maximum_absolute_terminal_pressure_component_replay_error_pa"
            ]
            if terminal_pressure_component_replay is not None
            else None
        ),
        "maximum_terminal_pressure_component_replay_error_witnesses": (
            terminal_pressure_component_replay[
                "maximum_terminal_pressure_component_replay_error_witnesses"
            ]
            if terminal_pressure_component_replay is not None
            else []
        ),
        "terminal_pressure_component_replay": terminal_pressure_component_replay,
        "terminal_network_state_replay_available": (
            terminal_network_state_replay is not None
        ),
        "all_terminal_network_states_match_independent_replay": (
            terminal_network_state_replay[
                "all_terminal_network_states_match_independent_replay"
            ]
            if terminal_network_state_replay is not None
            else None
        ),
        "terminal_network_state_replay_violation_count": (
            terminal_network_state_replay[
                "network_state_replay_violation_count"
            ]
            if terminal_network_state_replay is not None
            else None
        ),
        "terminal_network_state_replay_violation_positions": (
            terminal_network_state_replay[
                "network_state_replay_violation_positions"
            ]
            if terminal_network_state_replay is not None
            else []
        ),
        "terminal_network_state_replay_violations": (
            terminal_network_state_replay[
                "network_state_replay_violations"
            ]
            if terminal_network_state_replay is not None
            else []
        ),
        "terminal_network_state_projection_replay_available": (
            terminal_network_state_replay[
                "network_state_projection_replay_available"
            ]
            if terminal_network_state_replay is not None
            else False
        ),
        "all_terminal_network_state_projections_match_independent_replay": (
            terminal_network_state_replay[
                "all_terminal_network_state_projections_match_independent_replay"
            ]
            if terminal_network_state_replay is not None
            else None
        ),
        "terminal_network_state_projection_mismatch_count": (
            terminal_network_state_replay[
                "network_state_projection_mismatch_count"
            ]
            if terminal_network_state_replay is not None
            else None
        ),
        "terminal_network_state_projection_mismatch_positions": (
            terminal_network_state_replay[
                "network_state_projection_mismatch_positions"
            ]
            if terminal_network_state_replay is not None
            else []
        ),
        "terminal_network_state_projection_mismatches": (
            terminal_network_state_replay[
                "network_state_projection_mismatches"
            ]
            if terminal_network_state_replay is not None
            else []
        ),
        "terminal_network_state_projection_mismatch_details": (
            terminal_network_state_replay.get(
                "network_state_projection_mismatch_details",
                [],
            )
            if terminal_network_state_replay is not None
            else []
        ),
        "terminal_network_state_replay": terminal_network_state_replay,
        "all_steps_preserve_strict_sign_change_before_evaluation": all(
            step["strict_sign_change_before_evaluation"]
            for step in trace
        ),
        "all_midpoints_are_arithmetic_bracket_midpoints": all(
            step["midpoint_is_arithmetic_bracket_midpoint"]
            for step in trace
        ),
        "geometry_check_count": len(geometry_checks),
        "all_recorded_widths_match_airflow_brackets": all(
            check["recorded_width_matches_airflow_bracket"]
            for check in geometry_checks
        ),
        "all_recorded_width_fractions_match_iteration_sequence": all(
            check["recorded_width_fraction_matches_iteration_sequence"]
            for check in geometry_checks
        ),
        "all_trace_geometry_consistent": all(
            check["recorded_width_matches_airflow_bracket"]
            and check[
                "recorded_width_fraction_matches_iteration_sequence"
            ]
            for check in geometry_checks
        ),
        "maximum_absolute_trace_width_error_m3_h": (
            max(
                (
                    check["absolute_width_error_m3_h"]
                    for check in geometry_checks
                ),
                default=0.0,
            )
        ),
        "maximum_absolute_trace_width_fraction_error": (
            max(
                (
                    check["absolute_width_fraction_error"]
                    for check in geometry_checks
                ),
                default=0.0,
            )
        ),
        "geometry_checks": geometry_checks,
        "decision_semantic_check_count": len(decision_semantic_checks),
        "all_decisions_match_midpoint_residual_semantics": all(
            check["decision_matches_midpoint_residual_semantics"]
            for check in decision_semantic_checks
        ),
        "decision_semantic_violation_iterations": [
            check["iteration"]
            for check in decision_semantic_checks
            if not check["decision_matches_midpoint_residual_semantics"]
        ],
        "decision_semantic_checks": decision_semantic_checks,
        "termination_record_count": len(termination_indices),
        "termination_record_is_last": (
            termination_indices == [len(trace) - 1]
        ),
        "terminal_outcome_consistent": terminal_outcome_consistent,
        "trace_origin_replay": origin_replay,
        "trace_origin_to_terminal_replay_consistent": (
            origin_replay is not None
            and origin_replay["trace_origin_to_terminal_replay_consistent"]
        ),
        "iteration_limit_terminal_replay": terminal_limit_replay,
        "replace_low_endpoint_count": sum(
            step["decision"] == "replace_low_endpoint" for step in trace
        ),
        "replace_high_endpoint_count": sum(
            step["decision"] == "replace_high_endpoint" for step in trace
        ),
        "transition_record_count": len(transition_checks),
        "all_airflow_bracket_transitions_replay_recorded_decisions": all(
            check["next_airflow_bracket_matches_decision"]
            for check in transition_checks
        ),
        "all_residual_bracket_transitions_replay_recorded_decisions": all(
            check["next_residual_bracket_matches_decision"]
            for check in transition_checks
        ),
        "all_state_transitions_replay_recorded_decisions": all(
            check["state_transition_replays_recorded_decision"]
            for check in transition_checks
        ),
        "transition_checks": transition_checks,
        "decision_sequence": "".join(
            symbol_by_decision[step["decision"]] for step in trace
        ),
        "decision_legend": legend,
        "scope_note": (
            "The decision trace preserves every completed bounded-bisection "
            "midpoint evaluation. L replaces the positive-residual low "
            "endpoint, H replaces the negative-residual high endpoint, and T "
            "accepts a midpoint within the configured operating-pressure "
            "tolerance. The replay audit verifies that each nonterminal L/H "
            "decision produces the next recorded airflow/residual bracket, "
            "that iteration numbering is contiguous, and that every recorded "
            "bracket width equals its endpoint span with the binary width "
            "fraction implied by its iteration. The raw-state audit "
            "independently recomputes strict sign-change and arithmetic-"
            "midpoint facts from the recorded numeric state and checks the "
            "stored flags against those recomputed facts. The pressure-state "
            "audit independently checks each retained midpoint's fixed-plus-"
            "loop system-pressure identity and fan-minus-system residual "
            "identity, and anchors the retained fixed-pressure component to "
            "the study input. The independent residual-replay audit "
            "reconstructs the active bisection states from the selected "
            "supplied fan segment, freshly re-solves the nonlinear loop at "
            "each low/high/midpoint airflow, and checks retained residuals "
            "against that independent fan/system evaluation. The independent "
            "pressure-component replay additionally records exact violating "
            "iteration/position/component tuples and tied maximum-error "
            "witnesses. The decision-semantics audit "
            "independently verifies each L/H/T choice against the recorded "
            "midpoint residual and configured operating-pressure tolerance. "
            "The origin replay additionally anchors the first trace state to "
            "the selected supplied-point "
            "bracket and reconstructs the complete decision chain through the "
            "terminal retained bracket. For an iteration-limit "
            "outcome, the final L/H decision is additionally replayed into "
            "the retained remaining bracket without accepting an operating "
            "point. This is numerical implementation provenance only; it is "
            "not physical uncertainty, an interpolation-error bound, a "
            "stability margin, or an equipment-acceptance criterion."
        ),
    }

def _nonconverged_result(
    study: FanVariableFrictionLoopStudy,
    *,
    curve_checks: list[dict],
    message: str,
) -> dict:
    return _with_solver_result_integrity({
        "study": study.name,
        "status": "non_converged",
        "fan_curve": study.fan_curve.name,
        "fan_discharge_node": study.fan_discharge_node,
        "fan_suction_node": study.fan_suction_node,
        "fixed_pressure_pa": round(study.fixed_pressure_pa, 6),
        "fan_curve_airflow_range_m3_h": [
            round(study.fan_curve.points[0].airflow_m3_h, 6),
            round(study.fan_curve.points[-1].airflow_m3_h, 6),
        ],
        "fan_curve_point_checks": curve_checks,
        "fan_curve_supplied_point_residual_audit": (
            _fan_curve_supplied_point_residual_audit(
                study,
                curve_checks,
            )
        ),
        "fan_curve_supplied_point_network_state_replay": (
            _fan_curve_supplied_point_network_state_replay_audit(
                study,
                curve_checks,
            )
        ),
        "fan_operating_point": None,
        "operating_point_search_evidence": None,
        "operating_network_solution": None,
        "system_pressure_check": None,
        "power_evidence": None,
        "solver_diagnostics": {
            "converged": False,
            "termination_reason": "network_solver_non_convergence",
            "operating_iterations": 0,
            "operating_pressure_tolerance_pa": (
                study.operating_pressure_tolerance_pa
            ),
        },
        "message": message,
        "scope_note": _scope_note(),
    })


def _scope_note() -> str:
    return (
        "This workflow couples the supplied fan curve directly to the "
        "two-terminal loop network while re-solving flow-dependent Darcy "
        "friction at every evaluated airflow. Fan pressure is interpolated "
        "only between supplied fan points and is never extrapolated. "
        "Automatic Darcy updates reuse the existing explicit roughness, "
        "kinematic-viscosity, density, geometry, and local-K model; edges "
        "with explicit resistance or user-supplied friction remain fixed. "
        "This is a steady incompressible engineering screening model, not "
        "CFD. It does not infer dampers, leakage, controls, system effect, "
        "acoustics, stall/surge limits, motor/VFD limits, transients, or "
        "manufacturer acceptance. Fluid pressure power is reported directly; "
        "shaft/electrical power is reported only from explicit efficiencies."
    )



def _selected_operating_state_replay_audit(
    study: FanVariableFrictionLoopStudy,
    *,
    selected_airflow_m3_h: float,
    recorded_fan_pressure_pa: float,
    recorded_loop_network_pressure_pa: float,
    recorded_system_pressure_pa: float,
    recorded_residual_pa: float,
    recorded_network_state_sha256: str,
    segment_left: FanCurvePoint,
    segment_right: FanCurvePoint,
    recorded_network_state_projection: dict | None = None,
    selected_supplied_point_index: int | None = None,
    bisection_trace: list[dict] | None = None,
) -> dict:
    pressure_tolerance_pa = 1e-9
    airflow_tolerance_m3_h = 1e-9

    _replayed_network, replayed_loop_pressure = _solve_network_at_airflow(
        study,
        selected_airflow_m3_h,
    )
    replayed_fan_pressure = _fan_pressure(
        segment_left,
        segment_right,
        selected_airflow_m3_h,
    )
    replayed_system_pressure = (
        study.fixed_pressure_pa + replayed_loop_pressure
    )
    replayed_residual = replayed_fan_pressure - replayed_system_pressure
    recorded_network_state = str(recorded_network_state_sha256)
    replayed_network_state = _network_state_sha256(_replayed_network)
    network_state_matches_independent_replay = (
        recorded_network_state == replayed_network_state
    )
    recomputed_network_state_projection = _network_state_projection(
        _replayed_network
    )
    network_state_projection_replay_available = (
        recorded_network_state_projection is not None
    )
    network_state_projection_mismatches = []
    network_state_projection_mismatch_paths = []
    network_state_projection_matches_independent_replay = None
    if network_state_projection_replay_available:
        network_state_projection_mismatches = (
            _network_state_projection_differences(
                recorded_network_state_projection,
                recomputed_network_state_projection,
            )
        )
        network_state_projection_mismatch_paths = [
            mismatch["path"]
            for mismatch in network_state_projection_mismatches
        ]
        network_state_projection_matches_independent_replay = (
            not network_state_projection_mismatches
        )

    recorded_pressures = {
        "fan": float(recorded_fan_pressure_pa),
        "loop_network": float(recorded_loop_network_pressure_pa),
        "system": float(recorded_system_pressure_pa),
        "residual": float(recorded_residual_pa),
    }
    replayed_pressures = {
        "fan": replayed_fan_pressure,
        "loop_network": replayed_loop_pressure,
        "system": replayed_system_pressure,
        "residual": replayed_residual,
    }
    component_checks = {}
    violations = []
    for component in ("fan", "loop_network", "system", "residual"):
        recorded = recorded_pressures[component]
        recomputed = replayed_pressures[component]
        absolute_error = abs(recorded - recomputed)
        matches = math.isclose(
            recorded,
            recomputed,
            rel_tol=0.0,
            abs_tol=pressure_tolerance_pa,
        )
        component_checks[component] = {
            "recorded_pressure_pa": recorded,
            "recomputed_pressure_pa": round(recomputed, 9),
            "absolute_error_pa": absolute_error,
            "matches_independent_replay": matches,
        }
        if not matches:
            violations.append(
                {
                    "component": component,
                    **component_checks[component],
                }
            )

    if not network_state_matches_independent_replay:
        violations.append(
            {
                "component": "network_state_sha256",
                "recorded_network_state_sha256": recorded_network_state,
                "recomputed_network_state_sha256": replayed_network_state,
            }
        )
    if (
        network_state_projection_replay_available
        and network_state_projection_matches_independent_replay is False
    ):
        violations.append(
            {
                "component": "network_state_projection",
                "mismatch_paths": network_state_projection_mismatch_paths,
            }
        )

    if selected_supplied_point_index is not None:
        selection_source = "supplied_fan_curve_point"
        expected_airflow = float(
            study.fan_curve.points[selected_supplied_point_index].airflow_m3_h
        )
    elif bisection_trace:
        selection_source = "terminal_bisection_midpoint"
        expected_airflow = float(
            bisection_trace[-1]["midpoint_airflow_m3_h"]
        )
    else:
        selection_source = None
        expected_airflow = None

    selection_airflow_error = (
        abs(float(selected_airflow_m3_h) - expected_airflow)
        if expected_airflow is not None
        else None
    )
    selection_origin_matches = (
        math.isclose(
            float(selected_airflow_m3_h),
            expected_airflow,
            rel_tol=0.0,
            abs_tol=airflow_tolerance_m3_h,
        )
        if expected_airflow is not None
        else False
    )

    maximum_error = max(
        check["absolute_error_pa"]
        for check in component_checks.values()
    )
    maximum_error_witnesses = [
        {
            "component": component,
            **check,
        }
        for component, check in component_checks.items()
        if maximum_error > 0.0
        and math.isclose(
            check["absolute_error_pa"],
            maximum_error,
            rel_tol=0.0,
            abs_tol=1e-15,
        )
    ]

    if not network_state_projection_replay_available:
        network_state_projection_replay_verdict = (
            "selected_network_state_projection_replay_not_available"
        )
    elif network_state_projection_matches_independent_replay:
        network_state_projection_replay_verdict = (
            "selected_network_state_projection_replay_consistent"
        )
    else:
        network_state_projection_replay_verdict = (
            "selected_network_state_projection_replay_inconsistent"
        )

    return {
        "available": True,
        "pressure_replay_absolute_tolerance_pa": pressure_tolerance_pa,
        "selection_airflow_absolute_tolerance_m3_h": (
            airflow_tolerance_m3_h
        ),
        "selection_source": selection_source,
        "selected_airflow_replay_input_m3_h": float(selected_airflow_m3_h),
        "recorded_selected_airflow_m3_h": round(
            selected_airflow_m3_h,
            9,
        ),
        "expected_selected_airflow_m3_h": (
            round(expected_airflow, 9)
            if expected_airflow is not None
            else None
        ),
        "absolute_selection_airflow_error_m3_h": selection_airflow_error,
        "selected_airflow_matches_search_origin": selection_origin_matches,
        "network_state_replay_available": True,
        "network_state_replay_algorithm": "sha256",
        "network_state_replay_canonicalization": (
            _NETWORK_STATE_CANONICALIZATION
        ),
        "recorded_network_state_sha256": recorded_network_state,
        "recomputed_network_state_sha256": replayed_network_state,
        "network_state_matches_independent_replay": (
            network_state_matches_independent_replay
        ),
        "network_state_projection_replay_available": (
            network_state_projection_replay_available
        ),
        "recorded_network_state_projection": (
            recorded_network_state_projection
        ),
        "recomputed_network_state_projection": (
            recomputed_network_state_projection
        ),
        "network_state_projection_matches_independent_replay": (
            network_state_projection_matches_independent_replay
        ),
        "selected_network_state_projection_replay_consistent": (
            network_state_projection_matches_independent_replay
        ),
        "network_state_projection_replay_verdict": (
            network_state_projection_replay_verdict
        ),
        "network_state_projection_mismatch_count": (
            len(network_state_projection_mismatches)
            if network_state_projection_replay_available
            else None
        ),
        "network_state_projection_mismatch_paths": (
            network_state_projection_mismatch_paths
        ),
        "network_state_projection_mismatches": (
            network_state_projection_mismatches
        ),
        "network_state_projection_maximum_numeric_errors": (
            _maximum_network_state_projection_numeric_errors(
                network_state_projection_mismatches
            )
        ),
        "component_checks": component_checks,
        "all_pressure_components_match_independent_replay": all(
            check["matches_independent_replay"]
            for check in component_checks.values()
        ),
        "violation_count": len(violations),
        "violations": violations,
        "maximum_absolute_pressure_replay_error_pa": maximum_error,
        "maximum_pressure_replay_error_witnesses": (
            maximum_error_witnesses
        ),
        "all_selected_operating_state_matches_independent_replay": (
            selection_origin_matches
            and network_state_matches_independent_replay
            and (
                network_state_projection_matches_independent_replay
                if network_state_projection_replay_available
                else True
            )
            and all(
                check["matches_independent_replay"]
                for check in component_checks.values()
            )
        ),
    }


def solve_fan_variable_friction_loop(
    study: FanVariableFrictionLoopStudy,
) -> dict:
    points = study.fan_curve.points
    curve_checks: list[dict] = []
    point_networks: list[dict] = []

    try:
        for point in points:
            check, network = _point_check(study, point)
            curve_checks.append(check)
            point_networks.append(network)
    except RuntimeError as exc:
        return _nonconverged_result(
            study,
            curve_checks=curve_checks,
            message=(
                "The variable-friction loop solver did not converge while "
                f"evaluating the bounded fan curve: {exc}"
            ),
        )

    tolerance = study.operating_pressure_tolerance_pa
    selected_airflow: float | None = None
    selected_fan_pressure: float | None = None
    selected_network: dict | None = None
    selected_network_pressure: float | None = None
    selected_segment = 0
    selected_supplied_point_index: int | None = None
    final_bisection_bracket: dict | None = None
    initial_bisection_bracket: dict | None = None
    bisection_trace: list[dict] | None = None
    operating_iterations = 0
    termination_reason = "no_intersection_in_supplied_range"

    for index, (point, check, network) in enumerate(
        zip(points, curve_checks, point_networks)
    ):
        if abs(float(check["pressure_margin_pa"])) <= tolerance:
            selected_airflow = point.airflow_m3_h
            selected_fan_pressure = point.pressure_pa
            selected_network = network
            selected_network_pressure = float(
                check["loop_network_pressure_pa"]
            )
            selected_segment = min(index, len(points) - 2)
            selected_supplied_point_index = index
            termination_reason = "fan_curve_point_residual"
            break

    if selected_airflow is None:
        for index, (left, right) in enumerate(zip(points, points[1:])):
            left_residual = float(curve_checks[index]["pressure_margin_pa"])
            right_residual = float(
                curve_checks[index + 1]["pressure_margin_pa"]
            )
            if not (left_residual > 0.0 and right_residual < 0.0):
                continue

            low = left.airflow_m3_h
            high = right.airflow_m3_h
            low_residual = left_residual
            high_residual = right_residual
            low_fan_pressure = float(curve_checks[index]["fan_pressure_pa"])
            low_network_pressure = float(
                curve_checks[index]["loop_network_pressure_pa"]
            )
            low_system_pressure = float(
                curve_checks[index]["system_pressure_pa"]
            )
            high_fan_pressure = float(
                curve_checks[index + 1]["fan_pressure_pa"]
            )
            high_network_pressure = float(
                curve_checks[index + 1]["loop_network_pressure_pa"]
            )
            high_system_pressure = float(
                curve_checks[index + 1]["system_pressure_pa"]
            )
            low_network_state_projection = _network_state_projection(
                point_networks[index]
            )
            high_network_state_projection = _network_state_projection(
                point_networks[index + 1]
            )
            low_network_state_sha256 = _network_state_sha256(
                point_networks[index]
            )
            high_network_state_sha256 = _network_state_sha256(
                point_networks[index + 1]
            )
            supplied_segment_span = high - low
            initial_bisection_bracket = {
                "low_airflow_m3_h": round(low, 9),
                "high_airflow_m3_h": round(high, 9),
                "low_fan_minus_system_pressure_pa": round(
                    low_residual,
                    9,
                ),
                "high_fan_minus_system_pressure_pa": round(
                    high_residual,
                    9,
                ),
            }
            bisection_trace = []
            final: tuple[float, float, dict, float, float] | None = None

            try:
                for iteration in range(1, study.max_operating_iterations + 1):
                    airflow = 0.5 * (low + high)
                    fan_pressure = _fan_pressure(left, right, airflow)
                    network, network_pressure = _solve_network_at_airflow(
                        study, airflow
                    )
                    system_pressure = (
                        study.fixed_pressure_pa + network_pressure
                    )
                    residual = fan_pressure - system_pressure
                    midpoint_network_state_projection = (
                        _network_state_projection(network)
                    )
                    midpoint_network_state_sha256 = _network_state_sha256(
                        network
                    )
                    final = (
                        airflow,
                        fan_pressure,
                        network,
                        network_pressure,
                        residual,
                    )
                    operating_iterations = iteration
                    bracket_width = high - low
                    width_fraction = bracket_width / supplied_segment_span
                    bracket_midpoint = 0.5 * (low + high)
                    if abs(residual) <= tolerance:
                        decision = "accept_pressure_tolerance"
                    elif residual > 0.0:
                        decision = "replace_low_endpoint"
                    else:
                        decision = "replace_high_endpoint"
                    assert bisection_trace is not None
                    bisection_trace.append(
                        {
                            "iteration": iteration,
                            "low_airflow_m3_h": round(low, 9),
                            "high_airflow_m3_h": round(high, 9),
                            "midpoint_airflow_m3_h": round(airflow, 9),
                            "width_m3_h": round(bracket_width, 9),
                            "width_fraction_of_supplied_segment": round(
                                width_fraction,
                                15,
                            ),
                            "low_fan_minus_system_pressure_pa": round(
                                low_residual,
                                9,
                            ),
                            "low_fan_pressure_pa": round(
                                low_fan_pressure,
                                9,
                            ),
                            "low_loop_network_pressure_pa": round(
                                low_network_pressure,
                                9,
                            ),
                            "low_system_pressure_pa": round(
                                low_system_pressure,
                                9,
                            ),
                            "low_network_state_sha256": (
                                low_network_state_sha256
                            ),
                            "low_network_state_projection": (
                                low_network_state_projection
                            ),
                            "high_fan_minus_system_pressure_pa": round(
                                high_residual,
                                9,
                            ),
                            "high_fan_pressure_pa": round(
                                high_fan_pressure,
                                9,
                            ),
                            "high_loop_network_pressure_pa": round(
                                high_network_pressure,
                                9,
                            ),
                            "high_system_pressure_pa": round(
                                high_system_pressure,
                                9,
                            ),
                            "high_network_state_sha256": (
                                high_network_state_sha256
                            ),
                            "high_network_state_projection": (
                                high_network_state_projection
                            ),
                            "midpoint_fan_pressure_pa": round(
                                fan_pressure,
                                9,
                            ),
                            "midpoint_loop_network_pressure_pa": round(
                                network_pressure,
                                9,
                            ),
                            "midpoint_fixed_pressure_pa": round(
                                study.fixed_pressure_pa,
                                9,
                            ),
                            "midpoint_system_pressure_pa": round(
                                system_pressure,
                                9,
                            ),
                            "midpoint_fan_minus_system_pressure_pa": round(
                                residual,
                                9,
                            ),
                            "midpoint_network_state_sha256": (
                                midpoint_network_state_sha256
                            ),
                            "midpoint_network_state_projection": (
                                midpoint_network_state_projection
                            ),
                            "decision": decision,
                            "strict_sign_change_before_evaluation": (
                                low_residual > 0.0
                                and high_residual < 0.0
                            ),
                            "midpoint_is_arithmetic_bracket_midpoint": (
                                math.isclose(
                                    airflow,
                                    bracket_midpoint,
                                    rel_tol=0.0,
                                    abs_tol=1e-12,
                                )
                            ),
                        }
                    )
                    if abs(residual) <= tolerance:
                        expected_width_fraction = 0.5 ** (iteration - 1)
                        final_bisection_bracket = {
                            "low_airflow_m3_h": round(low, 9),
                            "high_airflow_m3_h": round(high, 9),
                            "width_m3_h": round(bracket_width, 9),
                            "half_width_m3_h": round(
                                0.5 * bracket_width,
                                9,
                            ),
                            "low_fan_minus_system_pressure_pa": round(
                                low_residual,
                                9,
                            ),
                            "low_fan_pressure_pa": round(low_fan_pressure, 9),
                            "low_loop_network_pressure_pa": round(
                                low_network_pressure,
                                9,
                            ),
                            "low_system_pressure_pa": round(
                                low_system_pressure,
                                9,
                            ),
                            "low_network_state_sha256": (
                                low_network_state_sha256
                            ),
                            "low_network_state_projection": (
                                low_network_state_projection
                            ),
                            "high_fan_minus_system_pressure_pa": round(
                                high_residual,
                                9,
                            ),
                            "high_fan_pressure_pa": round(high_fan_pressure, 9),
                            "high_loop_network_pressure_pa": round(
                                high_network_pressure,
                                9,
                            ),
                            "high_system_pressure_pa": round(
                                high_system_pressure,
                                9,
                            ),
                            "high_network_state_sha256": (
                                high_network_state_sha256
                            ),
                            "high_network_state_projection": (
                                high_network_state_projection
                            ),
                            "selected_midpoint_airflow_m3_h": round(
                                airflow,
                                9,
                            ),
                            "selected_fan_minus_system_pressure_pa": round(
                                residual,
                                9,
                            ),
                            "width_fraction_of_supplied_segment": round(
                                width_fraction,
                                12,
                            ),
                            "iteration": iteration,
                            "invariant_audit": {
                                "strict_sign_change_preserved": (
                                    low_residual > 0.0
                                    and high_residual < 0.0
                                ),
                                "selected_airflow_is_bracket_midpoint": (
                                    math.isclose(
                                        airflow,
                                        bracket_midpoint,
                                        rel_tol=0.0,
                                        abs_tol=1e-12,
                                    )
                                ),
                                "binary_contraction_step_count": (
                                    iteration - 1
                                ),
                                "expected_width_fraction_of_supplied_segment": round(
                                    expected_width_fraction,
                                    15,
                                ),
                                "actual_width_fraction_of_supplied_segment": round(
                                    width_fraction,
                                    15,
                                ),
                                "absolute_width_fraction_consistency_error": round(
                                    abs(
                                        width_fraction
                                        - expected_width_fraction
                                    ),
                                    18,
                                ),
                            },
                        }
                        termination_reason = "pressure_residual"
                        break
                    if residual > 0.0:
                        low = airflow
                        low_residual = residual
                        low_fan_pressure = fan_pressure
                        low_network_pressure = network_pressure
                        low_system_pressure = system_pressure
                        low_network_state_sha256 = (
                            midpoint_network_state_sha256
                        )
                        low_network_state_projection = (
                            midpoint_network_state_projection
                        )
                    else:
                        high = airflow
                        high_residual = residual
                        high_fan_pressure = fan_pressure
                        high_network_pressure = network_pressure
                        high_system_pressure = system_pressure
                        high_network_state_sha256 = (
                            midpoint_network_state_sha256
                        )
                        high_network_state_projection = (
                            midpoint_network_state_projection
                        )
                else:
                    termination_reason = "bisection_iteration_limit"
            except RuntimeError as exc:
                return _nonconverged_result(
                    study,
                    curve_checks=curve_checks,
                    message=(
                        "The variable-friction loop solver did not converge "
                        "during bounded fan/system root search: "
                        f"{exc}"
                    ),
                )

            if final is None:
                continue
            (
                selected_airflow,
                selected_fan_pressure,
                selected_network,
                selected_network_pressure,
                residual,
            ) = final
            selected_segment = index
            if abs(residual) > tolerance:
                terminal_width = high - low
                terminal_width_fraction = (
                    terminal_width / supplied_segment_span
                )
                expected_terminal_width_fraction = (
                    0.5 ** operating_iterations
                )
                terminal_bracket = {
                    "low_airflow_m3_h": round(low, 9),
                    "high_airflow_m3_h": round(high, 9),
                    "width_m3_h": round(terminal_width, 9),
                    "half_width_m3_h": round(
                        0.5 * terminal_width,
                        9,
                    ),
                    "low_fan_minus_system_pressure_pa": round(
                        low_residual,
                        9,
                    ),
                    "low_fan_pressure_pa": round(low_fan_pressure, 9),
                    "low_loop_network_pressure_pa": round(
                        low_network_pressure,
                        9,
                    ),
                    "low_system_pressure_pa": round(low_system_pressure, 9),
                    "low_network_state_sha256": low_network_state_sha256,
                    "low_network_state_projection": (
                        low_network_state_projection
                    ),
                    "high_fan_minus_system_pressure_pa": round(
                        high_residual,
                        9,
                    ),
                    "high_fan_pressure_pa": round(high_fan_pressure, 9),
                    "high_loop_network_pressure_pa": round(
                        high_network_pressure,
                        9,
                    ),
                    "high_system_pressure_pa": round(high_system_pressure, 9),
                    "high_network_state_sha256": high_network_state_sha256,
                    "high_network_state_projection": (
                        high_network_state_projection
                    ),
                    "width_fraction_of_supplied_segment": round(
                        terminal_width_fraction,
                        12,
                    ),
                    "completed_iteration_count": operating_iterations,
                    "invariant_audit": {
                        "strict_sign_change_preserved": (
                            low_residual > 0.0
                            and high_residual < 0.0
                        ),
                        "binary_contraction_step_count": (
                            operating_iterations
                        ),
                        "expected_width_fraction_of_supplied_segment": round(
                            expected_terminal_width_fraction,
                            15,
                        ),
                        "actual_width_fraction_of_supplied_segment": round(
                            terminal_width_fraction,
                            15,
                        ),
                        "absolute_width_fraction_consistency_error": round(
                            abs(
                                terminal_width_fraction
                                - expected_terminal_width_fraction
                            ),
                            18,
                        ),
                    },
                }
                search_evidence = {
                    "method": "bounded_bisection",
                    "supplied_segment_index": selected_segment,
                    "supplied_segment_low_airflow_m3_h": round(
                        left.airflow_m3_h,
                        6,
                    ),
                    "supplied_segment_high_airflow_m3_h": round(
                        right.airflow_m3_h,
                        6,
                    ),
                    "selected_supplied_point_index": None,
                    "operating_iterations": operating_iterations,
                    "initial_bisection_bracket": initial_bisection_bracket,
                    "final_bisection_bracket": None,
                    "bisection_trace": bisection_trace,
                    "bisection_trace_audit": _bisection_decision_trace_audit(
                        bisection_trace,
                        operating_iterations=operating_iterations,
                        termination_reason=termination_reason,
                        operating_pressure_tolerance_pa=tolerance,
                        expected_fixed_pressure_pa=study.fixed_pressure_pa,
                        study=study,
                        segment_left=left,
                        segment_right=right,
                        initial_bisection_bracket=initial_bisection_bracket,
                        iteration_limit_terminal_bracket=terminal_bracket,
                    ),
                    "iteration_limit_evidence": {
                        "last_evaluated_midpoint_airflow_m3_h": round(
                            selected_airflow,
                            9,
                        ),
                        "last_evaluated_fan_minus_system_pressure_pa": round(
                            residual,
                            9,
                        ),
                        "pressure_tolerance_satisfied": False,
                        "remaining_bisection_bracket": terminal_bracket,
                    },
                    "scope_note": (
                        "The iteration-limit evidence retains the active "
                        "signed-residual bracket remaining after the final "
                        "budgeted bisection evaluation. Its geometry and "
                        "binary-contraction audit are solver implementation "
                        "diagnostics only; no operating point is accepted, "
                        "and the remaining bracket is not physical airflow "
                        "uncertainty, interpolation error, a continuous "
                        "worst-case bound, or an equipment-acceptance limit."
                    ),
                }
                return _with_solver_result_integrity({
                    **_nonconverged_result(
                        study,
                        curve_checks=curve_checks,
                        message=(
                            "Bounded fan/system bisection reached "
                            "max_operating_iterations before satisfying the "
                            "configured pressure residual tolerance."
                        ),
                    ),
                    "operating_point_search_evidence": search_evidence,
                    "solver_diagnostics": {
                        "converged": False,
                        "termination_reason": termination_reason,
                        "operating_iterations": operating_iterations,
                        "operating_pressure_tolerance_pa": tolerance,
                        "final_pressure_residual_pa": round(residual, 9),
                        "bracket_low_airflow_m3_h": round(low, 9),
                        "bracket_high_airflow_m3_h": round(high, 9),
                    },
                })
            break

    base = {
        "study": study.name,
        "fan_curve": study.fan_curve.name,
        "fan_discharge_node": study.fan_discharge_node,
        "fan_suction_node": study.fan_suction_node,
        "fixed_pressure_pa": round(study.fixed_pressure_pa, 6),
        "fan_curve_airflow_range_m3_h": [
            round(points[0].airflow_m3_h, 6),
            round(points[-1].airflow_m3_h, 6),
        ],
        "fan_curve_point_checks": curve_checks,
        "fan_curve_supplied_point_residual_audit": (
            _fan_curve_supplied_point_residual_audit(
                study,
                curve_checks,
            )
        ),
        "fan_curve_supplied_point_network_state_replay": (
            _fan_curve_supplied_point_network_state_replay_audit(
                study,
                curve_checks,
            )
        ),
    }

    if selected_airflow is None:
        if float(curve_checks[0]["pressure_margin_pa"]) < 0.0:
            message = (
                "System pressure exceeds fan pressure at the lowest supplied "
                "airflow point. No lower-flow fan extrapolation is performed."
            )
        else:
            message = (
                "Fan pressure remains above system pressure at the highest "
                "supplied airflow point. No higher-flow fan extrapolation is "
                "performed."
            )
        return _with_solver_result_integrity({
            **base,
            "status": "no_intersection_in_supplied_range",
            "fan_operating_point": None,
            "operating_point_search_evidence": None,
            "operating_network_solution": None,
            "system_pressure_check": None,
            "power_evidence": None,
            "solver_diagnostics": {
                "converged": True,
                "termination_reason": termination_reason,
                "operating_iterations": 0,
                "operating_pressure_tolerance_pa": tolerance,
            },
            "message": message,
            "scope_note": _scope_note(),
        })

    assert selected_fan_pressure is not None
    assert selected_network is not None
    assert selected_network_pressure is not None
    system_pressure = study.fixed_pressure_pa + selected_network_pressure
    residual = selected_fan_pressure - system_pressure
    airflow_m3_s = selected_airflow / 3600.0
    left = points[selected_segment]
    right = points[selected_segment + 1]
    vf = selected_network["variable_friction"]
    power_evidence = analyze_fan_pressure_power(
        selected_airflow,
        selected_fan_pressure,
        study.power_efficiencies,
    )
    network_pressure_power_w = (
        airflow_m3_s * selected_network_pressure
    )
    fixed_pressure_power_w = airflow_m3_s * study.fixed_pressure_pa
    edge_dissipation_w = selected_network["pressure_power"][
        "total_edge_dissipation_w"
    ]
    fan_to_system_power_residual_w = (
        power_evidence["fluid_air_power_w"]
        - fixed_pressure_power_w
        - edge_dissipation_w
    )
    selected_residual_audit = _with_selected_crossing_feature(
        base["fan_curve_supplied_point_residual_audit"],
        termination_reason=termination_reason,
        selected_airflow_m3_h=selected_airflow,
        selected_segment_index=selected_segment,
    )
    selected_operating_state_replay = (
        _selected_operating_state_replay_audit(
            study,
            selected_airflow_m3_h=selected_airflow,
            recorded_fan_pressure_pa=selected_fan_pressure,
            recorded_loop_network_pressure_pa=selected_network_pressure,
            recorded_system_pressure_pa=system_pressure,
            recorded_residual_pa=residual,
            recorded_network_state_sha256=_network_state_sha256(
                selected_network
            ),
            recorded_network_state_projection=_network_state_projection(
                selected_network
            ),
            segment_left=left,
            segment_right=right,
            selected_supplied_point_index=selected_supplied_point_index,
            bisection_trace=bisection_trace,
        )
    )
    operating_point_search_evidence = {
        "method": (
            "supplied_point_tolerance_contact"
            if termination_reason == "fan_curve_point_residual"
            else "bounded_bisection"
        ),
        "supplied_segment_index": selected_segment,
        "supplied_segment_low_airflow_m3_h": round(
            left.airflow_m3_h,
            6,
        ),
        "supplied_segment_high_airflow_m3_h": round(
            right.airflow_m3_h,
            6,
        ),
        "selected_supplied_point_index": selected_supplied_point_index,
        "operating_iterations": operating_iterations,
        "selected_operating_state_replay": selected_operating_state_replay,
        "initial_bisection_bracket": initial_bisection_bracket,
        "final_bisection_bracket": final_bisection_bracket,
        "bisection_trace": bisection_trace,
        "bisection_trace_audit": _bisection_decision_trace_audit(
            bisection_trace,
            operating_iterations=operating_iterations,
            termination_reason=termination_reason,
            operating_pressure_tolerance_pa=tolerance,
            expected_fixed_pressure_pa=study.fixed_pressure_pa,
            study=study,
            segment_left=left,
            segment_right=right,
            initial_bisection_bracket=initial_bisection_bracket,
            solved_terminal_bracket=final_bisection_bracket,
        ),
        "scope_note": (
            "The final bisection bracket is the active signed-residual search "
            "interval immediately before a pressure-tolerance midpoint "
            "termination. Bounded-bisection solutions also retain every "
            "midpoint decision that led to that terminal bracket. Iteration-"
            "limit outcomes retain the same completed decision trace and "
            "replay its final L/H decision into the remaining active bracket "
            "without accepting a root; direct supplied-point contacts do not "
            "fabricate a bisection trace. Bracket width and the decision trace "
            "are numerical search "
            "provenance only; they are not physical airflow uncertainty, "
            "interpolation-error bounds, continuous worst-case guarantees, "
            "stability margins, or equipment-acceptance criteria."
        ),
    }

    power_evidence["system_components"] = {
        "fixed_pressure_power_w": round(fixed_pressure_power_w, 9),
        "loop_network_terminal_pressure_power_w": round(
            network_pressure_power_w, 9
        ),
        "loop_network_edge_dissipation_w": edge_dissipation_w,
        "loop_network_energy_balance_residual_w": selected_network[
            "pressure_power"
        ]["balance_residual_w"],
        "fan_to_fixed_plus_edge_loss_residual_w": round(
            fan_to_system_power_residual_w, 9
        ),
    }

    return _with_solver_result_integrity({
        **base,
        "status": "solved",
        "fan_curve_supplied_point_residual_audit": selected_residual_audit,
        "operating_point_search_evidence": operating_point_search_evidence,
        "fan_operating_point": {
            "airflow_m3_h": round(selected_airflow, 6),
            "airflow_m3_s": round(airflow_m3_s, 9),
            "fan_pressure_pa": round(selected_fan_pressure, 9),
            "system_pressure_pa": round(system_pressure, 9),
            "pressure_residual_pa": round(residual, 9),
            "air_power_kw": round(
                airflow_m3_s * system_pressure / 1000.0, 9
            ),
            "interpolation_segment": {
                "low_airflow_m3_h": round(left.airflow_m3_h, 6),
                "high_airflow_m3_h": round(right.airflow_m3_h, 6),
            },
        },
        "operating_network_solution": selected_network,
        "power_evidence": power_evidence,
        "system_pressure_check": {
            "fixed_pressure_pa": round(study.fixed_pressure_pa, 6),
            "loop_network_pressure_pa": round(
                selected_network_pressure, 9
            ),
            "total_system_pressure_pa": round(system_pressure, 9),
            "fan_pressure_pa": round(selected_fan_pressure, 9),
            "fan_minus_system_pressure_pa": round(residual, 9),
        },
        "solver_diagnostics": {
            "converged": True,
            "termination_reason": termination_reason,
            "operating_iterations": operating_iterations,
            "operating_pressure_tolerance_pa": tolerance,
            "network_outer_iterations": vf["outer_iterations"],
            "network_newton_iterations": selected_network["iterations"],
            "network_resistance_relative_tolerance": vf[
                "resistance_relative_tolerance"
            ],
            "network_max_relative_resistance_closure_error": vf[
                "max_relative_resistance_closure_error"
            ],
            "max_abs_mass_balance_residual_m3_h": selected_network[
                "max_abs_mass_balance_residual_m3_h"
            ],
            "max_abs_pressure_law_residual_pa": selected_network[
                "max_abs_pressure_law_residual_pa"
            ],
        },
        "message": (
            "Operating point found inside the supplied fan-curve range by "
            "bounded interpolation with a complete variable-friction loop "
            "re-solve at every evaluated airflow."
        ),
        "scope_note": _scope_note(),
    })
