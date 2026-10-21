"""Revision-checked, non-executing handoff from AI Assistant to CFD workspace.

Approval only opens CleanroomX's existing CFD workspace. The solver requires
a separate human operation and its original input/runtime verification.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from .ai_assistant import project_snapshot_sha256
from .cfd_multizone import verify_multizone_inputs
from .project import (
    ProjectDocument, capture_project_file_revision,
    load_project_document_with_revision, project_file_revision_matches,
)
from .strict_json import load_strict_json_snapshot

SCHEMA = "cleanroomx.ai-cfd-run-handoff"
VERSION = 1
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_SOLVER_STAGES = ("blockMesh", "checkMesh", "simpleFoam", "postProcess")


def _digest(value: dict[str, Any]) -> str:
    return sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _require_hash(value: Any, label: str) -> str:
    if type(value) is not str or _HASH.fullmatch(value) is None:
        raise ValueError(label + " must be a SHA-256 digest")
    return value


def _ensure_unexecuted_case(root: Path) -> None:
    """Never reuse an already executed case, including a partial/failed one."""
    if any((root / name).exists() or (root / name).is_symlink()
           for name in ("run-receipt.json", "execution-receipt.json")):
        raise ValueError("CFD case already has an execution receipt")
    for stage in _SOLVER_STAGES:
        if any((root / (stage + suffix)).exists()
               or (root / (stage + suffix)).is_symlink()
               for suffix in (".log", ".log.gz")):
            raise ValueError("CFD case has prior solver logs; create a fresh case")
    for child in root.iterdir():
        if (child.is_dir() or child.is_symlink()) and re.fullmatch(
            r"[0-9]+(?:\.[0-9]+)?", child.name
        ) and float(child.name) > 0:
            raise ValueError("CFD case has prior computed time directories")


def prepare_cfd_run_handoff(
    case_directory: str | Path, *,
    project: ProjectDocument, project_path: str | Path,
) -> dict[str, Any]:
    """Bind the existing open-door generated case to an exact saved project.

    This only checks existing inputs and returns a local, read-only preview.
    It does not approve or execute a simulation, or write an approval token.
    """
    if not isinstance(project, ProjectDocument):
        raise TypeError("An in-memory CleanroomX ProjectDocument is required")
    saved_path = Path(project_path).expanduser()
    if saved_path.is_symlink():
        raise ValueError("Saved project must not be a symlink")
    saved_path = saved_path.resolve(strict=True)
    saved_project, before = load_project_document_with_revision(saved_path)
    if not before.exists or not before.sha256:
        raise ValueError("A saved project revision is required")
    if project_snapshot_sha256(project) != project_snapshot_sha256(saved_project):
        raise ValueError("Save current project edits before preparing CFD handoff")

    candidate = Path(case_directory).expanduser()
    if candidate.is_symlink() or not candidate.is_dir():
        raise ValueError("CFD case must be a regular directory, not a symlink")
    # Existing canonical gate verifies the manifest's eight solver input hashes.
    root, manifest = verify_multizone_inputs(candidate)
    snapshot = load_strict_json_snapshot(root / "manifest.json", max_bytes=4 * 1024 * 1024)
    if type(snapshot.value) is not dict or snapshot.value != manifest:
        raise ValueError("CFD case manifest changed during handoff preparation")
    case_source = _require_hash(manifest.get("project_source_sha256"), "Case project source")
    if case_source != before.sha256:
        raise ValueError("CFD case belongs to a different saved project revision")
    _ensure_unexecuted_case(root)

    # Recheck both sources after the inventory walk; the existing solver
    # runner independently checks its inputs again on actual execution.
    current_root, current_manifest = verify_multizone_inputs(root)
    latest = load_strict_json_snapshot(root / "manifest.json", max_bytes=4 * 1024 * 1024)
    if (current_root != root or current_manifest != manifest
            or latest.raw_bytes != snapshot.raw_bytes):
        raise ValueError("CFD case changed during handoff preparation")
    after = capture_project_file_revision(saved_path)
    if not project_file_revision_matches(before, after):
        raise ValueError("Saved project changed during CFD handoff preparation")

    plan = {
        "schema": SCHEMA,
        "schema_version": VERSION,
        "case_directory": str(root),
        "project_source_sha256": before.sha256,
        "project_snapshot_sha256": project_snapshot_sha256(project),
        "case_manifest_sha256": sha256(snapshot.raw_bytes).hexdigest(),
        "scenario": "all_doors_open",
        "execution_mode": "open_existing_cfd_workspace_only",
        "state": "proposal_not_executed",
        "requires_explicit_user_confirmation": True,
        "solver_executed": False,
        "engineering_release": "HOLD",
        "closed_door_5pa_demonstrated": False,
        "limitations": [
            "Handoff does not run OpenFOAM or change the saved project or case.",
            "The target workspace requires a separate explicit Run action.",
            "Manifest hash integrity does not authenticate external authorship.",
            "The open-door case does not demonstrate a closed-door 5 Pa cascade.",
        ],
    }
    plan["handoff_sha256"] = _digest(plan)
    return plan


def verify_cfd_run_handoff(plan: dict[str, Any]) -> bool:
    """Validate a preview's integrity; this is not authorization to execute."""
    if type(plan) is not dict or plan.get("schema") != SCHEMA:
        return False
    if type(plan.get("schema_version")) is not int or plan["schema_version"] != VERSION:
        return False
    if (plan.get("state") != "proposal_not_executed"
            or plan.get("requires_explicit_user_confirmation") is not True
            or plan.get("solver_executed") is not False
            or plan.get("engineering_release") != "HOLD"
            or plan.get("closed_door_5pa_demonstrated") is not False
            or plan.get("execution_mode") != "open_existing_cfd_workspace_only"):
        return False
    try:
        for field in (
            "handoff_sha256", "case_manifest_sha256", "project_source_sha256",
            "project_snapshot_sha256",
        ):
            _require_hash(plan.get(field), field)
        if type(plan.get("case_directory")) is not str or not plan["case_directory"]:
            return False
        return _digest({k: v for k, v in plan.items() if k != "handoff_sha256"}) == plan["handoff_sha256"]
    except (TypeError, ValueError, KeyError, OverflowError):
        return False


