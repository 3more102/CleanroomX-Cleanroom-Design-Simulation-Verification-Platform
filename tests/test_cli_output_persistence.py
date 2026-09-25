from __future__ import annotations

import ast
import json
from pathlib import Path
import sys

import pytest

import cleanroomx
import cleanroomx.fan_curve_cli as fan_curve_cli


def test_cli_modules_do_not_bypass_atomic_output_persistence():
    package_dir = Path(cleanroomx.__file__).resolve().parent
    offenders: list[str] = []

    for path in sorted(package_dir.glob("*_cli.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "write_text"
            ):
                offenders.append(f"{path.name}:{node.lineno}")

    assert offenders == []


def test_cli_atomic_output_preserves_previous_result_when_replace_fails(
    tmp_path,
    monkeypatch,
):
    repository_root = Path(__file__).resolve().parents[1]
    study = repository_root / "examples" / "fan_operating_point_demo.json"
    output = tmp_path / "fan-result.json"
    output.write_text("previous committed result\n", encoding="utf-8")

    concrete_path_type = type(output)
    original_replace = concrete_path_type.replace

    def fail_output_replace(self, target):
        if Path(target) == output:
            raise OSError("injected atomic replacement failure")
        return original_replace(self, target)

    monkeypatch.setattr(concrete_path_type, "replace", fail_output_replace)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cleanroomx-fan-curve",
            str(study),
            "--format",
            "json",
            "--output",
            str(output),
        ],
    )

    with pytest.raises(OSError, match="injected atomic replacement failure"):
        fan_curve_cli.main()

    assert output.read_text(encoding="utf-8") == "previous committed result\n"
    assert list(tmp_path.glob(f".{output.name}.*.tmp")) == []


def test_cli_atomic_output_replaces_existing_result_on_success(tmp_path, monkeypatch):
    repository_root = Path(__file__).resolve().parents[1]
    study = repository_root / "examples" / "fan_operating_point_demo.json"
    output = tmp_path / "fan-result.json"
    output.write_text("stale\n", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cleanroomx-fan-curve",
            str(study),
            "--format",
            "json",
            "--output",
            str(output),
        ],
    )

    exit_code = fan_curve_cli.main()
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["status"] == "solved"
    assert list(tmp_path.glob(f".{output.name}.*.tmp")) == []
