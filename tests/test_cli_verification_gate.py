from __future__ import annotations

import json
import sys
from pathlib import Path

import cleanroomx.cli as cli


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(
        json.dumps(payload, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    return path


def _run(
    monkeypatch,
    capsys,
    *args: str,
) -> tuple[int, dict]:
    monkeypatch.setattr(sys, "argv", ["cleanroomx", *args])
    exit_code = cli.main()
    payload = json.loads(capsys.readouterr().out)
    return exit_code, payload


def _complete_room() -> dict:
    return {
        "name": "Verified room",
        "length_m": 5.0,
        "width_m": 4.0,
        "height_m": 3.0,
        "supply_airflow_m3_h": 1800.0,
        "min_ach": 20.0,
        "min_pressure_pa": 10.0,
        "observed_pressure_pa": 14.0,
        "particle_requirements": [
            {
                "size_um": 0.5,
                "max_concentration_per_m3": 400000.0,
                "observed_concentration_per_m3": 120000.0,
            }
        ],
    }


def test_legacy_verify_exit_code_preserves_no_failure_compatibility(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    room = _complete_room()
    room.pop("min_pressure_pa")
    room.pop("observed_pressure_pa")
    path = _write_json(tmp_path / "partial-room.json", room)

    exit_code, result = _run(monkeypatch, capsys, "verify", str(path))

    assert exit_code == 0
    assert result["status"] == "pass_with_unchecked"
    assert result["verified"] is False
    assert result["no_failures_detected"] is True
    assert result["passed"] is True


def test_require_verified_rejects_partial_room_verification(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    room = _complete_room()
    room.pop("min_pressure_pa")
    room.pop("observed_pressure_pa")
    path = _write_json(tmp_path / "partial-room.json", room)

    exit_code, result = _run(
        monkeypatch,
        capsys,
        "verify",
        str(path),
        "--require-verified",
    )

    assert exit_code == 2
    assert result["status"] == "pass_with_unchecked"
    assert result["verified"] is False
    assert result["no_failures_detected"] is True


def test_require_verified_rejects_entirely_unchecked_room(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    room = {
        "name": "Unconfigured room",
        "length_m": 5.0,
        "width_m": 4.0,
        "height_m": 3.0,
        "supply_airflow_m3_h": 1200.0,
    }
    path = _write_json(tmp_path / "unchecked-room.json", room)

    exit_code, result = _run(
        monkeypatch,
        capsys,
        "verify",
        str(path),
        "--require-verified",
    )

    assert exit_code == 2
    assert result["status"] == "not_checked"
    assert result["verified"] is False
    assert result["no_failures_detected"] is True


def test_require_verified_accepts_complete_room_verification(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    path = _write_json(tmp_path / "verified-room.json", _complete_room())

    exit_code, result = _run(
        monkeypatch,
        capsys,
        "verify",
        str(path),
        "--require-verified",
    )

    assert exit_code == 0
    assert result["status"] == "pass"
    assert result["complete"] is True
    assert result["verified"] is True
    assert result["no_failures_detected"] is True


def test_require_verified_project_gate_is_opt_in_and_fail_closed(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project = {
        "name": "Incomplete project",
        "rooms": [
            {
                "name": "Room A",
                "length_m": 5.0,
                "width_m": 4.0,
                "height_m": 3.0,
                "supply_airflow_m3_h": 1200.0,
            }
        ],
        "pressure_cascade": [],
    }
    path = _write_json(tmp_path / "project.json", project)

    legacy_exit, legacy_result = _run(
        monkeypatch,
        capsys,
        "verify-project",
        str(path),
    )
    strict_exit, strict_result = _run(
        monkeypatch,
        capsys,
        "verify-project",
        str(path),
        "--require-verified",
    )

    assert legacy_exit == 0
    assert strict_exit == 2
    assert legacy_result == strict_result
    assert strict_result["status"] == "not_checked"
    assert strict_result["verified"] is False
    assert strict_result["no_failures_detected"] is True
