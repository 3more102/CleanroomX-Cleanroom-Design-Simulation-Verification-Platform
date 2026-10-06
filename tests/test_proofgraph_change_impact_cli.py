from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

import cleanroomx.proofgraph_change_impact_cli as cli
from cleanroomx.proofgraph import (
    ComplianceCheck,
    ComplianceFinding,
    ComplianceVerdict,
    DesignEvidence,
    EvidenceSource,
    ProofGraph,
    Requirement,
    RequirementSet,
    VerificationRun,
)
from cleanroomx.proofgraph_change_impact_cli import main


def _graph(*, source_revision: str = "a" * 64) -> ProofGraph:
    source = EvidenceSource(
        id="SOURCE",
        kind="ifc",
        reference="facility.ifc",
        revision=source_revision,
    )
    requirement = Requirement(
        id="REQ",
        title="Pressure relationship",
        source="Project URS",
        criteria={"operator": "min", "expected": 10.0, "unit": "Pa"},
    )
    evidence = DesignEvidence(
        id="EVIDENCE",
        property_name="pressure_differential_pa",
        value=13.0,
        unit="Pa",
        source_id=source.id,
    )
    check = ComplianceCheck(
        id="CHECK",
        requirement_id=requirement.id,
        evidence_ids=(evidence.id,),
        required_evidence_kinds=("design",),
    )
    finding = ComplianceFinding(
        id="FINDING",
        check_id=check.id,
        requirement_id=requirement.id,
        status="pass",
        reason="Pressure relationship passes.",
        evidence_ids=(evidence.id,),
        evidence_present=True,
        expected=10.0,
        actual=13.0,
        unit="Pa",
        delta=3.0,
    )
    verdict = ComplianceVerdict(
        id="VERDICT",
        requirement_id=requirement.id,
        status="pass",
        finding_ids=(finding.id,),
        reason=finding.reason,
    )
    run = VerificationRun(
        id="RUN",
        requirement_set_id="URS",
        check_ids=(check.id,),
        verdict_ids=(verdict.id,),
        input_sha256="b" * 64,
    )
    return ProofGraph(
        id="GRAPH",
        requirement_set=RequirementSet(
            id="URS",
            version="1",
            title="URS",
            source="Project URS",
            requirements=(requirement,),
        ),
        evidence_sources=(source,),
        evidence=(evidence,),
        checks=(check,),
        findings=(finding,),
        verdicts=(verdict,),
        verification_runs=(run,),
    )


def _write(path: Path, graph: ProofGraph) -> Path:
    path.write_text(
        json.dumps(graph.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def test_cli_emits_deterministic_json_for_identical_graphs(
    tmp_path: Path, capsys
) -> None:
    baseline = _write(tmp_path / "baseline.json", _graph())
    candidate = _write(tmp_path / "candidate.json", _graph())

    assert main([str(baseline), str(candidate), "--require-identical"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["changed"] is False
    assert len(payload["impact_sha256"]) == 64


def test_cli_require_no_stale_fails_when_source_revision_changes(
    tmp_path: Path, capsys
) -> None:
    baseline = _write(tmp_path / "baseline.json", _graph())
    candidate = _write(
        tmp_path / "candidate.json",
        _graph(source_revision="c" * 64),
    )

    assert main([str(baseline), str(candidate), "--require-no-stale"]) == 2

    payload = json.loads(capsys.readouterr().out)
    assert payload["potentially_stale_candidate"]["evidence_ids"] == ["EVIDENCE"]
    assert payload["potentially_stale_candidate"]["verdict_ids"] == ["VERDICT"]


def test_cli_require_identical_reports_changed_candidate(
    tmp_path: Path, capsys
) -> None:
    baseline_graph = _graph()
    changed_evidence = replace(baseline_graph.evidence[0], value=14.0)
    changed_finding = replace(
        baseline_graph.findings[0],
        actual=14.0,
        delta=4.0,
    )
    candidate_graph = replace(
        baseline_graph,
        evidence=(changed_evidence,),
        findings=(changed_finding,),
    )
    baseline = _write(tmp_path / "baseline.json", baseline_graph)
    candidate = _write(tmp_path / "candidate.json", candidate_graph)

    assert main([str(baseline), str(candidate), "--require-identical"]) == 2
    assert json.loads(capsys.readouterr().out)["changed"] is True


def test_cli_refuses_output_that_aliases_input_without_modifying_it(
    tmp_path: Path, capsys
) -> None:
    baseline = _write(tmp_path / "baseline.json", _graph())
    candidate = _write(tmp_path / "candidate.json", _graph())
    before = baseline.read_bytes()

    assert main(
        [str(baseline), str(candidate), "--output", str(baseline)]
    ) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error:" in captured.err
    assert "Traceback" not in captured.err
    assert baseline.read_bytes() == before


def test_cli_rejects_invalid_strict_json_without_traceback(
    tmp_path: Path, capsys
) -> None:
    baseline = tmp_path / "bad.json"
    baseline.write_text('{"schema":"a","schema":"b"}\n', encoding="utf-8")
    candidate = _write(tmp_path / "candidate.json", _graph())

    assert main([str(baseline), str(candidate)]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "duplicate JSON object key" in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize("invalid_side", ["baseline", "candidate"])
@pytest.mark.parametrize(
    ("field", "value"),
    [("kind", []), ("kind", {}), ("provenance", None)],
)
def test_cli_rejects_malformed_evidence_without_touching_files(
    tmp_path: Path, capsys, invalid_side: str, field: str, value
) -> None:
    baseline = _write(tmp_path / "baseline.json", _graph())
    candidate = _write(tmp_path / "candidate.json", _graph())
    invalid = baseline if invalid_side == "baseline" else candidate
    document = json.loads(invalid.read_text(encoding="utf-8"))
    document["evidence"][0][field] = value
    invalid.write_text(json.dumps(document), encoding="utf-8")
    output = tmp_path / "report.json"
    output.write_text("previous report\n", encoding="utf-8")
    before = {path: path.read_bytes() for path in (baseline, candidate, output)}

    assert main([str(baseline), str(candidate), "--output", str(output)]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith(
        "cleanroomx-proofgraph-diff: error: invalid input structure:"
    )
    assert "Traceback" not in captured.err
    assert all(path.read_bytes() == payload for path, payload in before.items())


def test_cli_does_not_hide_unexpected_loader_runtime_error(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    def fail(_path):
        raise RuntimeError("programming defect")

    monkeypatch.setattr(cli, "_load_graph", fail)
    with pytest.raises(RuntimeError, match="programming defect"):
        main([str(tmp_path / "baseline.json"), str(tmp_path / "candidate.json")])
    assert capsys.readouterr().err == ""
