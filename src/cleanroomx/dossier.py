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


def _consistency_summary(result: dict | None) -> dict:
    if result is None or result.get("status") == "not_configured":
        return {
            "status": "not_configured",
            "comparison_count": 0,
            "failed_comparisons": 0,
            "required_unmapped_rooms": 0,
            "issue_count": 0,
        }
    required_unmapped = len(
        result.get("required_unmapped_verification_rooms", [])
    ) + len(result.get("required_unmapped_hvac_rooms", []))
    return {
        "status": result["status"],
        "comparison_count": len(result.get("comparisons", [])),
        "failed_comparisons": result.get("failed_comparison_count", 0),
        "required_unmapped_rooms": required_unmapped,
        "issue_count": result.get("issue_count", 0),
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
    consistency: dict | None = None,
) -> dict:
    recovery = recovery or []
    uncertainty = uncertainty or []
    qualification = qualification or []
    thermal_uncertainty = thermal_uncertainty or []
    psychrometric_uncertainty = psychrometric_uncertainty or []
    fan_operating_points = fan_operating_points or []

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
        "cross_module_consistency": _consistency_summary(consistency),
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
        "cross_module_consistency_issues": components[
            "cross_module_consistency"
        ].get("issue_count", 0),
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
        "cross_module_consistency_not_checked": (
            1
            if components["cross_module_consistency"]["status"] == "not_checked"
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
    from .consistency import check_verification_hvac_airflow_consistency
    from .fan_curve import solve_fan_operating_point
    from .fan_curve_io import load_fan_operating_point_study
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

    manifest_path = Path(manifest_path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    name = str(data.get("name", "")).strip()
    if not name:
        raise ValueError("dossier name cannot be empty")

    manifest_dir = manifest_path.resolve().parent
    source_records: list[dict] = []

    verification = None
    verification_path = data.get("verification_project")
    if verification_path is not None:
        source = _source_record("verification_project", verification_path, manifest_dir)
        source_records.append(source)
        verification = verify_project(load_project(source["_resolved_path"])).to_dict()

    hvac = None
    hvac_path = data.get("hvac_project")
    if hvac_path is not None:
        source = _source_record("hvac_project", hvac_path, manifest_dir)
        source_records.append(source)
        hvac = analyze_hvac_project(load_hvac_project(source["_resolved_path"]))

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

    if not source_records:
        raise ValueError("dossier must reference at least one analysis input file")

    consistency_block = data.get("consistency_checks", {})
    if not isinstance(consistency_block, dict):
        raise ValueError("consistency_checks must be an object when provided")
    consistency = check_verification_hvac_airflow_consistency(
        verification,
        hvac,
        consistency_block.get("verification_hvac_airflow"),
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
        consistency=consistency,
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
        "consistency_checks": {
            "verification_hvac_airflow": consistency,
        },
    }
