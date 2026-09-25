from __future__ import annotations

from pathlib import Path
import sys

import pytest

import cleanroomx.fan_curve_cli as fan_curve_cli


def _stub_fan_curve_cli(monkeypatch, target: Path) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cleanroomx-fan-curve",
            "ignored.json",
            "--format",
            "markdown",
            "--output",
            str(target),
        ],
    )
    monkeypatch.setattr(
        fan_curve_cli,
        "load_fan_operating_point_study",
        lambda _path: {"study": "stub"},
    )
    monkeypatch.setattr(
        fan_curve_cli,
        "solve_fan_operating_point",
        lambda _study: {"status": "solved"},
    )
    monkeypatch.setattr(
        fan_curve_cli,
        "markdown_fan_operating_point_report",
        lambda _result: "new report\n",
    )


def test_cli_output_replace_failure_preserves_existing_report(tmp_path, monkeypatch):
    target = tmp_path / "report.md"
    target.write_text("previous report\n", encoding="utf-8")
    _stub_fan_curve_cli(monkeypatch, target)

    def fail_replace(self, destination):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        fan_curve_cli.main()

    assert target.read_text(encoding="utf-8") == "previous report\n"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_output_capable_cli_modules_do_not_truncate_targets_in_place():
    package_dir = Path(fan_curve_cli.__file__).resolve().parent
    offenders = []
    for path in sorted(package_dir.glob("*_cli.py")):
        source = path.read_text(encoding="utf-8")
        if "--output" in source and ".write_text(" in source:
            offenders.append(path.name)

    assert offenders == []
