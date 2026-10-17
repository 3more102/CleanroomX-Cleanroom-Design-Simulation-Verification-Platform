from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import sys

import pytest

from cleanroomx import cfd_pipeline_cli
from cleanroomx.cfd_sync import SNAPSHOT_SCHEMA, STATE_SCHEMA
from cleanroomx.cfd_openfoam_timeseries import (
    export_openfoam_time_series_csv,
    read_openfoam_sync_time_series,
)
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
        "field_data": {},
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


def _write_field_series_store(tmp_path):
    root, state, snapshot, snapshot_path = _write_store(tmp_path)

    def field_data(mean, minimum, maximum):
        return {
            "velocity": {
                "array_name": "U",
                "units": "m/s",
                "units_source": "explicit_caller_field_map",
                "components": 3,
                "summary": {
                    "minimum": minimum,
                    "maximum": maximum,
                    "mean": mean,
                    "mean_weighting": "cell_volume",
                },
            }
        }

    def store_snapshot(record, value):
        value["fields"]["field_data"] = field_data(
            record["mean"], record["minimum"], record["maximum"]
        )
        fields_hash = _canonical_sha256(value["fields"])
        value["fields_sha256"] = fields_hash
        raw = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
        target = root / value["snapshot_relative_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        record_data = state["records"][record["relative_path"]]
        record_data.update({
            "source_sha256": value["source_sha256"],
            "fields_sha256": fields_hash,
            "snapshot_sha256": hashlib.sha256(raw).hexdigest(),
            "snapshot_size_bytes": len(raw),
            "mesh_cells": value["fields"]["mesh_cells"],
        })

    original_record = {
        **state["records"]["case-a_100.vtk"],
        "mean": [1.0, 0.0, 0.0],
        "minimum": [0.5, 0.0, 0.0],
        "maximum": [1.5, 0.0, 0.0],
    }
    original_value = copy.deepcopy(snapshot)
    original_value["snapshot_relative_path"] = snapshot_path
    original_value["fields"]["source_sha256"] = original_record["source_sha256"]
    store_snapshot(original_record, original_value)

    source_path = "case-a_200.vtk"
    source_hash = "c" * 64
    token = hashlib.sha256((state["simulation_id"] + "\0" + source_path).encode()).hexdigest()
    second_value = copy.deepcopy(snapshot)
    second_value.update({
        "solver_time": "200",
        "source_relative_path": source_path,
        "snapshot_relative_path": f"snapshots/{token}.json",
        "source_sha256": source_hash,
        "imported_at": "2026-10-17T09:00:02Z",
        "first_seen_at": "2026-10-17T09:00:01Z",
    })
    second_value["fields"]["source_sha256"] = source_hash
    second_record = {
        "relative_path": source_path,
        "case_id": "case-a",
        "logical_key": "case-a\0 200",
        "solver_time": "200",
        "canonical_solver_time": "200",
        "status": "imported",
        "source_sha256": source_hash,
        "mesh_cells": 16,
        "snapshot_relative_path": f"snapshots/{token}.json",
        "mean": [1.5, 0.1, 0.0],
        "minimum": [1.0, 0.0, 0.0],
        "maximum": [2.0, 0.2, 0.0],
    }
    state["records"][source_path] = {
        key: value for key, value in second_record.items()
        if key not in {"mean", "minimum", "maximum"}
    }
    store_snapshot(second_record, second_value)
    (root / "sync-state.json").write_text(
        json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return root


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


def test_openfoam_proofgraph_exposes_descriptive_field_time_series(tmp_path):
    root = _write_field_series_store(tmp_path)

    graph = build_openfoam_sync_proofgraph(root).to_dict()
    validated = proofgraph_from_dict(graph)
    series = next(
        item for item in graph["evidence"]
        if item["property_name"] == "openfoam_field_time_series"
    )
    component_metrics = series["value"]["component_metrics"]
    upstream = series["provenance"][0]["upstream_evidence_ids"]

    assert series["value"]["coverage_status"] == "complete"
    assert series["value"]["same_mesh_verified"] is False
    assert series["value"]["solver_time_semantics"].startswith("Numeric OpenFOAM time labels")
    assert [item["solver_time_label"] for item in series["value"]["samples"]] == ["100", "200"]
    assert component_metrics[0]["absolute_range"] == pytest.approx(0.5)
    assert component_metrics[0]["first_to_last_delta"] == pytest.approx(0.5)
    assert component_metrics[0]["relative_range_over_mean_absolute_value"] == pytest.approx(0.4)
    assert component_metrics[1]["relative_range_over_mean_absolute_value"] == pytest.approx(2.0)
    assert component_metrics[2]["relative_range_over_mean_absolute_value"] == 0.0
    assert len(upstream) == 2
    assert series["value"]["scientific_validation"] == "BLOCKED"
    assert graph["verification_runs"][0]["metadata"]["field_time_series_count"] == 1
    assert _verdicts(graph)["OPENFOAM-SCIENTIFIC-VALIDATION"] == "not_checked"
    assert validated.to_dict()["graph_sha256"] == graph["graph_sha256"]


def test_openfoam_timeseries_reader_exports_integrity_bound_rows(tmp_path):
    root = _write_field_series_store(tmp_path)

    series = read_openfoam_sync_time_series(root)
    output = tmp_path / "velocity.csv"
    export_openfoam_time_series_csv(
        series,
        output,
        case_id="case-a",
        field="velocity",
    )
    with output.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))

    assert series["integrity_status"] == "pass"
    assert series["scientific_validation"] == "BLOCKED"
    assert [row["solver_time_label"] for row in rows] == ["100", "200"]
    assert rows[0]["mean_component_1"] == "1"
    assert rows[1]["mean_component_1"] == "1.5"
    assert rows[0]["mean_weighting"] == "cell_volume"
    assert rows[0]["coverage_status"] == "complete"
    assert rows[0]["field_sample_count"] == rows[0]["case_snapshot_count"] == "2"
    assert rows[0]["scientific_validation"] == "BLOCKED"
    assert rows[0]["solver_time_units"] == "not_asserted"
    assert all(len(row["snapshot_sha256"]) == 64 for row in rows)
    assert all(len(row["source_vtk_sha256_recorded_at_import"]) == 64 for row in rows)


