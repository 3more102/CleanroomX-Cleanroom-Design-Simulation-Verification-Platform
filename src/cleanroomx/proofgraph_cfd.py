"""ProofGraph projection for external nine-case CFD evidence.

The adapter preserves local execution integrity and optional grid-screening
results while keeping numerical/physical engineering approval explicitly
blocked. Hash agreement is not solver authenticity or independent custody.
"""
from __future__ import annotations

import hashlib
import stat
from pathlib import Path
from typing import Iterable

from .cfd_grid_receipt import verify_grid_run_evidence
from .cfd_grid_study import analyze_vtk_grid_study, validate_grid_spec
from .proofgraph_models import (
    CalculationEvidence,
    ComplianceCheck,
    ComplianceFinding,
    ComplianceVerdict,
    EvidenceSource,
    ProofGraph,
    ProvenanceRecord,
    Requirement,
    RequirementSet,
    SimulationEvidence,
    VerificationRun,
    _canonical_sha256,
)
from .strict_json import load_strict_json_snapshot


_MAX_EVIDENCE_JSON_BYTES = 2_000_000
_RUN_REQUIREMENT = "cfd-nine-case-local-execution-integrity"
_PHYSICAL_REQUIREMENT = "cfd-independent-measured-correlation"
_GRID_REQUIREMENT_PREFIX = "cfd-grid-screening-configuration-"


def _read_snapshot(path: Path):
    """Read one small, regular, single-link JSON evidence file."""
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None, None
    if stat.S_ISLNK(metadata.st_mode):
        return None, "symlink"
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        return None, "not_regular_or_hardlinked"
    try:
        return load_strict_json_snapshot(path, max_bytes=_MAX_EVIDENCE_JSON_BYTES), None
    except (OSError, ValueError, UnicodeError) as exc:
        return None, type(exc).__name__


def _snapshot_digest(snapshot) -> str | None:
    if snapshot is None:
        return None
    return hashlib.sha256(snapshot.raw_bytes).hexdigest()


def _manifest_summary(value, digest: str) -> dict:
    manifest = value if type(value) is dict else {}
    files = manifest.get("files")
    cases = manifest.get("case_inputs")
    return {
        "raw_sha256": digest,
        "schema_version": manifest.get("schema_version")
        if type(manifest.get("schema_version")) is str else None,
        "status": manifest.get("status") if type(manifest.get("status")) is str else None,
        "family_spec_sha256": manifest.get("family_spec_sha256")
        if type(manifest.get("family_spec_sha256")) is str else None,
        "case_count": len(cases) if type(cases) is dict else None,
        "source_file_count": len(files) if type(files) is dict else None,
    }


def _receipt_summary(value, digest: str) -> dict:
    receipt = value if type(value) is dict else {}
    raw_cases = receipt.get("cases")
    cases = []
    if type(raw_cases) is dict:
        for key in sorted(raw_cases):
            case = raw_cases[key]
            if type(key) is not str or type(case) is not dict:
                continue
            raw_stages = case.get("stages")
            stages = []
            if type(raw_stages) is list:
                for stage in raw_stages:
                    if type(stage) is not dict:
                        continue
                    stages.append({
                        name: stage[name]
                        for name in ("command", "returncode", "status", "log", "log_sha256")
                        if type(stage.get(name)) in (str, int, type(None))
                    })
            mesh_files = case.get("mesh_files")
            mesh_digest = (
                _canonical_sha256(mesh_files) if type(mesh_files) is dict else None
            )
            cases.append({
                "case": key,
                "status": case.get("status") if type(case.get("status")) is str else None,
                "stages": stages,
                "mesh_file_count": len(mesh_files) if type(mesh_files) is dict else None,
                "mesh_digest_map_sha256": mesh_digest,
            })
    executables = receipt.get("executables")
    executable_summary = None
    if type(executables) is dict:
        executable_summary = {
            key: executables[key]
            for key in sorted(executables)
            if type(key) is str and type(executables[key]) is str
        }
    return {
        "raw_sha256": digest,
        "schema_version": receipt.get("schema_version")
        if type(receipt.get("schema_version")) is str else None,
        "source_manifest_sha256": receipt.get("source_manifest_sha256")
        if type(receipt.get("source_manifest_sha256")) is str else None,
        "status": receipt.get("status") if type(receipt.get("status")) is str else None,
        "engineering_review": receipt.get("engineering_review")
        if type(receipt.get("engineering_review")) is str else None,
        "physical_validation": receipt.get("physical_validation")
        if type(receipt.get("physical_validation")) is str else None,
        "foam_version": receipt.get("foam_version")
        if type(receipt.get("foam_version")) is str else None,
        "executables": executable_summary,
        "cases": cases,
    }


