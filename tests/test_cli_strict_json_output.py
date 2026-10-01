from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

import cleanroomx.cli_output as cli_output
import cleanroomx.dossier_cli as dossier_cli
import cleanroomx.duct_flow_cli as duct_flow_cli
import cleanroomx.hvac_cli as hvac_cli
import cleanroomx.recovery_cli as recovery_cli
from cleanroomx.cli_output import CLIOutputError, dumps_strict_json, write_cli_output
from cleanroomx.strict_json import StrictJSONError


def test_strict_cli_json_serializer_accepts_standard_json() -> None:
    payload = {"name": "Δ", "values": [1, 2.5, True, None]}
    text = dumps_strict_json(payload)
    assert json.loads(text) == payload


def test_strict_cli_json_serializer_rejects_nonfinite_with_path() -> None:
    with pytest.raises(StrictJSONError, match=r"\$\.result contains a non-finite number"):
        dumps_strict_json({"result": float("nan")})


def test_strict_cli_json_serializer_rejects_non_string_object_keys() -> None:
    with pytest.raises(StrictJSONError, match="non-string object key"):
        dumps_strict_json({1: "silently coerced by json.dumps"})


def test_strict_cli_json_serializer_normalizes_compatible_container_subclasses() -> None:
    class ResultDict(dict):
        pass

    class ResultList(list):
        pass

    payload = ResultDict({"values": ResultList([1, (2, 3)])})

    assert json.loads(dumps_strict_json(payload)) == {"values": [1, [2, 3]]}


def test_strict_cli_json_serializer_rejects_invalid_utf8_text() -> None:
    with pytest.raises(StrictJSONError, match="valid UTF-8 text"):
        dumps_strict_json({"value": "\ud800"})


def test_strict_cli_json_serializer_rejects_cycles() -> None:
    payload: list[object] = []
    payload.append(payload)

    with pytest.raises(StrictJSONError, match="cyclic reference"):
        dumps_strict_json(payload)


def test_strict_cli_json_serializer_rejects_non_json_values() -> None:
    with pytest.raises(StrictJSONError, match="non-JSON value of type set"):
        dumps_strict_json({"value": {1, 2}})


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

def test_protected_cli_writer_refuses_direct_input_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "input.json"
    source.write_bytes(b'{"engineering": "source"}\n')
    before = source.read_bytes()

    with pytest.raises(CLIOutputError, match="protected input"):
        write_cli_output(
            source,
            '{"report": true}\n',
            protected_inputs=(source,),
        )

    assert source.read_bytes() == before


def test_protected_cli_writer_refuses_hardlink_input_alias(tmp_path: Path) -> None:
    source = tmp_path / "input.json"
    source.write_bytes(b'{"engineering": "source"}\n')
    alias = tmp_path / "report.json"
    alias.hardlink_to(source)
    before = source.read_bytes()

    with pytest.raises(CLIOutputError, match="protected input"):
        write_cli_output(
            alias,
            '{"report": true}\n',
            protected_inputs=(source,),
        )

    assert source.read_bytes() == before
    assert alias.read_bytes() == before


def test_protected_cli_writer_rechecks_identity_before_replace(
    monkeypatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.json"
    source.write_bytes(b'{"engineering": "source"}\n')
    output = tmp_path / "report.json"
    output.write_bytes(b'{"report": "previous"}\n')
    source_before = source.read_bytes()

    def race_atomic_write(path, text, *, before_replace=None):
        target = Path(path)
        target.unlink()
        target.hardlink_to(source)
        assert before_replace is not None
        before_replace()
        pytest.fail("protected output identity recheck should have failed")

    monkeypatch.setattr(cli_output, "atomic_write_text", race_atomic_write)

    with pytest.raises(CLIOutputError, match="protected input"):
        write_cli_output(
            output,
            '{"report": "new"}\n',
            protected_inputs=(source,),
        )

    assert source.read_bytes() == source_before


def test_hvac_cli_refuses_to_replace_its_input(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    source = tmp_path / "hvac.json"
    source.write_bytes(b'{"engineering": "source"}\n')
    before = source.read_bytes()
    monkeypatch.setattr(hvac_cli, "load_hvac_project", lambda _path: object())
    monkeypatch.setattr(
        hvac_cli,
        "analyze_hvac_project",
        lambda _project: {"status": "complete"},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cleanroomx-hvac",
            str(source),
            "--format",
            "json",
            "--output",
            str(source),
        ],
    )

    assert hvac_cli.main() == 1
    captured = capsys.readouterr()
    assert "protected input" in captured.err
    assert source.read_bytes() == before


def test_dossier_cli_refuses_to_replace_declared_dependency(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    manifest = tmp_path / "dossier.json"
    manifest.write_text("{}\n", encoding="utf-8")
    dependency = tmp_path / "verification.json"
    dependency.write_bytes(b'{"engineering": "dependency"}\n')
    before = dependency.read_bytes()

    monkeypatch.setattr(
        dossier_cli,
        "load_strict_json",
        lambda _path: {"verification_project": dependency.name},
    )
    monkeypatch.setattr(
        dossier_cli,
        "run_analysis",
        lambda *_args, **_kwargs: SimpleNamespace(
            result={"executive_summary": {"state": "complete"}},
            markdown="dossier\n",
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cleanroomx-dossier",
            str(manifest),
            "--format",
            "json",
            "--output",
            str(dependency),
        ],
    )

    assert dossier_cli.main() == 1
    captured = capsys.readouterr()
    assert "protected input" in captured.err
    assert dependency.read_bytes() == before