def test_openfoam_timeseries_reports_partial_field_coverage(tmp_path):
    root = _write_field_series_store(tmp_path)
    state_path = root / "sync-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    second_record = state["records"]["case-a_200.vtk"]
    snapshot_path = root / second_record["snapshot_relative_path"]
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot["fields"]["field_data"] = {}
    fields_hash = _canonical_sha256(snapshot["fields"])
    snapshot["fields_sha256"] = fields_hash
    raw = (json.dumps(snapshot, sort_keys=True, separators=(",", ":")) + "\n").encode()
    snapshot_path.write_bytes(raw)
    second_record["fields_sha256"] = fields_hash
    second_record["snapshot_sha256"] = hashlib.sha256(raw).hexdigest()
    second_record["snapshot_size_bytes"] = len(raw)
    state_path.write_text(
        json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    series = read_openfoam_sync_time_series(root)
    assert len(series["rows"]) == 1
    assert series["rows"][0]["coverage_status"] == "partial"
    assert series["rows"][0]["field_sample_count"] == 1
    assert series["rows"][0]["case_snapshot_count"] == 2


def test_openfoam_timeseries_export_refuses_to_overwrite_snapshot(tmp_path):
    root = _write_field_series_store(tmp_path)
    series = read_openfoam_sync_time_series(root)
    protected = next(
        Path(path)
        for path in series["protected_inputs"]
        if "/snapshots/" in path
    )
    before = protected.read_bytes()

    with pytest.raises(ValueError, match="output path must be different"):
        export_openfoam_time_series_csv(
            series,
            protected,
            case_id="case-a",
            field="velocity",
        )

    assert protected.read_bytes() == before


def test_openfoam_timeseries_export_cli_publishes_csv(tmp_path, monkeypatch):
    root = _write_field_series_store(tmp_path)
    output = tmp_path / "cli-velocity.csv"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cleanroomx-cfd-pipeline",
            "timeseries-export",
            str(root),
            "--case-id",
            "case-a",
            "--field",
            "velocity",
            "--output",
            str(output),
        ],
    )

    assert cfd_pipeline_cli.main() == 0
    with output.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 2


def test_openfoam_time_series_exports_verified_component_means_and_hashes(tmp_path):
    root = _write_field_series_store(tmp_path)

    series = read_openfoam_sync_time_series(root)
    output = tmp_path / "velocity-time-series.csv"
    export_openfoam_time_series_csv(
        series,
        output,
        case_id="case-a",
        field="velocity",
    )
    rows = list(csv.DictReader(io.StringIO(output.read_text(encoding="utf-8"))))

    assert [(row["solver_time_label"], row["mean_component_1"]) for row in rows] == [
        ("100", "1"),
        ("200", "1.5"),
    ]
    assert rows[0]["units"] == "m/s"
    assert rows[0]["mean_weighting"] == "cell_volume"
    assert rows[0]["minimum_component_1"] == "0.5"
    assert rows[0]["maximum_component_1"] == "1.5"
    assert rows[0]["source_vtk_sha256_recorded_at_import"] == "b" * 64
    assert rows[1]["source_vtk_sha256_recorded_at_import"] == "c" * 64
    assert all(row["snapshot_sha256"] for row in rows)
    assert series["scientific_validation"] == "BLOCKED"


def test_openfoam_time_series_export_protects_verified_result_inputs(tmp_path):
    root = _write_field_series_store(tmp_path)
    series = read_openfoam_sync_time_series(root)
    state_path = root / "sync-state.json"
    before = state_path.read_bytes()

    with pytest.raises(ValueError, match="output path must be different"):
        export_openfoam_time_series_csv(
            series,
            state_path,
            case_id="case-a",
            field="velocity",
        )

    assert state_path.read_bytes() == before


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

