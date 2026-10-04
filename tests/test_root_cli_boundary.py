from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import cleanroomx.cli as cli


def _run(monkeypatch, capsys, *args: str):
    monkeypatch.setattr(sys, "argv", ["cleanroomx", *args])
    exit_code = cli.main()
    return exit_code, capsys.readouterr()


def _valid_room(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "name": "Root CLI room",
                "length_m": 5.0,
                "width_m": 4.0,
                "height_m": 3.0,
                "supply_airflow_m3_h": 1200.0,
            },
            sort_keys=True,
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    return path


def test_root_cli_missing_file_is_deterministic_user_error(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    exit_code, captured = _run(
        monkeypatch,
        capsys,
        "verify",
        str(tmp_path / "missing-room.json"),
    )

    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.startswith("cleanroomx: error: ")
    assert "Traceback" not in captured.err


def test_root_cli_normalizes_missing_required_input_field(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    source = tmp_path / "broken-room.json"
    source.write_text("{}\n", encoding="utf-8")

    exit_code, captured = _run(monkeypatch, capsys, "verify", str(source))

    assert exit_code == 1
    assert captured.out == ""
    assert "invalid input structure: missing required field 'name'" in captured.err
    assert "Traceback" not in captured.err


def test_root_cli_normalizes_wrong_root_shape(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    source = tmp_path / "wrong-root.json"
    source.write_text("[]\n", encoding="utf-8")

    exit_code, captured = _run(monkeypatch, capsys, "verify", str(source))

    assert exit_code == 1
    assert captured.out == ""
    assert "invalid input structure:" in captured.err
    assert "Traceback" not in captured.err


def test_root_cli_rejects_nonfinite_calculator_input_without_traceback(
    monkeypatch,
    capsys,
) -> None:
    exit_code, captured = _run(
        monkeypatch,
        capsys,
        "decay",
        "--initial",
        "nan",
        "--ach",
        "20",
        "--minutes",
        "5",
    )

    assert exit_code == 1
    assert captured.out == ""
    assert "initial_concentration_per_m3 must be finite" in captured.err
    assert "Traceback" not in captured.err


def test_root_cli_fails_closed_on_nonfinite_result_json(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(cli, "decay_concentration", lambda *args: float("nan"))

    exit_code, captured = _run(
        monkeypatch,
        capsys,
        "decay",
        "--initial",
        "1",
        "--ach",
        "20",
        "--minutes",
        "5",
    )

    assert exit_code == 1
    assert captured.out == ""
    assert "$.concentration_per_m3 contains a non-finite number" in captured.err
    assert "Traceback" not in captured.err


def test_root_cli_does_not_swallow_unexpected_runtime_defects(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = _valid_room(tmp_path / "room.json")

    def explode(_room):
        raise RuntimeError("verification implementation defect")

    monkeypatch.setattr(cli, "verify_room", explode)
    monkeypatch.setattr(sys, "argv", ["cleanroomx", "verify", str(source)])

    with pytest.raises(RuntimeError, match="verification implementation defect"):
        cli.main()
