"""Verified analysis adapter for CleanroomX sync-vtk v3 snapshot stores.

The adapter binds state, snapshot JSON and source VTK bytes. It does not prove
that OpenFOAM executed, that VTK values match native field files, or that the
result is physically valid. The original VTK source tree must remain available
because the v3 snapshot stores field payloads but not cell-center geometry.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path, PurePosixPath
from typing import Any

from .cfd_proofgraph import _asset_path, _hash_regular_file, _read_json, _require_sha256
from .cfd_result_analysis import (
    AnalysisSession, BOUNDARY, MAX_SNAPSHOTS, _new_report, _numeric_time,
    _source, _summarize, _unique_sources, digest,
)
from .cfd_sync import STATE_SCHEMA, SNAPSHOT_SCHEMA, _SIMULATION_ID, _canonical_time
from .cfd_vtk import MAX_VTK_BYTES, VTK_FIELD_MAP_SCHEMA, validate_vtk_field_map
from .proofgraph_models import (
    ComplianceCheck, ComplianceFinding, ComplianceVerdict, EvidenceSource,
    ProofGraph, ProvenanceRecord, Requirement, RequirementSet, SimulationEvidence,
    VerificationRun,
)

MAX_STATE_BYTES = 64 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 128 * 1024 * 1024
MAX_STATE_RECORDS = 100_000
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SEMANTIC = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")


def _compact_sha(value: Any, label: str) -> str:
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} is not strict JSON") from error
    return hashlib.sha256(encoded).hexdigest()


def _safe_relative(value: Any, label: str, *, max_length: int = 1024) -> str:
    if (
        type(value) is not str or not value or len(value) > max_length
        or "\\" in value or ":" in value or "\x00" in value
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ValueError(f"{label} must be a safe relative POSIX path")
    parsed = PurePosixPath(value)
    if (
        parsed.is_absolute() or parsed.as_posix() != value
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise ValueError(f"{label} must be a safe relative POSIX path")
    return value


def _safe_case_id(value: Any) -> str:
    return _safe_relative(value, "VTK snapshot case_id", max_length=256)


def _finite_number(value: Any, label: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def _validate_fields_payload(fields: Any, *, cell_count: int) -> dict:
    if type(fields) is not dict:
        raise ValueError("VTK snapshot fields must be an object")
    if type(fields.get("source_sha256")) is not str or not _SHA256.fullmatch(fields["source_sha256"]):
        raise ValueError("VTK snapshot fields source_sha256 is invalid")
    if type(fields.get("mesh_cells")) is not int or fields["mesh_cells"] != cell_count or cell_count <= 0:
        raise ValueError("VTK snapshot cell count is inconsistent")
    cells = fields.get("cells")
    if type(cells) is not list or len(cells) != cell_count:
        raise ValueError("VTK snapshot cell payload length is inconsistent")
    for index, cell in enumerate(cells):
        if type(cell) is not dict:
            raise ValueError(f"VTK snapshot cell {index} must be an object")
        if _finite_number(cell.get("volume_m3"), f"cell {index} volume_m3") <= 0:
            raise ValueError(f"VTK snapshot cell {index} has nonpositive volume")
        velocity = cell.get("velocity_m_s")
        if type(velocity) is not list or len(velocity) != 3:
            raise ValueError(f"VTK snapshot cell {index} velocity_m_s must have three components")
        for component in velocity:
            _finite_number(component, f"cell {index} velocity component")
        if "temperature_K" in cell and _finite_number(cell["temperature_K"], "temperature_K") <= 0:
            raise ValueError("VTK snapshot contains nonpositive absolute temperature")
        if "contaminant_concentration" in cell and _finite_number(
            cell["contaminant_concentration"], "contaminant_concentration"
        ) < 0:
            raise ValueError("VTK snapshot contains negative contaminant concentration")
        if "recirculating" in cell and type(cell["recirculating"]) is not bool:
            raise ValueError("VTK snapshot recirculating label must be boolean")

    field_data = fields.get("field_data", {})
    unavailable = fields.get("unavailable_fields", [])
    if type(field_data) is not dict or type(unavailable) is not list:
        raise ValueError("VTK snapshot mapped-field metadata has an invalid shape")
    for semantic, item in field_data.items():
        if type(semantic) is not str or not _SEMANTIC.fullmatch(semantic) or type(item) is not dict:
            raise ValueError("VTK snapshot mapped-field metadata is invalid")
        array_name, units, components = item.get("array_name"), item.get("units"), item.get("components")
        if type(array_name) is not str or not array_name.strip() or len(array_name) > 128:
            raise ValueError("VTK snapshot mapped field has an invalid array name")
        if type(units) is not str or not units.strip() or len(units) > 64:
            raise ValueError("VTK snapshot mapped field must retain explicit units")
        if type(components) is not int or components not in (1, 3):
            raise ValueError("VTK snapshot mapped field must be scalar or three-component")
        values = item.get("values")
        if type(values) is not list or len(values) != cell_count:
            raise ValueError("VTK snapshot mapped field length differs from the mesh cell count")
        for value in values:
            if components == 1:
                _finite_number(value, f"mapped field {array_name}")
            else:
                if type(value) is not list or len(value) != 3:
                    raise ValueError(f"Mapped vector field {array_name} must contain three components")
                for component in value:
                    _finite_number(component, f"mapped field {array_name}")
    for item in unavailable:
        if (
            type(item) is not dict
            or type(item.get("array_name")) is not str
            or type(item.get("semantic")) is not str
            or not _SEMANTIC.fullmatch(item["semantic"])
            or type(item.get("units")) is not str
            or item.get("reason") != "not_present_in_vtk_cell_data"
        ):
            raise ValueError("VTK snapshot unavailable-field metadata is invalid")

    contaminant_array = fields.get("contaminant_array")
    has_contaminant = fields.get("has_contaminant_field")
    if type(has_contaminant) is not bool or has_contaminant != (contaminant_array is not None):
        raise ValueError("VTK snapshot contaminant declaration is inconsistent")
    if contaminant_array is not None and (
        type(contaminant_array) is not str or not contaminant_array.strip() or len(contaminant_array) > 128
    ):
        raise ValueError("VTK snapshot contaminant array name is invalid")
    temperature = fields.get("temperature_field")
    has_temperature = fields.get("has_temperature_field")
    if type(has_temperature) is not bool or has_temperature != (temperature is not None):
        raise ValueError("VTK snapshot temperature declaration is inconsistent")
    if temperature is not None and (
        type(temperature) is not dict
        or type(temperature.get("array_name")) is not str
        or not temperature["array_name"].strip()
        or temperature.get("units") != "K"
        or temperature.get("units_source") != "explicit_caller_declaration"
    ):
        raise ValueError("VTK snapshot temperature must retain an explicit kelvin declaration")
    if type(fields.get("has_recirculation_labels")) is not bool:
        raise ValueError("VTK snapshot recirculation-label declaration is invalid")
    return fields


def _reconstruct_field_map(fields: dict, expected_hash: str | None) -> dict | None:
    field_data = fields.get("field_data", {})
    unavailable = fields.get("unavailable_fields", [])
    if expected_hash is None:
        if field_data or unavailable or "field_map_schema" in fields:
            raise ValueError("Snapshot contains mapped fields but sync-state.json has no field-map identity")
        return None
    if fields.get("field_map_schema") != VTK_FIELD_MAP_SCHEMA:
        raise ValueError("VTK snapshot field-map schema is missing or unsupported")
    entries = {}
    for semantic, item in field_data.items():
        array_name = item["array_name"]
        if array_name in entries:
            raise ValueError("VTK snapshot field map repeats an array name")
        entries[array_name] = {"semantic": semantic, "units": item["units"]}
    for item in unavailable:
        array_name = item["array_name"]
        if array_name in entries:
            raise ValueError("VTK snapshot field map repeats an unavailable array name")
        entries[array_name] = {"semantic": item["semantic"], "units": item["units"]}
    normalized = validate_vtk_field_map({
        "schema_version": VTK_FIELD_MAP_SCHEMA,
        "fields": entries,
    })
    if _compact_sha(normalized, "reconstructed VTK field map") != expected_hash:
        raise ValueError("Reconstructed VTK field map does not match sync-state.json")
    return normalized


def _validate_snapshot(
    root: Path,
    source_root: Path,
    relative: str,
    record: dict,
    *,
    simulation_id: str,
    configuration_sha256: str,
    field_map_sha256: str | None,
    state_source: dict,
) -> tuple[dict, dict]:
    relative = _safe_relative(relative, "VTK source relative path")
    if record.get("relative_path") != relative:
        raise ValueError("VTK sync record key differs from its relative_path")
    case_id = _safe_case_id(record.get("case_id"))
    time_name = record.get("solver_time")
    canonical_time = _canonical_time(time_name) if type(time_name) is str else None
    if canonical_time is None or canonical_time != record.get("canonical_solver_time"):
        raise ValueError("VTK sync record solver time is invalid or noncanonical")
    if _numeric_time(time_name) <= 0:
        raise ValueError("Initial time zero cannot be presented as a solver result")

    source_path, normalized_relative = _asset_path(source_root, relative)
    if normalized_relative != relative or source_path.suffix.lower() not in (".vtk", ".vtu"):
        raise ValueError("VTK source path is not a canonical internal VTK dataset path")
    source_sha256, source_size = _hash_regular_file(source_path, max_bytes=MAX_VTK_BYTES)
    if (
        source_sha256 != record.get("source_sha256")
        or type(record.get("size_bytes")) is not int
        or source_size != record["size_bytes"]
    ):
        raise ValueError("VTK source bytes no longer match the accepted sync-vtk record")

    expected_token = hashlib.sha256(
        (simulation_id + "\0" + relative).encode("utf-8")
    ).hexdigest()
    expected_snapshot_relative = f"snapshots/{expected_token}.json"
    snapshot_relative = record.get("snapshot_relative_path")
    if snapshot_relative != expected_snapshot_relative:
        raise ValueError("VTK snapshot path does not match its simulation and source identity")
    snapshot_path, normalized_snapshot_relative = _asset_path(root, snapshot_relative)
    if normalized_snapshot_relative != snapshot_relative:
        raise ValueError("VTK snapshot path is not canonical")
    snapshot, snapshot_raw = _read_json(snapshot_path, max_bytes=MAX_SNAPSHOT_BYTES)
    snapshot_sha256 = hashlib.sha256(snapshot_raw).hexdigest()
    if (
        snapshot_sha256 != record.get("snapshot_sha256")
        or type(record.get("snapshot_size_bytes")) is not int
        or len(snapshot_raw) != record["snapshot_size_bytes"]
    ):
        raise ValueError("VTK result snapshot hash or size differs from sync-state.json")
    if snapshot.get("field_map_sha256") != field_map_sha256:
        raise ValueError("VTK snapshot field-map identity differs from sync-state.json")
    if snapshot.get("configuration_sha256") != configuration_sha256:
        raise ValueError("VTK snapshot configuration identity differs from sync-state.json")
    if (
        snapshot.get("schema_version") != SNAPSHOT_SCHEMA
        or snapshot.get("simulation_id") != simulation_id
        or snapshot.get("case_id") != case_id
        or snapshot.get("solver_time") != time_name
        or snapshot.get("source_relative_path") != relative
        or snapshot.get("source_sha256") != source_sha256
        or snapshot.get("source_size_bytes") != source_size
        or snapshot.get("data_status") != "imported"
        or snapshot.get("scientific_validation") != "BLOCKED"
    ):
        raise ValueError("VTK snapshot identity or scientific-validation boundary is inconsistent")

    fields = snapshot.get("fields")
    if type(fields) is not dict:
        raise ValueError("VTK snapshot is missing its imported field payload")
    fields_sha256 = _compact_sha(fields, "VTK snapshot field payload")
    if (
        type(snapshot.get("fields_sha256")) is not str
        or not _SHA256.fullmatch(snapshot["fields_sha256"])
        or fields_sha256 != snapshot["fields_sha256"]
        or fields_sha256 != record.get("fields_sha256")
    ):
        raise ValueError("VTK snapshot field payload hash differs from its state record")
    fields = _validate_fields_payload(fields, cell_count=record.get("mesh_cells"))
    if fields.get("source_sha256") != source_sha256:
        raise ValueError("Imported VTK field payload is not bound to the source dataset")
    if (
        record.get("field_data_names") != sorted(fields.get("field_data", {}))
        or record.get("unavailable_field_names") != sorted(
            item["semantic"] for item in fields.get("unavailable_fields", [])
        )
    ):
        raise ValueError("VTK sync record field availability differs from its snapshot payload")
    normalized_field_map = _reconstruct_field_map(fields, field_map_sha256)

    definitions = {}
    for semantic, item in fields.get("field_data", {}).items():
        array_name = item["array_name"]
        # U is the canonical velocity vector and is exposed as speed/U_x/U_y/U_z.
        if array_name == "U":
            continue
        definitions[array_name] = {
            "array_name": array_name,
            "label": semantic.replace("_", " ").title(),
            "units": item["units"],
            "semantic": semantic,
        }
    temperature = fields.get("temperature_field")
    import_options = {
        "contaminant_array": fields.get("contaminant_array"),
        "temperature_array": temperature["array_name"] if temperature else None,
        "temperature_units": "K" if temperature else None,
        "recirculation_array": "recirculating" if fields["has_recirculation_labels"] else None,
    }
    vtk_source = _source(
        source_path, source_sha256, role="vtk_snapshot_source",
        case_id=case_id, time_name=time_name,
    )
    snapshot_source = _source(
        snapshot_path, snapshot_sha256, role="vtk_result_snapshot",
        case_id=case_id, time_name=time_name,
    )
    analysis_snapshot = {
        "case_id": case_id,
        "region": "whole mesh (no verified room cell mask supplied)",
        "time_name": time_name,
        "cell_count": fields["mesh_cells"],
        "vtk_source": vtk_source,
        "sources": [state_source, snapshot_source, vtk_source],
        "field_definitions": definitions,
        "vtk_field_map": normalized_field_map,
        "vtk_import_options": import_options,
        "allow_unavailable_fields": True,
        "stored_import_sha256": fields_sha256,
        "snapshot_sha256": snapshot_sha256,
        "source_fields_rehashed": False,
        "import_status": "PASS_DIAGNOSTIC_ONLY",
        "execution_status": "vtk_snapshot_import_only_solver_execution_not_verified",
    }
    return analysis_snapshot, {
        "case_id": case_id,
        "time_name": time_name,
        "snapshot_sha256": snapshot_sha256,
        "source_sha256": source_sha256,
        "fields_sha256": fields_sha256,
        "snapshot_path": snapshot_path,
        "source_path": source_path,
        "fields": fields,
    }


def _snapshot_store_proofgraph(
    simulation_id: str,
    state_sha256: str,
    configuration_sha256: str,
    field_map_sha256: str | None,
    verified_snapshots: list[dict],
) -> ProofGraph:
    snapshot_identity = [
        {
            "case_id": item["case_id"],
            "time_name": item["time_name"],
            "snapshot_sha256": item["snapshot_sha256"],
            "source_sha256": item["source_sha256"],
            "fields_sha256": item["fields_sha256"],
        }
        for item in verified_snapshots
    ]
    payload = {
        "simulation_id": simulation_id,
        "state_sha256": state_sha256,
        "configuration_sha256": configuration_sha256,
        "field_map_sha256": field_map_sha256,
        "snapshots": snapshot_identity,
        "integrity_scope": "local_hash_link_consistency_not_authenticity",
        "scientific_validation": "BLOCKED",
        "solver_execution_verified": False,
        "native_openfoam_fields_verified": False,
    }
    input_sha256 = digest(payload)
    suffix = input_sha256[:16]
    source_id = "SOURCE-VTK-SNAPSHOT-" + suffix
    evidence_id = "EVIDENCE-VTK-SNAPSHOT-" + suffix
    integrity_requirement = "REQ-VTK-SNAPSHOT-INTEGRITY-" + suffix
    science_requirement = "REQ-VTK-SNAPSHOT-SCIENCE-" + suffix
    integrity_check = "CHECK-VTK-SNAPSHOT-INTEGRITY-" + suffix
    science_check = "CHECK-VTK-SNAPSHOT-SCIENCE-" + suffix
    integrity_finding = "FIND-VTK-SNAPSHOT-INTEGRITY-" + suffix
    science_finding = "FIND-VTK-SNAPSHOT-SCIENCE-" + suffix
    integrity_verdict = "VERDICT-VTK-SNAPSHOT-INTEGRITY-" + suffix
    science_verdict = "VERDICT-VTK-SNAPSHOT-SCIENCE-" + suffix
    requirements = RequirementSet(
        id="REQSET-VTK-SNAPSHOT-" + suffix,
        version="1",
        title="VTK snapshot integrity and scientific-validation evidence",
        source="CleanroomX sync-vtk v3 result-store adapter",
        requirements=(
            Requirement(
                id=integrity_requirement,
                title="VTK snapshot source and payload integrity",
                source="CleanroomX sync-vtk v3 state, snapshots and VTK assets",
                reference="sync-state.json",
                criteria={
                    "required": "State, snapshot, field payload and source VTK hashes are locally consistent.",
                    "decision_scope": "artifact_integrity_only",
                },
            ),
            Requirement(
                id=science_requirement,
                title="Independent OpenFOAM and physical cleanroom validation",
                source="Independent solver, native-field and measured-data evidence",
                criteria={
                    "required": [
                        "Verify actual OpenFOAM solver execution and convergence",
                        "Compare VTK values with original native OpenFOAM fields",
                        "Correlate against independent cleanroom measurements",
                    ],
                    "decision_scope": "physical_validation",
                },
            ),
        ),
    )
    source = EvidenceSource(
        id=source_id,
        kind="openfoam_vtk_sync_state_v3",
        reference="sync-state.json",
        revision=state_sha256,
    )
    evidence = SimulationEvidence(
        id=evidence_id,
        property_name="openfoam_vtk_snapshot_store_integrity",
        value=payload,
        source_id=source_id,
        version=state_sha256,
        subject_ref=simulation_id,
        provenance=(
            ProvenanceRecord(
                id="PROV-VTK-SNAPSHOT-" + suffix,
                source_id=source_id,
                origin="CleanroomX sync-vtk v3 snapshot store",
                originating_file="sync-state.json and referenced snapshots",
                originating_calculation="state, snapshot, field payload and source VTK SHA-256 verification",
                method="local_hash_link_consistency_not_authenticity",
            ),
        ),
    )
    checks = (
        ComplianceCheck(
            id=integrity_check,
            requirement_id=integrity_requirement,
            evidence_ids=(evidence_id,),
            required_evidence_kinds=("simulation",),
        ),
        ComplianceCheck(
            id=science_check,
            requirement_id=science_requirement,
            evidence_ids=(evidence_id,),
        ),
    )
    integrity_status = "pass" if verified_snapshots else "not_checked"
    integrity_reason = (
        "Every imported snapshot, its field payload and source VTK dataset passed local hash-link checks. "
        "This does not establish authenticity or solver execution."
        if verified_snapshots else
        "No imported VTK snapshots are available to verify yet."
    )
    findings = (
        ComplianceFinding(
            id=integrity_finding,
            check_id=integrity_check,
            requirement_id=integrity_requirement,
            status=integrity_status,
            reason=integrity_reason,
            evidence_ids=(evidence_id,),
            evidence_present=True,
            expected="Locally consistent state, snapshot, field-payload and source VTK hashes",
            actual={"verified_snapshot_count": len(verified_snapshots), "state_sha256": state_sha256},
        ),
        ComplianceFinding(
            id=science_finding,
            check_id=science_check,
            requirement_id=science_requirement,
            status="not_checked",
            reason=(
                "A VTK snapshot store does not bind original native OpenFOAM field files, solver logs, "
                "convergence evidence or independent cleanroom measurements."
            ),
            evidence_ids=(evidence_id,),
            evidence_present=True,
            expected="Independent native-field, solver-convergence and physical-correlation evidence",
            actual="not checked by the sync-vtk v3 adapter",
        ),
    )
    verdicts = (
        ComplianceVerdict(
            id=integrity_verdict,
            requirement_id=integrity_requirement,
            status=integrity_status,
            finding_ids=(integrity_finding,),
            reason=integrity_reason,
        ),
        ComplianceVerdict(
            id=science_verdict,
            requirement_id=science_requirement,
            status="not_checked",
            finding_ids=(science_finding,),
            reason="Scientific and physical validation remain BLOCKED.",
        ),
    )
    return ProofGraph(
        id="PROOFGRAPH-VTK-SNAPSHOT-" + suffix,
        requirement_set=requirements,
        evidence_sources=(source,),
        evidence=(evidence,),
        checks=checks,
        findings=findings,
        verdicts=verdicts,
        verification_runs=(
            VerificationRun(
                id="RUN-VTK-SNAPSHOT-" + suffix,
                requirement_set_id=requirements.id,
                check_ids=(integrity_check, science_check),
                verdict_ids=(integrity_verdict, science_verdict),
                input_sha256=input_sha256,
                metadata={
                    "adapter": "cleanroomx.cfd_vtk_snapshot_analysis",
                    "simulation_id": simulation_id,
                    "verified_snapshot_count": len(verified_snapshots),
                    "solver_execution_verified": False,
                    "native_openfoam_fields_verified": False,
                    "scientific_validation": "BLOCKED",
                },
            ),
        ),
    )


def analyze_vtk_snapshot_results(
    result_directory: str | Path,
    simulation_id: str,
    *,
    case_directory: str | Path | None = None,
    verify_native_sources: bool = False,
) -> AnalysisSession:
    """Analyze one sync-vtk v3 store with strict local integrity checks."""
    if type(simulation_id) is not str or not _SIMULATION_ID.fullmatch(simulation_id):
        raise ValueError("Simulation ID contains unsupported characters")
    if type(verify_native_sources) is not bool:
        raise ValueError("verify_native_sources must be a boolean")
    if case_directory is not None or verify_native_sources:
        raise ValueError(
            "sync-vtk v3 does not bind original native OpenFOAM fields or solver logs; "
            "use a matching native sync-case/grid result store for those checks"
        )
    candidate = Path(result_directory).expanduser()
    if candidate.is_symlink() or not candidate.is_dir():
        raise ValueError("VTK snapshot result directory must be a regular directory")
    root = candidate.resolve(strict=True)
    state_path = root / "sync-state.json"
    if state_path.is_symlink() or not state_path.is_file():
        raise ValueError("VTK snapshot store requires a regular non-linked sync-state.json")
    state, state_raw = _read_json(state_path, max_bytes=MAX_STATE_BYTES)
    state_sha256 = hashlib.sha256(state_raw).hexdigest()
    if (
        state.get("schema_version") != STATE_SCHEMA
        or state.get("simulation_id") != simulation_id
        or type(state.get("records")) is not dict
        or len(state["records"]) > MAX_STATE_RECORDS
    ):
        raise ValueError("sync-state.json schema, simulation identity or record table is invalid")

    configuration_sha256 = _require_sha256(
        state.get("configuration_sha256"), "sync-state.configuration_sha256"
    )
    field_map_sha256 = state.get("field_map_sha256")
    if field_map_sha256 is not None:
        _require_sha256(field_map_sha256, "sync-state.field_map_sha256")
    if state.get("output_root") != str(root):
        raise ValueError("sync-state.json output_root does not match the selected result store")
    source_root_text = state.get("source_root")
    if type(source_root_text) is not str or not Path(source_root_text).is_absolute():
        raise ValueError("sync-state.json source_root must be an absolute path")
    source_candidate = Path(source_root_text)
    if source_candidate.is_symlink() or not source_candidate.is_dir():
        raise ValueError("Original VTK source_root must remain a regular directory for geometry analysis")
    source_root = source_candidate.resolve(strict=True)
    if str(source_root) != source_root_text:
        raise ValueError("sync-state.json source_root is not canonical")
    if (
        source_root == root
        or source_root in root.parents
        or root in source_root.parents
    ):
        raise ValueError("VTK source and result-store directories must not contain one another")

    state_source = _source(
        state_path, state_sha256, role="vtk_sync_state", case_id="result_store"
    )
    report = _new_report(simulation_id, "vtk_snapshot_sync")
    report["interpretation"] = (
        BOUNDARY + " This VTK-only store does not prove OpenFOAM solver execution, "
        "native field parity or physical cleanroom validity."
    )
    report["sources"].append(state_source)
    report["reproducibility"].update(
        native_source_bytes_rehashed=False,
        native_source_verification_requested=False,
        native_bytes_verified=0,
        vtk_source_bytes_rehashed=False,
        snapshot_import_payload_rehashed=False,
        configuration_file_bytes_rehashed=False,
        configuration_sha256=configuration_sha256,
        field_map_sha256=field_map_sha256,
        integrity_scope="local_hash_link_consistency_not_authenticity",
    )

    cases: dict[str, dict] = {}
    verified_snapshots: list[dict] = []
    proof_records: list[dict] = []
    nonimported_statuses = {"pending_stability", "waiting_for_valid_export", "duplicate"}
    for relative, record in sorted(state["records"].items()):
        relative = _safe_relative(relative, "VTK sync record path")
        if type(record) is not dict or record.get("relative_path") != relative:
            raise ValueError("sync-state.json contains an invalid result record")
        case_id = _safe_case_id(record.get("case_id"))
        status = record.get("status")
        if type(status) is not str:
            raise ValueError("VTK sync record status must be text")
        if status in ("snapshot_integrity_failure", "stale_changed_after_import", "conflicting_time_snapshot"):
            raise ValueError(f"VTK sync store contains a blocked record status: {status}")
        case = cases.setdefault(case_id, {
            "case_id": case_id,
            "configuration_hash": configuration_sha256,
            "solver_release": None,
            "solver_build": None,
            "sync_status": "VTK import only; solver execution not verified",
            "solver_returncode": None,
            "solver_log_status": None,
            "error_count": 0,
            "snapshot_count": 0,
        })
        if status != "imported":
            if status not in nonimported_statuses:
                case["error_count"] += 1
            report["availability"].append({
                "case_id": case_id,
                "analysis": "vtk_snapshot_ingestion",
                "status": "not_available",
                "reason": f"Source record {relative!r} is not imported; current status is {status!r}.",
            })
            continue
        if len(verified_snapshots) >= MAX_SNAPSHOTS:
            raise ValueError("Analysis exceeds 256 VTK snapshots; select a smaller result store")
        analysis_snapshot, proof_record = _validate_snapshot(
            root, source_root, relative, record,
            simulation_id=simulation_id,
            configuration_sha256=configuration_sha256,
            field_map_sha256=field_map_sha256,
            state_source=state_source,
        )
        _summarize(analysis_snapshot)
        # _summarize re-hashes the source VTK and compares its re-imported
        # field payload with the immutable snapshot before these flags turn true.
        report["reproducibility"]["vtk_source_bytes_rehashed"] = True
        report["reproducibility"]["snapshot_import_payload_rehashed"] = True
        verified_snapshots.append(analysis_snapshot)
        proof_records.append(proof_record)
        case["snapshot_count"] += 1
        report["snapshots"].append(analysis_snapshot)
        report["sources"].extend(analysis_snapshot["sources"])
        for missing in proof_record["fields"].get("unavailable_fields", []):
            report["availability"].append({
                "case_id": case_id,
                "analysis": missing["semantic"],
                "status": "not_available",
                "reason": (
                    f"Mapped VTK array {missing['array_name']!r} is absent from the source dataset; "
                    "it is not synthesized."
                ),
            })
        mapped_names = {
            item["array_name"] for item in proof_record["fields"].get("field_data", {}).values()
        }
        if (
            proof_record["fields"].get("has_contaminant_field")
            and proof_record["fields"].get("contaminant_array") not in mapped_names
        ):
            report["availability"].append({
                "case_id": case_id,
                "analysis": "contaminant_concentration_units",
                "status": "not_available",
                "reason": (
                    "A contaminant array was selected, but the snapshot does not record explicit units; "
                    "it is excluded from quantitative field graphs."
                ),
            })

    for case_id in sorted(cases):
        report["cases"].append(cases[case_id])
    if not verified_snapshots:
        report["status"] = "not_available"
        report["availability"].append({
            "analysis": "fields",
            "status": "not_available",
            "reason": "No imported sync-vtk v3 snapshots are available for analysis yet.",
        })
    report["availability"].extend([
        {
            "analysis": "residuals_mesh",
            "status": "not_available",
            "reason": "sync-vtk v3 snapshots do not bind native solver logs or checkMesh receipts.",
        },
        {
            "analysis": "native_source_field_verification",
            "status": "not_available",
            "reason": "sync-vtk v3 stores do not record original native OpenFOAM field-file hashes.",
        },
        {
            "analysis": "room_airflow_ach",
            "status": "not_available",
            "reason": "No verified room-cell masks or per-room boundary-flux evidence is present in this store.",
        },
    ])
    report["sources"] = _unique_sources(report["sources"])
    graph = _snapshot_store_proofgraph(
        simulation_id, state_sha256, configuration_sha256, field_map_sha256, proof_records
    )
    return AnalysisSession(report, graph, (root, source_root))
