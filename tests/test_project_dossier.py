from __future__ import annotations

import copy
import json

import cleanroomx.project_dossier_cli as dossier_cli
from cleanroomx.project import (
    AnalysisDocument,
    ProjectDocument,
    capture_project_file_revision,
    load_project_document,
    save_project_document,
)
from cleanroomx.project_dossier import (
    PROJECT_ENGINEERING_DOSSIER_SCHEMA,
    build_project_engineering_dossier,
    markdown_project_engineering_dossier,
)
from cleanroomx.project_requirement_evidence_mappings import (
    PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY,
    PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA,
    PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA_VERSION,
)
from cleanroomx.project_requirements import (
    PROJECT_REQUIREMENTS_METADATA_KEY,
    PROJECT_REQUIREMENTS_SCHEMA,
    PROJECT_REQUIREMENTS_SCHEMA_VERSION,
)
from cleanroomx.project_requirements_workflow import run_project_requirements_workflow
from cleanroomx.project_verification_persistence import (
    persist_project_requirements_workflow_run,
)


ROOM_INPUT = {
    "name": "ROOM-A",
    "length_m": 6.0,
    "width_m": 4.0,
    "height_m": 3.0,
    "supply_airflow_m3_h": 1800.0,
    "min_ach": 20.0,
    "min_pressure_pa": 10.0,
    "observed_pressure_pa": 14.0,
    "particle_requirements": [
        {
            "size_um": 0.5,
            "max_concentration_per_m3": 400000.0,
            "observed_concentration_per_m3": 120000.0,
        }
    ],
}


def _requirements() -> dict:
    return {
        "schema": PROJECT_REQUIREMENTS_SCHEMA,
        "schema_version": PROJECT_REQUIREMENTS_SCHEMA_VERSION,
        "sets": [
            {
                "id": "urs-main",
                "title": "Approved URS",
                "description": "Project criteria.",
                "source": "URS.pdf",
                "source_revision": "Rev C",
                "requirements": [
                    {
                        "id": "REQ-ACH",
                        "title": "Room ACH",
                        "description": "Room air change criterion.",
                        "discipline": "HVAC",
                        "category": "air_change_rate",
                        "source": "Project URS",
                        "source_revision": "Rev C",
                        "reference": "7.2",
                        "unit": "1/h",
                        "target": None,
                        "minimum": 20.0,
                        "maximum": None,
                        "tolerance": 0.0,
                        "applicability": "applicable",
                        "scope": ["ROOM-A"],
                        "verification_method": "calculation",
                        "required_evidence": ["calculation"],
                        "status": "approved",
                        "assumptions": [],
                        "notes": None,
                    }
                ],
            }
        ],
    }


def _mappings() -> dict:
    return {
        "schema": PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA,
        "schema_version": PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA_VERSION,
        "mappings": [
            {
                "id": "MAP-ACH",
                "requirement_id": "REQ-ACH",
                "analysis_id": "room-a",
                "expected_analysis_kind": "room_verification",
                "subject_ref": "ROOM-A",
                "property_name": "air_change_rate",
                "result_path": ["ach"],
                "unit": "1/h",
                "evidence_kinds": ["calculation"],
                "status": "active",
                "notes": None,
            }
        ],
    }


def _project() -> ProjectDocument:
    return ProjectDocument(
        name="Project-native dossier demo",
        description="Canonical requirements-to-evidence dossier test.",
        analyses=[
            AnalysisDocument(
                id="room-a",
                name="Room A verification",
                kind="room_verification",
                input=copy.deepcopy(ROOM_INPUT),
            )
        ],
        active_analysis_id="room-a",
        metadata={
            PROJECT_REQUIREMENTS_METADATA_KEY: _requirements(),
            PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY: _mappings(),
        },
    )


def _persisted_project(tmp_path):
    path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        _project(),
    )
    workflow = run_project_requirements_workflow(path, "room-a")
    persisted = persist_project_requirements_workflow_run(
        path,
        workflow,
        completed_at_utc="2026-10-01T11:00:00Z",
    )
    project = load_project_document(path)
    revision = capture_project_file_revision(path)
    return path, project, revision, persisted


def test_project_engineering_dossier_is_deterministic_and_does_not_mutate():
    project = ProjectDocument(name="Empty evidence project")
    before = project.to_dict()
    source_revision = "a" * 64

    first = build_project_engineering_dossier(
        project,
        source_project_revision=source_revision,
    )
    second = build_project_engineering_dossier(
        project,
        source_project_revision=source_revision,
    )

    assert first == second
    assert project.to_dict() == before
    assert first["schema"] == PROJECT_ENGINEERING_DOSSIER_SCHEMA
    assert first["source_project_revision"] == source_revision
    assert first["requirements"]["configured"] is False
    assert first["requirement_evidence_mappings"]["configured"] is False
    assert first["analysis_run_history"]["integrity"]["record_count"] == 0
    assert first["verification_run_history"]["integrity"]["record_count"] == 0
    assert len(first["dossier_sha256"]) == 64
    json.dumps(first, allow_nan=False)


