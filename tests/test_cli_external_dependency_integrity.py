from __future__ import annotations

import json
from pathlib import Path
import sys

import cleanroomx.application as application_module
from cleanroomx.consistency_cli import main as consistency_main
from cleanroomx.dossier_cli import main as dossier_main


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def _copy_example(tmp_path: Path, name: str) -> Path:
    destination = tmp_path / name
    destination.write_bytes((EXAMPLES / name).read_bytes())
    return destination


def test_consistency_cli_uses_revision_bound_execution(monkeypatch, tmp_path, capsys):
    verification = _copy_example(tmp_path, "facility_project.json")
    hvac = _copy_example(tmp_path, "consistency_hvac_demo.json")
    output = tmp_path / "consistency.json"

    original_run = application_module._run_consistency

    def mutate_dependency_then_run(payload, base_dir):
        verification.write_bytes(verification.read_bytes() + b"\n")
        return original_run(payload, base_dir)

    monkeypatch.setattr(
        application_module,
        "_run_consistency",
        mutate_dependency_then_run,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cleanroomx-consistency",
            str(verification),
            str(hvac),
            "--format",
            "json",
            "--output",
            str(output),
        ],
    )

    assert consistency_main() == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "result was discarded" in captured.err
    assert str(verification) in captured.err
    assert not output.exists()


def test_dossier_cli_uses_revision_bound_execution(monkeypatch, tmp_path, capsys):
    verification = _copy_example(tmp_path, "facility_project.json")
    manifest = tmp_path / "dossier.json"
    manifest.write_text(
        json.dumps(
            {
                "name": "Revision-bound dossier",
                "verification_project": verification.name,
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "dossier-output.json"

    original_run = application_module._run_dossier

    def mutate_dependency_then_run(payload, base_dir):
        verification.write_bytes(verification.read_bytes() + b"\n")
        return original_run(payload, base_dir)

    monkeypatch.setattr(
        application_module,
        "_run_dossier",
        mutate_dependency_then_run,
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
            str(output),
        ],
    )

    assert dossier_main() == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "result was discarded" in captured.err
    assert verification.name in captured.err
    assert not output.exists()


def test_consistency_cli_preserves_json_result_contract(monkeypatch, tmp_path, capsys):
    verification = _copy_example(tmp_path, "facility_project.json")
    hvac = _copy_example(tmp_path, "consistency_hvac_demo.json")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cleanroomx-consistency",
            str(verification),
            str(hvac),
            "--format",
            "json",
        ],
    )

    code = consistency_main()
    payload = json.loads(capsys.readouterr().out)

    assert code in {0, 2}
    assert payload["status"] in {
        "pass",
        "fail",
        "pass_with_scope_difference",
        "not_comparable",
    }
    assert "application_execution_provenance" not in payload


def test_dossier_cli_does_not_require_writable_manifest_directory(
    monkeypatch, tmp_path, capsys
):
    source_dir = tmp_path / "read-only-inputs"
    source_dir.mkdir()
    verification = source_dir / "facility_project.json"
    verification.write_bytes((EXAMPLES / "facility_project.json").read_bytes())
    manifest = source_dir / "dossier.json"
    manifest.write_text(
        json.dumps(
            {
                "name": "Read-only source dossier",
                "verification_project": verification.name,
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "dossier-output.json"
    source_dir.chmod(0o555)
    try:
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cleanroomx-dossier",
                str(manifest),
                "--format",
                "json",
                "--output",
                str(output),
            ],
        )
        code = dossier_main()
    finally:
        source_dir.chmod(0o755)

    assert code in {0, 2}
    assert capsys.readouterr().err == ""
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["source_files"][0]["path"] == verification.name


def test_dossier_cli_preserves_json_result_contract(monkeypatch, tmp_path, capsys):
    verification = _copy_example(tmp_path, "facility_project.json")
    manifest = tmp_path / "dossier.json"
    manifest.write_text(
        json.dumps(
            {
                "name": "Stable dossier",
                "verification_project": verification.name,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["cleanroomx-dossier", str(manifest), "--format", "json"],
    )

    code = dossier_main()
    payload = json.loads(capsys.readouterr().out)

    assert code in {0, 2}
    assert "executive_summary" in payload
    assert "source_files" in payload
