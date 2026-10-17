from __future__ import annotations

import hashlib
import json
import sys

import pytest

from cleanroomx import cfd_pipeline_cli
from cleanroomx.cfd_sync import SNAPSHOT_SCHEMA, STATE_SCHEMA
from cleanroomx.proofgraph_io import proofgraph_from_dict
from cleanroomx.proofgraph_openfoam import build_openfoam_sync_proofgraph


def _canonical_sha256(value: dict) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_store(tmp_path, *, include_pending: bool = False):
    root = tmp_path / "result-store"
    snapshots = root / "snapshots"
    snapshots.mkdir(parents=True)
    simulation_id = "simulation-001"
    config_hash = "a" * 64
    source_hash = "b" * 64
    source_path = "case-a_100.vtk"
    fields = {
        "source_sha256": source_hash,
        "mesh_cells": 16,
        "field_data": {"U": {"components": 3}},
    }
    fields_hash = _canonical_sha256(fields)
    snapshot = {
        "schema_version": SNAPSHOT_SCHEMA,
        "simulation_id": simulation_id,
        "configuration_sha256": config_hash,
        "field_map_sha256": None,
        "case_id": "case-a",
        "solver_time": "100",
        "source_relative_path": source_path,
        "source_sha256": source_hash,
        "source_size_bytes": 512,
        "source_mtime_ns": 1,
        "first_seen_at": "2026-10-17T09:00:00Z",
        "imported_at": "2026-10-17T09:00:01Z",
        "data_status": "imported",
        "scientific_validation": "BLOCKED",
        "fields_sha256": fields_hash,
        "fields": fields,
    }
    raw = (json.dumps(snapshot, sort_keys=True, separators=(",", ":")) + "\n").encode()
    token = hashlib.sha256((simulation_id + "\0" + source_path).encode()).hexdigest()
    snapshot_relative_path = f"snapshots/{token}.json"
    (root / snapshot_relative_path).write_bytes(raw)
    record = {
        "relative_path": source_path,
        "case_id": "case-a",
        "logical_key": "case-a\0 100",
        "solver_time": "100",
        "canonical_solver_time": "100",
        "status": "imported",
        "source_sha256": source_hash,
        "mesh_cells": 16,
        "fields_sha256": fields_hash,
        "snapshot_relative_path": snapshot_relative_path,
        "snapshot_sha256": hashlib.sha256(raw).hexdigest(),
        "snapshot_size_bytes": len(raw),
        "imported_at": snapshot["imported_at"],
    }
    records = {source_path: record}
    if include_pending:
        records["case-a_200.vtk"] = {
            "relative_path": "case-a_200.vtk",
            "case_id": "case-a",
            "solver_time": "200",
            "status": "pending_stability",
        }
    state = {
        "schema_version": STATE_SCHEMA,
        "simulation_id": simulation_id,
        "configuration_sha256": config_hash,
        "field_map_sha256": None,
        "source_root": str(tmp_path / "source-vtk"),
        "output_root": str(root),
        "created_at": "2026-10-17T09:00:00Z",
        "updated_at": "2026-10-17T09:00:01Z",
        "records": records,
    }
    (root / "sync-state.json").write_text(
        json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return root, state, snapshot, snapshot_relative_path


def _verdicts(graph: dict) -> dict[str, str]:
    return {item["requirement_id"]: item["status"] for item in graph["verdicts"]}


def test_openfoam_sync_result_exports_hash_verified_proofgraph(tmp_path):
    root, _state, _snapshot, _snapshot_path = _write_store(tmp_path)

    graph = build_openfoam_sync_proofgraph(root).to_dict()
    validated = proofgraph_from_dict(graph)

    assert _verdicts(graph) == {
        "OPENFOAM-SYNC-INTEGRITY": "pass",
        "OPENFOAM-SCIENTIFIC-VALIDATION": "not_checked",
    }
    assert graph["graph_sha256"] == validated.to_dict()["graph_sha256"]
    assert graph["verification_runs"][0]["metadata"]["scientific_validation"] == "BLOCKED"
    summary = next(
        item["value"]
        for item in graph["evidence"]
        if item["property_name"] == "openfoam_sync_integrity_summary"
    )
    assert summary["original_vtk_sources_rehashed"] is False
    assert summary["imported_snapshot_count"] == 1


def test_openfoam_sync_proofgraph_fails_closed_on_tampered_snapshot(tmp_path):
    root, _state, _snapshot, snapshot_path = _write_store(tmp_path)
    target = root / snapshot_path
    target.write_text(target.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(ValueError, match="snapshot SHA-256"):
        build_openfoam_sync_proofgraph(root)


def test_openfoam_sync_proofgraph_checks_canonical_fields_digest(tmp_path):
    root, state, snapshot, snapshot_path = _write_store(tmp_path)
    target = root / snapshot_path
    snapshot["fields"]["mesh_cells"] = 17
    raw = (json.dumps(snapshot, sort_keys=True, separators=(",", ":")) + "\n").encode()
    target.write_bytes(raw)
    state["records"]["case-a_100.vtk"]["snapshot_sha256"] = hashlib.sha256(raw).hexdigest()
    state["records"]["case-a_100.vtk"]["snapshot_size_bytes"] = len(raw)
    state["records"]["case-a_100.vtk"]["mesh_cells"] = 17
    (root / "sync-state.json").write_text(
        json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="fields digest"):
        build_openfoam_sync_proofgraph(root)


def test_openfoam_sync_proofgraph_warns_when_store_has_pending_results(tmp_path):
    root, _state, _snapshot, _snapshot_path = _write_store(tmp_path, include_pending=True)

    graph = build_openfoam_sync_proofgraph(root).to_dict()

    assert _verdicts(graph)["OPENFOAM-SYNC-INTEGRITY"] == "warning"
    assert _verdicts(graph)["OPENFOAM-SCIENTIFIC-VALIDATION"] == "not_checked"
    assert proofgraph_from_dict(graph).to_dict()["graph_sha256"] == graph["graph_sha256"]


def test_openfoam_sync_proofgraph_uses_no_pass_without_imported_snapshots(tmp_path):
    root, state, _snapshot, snapshot_path = _write_store(tmp_path)
    (root / snapshot_path).unlink()
    state["records"]["case-a_100.vtk"]["status"] = "pending_stability"
    (root / "sync-state.json").write_text(
        json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    graph = build_openfoam_sync_proofgraph(root).to_dict()

    assert _verdicts(graph)["OPENFOAM-SYNC-INTEGRITY"] == "not_checked"
    assert _verdicts(graph)["OPENFOAM-SCIENTIFIC-VALIDATION"] == "not_checked"


def test_openfoam_proofgraph_export_cli_publishes_protected_output(tmp_path, monkeypatch):
    root, _state, _snapshot, _snapshot_path = _write_store(tmp_path)
    output = tmp_path / "exported-proofgraph.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cleanroomx-cfd-pipeline",
            "proofgraph-export",
            str(root),
            "--output",
            str(output),
        ],
    )

    assert cfd_pipeline_cli.main() == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "cleanroomx.proofgraph"
    assert _verdicts(saved)["OPENFOAM-SYNC-INTEGRITY"] == "pass"


def test_openfoam_proofgraph_export_cli_will_not_overwrite_sync_input(
    tmp_path, monkeypatch, capsys
):
    root, _state, _snapshot, snapshot_path = _write_store(tmp_path)
    protected = root / snapshot_path
    before = protected.read_bytes()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cleanroomx-cfd-pipeline",
            "proofgraph-export",
            str(root),
            "--output",
            str(protected),
        ],
    )

    assert cfd_pipeline_cli.main() == 1
    assert protected.read_bytes() == before
    assert "output path must be different" in capsys.readouterr().err

