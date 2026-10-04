from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

import cleanroomx.cli_output as cli_output
import cleanroomx.dossier_cli as dossier_cli
import cleanroomx.fan_curve_cli as fan_curve_cli


def _discover_output_capable_cli_modules() -> tuple[Path, ...]:
    """Discover CLI modules that expose a file-output option.

    The set is derived from source, not a manually maintained filename list, so
    newly added output-capable commands automatically enter the safety gate.
    """
    package_dir = Path(cli_output.__file__).resolve().parent
    candidates = [*package_dir.glob("*_cli.py"), package_dir / "project_batch.py"]
    discovered: list[Path] = []
    for path in sorted(set(candidates)):
        source = path.read_text(encoding="utf-8")
        if '"--output"' in source or "'--output'" in source:
            discovered.append(path)
    return tuple(discovered)


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


def test_fan_curve_cli_cannot_publish_over_its_study(tmp_path, monkeypatch, capsys):
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
    assert "cleanroomx-fan-curve: error: output publication failed:" in captured.err
    assert "Traceback" not in captured.err
    assert source.read_bytes() == before


def test_dossier_cli_cannot_publish_over_declared_dependency(tmp_path, monkeypatch, capsys):
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
    assert "cleanroomx-dossier: error: output publication failed:" in captured.err
    assert "Traceback" not in captured.err
    assert dependency.read_bytes() == before


def test_alias_rejection_does_not_reresolve_source_for_diagnostic(
    tmp_path, monkeypatch
):
    source = tmp_path / "engineering-input.json"
    output = tmp_path / "report.json"

    monkeypatch.setattr(cli_output, "_paths_alias", lambda *_args: True)

    def unexpected_resolve(*_args, **_kwargs):
        raise RuntimeError("source path changed during diagnostic formatting")

    monkeypatch.setattr(Path, "resolve", unexpected_resolve)

    with pytest.raises(
        cli_output.CliOutputProtectionError,
        match="protected engineering input",
    ):
        cli_output.atomic_write_cli_output(
            output,
            "report\n",
            protected_inputs=(source,),
        )


def test_publish_cli_output_reports_persistence_failure(tmp_path, monkeypatch, capsys):
    output = tmp_path / "report.json"

    def fail_write(*_args, **_kwargs):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(cli_output, "atomic_write_text", fail_write)

    assert (
        cli_output.publish_cli_output(
            "cleanroomx-test",
            output,
            "report\n",
        )
        is False
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert (
        captured.err
        == "cleanroomx-test: error: output publication failed: simulated disk failure\n"
    )
    assert "Traceback" not in captured.err
    assert not output.exists()


def test_all_output_capable_clis_use_guarded_publication():
    candidates = _discover_output_capable_cli_modules()
    assert candidates

    for path in candidates:
        source = path.read_text(encoding="utf-8")
        uses_shared_writer = "publish_cli_output(" in source
        uses_revision_guarded_writer = (
            "atomic_write_text(" in source and "before_replace=" in source
        )

        assert uses_shared_writer or uses_revision_guarded_writer, path.name
        if uses_shared_writer:
            assert "protected_inputs=" in source, path.name
            assert "atomic_write_cli_output(" not in source, path.name
