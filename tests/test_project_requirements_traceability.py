from __future__ import annotations

import copy
import json

import cleanroomx.project_requirements_traceability_cli as traceability_cli

from cleanroomx.project import (
    AnalysisDocument,
    ProjectDocument,
    save_project_document,
)
from cleanroomx.project_requirement_evidence_mappings import (
    PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY,
    ProjectRequirementEvidenceMapping,
    ProjectRequirementEvidenceMappings,
)
from cleanroomx.project_requirement_verification import RequirementEvidenceAuthority
from cleanroomx.project_requirements import (
    PROJECT_REQUIREMENTS_METADATA_KEY,
    ProjectRequirement,
    ProjectRequirementSet,
    ProjectRequirements,
)
from cleanroomx.project_requirements_traceability import (
    PROJECT_REQUIREMENTS_TRACEABILITY_SCHEMA,
    build_project_requirements_traceability,
    markdown_project_requirements_traceability,
)
from cleanroomx.project_requirements_traceability_cli import (
    main as traceability_main,
)


def _project() -> ProjectDocument:
    requirement = ProjectRequirement(
        id="REQ-ACH",
        title="Room air changes",
        description="Minimum room air change criterion.",
        discipline="HVAC",
        category="air_change_rate",
        source="Project URS",
        source_revision="Rev C",
        reference="7.2",
        unit="1/h",
        minimum=20.0,
        tolerance=0.0,
        applicability="applicable",
        scope=("ROOM-A",),
        verification_method="calculation",
        required_evidence=("calculation",),
        status="approved",
    )
    requirements = ProjectRequirements(
        sets=(
            ProjectRequirementSet(
                id="URS-MAIN",
                title="Approved URS",
                source="URS.pdf",
                source_revision="Rev C",
                requirements=(requirement,),
            ),
        )
    )
    mappings = ProjectRequirementEvidenceMappings(
        mappings=(
            ProjectRequirementEvidenceMapping(
                id="MAP-ACH",
                requirement_id="REQ-ACH",
                analysis_id="room-a",
                expected_analysis_kind="room_verification",
                subject_ref="ROOM-A",
                property_name="air_change_rate",
                result_path=("ach",),
                unit="1/h",
                evidence_kinds=("calculation",),
                status="active",
            ),
        )
    )
    return ProjectDocument(
        name="Traceability demo",
        analyses=[
            AnalysisDocument(
                id="room-a",
                name="Room A verification",
                kind="room_verification",
                input={
                    "name": "ROOM-A",
                    "length_m": 6.0,
                    "width_m": 4.0,
                    "height_m": 3.0,
                    "supply_airflow_m3_h": 1800.0,
                    "min_ach": 20.0,
                    "min_pressure_pa": 10.0,
                    "observed_pressure_pa": 14.0,
                    "particle_requirements": [],
                },
            )
        ],
        active_analysis_id="room-a",
        metadata={
            PROJECT_REQUIREMENTS_METADATA_KEY: requirements.to_dict(),
            PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY: mappings.to_dict(),
        },
    )


def test_traceability_projects_canonical_requirements_and_mappings():
    project = _project()

    result = build_project_requirements_traceability(project)

    assert result["schema"] == PROJECT_REQUIREMENTS_TRACEABILITY_SCHEMA
    assert result["summary"] == {
        "requirement_set_count": 1,
        "requirement_count": 1,
        "mapping_count": 1,
        "active_mapping_count": 1,
        "active_mapped_requirement_count": 1,
        "evidence_authority_count": 0,
        "historical_reference_count": 0,
    }
    assert result["registries"]["requirements_sha256"] == project.metadata[
        PROJECT_REQUIREMENTS_METADATA_KEY
    ]["requirements_sha256"]
    assert result["registries"]["mappings_sha256"] == project.metadata[
        PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY
    ]["mappings_sha256"]
    requirement = result["requirements"][0]
    assert requirement["criterion"] == {
        "target": None,
        "minimum": 20.0,
        "maximum": None,
        "tolerance": 0.0,
        "unit": "1/h",
    }
    mapping = result["mappings"][0]
    assert mapping["reference_state"] == "resolved"
    assert mapping["resolved_analysis"] == {
        "id": "room-a",
        "name": "Room A verification",
        "kind": "room_verification",
    }
    json.dumps(result, allow_nan=False)


