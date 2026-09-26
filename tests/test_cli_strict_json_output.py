from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

import cleanroomx.dossier_cli as dossier_cli
import cleanroomx.duct_flow_cli as duct_flow_cli
import cleanroomx.hvac_cli as hvac_cli
import cleanroomx.recovery_cli as recovery_cli
from cleanroomx.cli_output import dumps_strict_json
from cleanroomx.strict_json import StrictJSONError


def test_strict_cli_json_serializer_accepts_standard_json() -> None:
    payload = {"name": "Δ", "values": [1, 2.5, True, None]}
    text = dumps_strict_json(payload)
    assert json.loads(text) == payload


def test_strict_cli_json_serializer_rejects_nonfinite_with_path() -> None:
    with pytest.raises(StrictJSONError, match=r"\$\.result contains a non-finite number"):
        dumps_strict_json({"result": float("nan")})


def _sentinel_output(tmp_path: Path) -> tuple[Path, bytes]:
    output = tmp_path / "existing.json"
    previous = b'{"status": "previous"}\n'
    output.write_bytes(previous)
    return output, previous


def test_hvac_cli_rejects_nonfinite_json_before_output_write(
    monkeypatch, tmp_path, capsys
) -> None:
    output, previous = _sentinel_output(tmp_path)
    monkeypatch.setattr(hvac_cli, "load_hvac_project", lambda _path: object())
    monkeypatch.setattr(
        hvac_cli, "analyze_hvac_project", lambda _project: {"result": float("nan")}
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["cleanroomx-hvac", "input.json", "--format", "json", "--output", str(output)],
    )

    assert hvac_cli.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "non-finite" in captured.err
    assert output.read_bytes() == previous


def test_recovery_cli_rejects_nonfinite_json_before_output_write(
    monkeypatch, tmp_path, capsys
) -> None:
    output, previous = _sentinel_output(tmp_path)
    monkeypatch.setattr(recovery_cli, "load_recovery_test", lambda _path: object())
    monkeypatch.setattr(
        recovery_cli, "analyze_recovery_test", lambda _test: {"result": float("inf")}
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cleanroomx-recovery-test",
            "input.json",
            "--format",
            "json",
            "--output",
            str(output),
        ],
    )

    assert recovery_cli.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "non-finite" in captured.err
    assert output.read_bytes() == previous


def test_duct_flow_cli_rejects_nonfinite_json_before_output_write(
    monkeypatch, tmp_path, capsys
) -> None:
    output, previous = _sentinel_output(tmp_path)
    monkeypatch.setattr(duct_flow_cli, "load_parallel_flow_network", lambda _path: object())
    monkeypatch.setattr(
        duct_flow_cli,
        "solve_parallel_branch_flows",
        lambda _network: {"result": float("-inf")},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cleanroomx-duct-flow",
            "input.json",
            "--format",
            "json",
            "--output",
            str(output),
        ],
    )

    assert duct_flow_cli.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "non-finite" in captured.err
    assert output.read_bytes() == previous


def test_dossier_cli_rejects_nonfinite_json_before_output_write(
    monkeypatch, tmp_path, capsys
) -> None:
    output, previous = _sentinel_output(tmp_path)
    monkeypatch.setattr(dossier_cli, "load_strict_json", lambda _path: {})
    monkeypatch.setattr(
        dossier_cli,
        "run_analysis",
        lambda *_args, **_kwargs: SimpleNamespace(
            result={"result": float("nan")},
            markdown="unused",
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cleanroomx-dossier",
            "manifest.json",
            "--format",
            "json",
            "--output",
            str(output),
        ],
    )

    assert dossier_cli.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "non-finite" in captured.err
    assert output.read_bytes() == previous