def _finding_bundle(
    *, requirement_id: str, check_id: str, status: str, reason: str,
    evidence_ids: tuple[str, ...], expected, actual,
):
    finding_id = f"finding:{requirement_id}"
    verdict_id = f"verdict:{requirement_id}"
    check = ComplianceCheck(
        id=check_id,
        requirement_id=requirement_id,
        evidence_ids=evidence_ids,
    )
    finding = ComplianceFinding(
        id=finding_id,
        check_id=check_id,
        requirement_id=requirement_id,
        status=status,
        reason=reason,
        evidence_ids=evidence_ids,
        evidence_present=bool(evidence_ids),
        expected=expected,
        actual=actual,
    )
    verdict = ComplianceVerdict(
        id=verdict_id,
        requirement_id=requirement_id,
        status=status,
        finding_ids=(finding_id,),
        reason=reason,
    )
    return check, finding, verdict


def proofgraph_from_cfd_grid_family(
    directory: str | Path,
    *,
    grid_study_specs: Iterable[str | Path] = (),
    graph_id: str | None = None,
) -> ProofGraph:
    """Project nine-case receipts and optional VTK grid studies into ProofGraph.

    `pass` is used only for a complete, locally hash-consistent execution
    receipt. GCI eligibility is represented as `warning` because it permits
    engineering review rather than granting approval. Independent measured
    correlation remains `unknown`; this function does not ingest or certify
    physical measurements.
    """
    supplied_root = Path(directory).expanduser()
    if supplied_root.is_symlink():
        raise ValueError("CFD grid family root must not be a symlink")
    root = supplied_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("CFD grid family root must be a directory")

    study_inputs: dict[int, tuple[Path, object, dict]] = {}
    seen_paths: set[Path] = set()
    seen_configurations: set[int] = set()
    for item in grid_study_specs:
        source = Path(item).expanduser()
        if source.is_symlink():
            raise ValueError("CFD grid-study spec must not be a symlink")
        spec_path = source.resolve(strict=True)
        if spec_path in seen_paths:
            raise ValueError("duplicate CFD grid-study spec path")
        seen_paths.add(spec_path)
        if not spec_path.is_file() or spec_path.stat().st_nlink != 1:
            raise ValueError("CFD grid-study spec must be a regular single-link file")
        snapshot = load_strict_json_snapshot(
            spec_path, max_bytes=_MAX_EVIDENCE_JSON_BYTES
        )
        spec = snapshot.value
        validate_grid_spec(spec)
        configuration = spec["configuration"]
        if configuration in seen_configurations:
            raise ValueError(
                f"duplicate CFD grid-study configuration {configuration}"
            )
        seen_configurations.add(configuration)
        report = analyze_vtk_grid_study(
            spec, base_directory=spec_path.parent
        )
        study_inputs[configuration] = (spec_path, snapshot, report)

    manifest_path = root / "manifest.json"
    receipt_path = root / "grid_run_evidence.json"
    manifest_before, manifest_before_error = _read_snapshot(manifest_path)
    receipt_before, receipt_before_error = _read_snapshot(receipt_path)
    verification = verify_grid_run_evidence(root)
    manifest_after, manifest_after_error = _read_snapshot(manifest_path)
    receipt_after, receipt_after_error = _read_snapshot(receipt_path)

    snapshot_changed = (
        _snapshot_digest(manifest_before) != _snapshot_digest(manifest_after)
        or _snapshot_digest(receipt_before) != _snapshot_digest(receipt_after)
    )
    findings = list(verification.get("findings", []))
    if snapshot_changed:
        findings.append("evidence_snapshot_changed_during_proofgraph_projection")
    snapshot_errors = {
        name: error
        for name, error in (
            ("manifest", manifest_after_error),
            ("receipt", receipt_after_error),
        )
        if error is not None
    }
    if snapshot_errors:
        findings.extend(
            f"{name}_snapshot_unavailable:{error}"
            for name, error in sorted(snapshot_errors.items())
        )

    receipt_present = receipt_before is not None or receipt_after is not None or (
        receipt_before_error is not None or receipt_after_error is not None
    )
    verification_status = verification.get("status")
    if snapshot_changed or snapshot_errors:
        verification_status = "evidence_integrity_failed"
    if not receipt_present:
        execution_status = "unknown"
        execution_reason = (
            "No nine-case execution receipt is present; generated cases are not "
            "solver execution evidence."
        )
    elif verification_status == "execution_logs_integrity_verified_requires_scientific_review":
        execution_status = "pass"
        execution_reason = (
            "The complete nine-case receipt, recorded stage logs and current "
            "source/mesh digests passed the local integrity screen. This does "
            "not establish solver authenticity, convergence, physical validity "
            "or certification."
        )
    elif verification_status == "incomplete_execution_logs_integrity_verified":
        execution_status = "unknown"
        execution_reason = (
            "The available receipt is internally consistent but execution is "
            "incomplete; the nine-case execution-integrity requirement is unknown."
        )
    else:
        execution_status = "fail"
        execution_reason = (
            "The existing execution receipt or its linked local evidence did "
            "not pass the independent integrity screen."
        )

    evidence_sources: list[EvidenceSource] = []
    evidence = []
    execution_evidence_ids: list[str] = []
    manifest_sha = _snapshot_digest(manifest_after)
    receipt_sha = _snapshot_digest(receipt_after)

    manifest_evidence_id = None
    if manifest_after is not None and manifest_sha is not None:
        manifest_source_id = f"source:cfd-grid-manifest:{manifest_sha[:16]}"
        manifest_evidence_id = f"evidence:cfd-grid-manifest:{manifest_sha[:16]}"
        evidence_sources.append(EvidenceSource(
            id=manifest_source_id,
            kind="simulation_input_manifest",
            reference="manifest.json",
            revision=manifest_sha,
        ))
        evidence.append(SimulationEvidence(
            id=manifest_evidence_id,
            property_name="cfd_grid_source_manifest_snapshot",
            value=_manifest_summary(manifest_after.value, manifest_sha),
            source_id=manifest_source_id,
            version=manifest_sha,
            subject_ref="nine-case-grid-family",
            provenance=(ProvenanceRecord(
                id=f"provenance:{manifest_evidence_id}",
                source_id=manifest_source_id,
                origin="manifest.json exact byte snapshot",
                method="SHA-256",
            ),),
        ))
        execution_evidence_ids.append(manifest_evidence_id)

    receipt_evidence_id = None
    if receipt_after is not None and receipt_sha is not None:
        receipt_source_id = f"source:cfd-grid-receipt:{receipt_sha[:16]}"
        receipt_evidence_id = f"evidence:cfd-grid-receipt:{receipt_sha[:16]}"
        evidence_sources.append(EvidenceSource(
            id=receipt_source_id,
            kind="simulation_execution_receipt",
            reference="grid_run_evidence.json",
            revision=receipt_sha,
        ))
        evidence.append(SimulationEvidence(
            id=receipt_evidence_id,
            property_name="cfd_grid_execution_receipt_snapshot",
            value=_receipt_summary(receipt_after.value, receipt_sha),
            source_id=receipt_source_id,
            version=receipt_sha,
            subject_ref="nine-case-grid-family",
            provenance=(ProvenanceRecord(
                id=f"provenance:{receipt_evidence_id}",
                source_id=receipt_source_id,
                origin="grid_run_evidence.json exact byte snapshot",
                upstream_evidence_ids=(
                    (manifest_evidence_id,) if manifest_evidence_id else ()
                ),
                method="SHA-256",
            ),),
        ))
        execution_evidence_ids.append(receipt_evidence_id)

    report_sha = _canonical_sha256({
        "manifest_sha256": manifest_sha,
        "receipt_sha256": receipt_sha,
        "verification": {
            **verification,
            "status": verification_status,
            "findings": findings,
        },
    })
    check_source_id = f"source:cfd-grid-integrity-check:{report_sha[:16]}"
    check_evidence_id = f"evidence:cfd-grid-integrity-check:{report_sha[:16]}"
    evidence_sources.append(EvidenceSource(
        id=check_source_id,
        kind="software_integrity_check",
        reference="cleanroomx.cfd-grid-run-verification.v1",
        revision=report_sha,
    ))
    upstream = tuple(
        evidence_id for evidence_id in (manifest_evidence_id, receipt_evidence_id)
        if evidence_id is not None
    )
    evidence.append(CalculationEvidence(
        id=check_evidence_id,
        property_name="cfd_grid_local_integrity_verification",
        value={
            "schema_version": verification.get("schema_version"),
            "status": verification_status,
            "findings": findings,
            "cases_checked": verification.get("cases_checked", 0),
            "logs_checked": verification.get("logs_checked", 0),
            "warning": verification.get("warning"),
            "snapshot_changed": snapshot_changed,
        },
        source_id=check_source_id,
        version=report_sha,
        subject_ref="nine-case-grid-family",
        provenance=(ProvenanceRecord(
            id=f"provenance:{check_evidence_id}",
            source_id=check_source_id,
            origin="verify_grid_run_evidence",
            upstream_evidence_ids=upstream,
            originating_calculation="verify_grid_run_evidence",
            method="CleanroomX local integrity screen",
        ),),
    ))
    execution_evidence_ids.append(check_evidence_id)

    requirements = [Requirement(
        id=_RUN_REQUIREMENT,
        title="Nine-case execution receipt and local evidence integrity",
        source="CleanroomX CFD execution receipt",
        reference="docs/CFD_GRID_EXECUTION_EVIDENCE.md",
        scope=("nine-case OpenFOAM execution record", "local file integrity only"),
        criteria={
            "verification_service": "verify_grid_run_evidence",
            "eligible_status": "execution_logs_integrity_verified_requires_scientific_review",
            "not_claimed": ["solver_authenticity", "convergence", "physical_validation", "certification"],
        },
    )]
    requirements.extend(
        Requirement(
            id=f"{_GRID_REQUIREMENT_PREFIX}{configuration}",
            title=f"Three-grid numerical screening for configuration {configuration}",
            source="CleanroomX CFD grid-study screen",
            reference="docs/CFD_GRID_CONVERGENCE.md",
            scope=(f"configuration:{configuration}", "selected quantity and supplied tolerances"),
            criteria={
                "screening_service": "analyze_vtk_grid_study",
                "eligible_status": "eligible_for_engineering_review",
                "not_claimed": ["physical_validation", "model_validity", "certification"],
            },
        )
        for configuration in (1, 2, 3)
    )
    requirements.append(Requirement(
        id=_PHYSICAL_REQUIREMENT,
        title="Independent measured-cleanroom correlation and review",
        source="Independent measurement and engineering review",
        reference="issue #1296",
        scope=("aligned operating conditions", "measurement uncertainty", "independent review"),
        criteria={
            "required_measurement_status": "available_and_reviewed",
            "current_status": "not_available_to_this_adapter",
        },
    ))
    input_revision = _canonical_sha256({
        "manifest_sha256": manifest_sha,
        "receipt_sha256": receipt_sha,
        "verification_report_sha256": report_sha,
        "grid_studies": [
            {
                "configuration": configuration,
                "spec_sha256": hashlib.sha256(snapshot.raw_bytes).hexdigest(),
                "report_sha256": _canonical_sha256(report),
            }
            for configuration, (_, snapshot, report) in sorted(study_inputs.items())
        ],
    })
    requirement_set = RequirementSet(
        id=f"cfd-grid-evidence:{input_revision[:16]}",
        version=input_revision,
        title="CFD nine-case software evidence and validation gates",
        source="CleanroomX CFD ProofGraph adapter",
        requirements=tuple(requirements),
    )

    checks = []
    graph_findings = []
    verdicts = []
    check_ids = []
    verdict_ids = []
    execution_bundle = _finding_bundle(
        requirement_id=_RUN_REQUIREMENT,
        check_id=f"check:{_RUN_REQUIREMENT}",
        status=execution_status,
        reason=execution_reason,
        evidence_ids=tuple(execution_evidence_ids),
        expected={"all_nine_cases": "complete", "local_integrity": "verified"},
        actual={
            "receipt_status": verification.get("status"),
            "verification_status": verification_status,
            "cases_checked": verification.get("cases_checked", 0),
            "logs_checked": verification.get("logs_checked", 0),
            "findings": findings,
        },
    )
    for item in execution_bundle:
        (checks if isinstance(item, ComplianceCheck) else
         graph_findings if isinstance(item, ComplianceFinding) else verdicts).append(item)
    check_ids.append(execution_bundle[0].id)
    verdict_ids.append(execution_bundle[2].id)

    for configuration in (1, 2, 3):
        requirement_id = f"{_GRID_REQUIREMENT_PREFIX}{configuration}"
        study = study_inputs.get(configuration)
        if study is None:
            status = "not_checked"
            reason = "No three-grid VTK/log study was supplied for this configuration."
            actual = {"screening_status": "not_checked"}
            evidence_ids = ()
        else:
            spec_path, snapshot, report = study
            spec_sha = hashlib.sha256(snapshot.raw_bytes).hexdigest()
            source_id = f"source:cfd-grid-study:{configuration}:{spec_sha[:16]}"
            evidence_id = f"evidence:cfd-grid-study:{configuration}:{spec_sha[:16]}"
            evidence_sources.append(EvidenceSource(
                id=source_id,
                kind="three_grid_vtk_study",
                reference=spec_path.name,
                revision=spec_sha,
            ))
            evidence.append(CalculationEvidence(
                id=evidence_id,
                property_name="cfd_three_grid_screening_result",
                value={
                    "input_spec_sha256": spec_sha,
                    "spec_path": spec_path.name,
                    "report": report,
                    "boundary": "Screening eligibility is not model validation or physical acceptance.",
                },
                source_id=source_id,
                version=spec_sha,
                subject_ref=f"configuration:{configuration}",
                provenance=(ProvenanceRecord(
                    id=f"provenance:{evidence_id}",
                    source_id=source_id,
                    origin="three-grid study specification and source digests",
                    originating_file=spec_path.name,
                    originating_calculation="analyze_vtk_grid_study",
                    method="hash-bound VTK fields and solver-log screening",
                ),),
            ))
            evidence_ids = (evidence_id,)
            if report.get("status") == "eligible_for_engineering_review":
                status = "warning"
                reason = (
                    "The supplied three-grid study met its configured numerical "
                    "screening criteria and is eligible for engineering review; "
                    "this is not physical validation or acceptance."
                )
            else:
                status = "indeterminate"
                reason = (
                    "The supplied three-grid study is not eligible for engineering "
                    "review under its declared screening criteria."
                )
            actual = {
                "screening_status": report.get("status"),
                "blockers": report.get("blockers", []),
                "input_spec_sha256": spec_sha,
            }
        bundle = _finding_bundle(
            requirement_id=requirement_id,
            check_id=f"check:{requirement_id}",
            status=status,
            reason=reason,
            evidence_ids=evidence_ids,
            expected={"status": "eligible_for_engineering_review"},
            actual=actual,
        )
        checks.append(bundle[0])
        graph_findings.append(bundle[1])
        verdicts.append(bundle[2])
        check_ids.append(bundle[0].id)
        verdict_ids.append(bundle[2].id)

    physical_bundle = _finding_bundle(
        requirement_id=_PHYSICAL_REQUIREMENT,
        check_id=f"check:{_PHYSICAL_REQUIREMENT}",
        status="unknown",
        reason=(
            "This adapter has no independent measured cleanroom dataset or "
            "competent review record; physical validation remains unavailable."
        ),
        evidence_ids=(),
        expected={"independent_measurements": "available_and_reviewed"},
        actual={"physical_validation": "not_available", "engineering_review": "BLOCKED"},
    )
    checks.append(physical_bundle[0])
    graph_findings.append(physical_bundle[1])
    verdicts.append(physical_bundle[2])
    check_ids.append(physical_bundle[0].id)
    verdict_ids.append(physical_bundle[2].id)

    verification_run = VerificationRun(
        id=f"verification:cfd-grid-evidence:{input_revision[:16]}",
        requirement_set_id=requirement_set.id,
        check_ids=tuple(check_ids),
        verdict_ids=tuple(verdict_ids),
        input_sha256=input_revision,
        metadata={
            "adapter": "proofgraph_from_cfd_grid_family",
            "local_execution_integrity_status": verification_status,
            "grid_study_configurations": sorted(study_inputs),
            "solver_authenticity": "not_verified",
            "independent_custody": "not_verified",
            "numerical_convergence": (
                "screened_for_supplied_configurations_only"
                if study_inputs else "not_checked"
            ),
            "measurement_correlation": "not_available",
            "physical_validation": "not_available",
            "engineering_review": "BLOCKED",
            "certification": "not_claimed",
        },
    )
    return ProofGraph(
        id=graph_id or f"proofgraph:cfd-grid:{input_revision[:16]}",
        requirement_set=requirement_set,
        evidence_sources=tuple(evidence_sources),
        evidence=tuple(evidence),
        checks=tuple(checks),
        findings=tuple(graph_findings),
        verdicts=tuple(verdicts),
        verification_runs=(verification_run,),
    )
