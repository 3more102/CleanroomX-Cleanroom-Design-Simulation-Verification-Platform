from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tomllib

import pytest

import cleanroomx.cli_output as cli_output
import cleanroomx.dossier_cli as dossier_cli
import cleanroomx.fan_curve_cli as fan_curve_cli


def _configured_cli_modules() -> tuple[Path, ...]:
    """Resolve every installed CleanroomX console entry point to its source module."""
    package_dir = Path(cli_output.__file__).resolve().parent
    repository_root = package_dir.parents[1]
    pyproject = tomllib.loads(
        (repository_root / "pyproject.toml").read_text(encoding="utf-8")
    )
    scripts = pyproject["project"]["scripts"]

    modules: set[Path] = set()
    for command, entry_point in scripts.items():
        module_name, separator, _target = entry_point.partition(":")
        assert separator == ":", command
        assert module_name.startswith("cleanroomx."), command
        module_path = (
            repository_root
            / "src"
            / Path(*module_name.split(".")).with_suffix(".py")
        )
        assert module_path.is_file(), command
        modules.add(module_path)
    return tuple(sorted(modules))


def _call_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _exposes_output_option(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _call_name(node) != "add_argument":
            continue
        if any(
            isinstance(argument, ast.Constant) and argument.value == "--output"
            for argument in node.args
        ):
            return True
    return False


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


def test_all_configured_output_capable_clis_use_guarded_publication():
    configured = _configured_cli_modules()
    assert configured
    output_capable: list[Path] = []

    for path in configured:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        if not _exposes_output_option(tree):
            continue
        output_capable.append(path)

        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
        ]
        publish_calls = [
            call for call in calls if _call_name(call) == "publish_cli_output"
        ]
        atomic_calls = [
            call for call in calls if _call_name(call) == "atomic_write_text"
        ]
        direct_cli_writer_calls = [
            call for call in calls if _call_name(call) == "atomic_write_cli_output"
        ]

        assert publish_calls or atomic_calls, path.name
        assert not direct_cli_writer_calls, path.name

        for call in publish_calls:
            assert any(
                keyword.arg == "protected_inputs" for keyword in call.keywords
            ), path.name

        for call in atomic_calls:
            assert any(
                keyword.arg == "before_replace" for keyword in call.keywords
            ), path.name

    assert output_capable
