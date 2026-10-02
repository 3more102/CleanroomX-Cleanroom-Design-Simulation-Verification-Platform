from __future__ import annotations

import json
import importlib.metadata as metadata
from pathlib import Path
import subprocess
from types import SimpleNamespace
import sys

import pytest

import cleanroomx.cli_output as cli_output
import cleanroomx.dossier_cli as dossier_cli
import cleanroomx.fan_curve_cli as fan_curve_cli


STANDALONE_FILE_OUTPUT_CLIS = (
    "consistency_cli.py",
    "damper_study_cli.py",
    "dossier_cli.py",
    "duct_flow_cli.py",
    "fan_curve_cli.py",
    "fan_duct_network_cli.py",
    "fan_loop_network_cli.py",
    "fan_loop_speed_cli.py",
    "fan_loop_uncertainty_cli.py",
    "fan_network_cli.py",
    "fan_speed_cli.py",
    "fan_uncertainty_cli.py",
    "fan_variable_friction_loop_cli.py",
    "fan_variable_friction_speed_cli.py",
    "fan_variable_friction_uncertainty_cli.py",
    "hvac_cli.py",
    "loop_network_cli.py",
    "pressure_network_cli.py",
    "psychrometric_uncertainty_cli.py",
    "qualification_cli.py",
    "recovery_cli.py",
    "thermal_uncertainty_cli.py",
    "uncertainty_cli.py",
    "variable_friction_loop_cli.py",
)


def test_protected_cli_writer_rejects_direct_input_overwrite(tmp_path):
    source = tmp_path / "engineering-input.json"
    source.write_text('{"value": 1}\n', encoding="utf-8")
    before = source.read_bytes()

    with pytest.raises(cli_output.CliOutputProtectionError, match="protected engineering input"):
        cli_output.atomic_write_cli_output(
            source,
            "report\n",
            protected_inputs=(source,),
        )

    assert source.read_bytes() == before


def test_protected_cli_writer_rejects_existing_hardlink_alias(tmp_path):
    source = tmp_path / "engineering-input.json"
    source.write_text('{"value": 1}\n', encoding="utf-8")
    alias = tmp_path / "report.json"
    alias.hardlink_to(source)
    before = source.read_bytes()

    with pytest.raises(cli_output.CliOutputProtectionError, match="protected engineering input"):
        cli_output.atomic_write_cli_output(
            alias,
            "report\n",
            protected_inputs=(source,),
        )

    assert source.read_bytes() == before
    assert alias.read_bytes() == before


def test_protected_cli_writer_rechecks_identity_before_replace(tmp_path, monkeypatch):
    source = tmp_path / "engineering-input.json"
    source.write_text('{"value": 1}\n', encoding="utf-8")
    output = tmp_path / "report.json"
    before = source.read_bytes()

    def create_alias_then_recheck(path, text, *, before_replace=None):
        assert Path(path) == output
        assert text == "report\n"
        assert before_replace is not None
        output.hardlink_to(source)
        before_replace()
        raise AssertionError("unsafe replacement should not be reached")

    monkeypatch.setattr(cli_output, "atomic_write_text", create_alias_then_recheck)

    with pytest.raises(cli_output.CliOutputProtectionError, match="protected engineering input"):
        cli_output.atomic_write_cli_output(
            output,
            "report\n",
            protected_inputs=(source,),
        )

    assert source.read_bytes() == before
    assert output.read_bytes() == before


def test_fan_curve_cli_reports_protected_output_failure_without_traceback(
    tmp_path, monkeypatch, capsys
):
    source = tmp_path / "fan-study.json"
    source.write_text('{"engineering": "input"}\n', encoding="utf-8")
    before = source.read_bytes()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cleanroomx-fan-curve",
            str(source),
            "--format",
            "markdown",
            "--output",
            str(source),
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
        lambda _result: "report\n",
    )

    assert fan_curve_cli.main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("cleanroomx-fan-curve: error: output publication failed:")
    assert "protected engineering input" in captured.err
    assert "Traceback" not in captured.err
    assert source.read_bytes() == before


def test_dossier_cli_reports_dependency_output_failure_without_traceback(
    tmp_path, monkeypatch, capsys
):
    dependency = tmp_path / "verification.json"
    dependency.write_text("protected engineering dependency\n", encoding="utf-8")
    before = dependency.read_bytes()
    manifest = tmp_path / "dossier.json"
    manifest.write_text(
        json.dumps(
            {
                "name": "Protected dossier",
                "verification_project": dependency.name,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cleanroomx-dossier",
            str(manifest),
            "--output",
            str(dependency),
        ],
    )
    monkeypatch.setattr(
        dossier_cli,
        "run_analysis",
        lambda *args, **kwargs: SimpleNamespace(
            result={"executive_summary": {"state": "ok"}},
            markdown="report\n",
        ),
    )

    assert dossier_cli.main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("cleanroomx-dossier: error: output publication failed:")
    assert "protected engineering input" in captured.err
    assert "Traceback" not in captured.err
    assert dependency.read_bytes() == before


def test_output_error_wrapper_reports_publication_oserror_without_traceback(
    tmp_path, monkeypatch, capsys
):
    output = tmp_path / "report.md"

    def fail_publication(*_args, **_kwargs):
        raise OSError("simulated publication failure")

    monkeypatch.setattr(cli_output, "atomic_write_cli_output", fail_publication)

    assert not cli_output.write_cli_output_or_report_error(
        "cleanroomx-test",
        output,
        "report\n",
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "cleanroomx-test: error: output publication failed: "
        "simulated publication failure\n"
    )
    assert "Traceback" not in captured.err


def test_installed_fan_curve_entrypoint_reports_output_failure_cleanly(tmp_path):
    try:
        distribution = metadata.distribution("cleanroomx")
    except metadata.PackageNotFoundError:
        pytest.skip("installed package metadata is not available in this test environment")
    assert any(
        entry.name == "cleanroomx-fan-curve"
        for entry in distribution.entry_points
    )

    source = tmp_path / "fan-study.json"
    source.write_text('{"engineering": "input"}\n', encoding="utf-8")
    before = source.read_bytes()
    script = r"""
import importlib.metadata as metadata
import sys
import cleanroomx.fan_curve_cli as module

source = sys.argv[1]
module.load_fan_operating_point_study = lambda _path: {"study": "stub"}
module.solve_fan_operating_point = lambda _study: {"status": "solved"}
module.markdown_fan_operating_point_report = lambda _result: "report\n"
sys.argv = [
    "cleanroomx-fan-curve",
    source,
    "--format",
    "markdown",
    "--output",
    source,
]
entry = next(
    item
    for item in metadata.distribution("cleanroomx").entry_points
    if item.name == "cleanroomx-fan-curve"
)
raise SystemExit(entry.load()())
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(source)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert completed.stdout == ""
    assert completed.stderr.startswith(
        "cleanroomx-fan-curve: error: output publication failed:"
    )
    assert "protected engineering input" in completed.stderr
    assert "Traceback" not in completed.stderr
    assert source.read_bytes() == before


def test_all_standalone_file_output_clis_report_publication_failures():
    package_dir = Path(cli_output.__file__).resolve().parent
    for filename in STANDALONE_FILE_OUTPUT_CLIS:
        source = (package_dir / filename).read_text(encoding="utf-8")
        assert "--output" in source, filename
        assert "write_cli_output_or_report_error(" in source, filename
        assert "atomic_write_cli_output(" not in source, filename
        assert "atomic_write_text(args.output, text)" not in source, filename
