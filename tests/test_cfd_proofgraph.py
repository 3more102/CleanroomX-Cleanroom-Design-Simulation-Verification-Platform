from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cleanroomx.cfd_proofgraph import (
    export_openfoam_proofgraph,
    proofgraph_from_openfoam_sync_results,
)
from cleanroomx.proofgraph_io import proofgraph_from_dict


SIMULATION_ID = "simulation-001"
CONFIGURATION_HASH = "a" * 64


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_case(root: Path, configuration: int = 1) -> Path:
    case = root / SIMULATION_ID / f"configuration_{configuration}"
    output = case / "results" / "time_100"
    vtk_path = output / "VTK" / "field.vtk"
    log_path = output / "foamToVTK.log"
    vtk_path.parent.mkdir(parents=True)
    vtk_bytes = b"# vtk DataFile Version 3.0\nfixture\n"
    log_bytes = b"OpenFOAM Foundation v10\nTime: 100\nEnd\n"
    vtk_path.write_bytes(vtk_bytes)
    log_path.write_bytes(log_bytes)

    assets = [
        {
            "path": vtk_path.relative_to(case).as_posix(),
            "sha256": _sha256(vtk_bytes),
            "size_bytes": len(vtk_bytes),
        },
        {
            "path": log_path.relative_to(case).as_posix(),
            "sha256": _sha256(log_bytes),
            "size_bytes": len(log_bytes),
        },
    ]
    source_fields = {
        "U": {
            "path": "100/U",
            "sha256": "c" * 64,
            "size_bytes": 48,
        }
    }
    source_fingerprint = _sha256(
        json.dumps(
            source_fields,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )
    record = {
        "time_name": "100",
        "selected_times": ["100"],
        "input_fingerprint_sha256": source_fingerprint,
        "source_fields": source_fields,
        "fields": {"U": {"units": "m/s"}},
        "cell_count": 12,
        "imported_field_summary": {"U": {"status": "PASS"}},
        "native_vtk_parity": {"U": {"status": "PASS"}},
        "cleanroomx_analysis_import": {"status": "PASS"},
        "surface_phi_parity": None,
        "assets": assets,
        "foamToVTK_log_sha256": _sha256(log_bytes),
        "import_status": "PASS_DIAGNOSTIC_ONLY",
        "scientific_validation": "BLOCKED",
    }
    receipt_path = output / "receipt.json"
    receipt_document = {
        "schema_version": "cleanroomx.openfoam-result-sync.v2",
        "simulation_id": SIMULATION_ID,
        "case_id": f"configuration_{configuration}",
        "configuration_hash": CONFIGURATION_HASH,
        "time_name": "100",
        "record": record,
    }
    receipt_bytes = (json.dumps(receipt_document, sort_keys=True, indent=2) + "\n").encode()
    receipt_path.write_bytes(receipt_bytes)
    record["receipt"] = {
        "path": receipt_path.relative_to(case).as_posix(),
        "sha256": _sha256(receipt_bytes),
    }
    manifest = {
        "schema_version": "cleanroomx.openfoam-result-sync.v2",
        "interpretation": "solver_output_import_and_integrity_only",
        "scientific_validation": "BLOCKED",
        "simulation_id": SIMULATION_ID,
        "case_id": f"configuration_{configuration}",
        "configuration_hash": CONFIGURATION_HASH,
        "solver_release": "OpenFOAM Foundation v10",
        "solver_build": "10-test-build",
        "status": "results_synced",
        "solver_returncode": 0,
        "solver_log_status": "completed",
        "record_count": 1,
        "error_count": 0,
        "records": {"100": record},
        "errors": [],
    }
    (case / "sync_manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return case


def test_openfoam_sync_export_is_hash_linked_and_keeps_validation_blocked(tmp_path):
    _write_case(tmp_path)

    graph = proofgraph_from_openfoam_sync_results(tmp_path, SIMULATION_ID)
    document = graph.to_dict()
    proofgraph_from_dict(document)

    assert document["graph_sha256"]
    assert len(document["evidence"]) == 1
    evidence = document["evidence"][0]
    manifest = json.loads(
        (
            tmp_path
            / SIMULATION_ID
            / "configuration_1"
            / "sync_manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert evidence["kind"] == "simulation"
    assert evidence["value"]["asset_hashes_verified"] is True
    assert evidence["value"]["integrity_scope"] == "local_hash_link_consistency_not_authenticity"
    assert evidence["value"]["scientific_validation"] == "BLOCKED"
    assert evidence["value"]["records"][0]["assets"][0]["sha256"]
    assert (
        evidence["value"]["records"][0]["input_fingerprint_sha256"]
        == manifest["records"]["100"]["input_fingerprint_sha256"]
    )

    statuses = {item["id"]: item["status"] for item in document["verdicts"]}
    assert statuses["VERDICT-OPENFOAM-CFG-1-ARTIFACT-INTEGRITY"] == "pass"
    assert statuses["VERDICT-OPENFOAM-CFG-1-SCIENTIFIC-VALIDATION"] == "not_checked"
    for configuration in (2, 3):
        assert statuses[f"VERDICT-OPENFOAM-CFG-{configuration}-ARTIFACT-INTEGRITY"] == "not_checked"
        assert statuses[f"VERDICT-OPENFOAM-CFG-{configuration}-SCIENTIFIC-VALIDATION"] == "not_checked"


def test_openfoam_sync_export_rejects_changed_result_asset(tmp_path):
    case = _write_case(tmp_path)
    asset = case / "results" / "time_100" / "VTK" / "field.vtk"
    asset.write_bytes(b"modified after synchronization")

    with pytest.raises(ValueError, match="hash or size"):
        proofgraph_from_openfoam_sync_results(tmp_path, SIMULATION_ID)


def test_openfoam_sync_export_rejects_unsafe_asset_path(tmp_path):
    case = _write_case(tmp_path)
    manifest_path = case / "sync_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["records"]["100"]["assets"][0]["path"] = "../outside.vtk"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="escapes"):
        proofgraph_from_openfoam_sync_results(tmp_path, SIMULATION_ID)


def test_openfoam_sync_export_rejects_windows_drive_asset_path(tmp_path):
    case = _write_case(tmp_path)
    manifest_path = case / "sync_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["records"]["100"]["assets"][0]["path"] = "C:/outside.vtk"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="safe relative POSIX"):
        proofgraph_from_openfoam_sync_results(tmp_path, SIMULATION_ID)


def test_openfoam_sync_export_rejects_case_id_from_another_configuration(tmp_path):
    case = _write_case(tmp_path)
    manifest_path = case / "sync_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    record = manifest["records"]["100"]
    receipt_path = case / record["receipt"]["path"]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    # Keep the manifest and receipt mutually consistent so this exercises the
    # missing directory-to-configuration identity check.
    manifest["case_id"] = "configuration_2"
    receipt["case_id"] = "configuration_2"
    receipt_bytes = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode()
    receipt_path.write_bytes(receipt_bytes)
    record["receipt"]["sha256"] = _sha256(receipt_bytes)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="does not match its configuration directory"):
        proofgraph_from_openfoam_sync_results(tmp_path, SIMULATION_ID)


def test_openfoam_sync_export_recomputes_source_field_fingerprint(tmp_path):
    case = _write_case(tmp_path)
    manifest_path = case / "sync_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["records"]["100"]["source_fields"]["U"]["sha256"] = "d" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="input fingerprint"):
        proofgraph_from_openfoam_sync_results(tmp_path, SIMULATION_ID)


def test_openfoam_sync_export_is_atomic_and_serializes_valid_graph(tmp_path):
    _write_case(tmp_path)
    destination = tmp_path / "proofgraph.json"

    document = export_openfoam_proofgraph(tmp_path, SIMULATION_ID, destination)

    assert json.loads(destination.read_text(encoding="utf-8")) == document
    assert destination.read_bytes().endswith(b"\n")
    assert proofgraph_from_dict(document).to_dict() == document


def test_openfoam_sync_export_requires_at_least_one_manifest(tmp_path):
    (tmp_path / SIMULATION_ID).mkdir()

    with pytest.raises(ValueError, match="No valid OpenFOAM"):
        proofgraph_from_openfoam_sync_results(tmp_path, SIMULATION_ID)