def test_project_engineering_dossier_preserves_canonical_verification_evidence(tmp_path):
    _path, project, revision, persisted = _persisted_project(tmp_path)

    dossier = build_project_engineering_dossier(
        project,
        source_project_revision=revision.sha256,
        base_dir=tmp_path,
    )

    assert dossier["requirements"]["configured"] is True
    assert dossier["requirements"]["requirement_count"] == 1
    assert dossier["requirements"]["requirements_sha256"] == (
        persisted.record["requirements_sha256"]
    )
    assert dossier["requirement_evidence_mappings"]["mapping_count"] == 1
    assert dossier["requirement_evidence_mappings"]["mappings_sha256"] == (
        persisted.record["mappings_sha256"]
    )
    history = dossier["verification_run_history"]
    assert history["integrity"]["record_count"] == 1
    assert history["records"][0] == persisted.record
    assert history["records"][0]["evidence"][0]["evidence_locator"] == "/result/ach"
    assert history["latest_by_analysis"][0]["status"] == "pass"
    assert history["latest_by_analysis"][0]["verified"] is True
    assert history["latest_by_analysis"][0]["current_assessment"]["state"] == "current"
    assert history["latest_by_analysis"][0]["current_assessment"]["current"] is True
    assert (
        history["latest_by_analysis"][0]["project_source_revision"]
        == persisted.record["project_source_revision"]
    )
    assert dossier["project_diagnostics"]["project"]["verification_run_count"] == 1
    assert (
        dossier["engineering_boundary"][
            "historical_verification_is_current_certification"
        ]
        is False
    )


def test_project_engineering_dossier_marks_historical_pass_stale_after_edit(tmp_path):
    _path, project, _revision, _persisted = _persisted_project(tmp_path)
    project.analyses[0].input["supply_airflow_m3_h"] += 1.0

    dossier = build_project_engineering_dossier(
        project,
        source_project_revision="b" * 64,
        base_dir=tmp_path,
    )

    latest = dossier["verification_run_history"]["latest_by_analysis"][0]
    assert latest["status"] == "pass"
    assert latest["verified"] is True
    assessment = latest["current_assessment"]
    assert assessment["state"] == "stale"
    assert assessment["current"] is False
    assert "analysis_input_changed" in assessment["mismatch_reasons"]

    markdown = markdown_project_engineering_dossier(dossier)
    assert "Historical status" in markdown
    assert "Current currency" in markdown
    assert "stale (analysis_input_changed)" in markdown


def test_project_engineering_dossier_markdown_verifies_digest(tmp_path):
    _path, project, revision, _persisted = _persisted_project(tmp_path)
    dossier = build_project_engineering_dossier(
        project,
        source_project_revision=revision.sha256,
        base_dir=tmp_path,
    )

    markdown = markdown_project_engineering_dossier(dossier)

    assert "# CleanroomX Project Engineering Dossier" in markdown
    assert "Latest retained verification by analysis" in markdown
    assert "Room A verification" in markdown
    assert "Historical status" in markdown
    assert "Current currency" in markdown
    assert "| Room A verification | 1 | pass | current |" in markdown
    assert dossier["dossier_sha256"] in markdown

    tampered = copy.deepcopy(dossier)
    tampered["project"]["name"] = "Tampered"
    try:
        markdown_project_engineering_dossier(tampered)
    except ValueError as exc:
        assert "integrity digest is invalid" in str(exc)
    else:
        raise AssertionError("tampered dossier should be rejected")


def test_project_dossier_cli_writes_revision_bound_strict_json(tmp_path):
    project_path, _project_value, revision, _persisted = _persisted_project(tmp_path)
    output_path = tmp_path / "dossier.json"

    exit_code = dossier_cli.main(
        [str(project_path), "--output", str(output_path)]
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["schema"] == PROJECT_ENGINEERING_DOSSIER_SCHEMA
    assert payload["source_project_revision"] == revision.sha256
    assert payload["verification_run_history"]["integrity"]["record_count"] == 1
    assert len(payload["dossier_sha256"]) == 64
    json.dumps(payload, allow_nan=False)


def test_project_dossier_cli_writes_markdown(tmp_path):
    project_path, _project_value, _revision, _persisted = _persisted_project(tmp_path)
    output_path = tmp_path / "dossier.md"

    exit_code = dossier_cli.main(
        [
            str(project_path),
            "--format",
            "markdown",
            "--output",
            str(output_path),
        ]
    )

    text = output_path.read_text(encoding="utf-8")
    assert exit_code == 0
    assert "# CleanroomX Project Engineering Dossier" in text
    assert "Room A verification" in text
    assert "historical evidence" in text


def test_project_dossier_cli_refuses_source_as_output(tmp_path, capsys):
    project_path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        ProjectDocument(name="Protected source"),
    )
    before = project_path.read_bytes()

    exit_code = dossier_cli.main(
        [str(project_path), "--output", str(project_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert project_path.read_bytes() == before
    assert "output path must be different from the project source" in captured.err


def test_project_dossier_cli_discards_output_if_source_changes(tmp_path, monkeypatch):
    project_path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        ProjectDocument(name="Changing source"),
    )
    output_path = tmp_path / "dossier.json"
    output_path.write_text("previous-valid-report\n", encoding="utf-8")
    real_build = dossier_cli.build_project_engineering_dossier

    def mutate_source(project, *, source_project_revision, base_dir=None):
        result = real_build(
            project,
            source_project_revision=source_project_revision,
            base_dir=base_dir,
        )
        project_path.write_text(
            project_path.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
        return result

    monkeypatch.setattr(
        dossier_cli,
        "build_project_engineering_dossier",
        mutate_source,
    )

    exit_code = dossier_cli.main(
        [str(project_path), "--output", str(output_path)]
    )

    assert exit_code == 2
    assert output_path.read_text(encoding="utf-8") == "previous-valid-report\n"