def test_traceability_exposes_explicit_evidence_authority():
    project = _project()
    original = project.metadata[
        PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY
    ]
    original_mapping = ProjectRequirementEvidenceMapping(
        id="MAP-ACH",
        requirement_id="REQ-ACH",
        analysis_id="room-a",
        expected_analysis_kind="room_verification",
        subject_ref="ROOM-A",
        property_name="air_change_rate",
        result_path=("ach",),
        unit="1/h",
        evidence_kinds=("calculation",),
        status="active",
    )
    alternate_mapping = ProjectRequirementEvidenceMapping(
        id="MAP-ACH-ALT",
        requirement_id="REQ-ACH",
        analysis_id="room-a",
        expected_analysis_kind="room_verification",
        subject_ref="ROOM-A",
        property_name="air_change_rate",
        result_path=("ach",),
        unit="1/h",
        evidence_kinds=("calculation",),
        status="active",
    )
    registry = ProjectRequirementEvidenceMappings(
        mappings=(original_mapping, alternate_mapping),
        evidence_authority=(
            RequirementEvidenceAuthority(
                requirement_id="REQ-ACH",
                subject_ref="ROOM-A",
                evidence_id="MAP-ACH",
                authority_source="Project verification authority",
                decision_reference="DEC-REQ-AUTH",
                decision_revision="Rev 1",
                rationale="Approved calculation evidence selection.",
            ),
        ),
    )
    project.metadata[PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY] = (
        registry.to_dict()
    )

    result = build_project_requirements_traceability(project)
    authority = result["evidence_authority"][0]

    assert original["mappings_sha256"] != registry.sha256
    assert result["summary"]["evidence_authority_count"] == 1
    assert authority["analysis_id"] == "room-a"
    assert authority["evidence_id"] == "MAP-ACH"
    assert authority["candidate_mapping_ids"] == ["MAP-ACH", "MAP-ACH-ALT"]
    assert authority["decision_reference"] == "DEC-REQ-AUTH"

    report = markdown_project_requirements_traceability(result)
    assert "Explicit evidence authority" in report
    assert "DEC-REQ-AUTH" in report
    assert "MAP-ACH-ALT" in report


def test_traceability_preserves_historical_kind_mismatch_without_rebinding():
    project = _project()
    historical = ProjectRequirementEvidenceMappings(
        mappings=(
            ProjectRequirementEvidenceMapping(
                id="MAP-ACH",
                requirement_id="REQ-ACH",
                analysis_id="room-a",
                expected_analysis_kind="pressure_cascade",
                subject_ref="ROOM-A",
                property_name="air_change_rate",
                result_path=("ach",),
                unit="1/h",
                evidence_kinds=("calculation",),
                status="superseded",
            ),
        )
    )
    project.metadata[PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY] = (
        historical.to_dict()
    )

    result = build_project_requirements_traceability(project)

    mapping = result["mappings"][0]
    assert mapping["reference_state"] == "historical_reference"
    assert mapping["analysis_reference_state"] == "kind_mismatch"
    assert mapping["resolved_analysis"] is None
    assert mapping["current_analysis_candidate"]["kind"] == "room_verification"
    assert result["summary"]["historical_reference_count"] == 1


def test_traceability_markdown_exposes_identity_and_exact_result_path():
    traceability = build_project_requirements_traceability(_project())
    traceability["source"] = {
        "path": "/tmp/project.cleanroomx.json",
        "size_bytes": 1234,
        "sha256": "a" * 64,
        "stable_during_inspection": True,
    }
    report = markdown_project_requirements_traceability(traceability)

    assert "# Project Requirements Traceability" in report
    assert "a" * 64 in report
    assert "Source project bytes: 1234" in report
    assert "Source stable during inspection: True" in report
    assert "REQ-ACH" in report
    assert "MAP-ACH" in report
    assert r'\["ach"\]' in report
    assert "does not infer requirements" in report


