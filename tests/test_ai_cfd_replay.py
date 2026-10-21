"""Synthetic fixtures test replay binding, NOT a genuine solver run."""
from __future__ import annotations

import copy
import json

import pytest

from cleanroomx import ai_cfd_replay
from cleanroomx.ai_assistant_cli import build_offline_review, main
from cleanroomx.cfd_multizone_review import review_recorded_multizone
from cleanroomx.project import (
    capture_project_file_revision, new_project, save_project_document,
)


@pytest.fixture
def recorded(tmp_path):
    path = tmp_path / "project.json"
    project = new_project("Case replay contract")
    save_project_document(path, project)
    digest = capture_project_file_revision(path).sha256
    report = {
        "schema": "cleanroomx.multizone-results.v1",
        "scenario": "all_doors_open",
        "time_name": "100",
        "density_kg_m3": 1.2,
        "vertical_tolerance_m_s": 0.01,
        "pressure_reference": {"room_id": "B"},
        "provenance": {
            "project_source_sha256": digest,
            "manifest_sha256": "a" * 64,
            "run_receipt_sha256": "b" * 64,
        },
        "mesh": {"mesh_ok": True, "cells": 10},
        "solver_reported_convergence": False,
        "numerics": {"selected_iteration_reported_convergence": False},
        "rooms": {
            "A": {
                "name": "A", "mean_pressure_pa_relative_to_reference": 3.0,
                "net_outward_imbalance_m3_s": 0.01,
                "net_imbalance_fraction_of_throughflow": 0.02,
            },
            "B": {
                "name": "B", "mean_pressure_pa_relative_to_reference": 0.0,
                "net_outward_imbalance_m3_s": -0.01,
                "net_imbalance_fraction_of_throughflow": 0.02,
            },
        },
        "doors": {
            "AB": {
                "from_room": "A", "to_room": "B",
                "computed_delta_pressure_pa": 3.0,
                "design_delta_pressure_target_pa": 5.0,
                "computed_net_transfer_m3_s": 0.2,
                "computed_forward_m3_s": 0.3,
                "computed_reverse_m3_s": 0.1,
                "computed_face_count": 10,
                "open_face_count": 10,
            },
        },
        "global_net_outward_imbalance_m3_s": 0.0,
        "flow_balance": {
            "boundary_inflow_m3_s": 1.0,
            "boundary_outflow_m3_s": 1.0,
            "relative_boundary_imbalance": 0.0,
        },
    }
    export = tmp_path / "export"
    export.mkdir()
    (export / "report.json").write_text(json.dumps(report), encoding="utf-8")
    (export / "engineering-review.json").write_text(
        json.dumps(review_recorded_multizone(report)), encoding="utf-8",
    )
    case = tmp_path / "case"
    case.mkdir()
    return path, project, export, case, report


def test_case_replay_uses_canonical_analyzer_and_stays_hold(recorded, monkeypatch):
    path, project, export, case, report = recorded
    original_source = path.read_bytes()
    original_report = (export / "report.json").read_bytes()
    calls = []

    def analyzer(directory, **kwargs):
        calls.append((directory, kwargs))
        return {**copy.deepcopy(report), "cells": [], "residual_history": []}

    monkeypatch.setattr(ai_cfd_replay, "analyze_multizone_case", analyzer)
    evidence = ai_cfd_replay.replay_recorded_cfd(
        export, case, project=project, project_path=path,
    )
    assert calls == [(case, {
        "density_kg_m3": 1.2, "reference_room_id": "B",
        "vertical_tolerance_m_s": 0.01, "time_name": "100",
    })]
    assert evidence["report_matches_recomputed_fields"] is True
    assert evidence["status"] == "recorded_case_consistent"
    assert evidence["solver_producer_authenticated"] is False
    assert evidence["physical_validation_established"] is False
    assert evidence["engineering_release"] == "HOLD"
    assert path.read_bytes() == original_source
    assert (export / "report.json").read_bytes() == original_report


def test_case_replay_rejects_export_vs_recorded_field_mismatch(recorded, monkeypatch):
    path, project, export, case, report = recorded
    prior = copy.deepcopy(report)
    report["rooms"]["A"]["mean_pressure_pa_relative_to_reference"] = 4.0
    report["doors"]["AB"]["computed_delta_pressure_pa"] = 4.0
    (export / "report.json").write_text(json.dumps(report), encoding="utf-8")
    (export / "engineering-review.json").write_text(
        json.dumps(review_recorded_multizone(report)), encoding="utf-8",
    )
    monkeypatch.setattr(
        ai_cfd_replay, "analyze_multizone_case",
        lambda *args, **kwargs: {**prior, "cells": [], "residual_history": []},
    )
    with pytest.raises(ValueError, match="does not match recomputed"):
        ai_cfd_replay.replay_recorded_cfd(
            export, case, project=project, project_path=path,
        )


def test_case_replay_rejects_missing_and_symlinked_case(recorded, tmp_path):
    path, project, export, case, _ = recorded
    with pytest.raises(ValueError, match="real directory"):
        ai_cfd_replay.replay_recorded_cfd(
            export, tmp_path / "missing", project=project, project_path=path,
        )
    alias = tmp_path / "case-alias"
    try:
        alias.symlink_to(case, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("This environment prohibits symlink creation")
    with pytest.raises(ValueError, match="not a symlink"):
        ai_cfd_replay.replay_recorded_cfd(
            export, alias, project=project, project_path=path,
        )


def test_cli_rejects_case_without_export(recorded):
    path, _, _, case, _ = recorded
    with pytest.raises(ValueError, match="requires --cfd-export"):
        build_offline_review(path, cfd_case=case)


def test_cli_json_exposes_case_replay_without_model_or_solver(recorded, monkeypatch, capsys):
    from cleanroomx import ai_assistant_cli
    path, _, export, case, _ = recorded
    called = []
    def fake_replay(export_directory, case_directory, **kwargs):
        called.append((export_directory, case_directory))
        return {
            "status": "recorded_case_consistent",
            "engineering_release": "HOLD",
            "note": "Synthetic replay fixture only.",
        }
    monkeypatch.setattr(ai_assistant_cli, "replay_recorded_cfd", fake_replay)
    assert main([
        str(path), "--cfd-export", str(export),
        "--cfd-case", str(case), "--format", "json",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert called == [(str(export), str(case))]
    assert result["model_used"] is False
    assert result["network_used"] is False
    assert result["context"]["cfd_case_replay"]["engineering_release"] == "HOLD"
