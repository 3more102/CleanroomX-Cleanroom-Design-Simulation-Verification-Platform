"""Verify recorded nine-case CFD execution evidence without running OpenFOAM.

This is an integrity *screen*, not an authenticity guarantee, a convergence
assessment, measured-cleanroom validation, or a certification decision.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re

from .cfd_grid_runner import (
    INPUTS, RUN_SCHEMA, STAGES, VERSION_PATTERN, _MeshTreeScanBudget, _cases,
    _hash, _mesh_file_hashes, _verify_generated_inputs,
    _verify_runtime_source_tree,
)
from .strict_json import load_strict_json_snapshot

VERIFY_SCHEMA = "cleanroomx.cfd-grid-run-verification.v1"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _file_digest(path: Path) -> str:
    """Stream and validate one stable evidence-file revision."""
    return _hash(path)


def verify_grid_run_evidence(
    directory: str | Path, *,
    scan_budget: _MeshTreeScanBudget | None = None,
) -> dict:
    """Compare the existing receipt with current source files and stage logs.

    A success means only that the source and stage-log bytes match their
    recorded digests and that the receipt's internal state is consistent.
    The receipt is unsigned and the external executables are not attested.
    """
    supplied_root = Path(directory)
    if supplied_root.is_symlink():
        raise ValueError("Grid family root must not be a symlink")
    root = supplied_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Grid family root must be a directory")
    if scan_budget is None:
        scan_budget = _MeshTreeScanBudget()

    findings: list[str] = []
    result = {
        "schema_version": VERIFY_SCHEMA,
        "status": "evidence_integrity_failed",
        "engineering_review": "BLOCKED",
        "physical_validation": "not_performed",
        "findings": findings,
        "cases_checked": 0,
        "logs_checked": 0,
        "warning": (
            "Matching digests cannot prove independent runs, solver correctness, "
            "mesh convergence, physical validation, or certification"
        ),
    }

    if (root / "manifest.json").is_symlink():
        findings.append("source_manifest_is_symlink")
    for configuration in (1, 2, 3):
        configuration_dir = root / f"configuration_{configuration}"
        if configuration_dir.is_symlink():
            findings.append(f"source_configuration_is_symlink:configuration_{configuration}")

    # The runner reserves this namespace exactly once, before its first stage.
    # The marker persists after both successful and interrupted execution.
    # Its absence or substitution breaks the local execution custody record,
    # even when receipt/log digests still match. It is not authentication.
    reservation = root / ".grid_run_reserved"
    if reservation.is_symlink() or not reservation.is_dir():
        findings.append("missing_or_unsafe_execution_reservation")
    else:
        try:
            if any(reservation.iterdir()):
                findings.append("execution_reservation_not_empty")
        except OSError:
            findings.append("execution_reservation_unreadable")

    staging_receipt = root / ".grid_run_evidence.json.tmp"
    if staging_receipt.exists() or staging_receipt.is_symlink():
        findings.append("uncommitted_receipt_staging_present")

    receipt_path = root / "grid_run_evidence.json"
    if receipt_path.is_symlink():
        findings.append("receipt_is_symlink")
        return result
    try:
        if receipt_path.stat().st_nlink != 1:
            findings.append("receipt_is_hardlinked")
        receipt = load_strict_json_snapshot(
            receipt_path, max_bytes=2_000_000
        ).value
    except (OSError, ValueError, UnicodeError) as exc:
        findings.append("unreadable_or_invalid_receipt: " + type(exc).__name__)
        return result
    if type(receipt) is not dict or receipt.get("schema_version") != RUN_SCHEMA:
        findings.append("invalid_receipt_schema")
        return result
    # A v1 execution receipt must not smuggle an unreviewed validation or
    # certification claim through additional, unchecked fields.
    receipt_fields = {
        "schema_version", "source_manifest_sha256", "foam_version",
        "executables", "status", "engineering_review", "physical_validation",
        "cases", "warning",
    }
    if set(receipt) != receipt_fields:
        findings.append("unexpected_receipt_fields")
    if receipt.get("warning") != (
        "Solver execution is not residual convergence, mesh independence, "
        "physical validation or certification"
    ):
        findings.append("invalid_receipt_warning")

    try:
        current_manifest_sha = _verify_generated_inputs(root)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        current_manifest_sha = None
        findings.append("source_manifest_or_inputs_invalid: " + type(exc).__name__)
    # Compare checkMesh cell counts against the exact source manifest bytes.
    # This local integrity check is not authenticated execution provenance.
    expected_cells_by_case: dict[str, int] = {}
    if current_manifest_sha is not None:
        try:
            snapshot = load_strict_json_snapshot(
                root / "manifest.json", max_bytes=2_000_000
            )
            if ((root / "manifest.json").is_symlink()
                    or hashlib.sha256(snapshot.raw_bytes).hexdigest()
                    != current_manifest_sha):
                raise ValueError("Grid source manifest changed while checking cell totals")
            expected_cells_by_case = {
                key: snapshot.value["case_inputs"][key]["mesh_cells"]
                for key in _cases()
            }
        except (OSError, ValueError, TypeError, KeyError):
            findings.append("source_manifest_mesh_counts_unavailable")
    # A source symlink can be introduced after execution without changing
    # bytes or SHA-256. Report this independently of digest equality.
    for key in _cases():
        case_dir = root / key
        if case_dir.is_symlink():
            findings.append(f"source_case_is_symlink:{key}")
        for folder in ("system", "constant", "0"):
            source_dir = case_dir / folder
            if source_dir.is_symlink():
                findings.append(f"source_directory_is_symlink:{key}/{folder}")
    for key in _cases():
        for filename in INPUTS:
            if (root / key / filename).is_symlink():
                findings.append(f"source_file_is_symlink:{key}/{filename}")
        try:
            _verify_runtime_source_tree(
                root / key, key, scan_budget=scan_budget,
            )
        except (OSError, ValueError) as exc:
            findings.append(f"unexpected_or_unsafe_source_tree:{key}:{type(exc).__name__}")

    recorded_sha = receipt.get("source_manifest_sha256")
    if (type(recorded_sha) is not str
            or not _SHA256.fullmatch(recorded_sha)
            or current_manifest_sha != recorded_sha):
        findings.append("source_manifest_digest_mismatch")

    if receipt.get("engineering_review") != "BLOCKED":
        findings.append("receipt_review_state_must_be_blocked")
    if receipt.get("physical_validation") != "not_performed":
        findings.append("receipt_physical_validation_must_be_unperformed")
    if (type(receipt.get("foam_version")) is not str
            or not VERSION_PATTERN.fullmatch(receipt["foam_version"])):
        findings.append("unexpected_openfoam_version")
    executables = receipt.get("executables")
    if (type(executables) is not dict
            or set(executables) != {"foamVersion", *STAGES}
            or any(type(path) is not str or not path
                   for path in executables.values())):
        findings.append("invalid_executable_provenance")

    cases = receipt.get("cases")
    expected_cases = set(_cases())
    if type(cases) is not dict or set(cases) != expected_cases:
        findings.append("invalid_case_set")
        return result

    all_complete = True
    # Identical solver logs across distinct grid levels cannot establish
    # independent mesh executions. This is a replay screen, not proof that
    # distinct logs came from distinct runs.
    solver_log_hashes: dict[str, str] = {}
    # A byte-identical *complete* generated mesh snapshot reused between
    # levels of one configuration cannot substantiate distinct refinement.
    # Do not compare across configurations: different boundary conditions
    # can legitimately share the same geometric mesh. Empty snapshots have
    # no mesh evidence to compare and are handled by scientific review.
    mesh_snapshots_by_configuration: dict[
        str, dict[tuple[tuple[str, str], ...], str]
    ] = {}
    # Cases execute in deterministic order. Once one is not_run or running,
    # no later case can have started; a crashed run has one active prefix.
    inactive_suffix = False
    for key in _cases():
        data = cases[key]
        if (type(data) is not dict
                or set(data) != {"status", "stages", "mesh_files"}
                or type(data["stages"]) is not list
                or len(data["stages"]) > len(STAGES)
                or type(data["mesh_files"]) is not dict
                or len(data["mesh_files"]) > 4096):
            findings.append(f"invalid_case_record:{key}")
            all_complete = False
            continue
        result["cases_checked"] += 1
        # v2 binds the actual final polyMesh file contents, not just link
        # safety. Without an immutable signed receipt, this remains a local
        # consistency screen and must not assert mesh independence.
        recorded_mesh = data["mesh_files"]
        if any(
            type(name) is not str or not name or name.startswith("/")
            or name in (".", "..") or ".." in name.split("/")
            or "\\" in name
            or type(digest) is not str or not _SHA256.fullmatch(digest)
            for name, digest in recorded_mesh.items()
        ):
            findings.append(f"invalid_mesh_manifest:{key}")
        else:
            try:
                current_mesh = _mesh_file_hashes(
                    root / key, key, scan_budget=scan_budget,
                )
            except (OSError, ValueError):
                findings.append(f"missing_or_unsafe_mesh_output:{key}")
            else:
                if current_mesh != recorded_mesh:
                    findings.append(f"mesh_output_digest_mismatch:{key}")
                elif current_mesh:
                    config = key.split("/", 1)[0]
                    fingerprint = tuple(sorted(current_mesh.items()))
                    snapshots = mesh_snapshots_by_configuration.setdefault(config, {})
                    previous = snapshots.get(fingerprint)
                    if previous is not None:
                        findings.append(
                            f"replayed_mesh_output_across_grids:{key}:{previous}"
                        )
                    else:
                        snapshots[fingerprint] = key
        if inactive_suffix and data["status"] != "not_run":
            findings.append(f"out_of_sequence_case_state:{key}")
        if data["status"] in ("running", "not_run"):
            inactive_suffix = True
        stages = data["stages"]
        # An abrupt stop can leave a solver log on disk before its digest
        # reaches the atomic JSON receipt. Never call such an incomplete
        # snapshot integrity-verified: the unrecorded bytes are untrusted.
        for unrecorded_stage in STAGES[len(stages):]:
            orphan = root / key / (unrecorded_stage + ".log")
            if orphan.exists() or orphan.is_symlink():
                findings.append(f"unreceipted_stage_log:{key}:{unrecorded_stage}")
        successful = True
        for index, stage in enumerate(stages):
            expected_command = STAGES[index]
            expected_log = f"{key}/{expected_command}.log"
            if (type(stage) is not dict
                    or set(stage) != {
                        "command", "returncode", "status", "log", "log_sha256"
                    }
                    or stage["command"] != expected_command
                    or stage["log"] != expected_log):
                findings.append(f"invalid_stage_record:{key}:{index}")
                successful = False
                continue
            code = stage["returncode"]
            state = stage["status"]
            valid_exit = (
                (state == "completed" and type(code) is int and code == 0)
                or (state == "failed" and type(code) is int and code != 0)
                or (state in ("timed_out", "launch_failed") and code is None)
                or (state == "empty_output" and type(code) is int and code == 0)
                or (state == "mesh_check_rejected" and expected_command == "checkMesh"
                    and type(code) is int and code == 0)
                or (state == "source_drift" and type(code) is int)
            )
            if not valid_exit:
                findings.append(f"invalid_stage_exit:{key}:{expected_command}")
            if state != "completed":
                successful = False
            if state == "source_drift":
                # This is a recorded violation of source custody, not
                # trustworthy execution evidence even if the input is later
                # put back to its original digest.
                findings.append(f"stage_source_drift_recorded:{key}:{expected_command}")

            recorded_log_sha = stage["log_sha256"]
            path = root / expected_log
            if (type(recorded_log_sha) is not str
                    or not _SHA256.fullmatch(recorded_log_sha)
                    or path.is_symlink()):
                findings.append(f"invalid_log_reference:{key}:{expected_command}")
                continue
            try:
                resolved = path.resolve(strict=True)
                if not resolved.is_relative_to(root) or not resolved.is_file():
                    raise ValueError("outside case family or not a regular file")
                if resolved.stat().st_nlink != 1:
                    findings.append(f"hardlinked_stage_log:{key}:{expected_command}")
                    continue
                actual_sha = _file_digest(resolved)
            except (OSError, ValueError):
                findings.append(f"missing_or_unsafe_log:{key}:{expected_command}")
                continue
            result["logs_checked"] += 1
            if actual_sha != recorded_log_sha:
                findings.append(f"log_digest_mismatch:{key}:{expected_command}")
            else:
                # Zero-byte logs cannot substantiate successful execution;
                # conversely empty_output must describe truly empty bytes.
                empty_log = actual_sha == hashlib.sha256(b"").hexdigest()
                if state == "completed" and empty_log:
                    findings.append(f"empty_completed_stage_log:{key}:{expected_command}")
                if state == "empty_output" and not empty_log:
                    findings.append(f"invalid_empty_output_stage_log:{key}:{expected_command}")
                if expected_command == "checkMesh" and state in (
                    "completed", "mesh_check_rejected"
                ):
                    declared_cells = expected_cells_by_case.get(key)
                    if declared_cells is None:
                        # An altered/missing source manifest is a finding,
                        # never an uncaught exception or green receipt.
                        findings.append(f"unavailable_checkmesh_declared_cells:{key}")
                    else:
                        from .cfd_checkmesh_log import screen_checkmesh_verdict
                        try:
                            screen_checkmesh_verdict(
                                resolved, expected_cells=declared_cells
                            )
                        except (OSError, ValueError):
                            if state == "completed":
                                findings.append(f"invalid_completed_checkmesh_verdict:{key}")
                        else:
                            if state == "mesh_check_rejected":
                                findings.append(f"unexpected_clean_rejected_checkmesh_verdict:{key}")
                if expected_command == "simpleFoam" and state == "completed":
                    previous_case = solver_log_hashes.get(actual_sha)
                    if previous_case is not None:
                        same_configuration = (
                            previous_case.split("/", 1)[0] == key.split("/", 1)[0]
                        )
                        replay_kind = (
                            "replayed_solver_log_across_grids"
                            if same_configuration
                            else "replayed_solver_log_across_configurations"
                        )
                        findings.append(f"{replay_kind}:{key}:{previous_case}")
                    else:
                        solver_log_hashes[actual_sha] = key

        complete = len(stages) == len(STAGES) and successful
        if complete:
            if data["status"] != "executed_requires_convergence_review":
                findings.append(f"wrong_completed_case_status:{key}")
        else:
            all_complete = False
            if data["status"] not in ("not_run", "running", "execution_failed"):
                findings.append(f"wrong_incomplete_case_status:{key}")
            if data["status"] == "not_run" and stages:
                findings.append(f"not_run_case_has_stages:{key}")
            if (data["status"] == "execution_failed"
                    and (not stages or type(stages[-1]) is not dict
                         or stages[-1].get("status") == "completed")):
                findings.append(f"failed_case_has_no_failed_stage:{key}")
            if any(stage.get("status") != "completed" for stage in stages[:-1]
                   if type(stage) is dict):
                findings.append(f"continued_after_failed_stage:{key}")

    required_status = (
        "executed_requires_convergence_review" if all_complete else "incomplete"
    )
    if receipt.get("status") != required_status:
        findings.append("receipt_overall_status_inconsistent")

    if not findings:
        result["status"] = (
            "execution_logs_integrity_verified_requires_scientific_review"
            if all_complete else "incomplete_execution_logs_integrity_verified"
        )
    return result