def test_traceability_markdown_escapes_untrusted_structure():
    traceability = build_project_requirements_traceability(_project())
    traceability["project"]["name"] = "Plant\n# injected <script> *bold* [link] | x"
    traceability["requirements"][0]["id"] = "REQ|<tag>*critical*"
    traceability["mappings"][0]["property_name"] = "ach|<tag>*bold*\nnext"

    report = markdown_project_requirements_traceability(traceability)

    assert "Plant<br># injected &lt;script&gt; \\*bold\\* \\[link\\] \\| x" in report
    assert "REQ\\|&lt;tag&gt;\\*critical\\*" in report
    assert "ach\\|&lt;tag&gt;\\*bold\\*<br>next" in report
    assert "<script>" not in report


def test_traceability_cli_emits_stable_json(tmp_path, capsys):
    path = save_project_document(tmp_path / "project.cleanroomx.json", _project())

    exit_code = traceability_main([str(path)])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert payload["schema"] == PROJECT_REQUIREMENTS_TRACEABILITY_SCHEMA
    assert payload["source"]["stable_during_inspection"] is True
    assert len(payload["source"]["sha256"]) == 64
    assert payload["summary"]["active_mapping_count"] == 1


def test_traceability_cli_writes_markdown_atomically(tmp_path):
    path = save_project_document(tmp_path / "project.cleanroomx.json", _project())
    output = tmp_path / "traceability.md"

    exit_code = traceability_main(
        [str(path), "--format", "markdown", "--output", str(output)]
    )

    assert exit_code == 0
    text = output.read_text(encoding="utf-8")
    assert "Requirements SHA-256" in text
    assert "MAP-ACH" in text


def test_traceability_cli_refuses_to_overwrite_project(tmp_path, capsys):
    path = save_project_document(tmp_path / "project.cleanroomx.json", _project())

    exit_code = traceability_main([str(path), "--output", str(path)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "output path must be different from the project source" in captured.err


def test_traceability_cli_rechecks_output_identity_before_publication(
    tmp_path,
    monkeypatch,
):
    path = save_project_document(tmp_path / "project.cleanroomx.json", _project())
    output = tmp_path / "traceability.json"
    output.write_text("previous-valid-report\n", encoding="utf-8")
    real_guard = traceability_cli._assert_project_output_is_safe
    guard_calls = 0

    def race_guard(project, *, source, output):
        nonlocal guard_calls
        guard_calls += 1
        if guard_calls == 2:
            raise ValueError("output path identity changed before publication")
        real_guard(project, source=source, output=output)

    monkeypatch.setattr(
        traceability_cli,
        "_assert_project_output_is_safe",
        race_guard,
    )

    exit_code = traceability_cli.main(
        [str(path), "--output", str(output)]
    )

    assert exit_code == 2
    assert guard_calls == 2
    assert output.read_text(encoding="utf-8") == "previous-valid-report\n"

def test_traceability_cli_reports_project_path_resolution_errors(monkeypatch, capsys):
    def fail_resolve(self, strict=False):
        raise OSError("cannot resolve project path")

    monkeypatch.setattr(traceability_cli.Path, "resolve", fail_resolve)

    exit_code = traceability_cli.main(["broken.cleanroomx.json"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "cannot resolve project path" in captured.err

def test_traceability_cli_rechecks_source_revision_at_atomic_replace_boundary(
    tmp_path,
    monkeypatch,
):
    path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        _project(),
    )
    output = tmp_path / "traceability.json"
    output.write_text("previous-valid-report\n", encoding="utf-8")
    real_atomic_write_text = traceability_cli.atomic_write_text

    def mutate_source_after_staging(destination, text, *, before_replace=None):
        assert before_replace is not None

        def race_then_validate():
            path.write_bytes(path.read_bytes() + b"\n")
            before_replace()

        return real_atomic_write_text(
            destination,
            text,
            before_replace=race_then_validate,
        )

    monkeypatch.setattr(
        traceability_cli,
        "atomic_write_text",
        mutate_source_after_staging,
    )

    exit_code = traceability_cli.main(
        [str(path), "--output", str(output)]
    )

    assert exit_code == 2
    assert output.read_text(encoding="utf-8") == "previous-valid-report\n"

