from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys

import pytest

import cleanroomx.fan_curve_cli as fan_curve_cli
from cleanroomx.project import atomic_write_text


ROOT = Path(__file__).resolve().parents[1]

OUTPUT_CLI_MODULES = (
    "cleanroomx.consistency_cli",
    "cleanroomx.damper_study_cli",
    "cleanroomx.dossier_cli",
    "cleanroomx.duct_flow_cli",
    "cleanroomx.fan_curve_cli",
    "cleanroomx.fan_duct_network_cli",
    "cleanroomx.fan_loop_network_cli",
    "cleanroomx.fan_loop_speed_cli",
    "cleanroomx.fan_loop_uncertainty_cli",
    "cleanroomx.fan_network_cli",
    "cleanroomx.fan_speed_cli",
    "cleanroomx.fan_uncertainty_cli",
    "cleanroomx.fan_variable_friction_loop_cli",
    "cleanroomx.fan_variable_friction_speed_cli",
    "cleanroomx.fan_variable_friction_uncertainty_cli",
    "cleanroomx.hvac_cli",
    "cleanroomx.loop_network_cli",
    "cleanroomx.psychrometric_uncertainty_cli",
    "cleanroomx.qualification_cli",
    "cleanroomx.recovery_cli",
    "cleanroomx.thermal_uncertainty_cli",
    "cleanroomx.uncertainty_cli",
    "cleanroomx.variable_friction_loop_cli",
)


@pytest.mark.parametrize("module_name", OUTPUT_CLI_MODULES)
def test_file_output_cli_modules_share_atomic_writer(module_name):
    module = importlib.import_module(module_name)
    assert module.atomic_write_text is atomic_write_text


def test_fan_curve_cli_delegates_destination_write_atomically(tmp_path, monkeypatch):
    target = tmp_path / "fan-result.json"
    target.write_text("existing-output\n", encoding="utf-8")
    captured: dict[str, object] = {}

    def capture_atomic_write(path, text):
        captured["path"] = Path(path)
        captured["text"] = text
        return Path(path)

    monkeypatch.setattr(fan_curve_cli, "atomic_write_text", capture_atomic_write)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cleanroomx-fan-curve",
            str(ROOT / "examples" / "fan_operating_point_demo.json"),
            "--format",
            "json",
            "--output",
            str(target),
        ],
    )

    exit_code = fan_curve_cli.main()

    assert exit_code == 0
    assert captured["path"] == target
    assert target.read_text(encoding="utf-8") == "existing-output\n"
    payload = json.loads(str(captured["text"]))
    assert payload["status"] == "solved"


def test_atomic_writer_preserves_existing_output_when_replace_fails(
    tmp_path, monkeypatch
):
    target = tmp_path / "report.json"
    target.write_text("last-known-good\n", encoding="utf-8")

    def fail_replace(self, destination):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(type(target), "replace", fail_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        atomic_write_text(target, "new-output\n")

    assert target.read_text(encoding="utf-8") == "last-known-good\n"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []
