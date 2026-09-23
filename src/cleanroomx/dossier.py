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


def _verification_summary(result: dict | None) -> dict:
    if result is None:
        return {"status": "not_included", "counts": {}}

    statuses: list[str] = []
    for room in result.get("rooms", []):
        statuses.extend(item["status"] for item in room.get("findings", []))
    statuses.extend(item["status"] for item in result.get("pressure_cascade", []))
    counts = _count_statuses(statuses)
    if counts.get("fail", 0):
        status = "fail"
    elif counts.get("pass", 0) and counts.get("not_checked", 0):
        status = "pass_with_unchecked"
    elif counts.get("pass", 0):
        status = "pass"
    else:
        status = "not_checked"
    return {"status": status, "counts": counts}


def _hvac_summary(result: dict | None) -> dict:
    if result is None:
        return {"status": "not_included", "failed_air_balances": 0}
    rooms = result.get("rooms", [])
    failed = sum(
        not room.get("air_balance", {}).get("passes_minimum_surplus", False)
        for room in rooms
    )
    return {
        "status": "fail" if failed else "screening_complete",
        "failed_air_balances": failed,
        "room_count": len(rooms),
    }


def _recovery_summary(results: list[dict]) -> dict:
    if not results:
        return {"status": "not_included", "counts": {}}
    counts = _count_statuses(item["criterion_status"] for item in results)
    if counts.get("fail", 0):
        status = "fail"
    elif counts.get("incomplete", 0):
        status = "incomplete"
    elif counts.get("pass", 0) and counts.get("not_checked", 0):
        status = "pass_with_unchecked"
    elif counts.get("pass", 0):
        status = "pass"
    else:
        status = "not_checked"
    return {"status": status, "counts": counts, "test_count": len(results)}


def _qualification_summary(results: list[dict]) -> dict:
    if not results:
        return {"status": "not_included", "counts": {}}
    counts = _count_statuses(item["overall_status"] for item in results)
    if counts.get("fail", 0):
        status = "fail"
    elif counts.get("indeterminate", 0):
        status = "indeterminate"
    else:
        status = "pass"
    return {"status": status, "counts": counts, "analysis_count": len(results)}


def _uncertainty_summary(results: list[dict]) -> dict:
    if not results:
        return {"status": "not_included", "counts": {}}
    counts = _count_statuses(item["requirement"]["status"] for item in results)
    if counts.get("fail", 0):
        status = "fail"
    elif counts.get("indeterminate", 0):
        status = "indeterminate"
    elif counts.get("pass", 0) and counts.get("not_checked", 0):
        status = "pass_with_unchecked"
    elif counts.get("pass", 0):
        status = "pass"
    else:
        status = "not_checked"
    return {"status": status, "counts": counts, "room_count": len(results)}


def summarize_dossier_components(
    verification: dict | None,
    hvac: dict | None,
    recovery: list[dict],
    uncertainty: list[dict],
    qualification: list[dict] | None = None,
) -> dict:
    components = {
        "verification": _verification_summary(verification),
        "hvac": _hvac_summary(hvac),
        "recovery": _recovery_summary(recovery),
        "uncertainty": _uncertainty_summary(uncertainty),
        "qualification": _qualification_summary(qualification or []),
    }

    adverse = {
        "verification_failures": components["verification"]["counts"].get("fail", 0),
        "hvac_air_balance_failures": components["hvac"].get("failed_air_balances", 0),
        "recovery_failures": components["recovery"]["counts"].get("fail", 0),
        "recovery_incomplete": components["recovery"]["counts"].get("incomplete", 0),
        "uncertainty_failures": components["uncertainty"]["counts"].get("fail", 0),
        "uncertainty_indeterminate": components["uncertainty"]["counts"].get(
            "indeterminate", 0
        ),
        "qualification_failures": components["qualification"]["counts"].get("fail", 0),
        "qualification_indeterminate": components["qualification"]["counts"].get(
            "indeterminate", 0
        ),
    }
    unresolved = {
        "verification_not_checked": components["verification"]["counts"].get(
            "not_checked", 0
        ),
        "recovery_not_checked": components["recovery"]["counts"].get(
            "not_checked", 0
        ),
        "uncertainty_not_checked": components["uncertainty"]["counts"].get(
            "not_checked", 0
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
            "The dossier state is a workflow summary of configured CleanroomX checks. "
            "It is not cleanroom certification, regulatory approval, or a substitute "
            "for the applicable qualification protocol and engineering review."
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
    from .hvac import analyze_hvac_project
    from .hvac_io import load_hvac_project
    from .io import load_project
    from .project_verification import verify_project
    from .qualification import analyze_qualification_uncertainty
    from .qualification_io import load_qualification_uncertainty
    from .recovery_io import load_recovery_test
    from .recovery_test import analyze_recovery_test
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

    if not source_records:
        raise ValueError("dossier must reference at least one analysis input file")

    summary = summarize_dossier_components(
        verification, hvac, recovery, uncertainty, qualification
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
    }
