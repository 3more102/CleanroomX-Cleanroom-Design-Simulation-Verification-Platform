from __future__ import annotations

import importlib
from pathlib import Path
import sys
import tomllib

import pytest

from cleanroomx import hvac_cli


def _stub_hvac_run(monkeypatch) -> None:
    monkeypatch.setattr(hvac_cli, "load_hvac_project", lambda _path: object())
    monkeypatch.setattr(hvac_cli, "analyze_hvac_project", lambda _project: {})
    monkeypatch.setattr(
        hvac_cli,
        "markdown_hvac_report",
        lambda _result: "complete engineering report\n",
    )


def test_cli_output_uses_atomic_writer(tmp_path, monkeypatch):
    _stub_hvac_run(monkeypatch)
    target = tmp_path / "report.md"
    target.write_text("old report\n", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["cleanroomx-hvac", "ignored.json", "--output", str(target)],
    )

    assert hvac_cli.main() == 0
    assert target.read_text(encoding="utf-8") == "complete engineering report\n"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_cli_output_replace_failure_preserves_previous_complete_file(
    tmp_path,
    monkeypatch,
):
    _stub_hvac_run(monkeypatch)
    target = tmp_path / "report.md"
    target.write_text("previous complete report\n", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["cleanroomx-hvac", "ignored.json", "--output", str(target)],
    )

    def fail_replace(self, destination):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(type(target), "replace", fail_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        hvac_cli.main()

    assert target.read_text(encoding="utf-8") == "previous complete report\n"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_all_packaged_console_entrypoints_import_and_resolve():
    metadata = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    for script_name, target in metadata["project"]["scripts"].items():
        module_name, function_name = target.split(":", 1)
        module = importlib.import_module(module_name)
        entrypoint = getattr(module, function_name)
        assert callable(entrypoint), script_name
