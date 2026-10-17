"""Numerical screening regressions; synthetic solver text, never physical evidence."""
from __future__ import annotations

import hashlib
import json

import pytest

from cleanroomx.cfd_pipeline_cli import build_parser
from cleanroomx import cfd_two_room_numerics as numerics


def _criteria():
    return {
        "schema_version": numerics.SCHEMA,
        "fields": ["Ux", "Uy", "Uz", "p"],
        "max_initial_residual": 0.1,
        "max_final_residual": 0.01,
        "max_global_continuity": 0.001,
        "window": 2,
    }


def _fixture(tmp_path, monkeypatch):
    case = tmp_path / "case"
    case.mkdir()
    content = []
    for step in (1, 2, 3):
        content.append(f"Time = {step}")
        for field in ("Ux", "Uy", "Uz", "p"):
            content.append(
                f"smoothSolver: Solving for {field}, "
                f"Initial residual = {0.03 / step:.8g}, "
                f"Final residual = {0.003 / step:.8g}, No Iterations 2"
            )
        content.append(
            f"time step continuity errors : sum local = 0.00001, "
            f"global = {-0.00001 / step:.8g}, cumulative = 0"
        )
    content.append("End")
    log = case / "simpleFoam.log"
    log.write_text("\n".join(content) + "\n", encoding="utf-8")
    receipt = tmp_path / "receipt.json"
    receipt.write_text(
        json.dumps({
            "receipt_sha256": "a" * 64,
            "manifest_sha256": "b" * 64,
            "stages": [
                {"command": "blockMesh", "log_path": "blockMesh.log", "log_sha256": "c" * 64},
                {
                    "command": "simpleFoam", "log_path": "simpleFoam.log",
                    "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
                },
            ],
        }),
        encoding="utf-8",
    )
    calls = []
    monkeypatch.setattr(
        numerics, "proofgraph_from_two_room_receipt",
        lambda case_path, receipt_path: calls.append((case_path, receipt_path)),
    )
    return case, receipt, log, calls


def _rewrite_receipt_log_sha(receipt, log):
    doc = json.loads(receipt.read_text(encoding="utf-8"))
    doc["stages"][1]["log_sha256"] = hashlib.sha256(log.read_bytes()).hexdigest()
    receipt.write_text(json.dumps(doc), encoding="utf-8")


def test_receipt_bound_numerical_screen_reports_only_log_screen(tmp_path, monkeypatch):
    case, receipt, log, calls = _fixture(tmp_path, monkeypatch)
    result = numerics.screen_two_room_numerics(case, receipt, _criteria())
    assert calls == [(case, receipt)]
    assert result["status"] == "PROJECT_NUMERICAL_SCREEN_MET"
    assert result["solver_convergence"] == "NOT_ASSESSED"
    assert result["scientific_validation"] == "BLOCKED"
    assert result["mesh_independence"] == "NOT_ASSESSED"
    assert result["source_solver_log_sha256"] == hashlib.sha256(log.read_bytes()).hexdigest()
    assert result["source_receipt_sha256"] == "a" * 64
    assert len(result["unsigned_policy_sha256"]) == 64
    assert result["log_screen"]["status"] == "numerically_screened"
    assert result["log_screen"]["fields"]["p"]["sample_count"] == 3


def test_explicit_limit_violation_reports_not_met_without_validating_physics(tmp_path, monkeypatch):
    case, receipt, _, _ = _fixture(tmp_path, monkeypatch)
    criteria = _criteria()
    criteria["max_final_residual"] = 0.0000001
    result = numerics.screen_two_room_numerics(case, receipt, criteria)
    assert result["status"] == "PROJECT_NUMERICAL_SCREEN_NOT_MET"
    assert any("p: recent final residual exceeds" in x for x in result["log_screen"]["violations"])
    assert result["scientific_validation"] == "BLOCKED"


def test_missing_continuity_or_end_marker_does_not_pass(tmp_path, monkeypatch):
    case, receipt, log, _ = _fixture(tmp_path, monkeypatch)
    filtered = [
        line for line in log.read_text(encoding="utf-8").splitlines()
        if "time step continuity errors" not in line and line != "End"
    ]
    log.write_text("\n".join(filtered) + "\n", encoding="utf-8")
    _rewrite_receipt_log_sha(receipt, log)
    result = numerics.screen_two_room_numerics(case, receipt, _criteria())
    assert result["status"] == "PROJECT_NUMERICAL_SCREEN_NOT_MET"
    assert "missing requested global-continuity evidence" in result["log_screen"]["violations"]
    assert "solver log has no terminal End marker" in result["log_screen"]["violations"]


def test_changes_to_receipt_bound_solver_log_fail_closed(tmp_path, monkeypatch):
    case, receipt, log, _ = _fixture(tmp_path, monkeypatch)
    log.write_text(log.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="changed since its receipt"):
        numerics.screen_two_room_numerics(case, receipt, _criteria())


def test_missing_or_duplicated_solver_stage_is_rejected(tmp_path, monkeypatch):
    case, receipt, _, _ = _fixture(tmp_path, monkeypatch)
    document = json.loads(receipt.read_text(encoding="utf-8"))
    document["stages"].append(dict(document["stages"][1]))
    receipt.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one simpleFoam"):
        numerics.screen_two_room_numerics(case, receipt, _criteria())


def test_insufficient_terminal_window_is_not_numerical_pass(tmp_path, monkeypatch):
    case, receipt, _, _ = _fixture(tmp_path, monkeypatch)
    criteria = _criteria()
    criteria["window"] = 4
    result = numerics.screen_two_room_numerics(case, receipt, criteria)
    assert result["status"] == "PROJECT_NUMERICAL_SCREEN_NOT_MET"
    assert any("required 4 residual samples" in x for x in result["log_screen"]["violations"])


@pytest.mark.parametrize("mutation", [
    {"fields": ["p"]},
    {"fields": ["Ux", "Uy", "p", "Uz"]},
    {"fields": ["Ux", "Uy", "Uz", "p", "T"]},
    {"window": 1},
    {"window": True},
    {"window": 101},
    {"max_initial_residual": True},
    {"max_final_residual": float("nan")},
    {"max_global_continuity": 0},
    {"max_global_continuity": float("inf")},
    {"schema_version": "unknown"},
    {"unexpected": "field"},
])
def test_invalid_or_incomplete_criteria_fail_closed(mutation):
    policy = _criteria()
    policy.update(mutation)
    with pytest.raises(ValueError):
        numerics.validate_two_room_numerical_criteria(policy)


def test_numerical_cli_requires_explicit_criteria_file():
    parser = build_parser()
    args = parser.parse_args([
        "two-room-numerical-screen", "case", "receipt.json",
        "criteria.json", "--output", "screen.json",
    ])
    assert args.criteria == "criteria.json"
    assert args.output == "screen.json"
    with pytest.raises(SystemExit):
        parser.parse_args(["two-room-numerical-screen", "case", "receipt.json"])