def revalidate_cfd_run_handoff(
    plan: dict[str, Any], *,
    project: ProjectDocument, project_path: str | Path,
) -> Path:
    """Recheck the exact intended case at the final human-confirmation step."""
    if not verify_cfd_run_handoff(plan):
        raise ValueError("CFD handoff preview is invalid or has changed")
    fresh = prepare_cfd_run_handoff(
        plan["case_directory"], project=project, project_path=project_path,
    )
    if fresh["handoff_sha256"] != plan["handoff_sha256"]:
        raise ValueError("CFD project or case changed since the handoff preview")
    return Path(fresh["case_directory"])


def render_cfd_run_handoff(plan: dict[str, Any]) -> str:
    if not verify_cfd_run_handoff(plan):
        raise ValueError("Invalid CFD handoff preview")
    return (
        "GENERATED CFD CASE HANDOFF — NOT EXECUTED\n"
        "Case: " + plan["case_directory"] + "\n"
        "Saved project SHA-256: " + plan["project_source_sha256"][:12] + "\n"
        "Case manifest SHA-256: " + plan["case_manifest_sha256"][:12] + "\n"
        "Scenario: all doors OPEN, not closed-door pressure control\n"
        "Next step: with explicit confirmation, open the existing CFD workspace.\n"
        "No solver run will begin from the AI Assistant. In the CFD workspace, "
        "a separate Run action invokes the canonical OpenFOAM pipeline.\n"
        "Engineering release: HOLD; physical validation not established."
    )
