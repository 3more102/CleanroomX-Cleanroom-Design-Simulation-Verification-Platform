"""Regression tests for the sync-vtk v3 result-analysis adapter; no live solver."""
import json

import pytest

pytest.importorskip("vtk")

from cleanroomx.cfd_analysis_export import export_analysis_bundle
from cleanroomx.cfd_result_analysis import (
    analyze_selected_result_store, analyze_synced_results, build_analysis_graph,
)
from cleanroomx.cfd_sync import synchronize_openfoam_vtk_once
from cleanroomx.proofgraph_io import proofgraph_from_dict
from cfd_analysis_fixtures import write_vtk


RUN = "synthetic-vtk-run"
FIELD_MAP = {
    "schema_version": "cleanroomx.cfd-vtk-field-map.v1",
    "fields": {
        "p": {"semantic": "kinematic_pressure", "units": "m^2/s^2"},
        "T": {"semantic": "temperature_kelvin", "units": "K"},
        "k": {"semantic": "turbulent_kinetic_energy", "units": "m^2/s^2"},
    },
}


def make_store(tmp_path, *, field_map=FIELD_MAP):
    source = tmp_path / "vtk-source"
    dataset_dir = source / "configuration_1" / "100"
    dataset_dir.mkdir(parents=True)
    dataset = dataset_dir / "internal.vtk"
    write_vtk(dataset)
    configuration = tmp_path / "configuration.json"
    configuration.write_text('{"fixture":"synthetic"}\n', encoding="utf-8")
    output = tmp_path / "vtk-result-store"
    options = {
        "simulation_id": RUN,
        "configuration_file": configuration,
        "stable_seconds": 0.0,
    }
    if field_map is not None:
        options["field_map"] = field_map
    synchronize_openfoam_vtk_once(source, output, **options)
    report = synchronize_openfoam_vtk_once(source, output, **options)
    assert report["counts"].get("imported") == 1
    return source, dataset, configuration, output, report


def test_v3_snapshot_store_loads_in_shared_analysis_gui_and_exports(tmp_path):
    pytest.importorskip("matplotlib")
    _source, _dataset, _configuration, output, _sync_report = make_store(tmp_path)

    result = analyze_synced_results(output, RUN)
    assert result.report["mode"] == "vtk_snapshot_sync"
    assert result.report["scientific_validation"] == "BLOCKED"
    assert result.report["reproducibility"]["native_source_bytes_rehashed"] is False
    assert result.report["reproducibility"]["vtk_source_bytes_rehashed"] is True
    assert result.report["snapshots"][0]["time_name"] == "100"
    assert result.report["snapshots"][0]["statistics"]["speed"]["mean"] == pytest.approx(25 / 3)
    assert result.report["snapshots"][0]["statistics"]["p"]["mean"] == pytest.approx(6.0)
    assert result.report["snapshots"][0]["statistics"]["T"]["mean"] == pytest.approx(320.0)
    assert any(item["analysis"] == "turbulent_kinetic_energy" and item["status"] == "not_available"
               for item in result.report["availability"])

    selected = analyze_selected_result_store(output)
    assert selected.report == result.report
    graph = build_analysis_graph(
        [result], kind="cell_3d", field_name="p",
        case_id="configuration_1", time_name="100",
    )
    assert graph["series"]
    assert graph["series"][0]["points"]
    export = export_analysis_bundle([result], [graph], tmp_path / "analysis-export")
    proofgraph = proofgraph_from_dict(json.loads((export / "proofgraph-01.json").read_text(encoding="utf-8")))
    assert proofgraph.verdicts[0].status == "pass"
    assert result.report["scientific_validation"] == "BLOCKED"


def test_v3_snapshot_store_without_field_map_retains_velocity_analysis(tmp_path):
    _source, _dataset, _configuration, output, _sync_report = make_store(tmp_path, field_map=None)
    result = analyze_synced_results(output, RUN)
    assert set(result.report["snapshots"][0]["statistics"]) >= {"speed", "U_x", "U_y", "U_z"}
    assert result.report["snapshots"][0]["statistics"]["speed"]["mean"] == pytest.approx(25 / 3)


def test_v3_snapshot_hash_or_source_tampering_fails_closed(tmp_path):
    _source, _dataset, _configuration, output, report = make_store(tmp_path)
    snapshot_path = output / report["imported"][0]["snapshot_relative_path"]
    snapshot_path.write_bytes(snapshot_path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="snapshot hash or size"):
        analyze_synced_results(output, RUN)

    _source, dataset, _configuration, output, report = make_store(tmp_path / "second")
    dataset.write_bytes(dataset.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="source bytes"):
        analyze_synced_results(output, RUN)


def test_v3_snapshot_adapter_rejects_native_field_verification_claim(tmp_path):
    _source, _dataset, _configuration, output, _report = make_store(tmp_path)
    native_case = tmp_path / "native-case"
    native_case.mkdir()
    with pytest.raises(ValueError, match="does not bind original native OpenFOAM fields"):
        analyze_synced_results(
            output, RUN, case_directory=native_case, verify_native_sources=True
        )


def test_v3_snapshot_adapter_rejects_field_map_identity_mismatch(tmp_path):
    _source, _dataset, _configuration, output, _report = make_store(tmp_path)
    state_path = output / "sync-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["field_map_sha256"] = "0" * 64
    state_path.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
    with pytest.raises(ValueError, match="field-map identity"):
        analyze_synced_results(output, RUN)
