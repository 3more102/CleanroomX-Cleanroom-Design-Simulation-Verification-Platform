from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable


def _count_statuses(statuses: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for status in statuses:
        counts[status] = counts.get(status, 0) + 1
    return counts


def _status_from_counts(
    counts: dict[str, int],
    *,
    incomplete_is_adverse: bool = False,
) -> str:
    if counts.get("fail", 0):
        return "fail"
    if counts.get("indeterminate", 0):
        return "indeterminate"
    if incomplete_is_adverse and counts.get("incomplete", 0):
        return "incomplete"
    if counts.get("pass", 0) and counts.get("not_checked", 0):
        return "pass_with_unchecked"
    if counts.get("pass", 0):
        return "pass"
    if counts.get("not_checked", 0):
        return "not_checked"
    return "not_checked"


def _verification_summary(result: dict | None) -> dict:
    if result is None:
        return {"status": "not_included", "counts": {}}

    statuses: list[str] = []
    for room in result.get("rooms", []):
        statuses.extend(item["status"] for item in room.get("findings", []))
    statuses.extend(item["status"] for item in result.get("pressure_cascade", []))
    counts = _count_statuses(statuses)
    return {"status": _status_from_counts(counts), "counts": counts}


def _hvac_summary(result: dict | None) -> dict:
    if result is None:
        return {
            "status": "not_included",
            "failed_air_balances": 0,
            "fan_curve_duty_failures": 0,
            "fan_curve_duty_unresolved": 0,
            "room_count": 0,
        }
    rooms = result.get("rooms", [])
    failed = sum(
        not room.get("air_balance", {}).get("passes_minimum_surplus", False)
        for room in rooms
    )
    fan_check = result.get("fan_curve_duty_check")
    fan_status = fan_check.get("status") if fan_check is not None else None
    fan_failures = 1 if fan_status == "fail" else 0
    fan_unresolved = 1 if fan_status == "outside_supplied_range" else 0
    if failed or fan_failures:
        status = "fail"
    elif fan_unresolved:
        status = "attention_required"
    else:
        status = "screening_complete"
    return {
        "status": status,
        "failed_air_balances": failed,
        "fan_curve_duty_failures": fan_failures,
        "fan_curve_duty_unresolved": fan_unresolved,
        "room_count": len(rooms),
    }


def _recovery_summary(results: list[dict]) -> dict:
    if not results:
        return {"status": "not_included", "counts": {}, "test_count": 0}
    counts = _count_statuses(item["criterion_status"] for item in results)
    return {
        "status": _status_from_counts(counts, incomplete_is_adverse=True),
        "counts": counts,
        "test_count": len(results),
    }


def _qualification_summary(results: list[dict]) -> dict:
    if not results:
        return {"status": "not_included", "counts": {}, "analysis_count": 0}
    counts = _count_statuses(item["overall_status"] for item in results)
    return {
        "status": _status_from_counts(counts),
        "counts": counts,
        "analysis_count": len(results),
    }


def _uncertainty_summary(results: list[dict]) -> dict:
    if not results:
        return {"status": "not_included", "counts": {}, "room_count": 0}
    counts = _count_statuses(item["requirement"]["status"] for item in results)
    return {
        "status": _status_from_counts(counts),
        "counts": counts,
        "room_count": len(results),
    }


def _thermal_uncertainty_summary(results: list[dict]) -> dict:
    if not results:
        return {"status": "not_included", "counts": {}, "analysis_count": 0}
    counts = _count_statuses(item["overall_status"] for item in results)
    return {
        "status": _status_from_counts(counts),
        "counts": counts,
        "analysis_count": len(results),
    }


def _psychrometric_uncertainty_summary(results: list[dict]) -> dict:
    if not results:
        return {
            "status": "not_included",
            "analysis_count": 0,
            "missing_provenance_analyses": 0,
        }
    missing = sum(not item["traceability"]["complete"] for item in results)
    return {
        "status": (
            "complete_with_missing_provenance"
            if missing
            else "screening_complete"
        ),
        "analysis_count": len(results),
        "missing_provenance_analyses": missing,
    }


def _fan_system_uncertainty_summary(results: list[dict]) -> dict:
    if not results:
        return {
            "status": "not_included",
            "counts": {},
            "analysis_count": 0,
            "missing_provenance_analyses": 0,
        }
    counts = _count_statuses(item["status"] for item in results)
    missing = sum(not item["traceability"]["complete"] for item in results)
    if counts.get("indeterminate", 0):
        status = "attention_required"
    elif missing:
        status = "complete_with_missing_provenance"
    else:
        status = "screening_complete"
    return {
        "status": status,
        "counts": counts,
        "analysis_count": len(results),
        "missing_provenance_analyses": missing,
    }


def _fan_loop_uncertainty_summary(results: list[dict]) -> dict:
    if not results:
        return {
            "status": "not_included",
            "counts": {},
            "analysis_count": 0,
            "missing_provenance_analyses": 0,
        }
    counts = _count_statuses(item["status"] for item in results)
    missing = sum(not item["traceability"]["complete"] for item in results)
    if counts.get("indeterminate", 0):
        status = "attention_required"
    elif missing:
        status = "complete_with_missing_provenance"
    else:
        status = "screening_complete"
    return {
        "status": status,
        "counts": counts,
        "analysis_count": len(results),
        "missing_provenance_analyses": missing,
    }


def _fan_variable_friction_uncertainty_summary(results: list[dict]) -> dict:
    if not results:
        return {
            "status": "not_included",
            "counts": {},
            "analysis_count": 0,
            "corner_count": 0,
            "fan_curve_scenario_count": 0,
            "no_intersection_corner_count": 0,
            "missing_provenance_analyses": 0,
            "result_integrity_count": 0,
            "missing_result_integrity_analyses": 0,
            "solver_result_integrity_complete_coverage_analyses": 0,
            "solver_result_integrity_inconsistent_corner_count": 0,
            "solver_result_integrity_coverage_gap_corner_count": 0,
        }
    counts = _count_statuses(item["status"] for item in results)
    missing = sum(not item["traceability"]["complete"] for item in results)
    integrity_count = sum(
        isinstance(item.get("result_integrity", {}).get("sha256"), str)
        and len(item["result_integrity"]["sha256"]) == 64
        for item in results
    )
    solver_result_integrity_complete_coverage_analyses = sum(
        item.get("solver_result_integrity_summary", {}).get(
            "complete_corner_coverage"
        )
        is True
        for item in results
    )
    solver_result_integrity_inconsistent_corner_count = sum(
        item.get("solver_result_integrity_summary", {}).get(
            "inconsistent_corner_count", 0
        )
        for item in results
    )
    solver_result_integrity_coverage_gap_corner_count = sum(
        item.get("solver_result_integrity_summary", {}).get(
            "incomplete_corner_count", 0
        )
        for item in results
    )
    if counts.get("indeterminate", 0):
        status = "attention_required"
    elif missing:
        status = "complete_with_missing_provenance"
    else:
        status = "screening_complete"
    return {
        "status": status,
        "counts": counts,
        "analysis_count": len(results),
        "corner_count": sum(item.get("corner_count", 0) for item in results),
        "fan_curve_scenario_count": sum(
            len(item.get("fan_curve_scenarios", [])) for item in results
        ),
        "no_intersection_corner_count": sum(
            item.get("fan_curve_no_intersection_summary", {}).get(
                "no_intersection_corner_count", 0
            )
            for item in results
        ),
        "missing_provenance_analyses": missing,
        "result_integrity_count": integrity_count,
        "missing_result_integrity_analyses": len(results) - integrity_count,
        "solver_result_integrity_complete_coverage_analyses": (
            solver_result_integrity_complete_coverage_analyses
        ),
        "solver_result_integrity_inconsistent_corner_count": (
            solver_result_integrity_inconsistent_corner_count
        ),
        "solver_result_integrity_coverage_gap_corner_count": (
            solver_result_integrity_coverage_gap_corner_count
        ),
    }


def _fan_loop_speed_summary(results: list[dict]) -> dict:
    if not results:
        return {
            "status": "not_included",
            "counts": {},
            "study_count": 0,
            "speed_case_count": 0,
        }
    statuses = [
        case["status"]
        for result in results
        for case in result.get("speed_cases", [])
    ]
    counts = _count_statuses(statuses)
    unresolved = counts.get("no_intersection_in_supplied_range", 0)
    return {
        "status": "attention_required" if unresolved else "screening_complete",
        "counts": counts,
        "study_count": len(results),
        "speed_case_count": len(statuses),
    }


def _fan_variable_friction_loop_summary(results: list[dict]) -> dict:
    if not results:
        return {
            "status": "not_included",
            "counts": {},
            "study_count": 0,
        }
    counts = _count_statuses(item["status"] for item in results)
    non_solved = sum(
        count for status, count in counts.items() if status != "solved"
    )
    return {
        "status": (
            "attention_required" if non_solved else "screening_complete"
        ),
        "counts": counts,
        "study_count": len(results),
    }


def _fan_variable_friction_speed_summary(results: list[dict]) -> dict:
    if not results:
        return {
            "status": "not_included",
            "counts": {},
            "study_count": 0,
            "speed_case_count": 0,
        }
    statuses = [
        case["status"]
        for result in results
        for case in result.get("speed_cases", [])
    ]
    counts = _count_statuses(statuses)
    non_solved = sum(
        count for status, count in counts.items() if status != "solved"
    )
    return {
        "status": (
            "attention_required" if non_solved else "screening_complete"
        ),
        "counts": counts,
        "study_count": len(results),
        "speed_case_count": len(statuses),
    }


def _fan_operating_point_summary(results: list[dict]) -> dict:
    if not results:
        return {"status": "not_included", "counts": {}, "study_count": 0}
    counts = _count_statuses(item["status"] for item in results)
    unresolved = counts.get("no_intersection_in_supplied_range", 0)
    return {
        "status": "attention_required" if unresolved else "screening_complete",
        "counts": counts,
        "study_count": len(results),
    }


def _fan_duct_network_summary(results: list[dict]) -> dict:
    if not results:
        return {"status": "not_included", "counts": {}, "study_count": 0}
    counts = _count_statuses(item["status"] for item in results)
    unresolved = counts.get("no_intersection_in_supplied_range", 0)
    return {
        "status": "attention_required" if unresolved else "screening_complete",
        "counts": counts,
        "study_count": len(results),
    }


def _fan_parallel_network_summary(results: list[dict]) -> dict:
    if not results:
        return {"status": "not_included", "counts": {}, "study_count": 0}
    counts = _count_statuses(item["status"] for item in results)
    unresolved = counts.get("no_intersection_in_supplied_range", 0)
    return {
        "status": "attention_required" if unresolved else "screening_complete",
        "counts": counts,
        "study_count": len(results),
    }


def _fan_loop_network_summary(results: list[dict]) -> dict:
    if not results:
        return {"status": "not_included", "counts": {}, "study_count": 0}
    counts = _count_statuses(item["status"] for item in results)
    unresolved = counts.get("no_intersection_in_supplied_range", 0)
    return {
        "status": "attention_required" if unresolved else "screening_complete",
        "counts": counts,
        "study_count": len(results),
    }


def _damper_study_summary(results: list[dict]) -> dict:
    if not results:
        return {"status": "not_included", "counts": {}, "study_count": 0, "case_count": 0}
    counts = _count_statuses(item["status"] for item in results)
    return {
        "status": "screening_complete",
        "counts": counts,
        "study_count": len(results),
        "case_count": sum(len(item.get("cases", [])) for item in results),
    }


def _fan_speed_summary(results: list[dict]) -> dict:
    if not results:
        return {
            "status": "not_included",
            "counts": {},
            "study_count": 0,
            "speed_case_count": 0,
        }
    statuses = [
        case["status"]
        for result in results
        for case in result.get("speed_cases", [])
    ]
    counts = _count_statuses(statuses)
    unresolved = counts.get("no_intersection_in_supplied_range", 0)
    return {
        "status": "attention_required" if unresolved else "screening_complete",
        "counts": counts,
        "study_count": len(results),
        "speed_case_count": len(statuses),
    }


def _consistency_summary(result: dict | None) -> dict:
    if result is None:
        return {
            "status": "not_included",
            "shared_room_count": 0,
            "mismatch_count": 0,
            "room_set_mismatch": False,
            "issue_count": 0,
        }
    issue_count = result.get("mismatch_count", 0) + (
        1 if result.get("room_set_mismatch", False) else 0
    )
    return {
        "status": result["status"],
        "shared_room_count": result.get("shared_room_count", 0),
        "mismatch_count": result.get("mismatch_count", 0),
        "room_set_mismatch": result.get("room_set_mismatch", False),
        "issue_count": issue_count,
    }


def _fan_airflow_consistency_summary(result: dict | None) -> dict:
    if result is None:
        return {
            "status": "not_included",
            "study_count": 0,
            "solved_study_count": 0,
            "mismatch_count": 0,
            "unresolved_study_count": 0,
        }
    return {
        "status": result["status"],
        "study_count": result.get("study_count", 0),
        "solved_study_count": result.get("solved_study_count", 0),
        "mismatch_count": result.get("mismatch_count", 0),
        "unresolved_study_count": result.get("unresolved_study_count", 0),
    }


def summarize_dossier_components(
    verification: dict | None = None,
    hvac: dict | None = None,
    recovery: list[dict] | None = None,
    uncertainty: list[dict] | None = None,
    qualification: list[dict] | None = None,
    thermal_uncertainty: list[dict] | None = None,
    psychrometric_uncertainty: list[dict] | None = None,
    fan_operating_points: list[dict] | None = None,
    fan_system_uncertainty: list[dict] | None = None,
    fan_duct_networks: list[dict] | None = None,
    fan_parallel_networks: list[dict] | None = None,
    fan_loop_networks: list[dict] | None = None,
    fan_loop_uncertainty: list[dict] | None = None,
    damper_studies: list[dict] | None = None,
    fan_speed_studies: list[dict] | None = None,
    fan_loop_speed_studies: list[dict] | None = None,
    fan_variable_friction_loops: list[dict] | None = None,
    fan_variable_friction_speed_studies: list[dict] | None = None,
    fan_variable_friction_uncertainty: list[dict] | None = None,
    consistency: dict | None = None,
    fan_airflow_consistency: dict | None = None,
) -> dict:
    recovery = recovery or []
    uncertainty = uncertainty or []
    qualification = qualification or []
    thermal_uncertainty = thermal_uncertainty or []
    psychrometric_uncertainty = psychrometric_uncertainty or []
    fan_operating_points = fan_operating_points or []
    fan_system_uncertainty = fan_system_uncertainty or []
    fan_duct_networks = fan_duct_networks or []
    fan_parallel_networks = fan_parallel_networks or []
    fan_loop_networks = fan_loop_networks or []
    fan_loop_uncertainty = fan_loop_uncertainty or []
    damper_studies = damper_studies or []
    fan_speed_studies = fan_speed_studies or []
    fan_loop_speed_studies = fan_loop_speed_studies or []
    fan_variable_friction_loops = fan_variable_friction_loops or []
    fan_variable_friction_speed_studies = (
        fan_variable_friction_speed_studies or []
    )
    fan_variable_friction_uncertainty = (
        fan_variable_friction_uncertainty or []
    )

    components = {
        "verification": _verification_summary(verification),
        "hvac": _hvac_summary(hvac),
        "recovery": _recovery_summary(recovery),
        "uncertainty": _uncertainty_summary(uncertainty),
        "qualification": _qualification_summary(qualification),
        "thermal_uncertainty": _thermal_uncertainty_summary(thermal_uncertainty),
        "psychrometric_uncertainty": _psychrometric_uncertainty_summary(
            psychrometric_uncertainty
        ),
        "fan_operating_points": _fan_operating_point_summary(fan_operating_points),
        "fan_system_uncertainty": _fan_system_uncertainty_summary(
            fan_system_uncertainty
        ),
        "fan_duct_networks": _fan_duct_network_summary(fan_duct_networks),
        "fan_parallel_networks": _fan_parallel_network_summary(fan_parallel_networks),
        "fan_loop_networks": _fan_loop_network_summary(fan_loop_networks),
        "fan_loop_uncertainty": _fan_loop_uncertainty_summary(
            fan_loop_uncertainty
        ),
        "damper_studies": _damper_study_summary(damper_studies),
        "fan_speed_studies": _fan_speed_summary(fan_speed_studies),
        "fan_loop_speed_studies": _fan_loop_speed_summary(
            fan_loop_speed_studies
        ),
        "fan_variable_friction_loops": _fan_variable_friction_loop_summary(
            fan_variable_friction_loops
        ),
        "fan_variable_friction_speed_studies": (
            _fan_variable_friction_speed_summary(
                fan_variable_friction_speed_studies
            )
        ),
        "fan_variable_friction_uncertainty": (
            _fan_variable_friction_uncertainty_summary(
                fan_variable_friction_uncertainty
            )
        ),
        "cross_module_consistency": _consistency_summary(consistency),
        "hvac_fan_operating_airflow_consistency": _fan_airflow_consistency_summary(
            fan_airflow_consistency
        ),
    }

    adverse = {
        "verification_failures": components["verification"]["counts"].get("fail", 0),
        "hvac_air_balance_failures": components["hvac"].get("failed_air_balances", 0),
        "hvac_fan_curve_duty_failures": components["hvac"].get("fan_curve_duty_failures", 0),
        "hvac_fan_curve_duty_unresolved": components["hvac"].get("fan_curve_duty_unresolved", 0),
        "recovery_failures": components["recovery"]["counts"].get("fail", 0),
        "recovery_incomplete": components["recovery"]["counts"].get("incomplete", 0),
        "recovery_indeterminate": components["recovery"]["counts"].get("indeterminate", 0),
        "uncertainty_failures": components["uncertainty"]["counts"].get("fail", 0),
        "uncertainty_indeterminate": components["uncertainty"]["counts"].get("indeterminate", 0),
        "qualification_failures": components["qualification"]["counts"].get("fail", 0),
        "qualification_indeterminate": components["qualification"]["counts"].get("indeterminate", 0),
        "thermal_uncertainty_failures": components["thermal_uncertainty"]["counts"].get("fail", 0),
        "thermal_uncertainty_indeterminate": components["thermal_uncertainty"]["counts"].get("indeterminate", 0),
        "fan_operating_points_unsolved": components["fan_operating_points"]["counts"].get(
            "no_intersection_in_supplied_range", 0
        ),
        "fan_system_uncertainty_indeterminate": components[
            "fan_system_uncertainty"
        ]["counts"].get("indeterminate", 0),
        "fan_duct_networks_unsolved": components["fan_duct_networks"]["counts"].get(
            "no_intersection_in_supplied_range", 0
        ),
        "fan_parallel_networks_unsolved": components["fan_parallel_networks"]["counts"].get(
            "no_intersection_in_supplied_range", 0
        ),
        "fan_loop_networks_unsolved": components["fan_loop_networks"]["counts"].get(
            "no_intersection_in_supplied_range", 0
        ),
        "fan_loop_uncertainty_indeterminate": components[
            "fan_loop_uncertainty"
        ]["counts"].get("indeterminate", 0),
        "fan_speed_studies_unsolved": components["fan_speed_studies"]["counts"].get(
            "no_intersection_in_supplied_range", 0
        ),
        "fan_loop_speed_studies_unsolved": components[
            "fan_loop_speed_studies"
        ]["counts"].get("no_intersection_in_supplied_range", 0),
        "fan_variable_friction_loops_unsolved": components[
            "fan_variable_friction_loops"
        ]["counts"].get("no_intersection_in_supplied_range", 0),
        "fan_variable_friction_loops_non_converged": components[
            "fan_variable_friction_loops"
        ]["counts"].get("non_converged", 0),
        "fan_variable_friction_speed_studies_unsolved": components[
            "fan_variable_friction_speed_studies"
        ]["counts"].get("no_intersection_in_supplied_range", 0),
        "fan_variable_friction_speed_studies_non_converged": components[
            "fan_variable_friction_speed_studies"
        ]["counts"].get("non_converged", 0),
        "fan_variable_friction_uncertainty_indeterminate": components[
            "fan_variable_friction_uncertainty"
        ]["counts"].get("indeterminate", 0),
        "cross_module_consistency_failures": (
            components["cross_module_consistency"]["issue_count"]
            if components["cross_module_consistency"]["status"] == "fail"
            else 0
        ),
        "hvac_fan_operating_airflow_mismatches": (
            components["hvac_fan_operating_airflow_consistency"]["mismatch_count"]
            if components["hvac_fan_operating_airflow_consistency"]["status"] == "fail"
            else 0
        ),
    }
    unresolved = {
        "verification_not_checked": components["verification"]["counts"].get("not_checked", 0),
        "recovery_not_checked": components["recovery"]["counts"].get("not_checked", 0),
        "uncertainty_not_checked": components["uncertainty"]["counts"].get("not_checked", 0),
        "qualification_not_checked": components["qualification"]["counts"].get("not_checked", 0),
        "thermal_uncertainty_not_checked": components["thermal_uncertainty"]["counts"].get(
            "not_checked", 0
        ),
        "psychrometric_uncertainty_missing_provenance": components[
            "psychrometric_uncertainty"
        ].get("missing_provenance_analyses", 0),
        "fan_system_uncertainty_missing_provenance": components[
            "fan_system_uncertainty"
        ].get("missing_provenance_analyses", 0),
        "fan_loop_uncertainty_missing_provenance": components[
            "fan_loop_uncertainty"
        ].get("missing_provenance_analyses", 0),
        "fan_variable_friction_uncertainty_missing_provenance": components[
            "fan_variable_friction_uncertainty"
        ].get("missing_provenance_analyses", 0),
        "cross_module_consistency_not_comparable": (
            1
            if components["cross_module_consistency"]["status"] == "not_comparable"
            else 0
        ),
        "hvac_fan_operating_airflow_unresolved": (
            components["hvac_fan_operating_airflow_consistency"][
                "unresolved_study_count"
            ]
            if components["hvac_fan_operating_airflow_consistency"]["status"]
            in {"not_comparable", "pass_with_unresolved_studies"}
            else 0
        ),
    }

    adverse_count = sum(adverse.values())
    unresolved_count = sum(unresolved.values())
    if adverse_count:
        state = "attention_required"
    elif unresolved_count:
        state = "complete_with_unchecked"
    else:
        state = "no_adverse_findings"

    return {
        "state": state,
        "components": components,
        "adverse_items": adverse,
        "adverse_item_count": adverse_count,
        "unresolved_items": unresolved,
        "unresolved_item_count": unresolved_count,
        "scope_note": (
            "The dossier state is a workflow summary of configured CleanroomX checks "
            "and bounded engineering studies. It is not cleanroom certification, "
            "regulatory approval, equipment selection, or a substitute for the "
            "applicable qualification protocol and engineering review."
        ),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_record(kind: str, supplied_path: str, manifest_dir: Path) -> dict:
    path = (manifest_dir / supplied_path).resolve()
    if not path.is_file():
        raise ValueError(f"{kind} source file does not exist: {supplied_path}")
    return {
        "kind": kind,
        "path": supplied_path,
        "sha256": _sha256(path),
        "_resolved_path": path,
    }


def _clean_source(record: dict) -> dict:
    return {key: value for key, value in record.items() if not key.startswith("_")}


def build_dossier(manifest_path: str | Path) -> dict:
    manifest_path = Path(manifest_path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    return _build_dossier_from_dict(data, manifest_path.resolve().parent)


def _build_dossier_from_dict(data: dict, manifest_dir: str | Path) -> dict:
    from .consistency import (
        analyze_hvac_fan_airflow_consistency,
        analyze_project_consistency,
    )
    from .fan_curve import solve_fan_operating_point
    from .fan_curve_io import load_fan_operating_point_study
    from .fan_duct_network import analyze_fan_duct_network
    from .fan_uncertainty import analyze_fan_system_uncertainty
    from .fan_uncertainty_io import load_fan_system_uncertainty
    from .fan_duct_network_io import load_fan_duct_network_study
    from .fan_network import solve_fan_driven_parallel_network
    from .fan_network_io import load_fan_driven_parallel_network_study
    from .fan_loop_network import solve_fan_loop_network
    from .fan_loop_network_io import load_fan_loop_network_study
    from .fan_loop_uncertainty import analyze_fan_loop_network_uncertainty
    from .fan_loop_uncertainty_io import load_fan_loop_network_uncertainty
    from .fan_loop_speed import analyze_fan_loop_speed_study
    from .fan_loop_speed_io import load_fan_loop_speed_study
    from .fan_variable_friction_loop import solve_fan_variable_friction_loop
    from .fan_variable_friction_loop_io import (
        load_fan_variable_friction_loop_study,
    )
    from .fan_variable_friction_speed import (
        analyze_fan_variable_friction_speed_study,
    )
    from .fan_variable_friction_speed_io import (
        load_fan_variable_friction_speed_study,
    )
    from .fan_variable_friction_uncertainty import (
        analyze_fan_variable_friction_loop_uncertainty,
    )
    from .fan_variable_friction_uncertainty_io import (
        load_fan_variable_friction_loop_uncertainty,
    )
    from .damper_study import solve_loop_damper_study
    from .damper_study_io import load_loop_damper_study
    from .fan_speed import analyze_fan_speed_study
    from .fan_speed_io import load_fan_speed_study
    from .hvac import analyze_hvac_project
    from .hvac_io import load_hvac_project
    from .io import load_project
    from .project_verification import verify_project
    from .qualification import analyze_qualification_uncertainty
    from .qualification_io import load_qualification_uncertainty
    from .psychrometric_uncertainty import analyze_psychrometric_uncertainty
    from .psychrometric_uncertainty_io import load_psychrometric_uncertainty
    from .recovery_io import load_recovery_test
    from .recovery_test import analyze_recovery_test
    from .thermal_uncertainty import analyze_thermal_uncertainty
    from .thermal_uncertainty_io import load_thermal_uncertainty
    from .uncertainty import analyze_room_uncertainty
    from .uncertainty_io import load_uncertain_room

    if not isinstance(data, dict):
        raise ValueError("dossier manifest must contain a JSON object")
    manifest_dir = Path(manifest_dir).resolve()
    name = str(data.get("name", "")).strip()
    if not name:
        raise ValueError("dossier name cannot be empty")

    source_records: list[dict] = []

    verification = None
    verification_project = None
    verification_path = data.get("verification_project")
    if verification_path is not None:
        source = _source_record("verification_project", verification_path, manifest_dir)
        source_records.append(source)
        verification_project = load_project(source["_resolved_path"])
        verification = verify_project(verification_project).to_dict()

    hvac = None
    hvac_project = None
    hvac_path = data.get("hvac_project")
    if hvac_path is not None:
        source = _source_record("hvac_project", hvac_path, manifest_dir)
        source_records.append(source)
        hvac_project = load_hvac_project(source["_resolved_path"])
        hvac = analyze_hvac_project(hvac_project)

    recovery: list[dict] = []
    for item in data.get("recovery_tests", []):
        source = _source_record("recovery_test", item, manifest_dir)
        source_records.append(source)
        recovery.append(analyze_recovery_test(load_recovery_test(source["_resolved_path"])))

    qualification: list[dict] = []
    for item in data.get("qualification_analyses", []):
        source = _source_record("qualification_analysis", item, manifest_dir)
        source_records.append(source)
        qualification.append(
            analyze_qualification_uncertainty(
                load_qualification_uncertainty(source["_resolved_path"])
            )
        )

    uncertainty: list[dict] = []
    for item in data.get("uncertainty_rooms", []):
        source = _source_record("uncertainty_room", item, manifest_dir)
        source_records.append(source)
        uncertainty.append(
            analyze_room_uncertainty(load_uncertain_room(source["_resolved_path"]))
        )

    thermal_uncertainty: list[dict] = []
    for item in data.get("thermal_uncertainty_analyses", []):
        source = _source_record("thermal_uncertainty_analysis", item, manifest_dir)
        source_records.append(source)
        thermal_uncertainty.append(
            analyze_thermal_uncertainty(load_thermal_uncertainty(source["_resolved_path"]))
        )

    psychrometric_uncertainty: list[dict] = []
    for item in data.get("psychrometric_uncertainty_analyses", []):
        source = _source_record(
            "psychrometric_uncertainty_analysis", item, manifest_dir
        )
        source_records.append(source)
        psychrometric_uncertainty.append(
            analyze_psychrometric_uncertainty(
                load_psychrometric_uncertainty(source["_resolved_path"])
            )
        )

    fan_operating_points: list[dict] = []
    for item in data.get("fan_operating_point_studies", []):
        source = _source_record("fan_operating_point_study", item, manifest_dir)
        source_records.append(source)
        fan_operating_points.append(
            solve_fan_operating_point(
                load_fan_operating_point_study(source["_resolved_path"])
            )
        )

    fan_system_uncertainty: list[dict] = []
    for item in data.get("fan_system_uncertainty_analyses", []):
        source = _source_record(
            "fan_system_uncertainty_analysis", item, manifest_dir
        )
        source_records.append(source)
        fan_system_uncertainty.append(
            analyze_fan_system_uncertainty(
                load_fan_system_uncertainty(source["_resolved_path"])
            )
        )

    fan_duct_networks: list[dict] = []
    for item in data.get("fan_duct_network_studies", []):
        source = _source_record("fan_duct_network_study", item, manifest_dir)
        source_records.append(source)
        fan_duct_networks.append(
            analyze_fan_duct_network(
                load_fan_duct_network_study(source["_resolved_path"])
            )
        )

    fan_parallel_networks: list[dict] = []
    for item in data.get("fan_parallel_network_studies", []):
        source = _source_record("fan_parallel_network_study", item, manifest_dir)
        source_records.append(source)
        fan_parallel_networks.append(
            solve_fan_driven_parallel_network(
                load_fan_driven_parallel_network_study(source["_resolved_path"])
            )
        )

    fan_loop_networks: list[dict] = []
    for item in data.get("fan_loop_network_studies", []):
        source = _source_record("fan_loop_network_study", item, manifest_dir)
        source_records.append(source)
        fan_loop_networks.append(
            solve_fan_loop_network(load_fan_loop_network_study(source["_resolved_path"]))
        )

    fan_loop_uncertainty: list[dict] = []
    for item in data.get("fan_loop_uncertainty_analyses", []):
        source = _source_record(
            "fan_loop_uncertainty_analysis", item, manifest_dir
        )
        source_records.append(source)
        fan_loop_uncertainty.append(
            analyze_fan_loop_network_uncertainty(
                load_fan_loop_network_uncertainty(source["_resolved_path"])
            )
        )

    fan_loop_speed_studies: list[dict] = []
    for item in data.get("fan_loop_speed_studies", []):
        source = _source_record("fan_loop_speed_study", item, manifest_dir)
        source_records.append(source)
        fan_loop_speed_studies.append(
            analyze_fan_loop_speed_study(
                load_fan_loop_speed_study(source["_resolved_path"])
            )
        )

    fan_variable_friction_loops: list[dict] = []
    for item in data.get("fan_variable_friction_loop_studies", []):
        source = _source_record(
            "fan_variable_friction_loop_study", item, manifest_dir
        )
        source_records.append(source)
        fan_variable_friction_loops.append(
            solve_fan_variable_friction_loop(
                load_fan_variable_friction_loop_study(
                    source["_resolved_path"]
                )
            )
        )

    fan_variable_friction_speed_studies: list[dict] = []
    for item in data.get("fan_variable_friction_speed_studies", []):
        source = _source_record(
            "fan_variable_friction_speed_study", item, manifest_dir
        )
        source_records.append(source)
        fan_variable_friction_speed_studies.append(
            analyze_fan_variable_friction_speed_study(
                load_fan_variable_friction_speed_study(
                    source["_resolved_path"]
                )
            )
        )

    fan_variable_friction_uncertainty: list[dict] = []
    for item in data.get(
        "fan_variable_friction_uncertainty_analyses", []
    ):
        source = _source_record(
            "fan_variable_friction_uncertainty_analysis",
            item,
            manifest_dir,
        )
        source_records.append(source)
        fan_variable_friction_uncertainty.append(
            analyze_fan_variable_friction_loop_uncertainty(
                load_fan_variable_friction_loop_uncertainty(
                    source["_resolved_path"]
                )
            )
        )

    damper_studies: list[dict] = []
    for item in data.get("damper_studies", []):
        source = _source_record("damper_study", item, manifest_dir)
        source_records.append(source)
        damper_studies.append(
            solve_loop_damper_study(load_loop_damper_study(source["_resolved_path"]))
        )

    fan_speed_studies: list[dict] = []
    for item in data.get("fan_speed_studies", []):
        source = _source_record("fan_speed_study", item, manifest_dir)
        source_records.append(source)
        fan_speed_studies.append(
            analyze_fan_speed_study(
                load_fan_speed_study(source["_resolved_path"])
            )
        )

    if not source_records:
        raise ValueError("dossier must reference at least one analysis input file")

    consistency = None
    consistency_block = data.get("consistency_checks", {})
    if not isinstance(consistency_block, dict):
        raise ValueError("consistency_checks must be an object when provided")
    consistency_config = consistency_block.get("verification_hvac_airflow")
    if consistency_config is not None:
        if not isinstance(consistency_config, dict):
            raise ValueError(
                "verification_hvac_airflow consistency configuration must be an object"
            )
        if verification_project is None or hvac_project is None:
            raise ValueError(
                "verification_hvac_airflow consistency requires both "
                "verification_project and hvac_project"
            )
        allowed_keys = {
            "room_airflow_abs_tolerance_m3_h",
            "require_same_room_set",
        }
        unknown_keys = set(consistency_config) - allowed_keys
        if unknown_keys:
            raise ValueError(
                "unsupported verification_hvac_airflow option(s): "
                + ", ".join(sorted(unknown_keys))
            )
        consistency = analyze_project_consistency(
            verification_project,
            hvac_project,
            room_airflow_abs_tolerance_m3_h=consistency_config.get(
                "room_airflow_abs_tolerance_m3_h", 0.0
            ),
            require_same_room_set=consistency_config.get(
                "require_same_room_set", False
            ),
        )

    fan_airflow_consistency = None
    fan_airflow_config = consistency_block.get("hvac_fan_operating_airflow")
    if fan_airflow_config is not None:
        if not isinstance(fan_airflow_config, dict):
            raise ValueError(
                "hvac_fan_operating_airflow consistency configuration must be an object"
            )
        if hvac is None:
            raise ValueError(
                "hvac_fan_operating_airflow consistency requires hvac_project"
            )
        if not (
            fan_operating_points
            or fan_duct_networks
            or fan_parallel_networks
            or fan_loop_networks
            or fan_speed_studies
            or fan_loop_speed_studies
            or fan_variable_friction_loops
            or fan_variable_friction_speed_studies
            or fan_variable_friction_uncertainty
        ):
            raise ValueError(
                "hvac_fan_operating_airflow consistency requires at least one "
                "fan operating-point or fan-speed study"
            )
        allowed_keys = {"airflow_abs_tolerance_m3_h"}
        unknown_keys = set(fan_airflow_config) - allowed_keys
        if unknown_keys:
            raise ValueError(
                "unsupported hvac_fan_operating_airflow option(s): "
                + ", ".join(sorted(unknown_keys))
            )
        fan_airflow_consistency = analyze_hvac_fan_airflow_consistency(
            hvac,
            fan_operating_points=fan_operating_points,
            fan_duct_networks=fan_duct_networks,
            fan_parallel_networks=fan_parallel_networks,
            fan_loop_networks=fan_loop_networks,
            fan_speed_studies=fan_speed_studies,
            fan_loop_speed_studies=fan_loop_speed_studies,
            fan_variable_friction_loops=fan_variable_friction_loops,
            fan_variable_friction_speed_studies=(
                fan_variable_friction_speed_studies
            ),
            fan_variable_friction_uncertainty_analyses=(
                fan_variable_friction_uncertainty
            ),
            airflow_abs_tolerance_m3_h=fan_airflow_config.get(
                "airflow_abs_tolerance_m3_h", 0.0
            ),
        )

    summary = summarize_dossier_components(
        verification=verification,
        hvac=hvac,
        recovery=recovery,
        uncertainty=uncertainty,
        qualification=qualification,
        thermal_uncertainty=thermal_uncertainty,
        psychrometric_uncertainty=psychrometric_uncertainty,
        fan_operating_points=fan_operating_points,
        fan_system_uncertainty=fan_system_uncertainty,
        fan_duct_networks=fan_duct_networks,
        fan_parallel_networks=fan_parallel_networks,
        fan_loop_networks=fan_loop_networks,
        fan_loop_uncertainty=fan_loop_uncertainty,
        damper_studies=damper_studies,
        fan_speed_studies=fan_speed_studies,
        fan_loop_speed_studies=fan_loop_speed_studies,
        fan_variable_friction_loops=fan_variable_friction_loops,
        fan_variable_friction_speed_studies=(
            fan_variable_friction_speed_studies
        ),
        fan_variable_friction_uncertainty=(
            fan_variable_friction_uncertainty
        ),
        consistency=consistency,
        fan_airflow_consistency=fan_airflow_consistency,
    )
    return {
        "dossier": name,
        "metadata": {
            "project_reference": data.get("project_reference"),
            "revision": data.get("revision"),
            "prepared_by": data.get("prepared_by"),
            "notes": data.get("notes"),
        },
        "executive_summary": summary,
        "source_files": [_clean_source(item) for item in source_records],
        "verification": verification,
        "hvac": hvac,
        "recovery_tests": recovery,
        "qualification_analyses": qualification,
        "uncertainty_rooms": uncertainty,
        "thermal_uncertainty_analyses": thermal_uncertainty,
        "psychrometric_uncertainty_analyses": psychrometric_uncertainty,
        "fan_operating_point_studies": fan_operating_points,
        "fan_system_uncertainty_analyses": fan_system_uncertainty,
        "fan_duct_network_studies": fan_duct_networks,
        "fan_parallel_network_studies": fan_parallel_networks,
        "fan_loop_network_studies": fan_loop_networks,
        "fan_loop_uncertainty_analyses": fan_loop_uncertainty,
        "damper_studies": damper_studies,
        "fan_speed_studies": fan_speed_studies,
        "fan_loop_speed_studies": fan_loop_speed_studies,
        "fan_variable_friction_loop_studies": (
            fan_variable_friction_loops
        ),
        "fan_variable_friction_speed_studies": (
            fan_variable_friction_speed_studies
        ),
        "fan_variable_friction_uncertainty_analyses": (
            fan_variable_friction_uncertainty
        ),
        "consistency_checks": {
            "verification_hvac_airflow": consistency,
            "hvac_fan_operating_airflow": fan_airflow_consistency,
        },
    }
