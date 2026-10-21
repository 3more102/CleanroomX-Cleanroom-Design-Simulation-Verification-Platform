"""Synthetic export contract fixtures ONLY: not actual OpenFOAM measurements."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from cleanroomx.ai_cfd_evidence import (
    CFD_ASSISTANT_SCHEMA,
    _recorded_report,
    bound_cfd_evidence,
    format_cfd_evidence,
)
from cleanroomx.cfd_multizone_review import review_recorded_multizone
from cleanroomx.project import (
    capture_project_file_revision, load_project_document,
    new_project, save_project_document,
)


def _synthetic_export(source_sha: str, *, convergence: bool = False) -> dict:
    return {
        "schema": "cleanroomx.multizone-results.v1",
        "scenario": "all_doors_open",
        "time_name": "600",
        "provenance": {
            "project_source_sha256": source_sha,
            "manifest_sha256": "a" * 64,
            "run_receipt_sha256": "b" * 64,
        },
        "mesh": {"mesh_ok": True, "cells": 10},
        "solver_reported_convergence": convergence,
        "numerics": {
            "selected_iteration_reported_convergence": convergence,
        },
        "rooms": {
            "A": {
                "name": "Room A", "mean_pressure_pa_relative_to_reference": 3.25,
                "mean_speed_m_s": 0.12,
                "net_outward_imbalance_m3_s": 0.01,
                "net_imbalance_fraction_of_throughflow": 0.02,
            },
            "B": {
                "name": "Room B", "mean_pressure_pa_relative_to_reference": 0.0,
                "mean_speed_m_s": 0.08,
                "net_outward_imbalance_m3_s": -0.01,
                "net_imbalance_fraction_of_throughflow": 0.02,
            },
        },
        "doors": {
            "doorAB": {
                "from_room": "A", "to_room": "B",
                "computed_delta_pressure_pa": 3.25,
                "design_delta_pressure_target_pa": 5.0,
                "computed_net_transfer_m3_s": 0.2,
                "computed_forward_m3_s": 0.3,
                "computed_reverse_m3_s": 0.1,
                "computed_face_count": 70, "open_face_count": 70,
            },
        },
        "global_net_outward_imbalance_m3_s": 0.0,
        "flow_balance": {
            "boundary_inflow_m3_s": 1.0,
            "boundary_outflow_m3_s": 1.0,
            "relative_boundary_imbalance": 0.0,
        },
    }


def _saved_project_and_export(tmp_path):
    project_path = tmp_path / "facility.json"
    project = new_project("Cleanroom CFD")
    save_project_document(project_path, project)
    sha = capture_project_file_revision(project_path).sha256
    export = tmp_path / "cfd-export"
    export.mkdir()
    report = _synthetic_export(sha)
    (export / "report.json").write_text(
        json.dumps(report, allow_nan=False), encoding="utf-8"
    )
    (export / "engineering-review.json").write_text(
        json.dumps(review_recorded_multizone(report), allow_nan=False),
        encoding="utf-8",
    )
    return project_path, project, export, report


def test_matches_exact_saved_project_and_recomputes_engineering_hold(tmp_path):
    project_path, project, export, report = _saved_project_and_export(tmp_path)
    original_project = project_path.read_bytes()
    original_export = (export / "report.json").read_bytes()
    evidence = bound_cfd_evidence(
        export, project=project, project_path=project_path
    )
    assert evidence["schema"] == CFD_ASSISTANT_SCHEMA
    assert evidence["saved_project_source_sha256"] == capture_project_file_revision(
        project_path
    ).sha256
    assert evidence["source_iteration"] == "600"
    assert evidence["engineering_release"] == "HOLD"
    assert evidence["closed_door_5pa_demonstrated"] is False
    assert evidence["solver_reported_convergence_at_selected_iteration"] is False
    assert evidence["room_count"] == 2
    assert evidence["door_count"] == 1
    assert evidence["doors"][0]["delta_minus_target_pa"] == pytest.approx(-1.75)
    assert "OPEN_DOOR_SCENARIO" in {x["code"] for x in evidence["review_reasons"]}
    assert "NOT CERTIFIED" in format_cfd_evidence(evidence)
    assert "independent solver" in format_cfd_evidence(evidence)
    assert project_path.read_bytes() == original_project
    assert (export / "report.json").read_bytes() == original_export


def test_wrong_project_source_revision_never_binds(tmp_path):
    project_path, project, export, report = _saved_project_and_export(tmp_path)
    report["provenance"]["project_source_sha256"] = "f" * 64
    (export / "report.json").write_text(json.dumps(report), encoding="utf-8")
    (export / "engineering-review.json").write_text(
        json.dumps(review_recorded_multizone(report)), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="different saved project revision"):
        bound_cfd_evidence(export, project=project, project_path=project_path)


def test_unsaved_project_changes_block_attaching_export(tmp_path):
    project_path, project, export, _ = _saved_project_and_export(tmp_path)
    project.description = "Unsaved editing in memory"
    with pytest.raises(ValueError, match="unsaved changes"):
        bound_cfd_evidence(export, project=project, project_path=project_path)


def test_tampered_companion_review_is_rejected(tmp_path):
    project_path, project, export, _ = _saved_project_and_export(tmp_path)
    original = json.loads((export / "engineering-review.json").read_text())
    original["engineering_release"] = "PASS"
    (export / "engineering-review.json").write_text(
        json.dumps(original), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="does not match"):
        bound_cfd_evidence(export, project=project, project_path=project_path)


def test_missing_companion_is_recomputed_but_not_authenticated(tmp_path):
    project_path, project, export, _ = _saved_project_and_export(tmp_path)
    (export / "engineering-review.json").unlink()
    evidence = bound_cfd_evidence(export, project=project, project_path=project_path)
    assert evidence["companion_review_sha256"] is None
    assert evidence["engineering_release"] == "HOLD"
    assert any("not proof" in x.lower() for x in evidence["limitations"])


def test_invalid_nonfinite_and_oversized_json_rejected(tmp_path):
    project_path, project, export, _ = _saved_project_and_export(tmp_path)
    (export / "report.json").write_text('{"value":NaN}', encoding="utf-8")
    with pytest.raises(ValueError, match="non-finite"):
        bound_cfd_evidence(export, project=project, project_path=project_path)
    (export / "report.json").write_bytes(b" " * (4 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match="maximum"):
        bound_cfd_evidence(export, project=project, project_path=project_path)


def test_symlinked_report_refused(tmp_path):
    project_path, project, export, report = _saved_project_and_export(tmp_path)
    real = export / "real-report.json"
    real.write_text(json.dumps(report), encoding="utf-8")
    (export / "report.json").unlink()
    try:
        (export / "report.json").symlink_to(real)
    except (NotImplementedError, OSError):
        pytest.skip("Symlink creation not permitted by this filesystem")
    with pytest.raises(ValueError, match="regular exported"):
        bound_cfd_evidence(export, project=project, project_path=project_path)


def test_report_change_during_read_rejected(tmp_path, monkeypatch):
    from cleanroomx import ai_cfd_evidence
    project_path, project, export, report = _saved_project_and_export(tmp_path)
    original = ai_cfd_evidence.load_strict_json_snapshot
    calls = 0

    def switching(path, **kwargs):
        nonlocal calls
        loaded = original(path, **kwargs)
        if Path(path).name == "report.json":
            calls += 1
            if calls == 1:
                # Content modification after the stable initial read.
                (export / "report.json").write_text(
                    json.dumps({**report, "time_name": "601"}),
                    encoding="utf-8",
                )
        return loaded

    monkeypatch.setattr(ai_cfd_evidence, "load_strict_json_snapshot", switching)
    with pytest.raises(ValueError, match="changed during"):
        bound_cfd_evidence(export, project=project, project_path=project_path)


def test_user_cannot_supply_released_cfd_evidence_to_formatter():
    bogus = {
        "schema": CFD_ASSISTANT_SCHEMA,
        "schema_version": 1,
        "engineering_release": "PASS",
        "closed_door_5pa_demonstrated": True,
    }
    with pytest.raises(ValueError, match="Invalid"):
        format_cfd_evidence(bogus)



def test_headless_review_can_attach_matching_cfd_evidence(tmp_path, capsys):
    from cleanroomx.ai_assistant_cli import build_offline_review, main

    project_path, project, export, report = _saved_project_and_export(tmp_path)
    envelope = build_offline_review(project_path, cfd_export=export, actions=True)
    assert envelope["network_used"] is False
    assert envelope["model_used"] is False
    assert envelope["context"]["cfd_evidence"]["engineering_release"] == "HOLD"
    assert envelope["action_plan"]["schema"] == "cleanroomx.ai-assistant-action-plan"

    assert main([str(project_path), "--cfd-export", str(export)]) == 0
    assert "RECORDED CFD EXPORT REVIEW" in capsys.readouterr().out

    report["provenance"]["project_source_sha256"] = "f" * 64
    (export / "report.json").write_text(json.dumps(report), encoding="utf-8")
    (export / "engineering-review.json").write_text(
        json.dumps(review_recorded_multizone(report)), encoding="utf-8"
    )
    assert main([str(project_path), "--cfd-export", str(export)]) == 2
    assert "different saved project revision" in capsys.readouterr().err
