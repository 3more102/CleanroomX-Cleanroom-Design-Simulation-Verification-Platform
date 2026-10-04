from __future__ import annotations

from pathlib import Path
import sys

import cleanroomx.cli_output as cli_output
import cleanroomx.fan_curve_cli as fan_curve_cli
import cleanroomx.hvac_cli as hvac_cli
import pytest


CUSTOM_INPUT_BOUNDARY_CLIS = frozenset(
    {"consistency_cli.py", "dossier_cli.py"}
)


def _discover_standalone_file_output_clis() -> tuple[Path, ...]:
    package_dir = Path(cli_output.__file__).resolve().parent
    discovered: list[Path] = []
    for path in sorted(package_dir.glob("*_cli.py")):
        source = path.read_text(encoding="utf-8")
        if "publish_cli_output(" in source:
            discovered.append(path)
    return tuple(discovered)


def test_cli_error_boundary_reports_value_error_without_traceback(capsys) -> None:
    @cli_output.cli_error_boundary("cleanroomx-test")
    def fail() -> int:
        raise ValueError("invalid engineering input")

    assert fail() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "cleanroomx-test: error: invalid engineering input\n"
    assert "Traceback" not in captured.err


def test_cli_error_boundary_reports_oserror_without_traceback(capsys) -> None:
    @cli_output.cli_error_boundary("cleanroomx-test")
    def fail() -> int:
        raise OSError("input source unavailable")

    assert fail() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "cleanroomx-test: error: input source unavailable\n"
    assert "Traceback" not in captured.err


def test_hvac_cli_loader_failure_is_clean(monkeypatch, capsys) -> None:
    def fail_load(_path):
        raise ValueError("malformed HVAC input")

    monkeypatch.setattr(hvac_cli, "load_hvac_project", fail_load)
    monkeypatch.setattr(sys, "argv", ["cleanroomx-hvac", "broken.json"])

    assert hvac_cli.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "cleanroomx-hvac: error: malformed HVAC input\n"
    assert "Traceback" not in captured.err


def test_fan_curve_cli_analysis_failure_is_clean(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        fan_curve_cli,
        "load_fan_operating_point_study",
        lambda _path: object(),
    )

    def fail_analysis(_study):
        raise ValueError("invalid fan study")

    monkeypatch.setattr(fan_curve_cli, "solve_fan_operating_point", fail_analysis)
    monkeypatch.setattr(sys, "argv", ["cleanroomx-fan-curve", "broken.json"])

    assert fan_curve_cli.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "cleanroomx-fan-curve: error: invalid fan study\n"
    assert "Traceback" not in captured.err



def test_cli_error_boundary_preserves_explicit_exit_code() -> None:
    @cli_output.cli_error_boundary("cleanroomx-test")
    def status() -> int:
        return 3

    assert status() == 3


def test_cli_error_boundary_does_not_hide_unexpected_runtime_error() -> None:
    @cli_output.cli_error_boundary("cleanroomx-test")
    def fail() -> int:
        raise RuntimeError("programming defect")

    with pytest.raises(RuntimeError, match="programming defect"):
        fail()


def test_fan_curve_cli_missing_required_field_is_clean(
    monkeypatch, tmp_path, capsys
) -> None:
    source = tmp_path / "broken-fan-study.json"
    source.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["cleanroomx-fan-curve", str(source)])

    assert fan_curve_cli.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "cleanroomx-fan-curve: error: invalid input structure: "
        "missing required field 'fan_curve'\n"
    )
    assert "Traceback" not in captured.err


def test_hvac_cli_wrong_root_shape_is_clean(monkeypatch, tmp_path, capsys) -> None:
    source = tmp_path / "broken-hvac.json"
    source.write_text("[]\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["cleanroomx-hvac", str(source)])

    assert hvac_cli.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith(
        "cleanroomx-hvac: error: invalid input structure:"
    )
    assert "Traceback" not in captured.err

def test_all_standalone_file_output_clis_use_shared_error_boundary() -> None:
    candidates = _discover_standalone_file_output_clis()
    assert candidates
    for path in candidates:
        source = path.read_text(encoding="utf-8")
        assert "from .cli_output import cli_error_boundary" in source, path.name
        assert "@cli_error_boundary(" in source, path.name


def test_all_file_loader_clis_use_structural_input_boundary() -> None:
    candidates = _discover_standalone_file_output_clis()
    assert candidates
    for path in candidates:
        if path.name in CUSTOM_INPUT_BOUNDARY_CLIS:
            continue
        source = path.read_text(encoding="utf-8")
        assert "load_cli_input" in source, path.name
        assert "load_cli_input(" in source, path.name
