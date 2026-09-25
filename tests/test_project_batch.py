from __future__ import annotations

import copy
import json

import cleanroomx.project_batch as project_batch
from cleanroomx.project import AnalysisDocument, ProjectDocument, save_project_document
from cleanroomx.project_batch import (
    PROJECT_BATCH_SCHEMA,
    ProjectAnalysisOutcome,
    ProjectBatchRun,
    main,
    project_batch_exit_code,
    render_project_batch_markdown,
    run_project_file,
)


ROOM_INPUT = {
    "name": "Example cleanroom",
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


def _project(*, include_invalid: bool = False) -> ProjectDocument:
    analyses = []
    if include_invalid:
        analyses.append(
            AnalysisDocument(
                id="bad",
                name="Invalid room",
                kind="room_verification",
                input={"name": "Incomplete room"},
            )
        )
    analyses.extend(
        [
            AnalysisDocument(
                id="room-a",
                name="Room A",
                kind="room_verification",
                input=copy.deepcopy(ROOM_INPUT),
            ),
            AnalysisDocument(
                id="room-b",
                name="Room B",
                kind="room_verification",
                input={**copy.deepcopy(ROOM_INPUT), "name": "Second cleanroom"},
            ),
        ]
    )
    return ProjectDocument(
        name="Batch Demo",
        analyses=analyses,
        active_analysis_id=analyses[0].id,
    )


def test_project_batch_runs_all_analyses_in_project_order_and_is_deterministic(tmp_path):
    path = save_project_document(tmp_path / "batch.cleanroomx.json", _project())

    first = run_project_file(path)
    second = run_project_file(path)

    assert first.source_stable_during_run is True
    assert first.selected_analysis_ids == ("room-a", "room-b")
    assert [item.analysis_id for item in first.outcomes] == ["room-a", "room-b"]
    assert first.completed_count == 2
    assert first.error_count == 0
    assert project_batch_exit_code(first) == 0
    assert first.to_dict() == second.to_dict()

    payload = first.to_dict()
    assert payload["schema"] == PROJECT_BATCH_SCHEMA
    assert payload["project"]["source_revision"]["sha256"]
    for outcome in payload["analyses"]:
        provenance = outcome["run"]["diagnostics"]["application_execution_provenance"]
        assert provenance["analysis_kind"] == "room_verification"
        assert provenance["input_sha256"]


def test_project_batch_selection_preserves_project_order_not_cli_order(tmp_path):
    path = save_project_document(tmp_path / "batch.cleanroomx.json", _project())

    batch = run_project_file(path, analysis_ids=["room-b", "room-a"])

    assert batch.selected_analysis_ids == ("room-a", "room-b")
    assert [item.analysis_id for item in batch.outcomes] == ["room-a", "room-b"]


def test_project_batch_isolates_analysis_failure_and_continues_by_default(tmp_path):
    path = save_project_document(
        tmp_path / "batch.cleanroomx.json",
        _project(include_invalid=True),
    )

    batch = run_project_file(path)

    assert [item.execution_state for item in batch.outcomes] == [
        "error",
        "completed",
        "completed",
    ]
    assert batch.error_count == 1
    assert batch.completed_count == 2
    assert batch.outcomes[0].error_type
    assert batch.outcomes[0].error_message
    assert project_batch_exit_code(batch) == 2


def test_project_batch_fail_fast_stops_after_first_execution_error(tmp_path):
    path = save_project_document(
        tmp_path / "batch.cleanroomx.json",
        _project(include_invalid=True),
    )

    batch = run_project_file(path, fail_fast=True)

    assert batch.attempted_count == 1
    assert batch.outcomes[0].analysis_id == "bad"
    assert batch.outcomes[0].execution_state == "error"
    assert batch.source_stable_during_run is True


def test_project_batch_stops_scheduling_when_source_changes_mid_run(tmp_path, monkeypatch):
    path = save_project_document(tmp_path / "batch.cleanroomx.json", _project())
    original_run_analysis = project_batch.run_analysis
    mutated = False

    def run_and_modify_source(kind, payload, *, base_dir=None):
        nonlocal mutated
        result = original_run_analysis(kind, payload, base_dir=base_dir)
        if not mutated:
            mutated = True
            path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
        return result

    monkeypatch.setattr(project_batch, "run_analysis", run_and_modify_source)

    batch = run_project_file(path)

    assert batch.source_stable_during_run is False
    assert batch.source_change_stage == "after-analysis"
    assert batch.source_change_analysis_id == "room-a"
    assert batch.attempted_count == 1
    assert batch.completed_count == 1
    assert project_batch_exit_code(batch) == 3


def test_project_batch_cli_writes_strict_json_atomically(tmp_path):
    project_path = save_project_document(tmp_path / "batch.cleanroomx.json", _project())
    output_path = tmp_path / "batch-result.json"

    code = main(
        [
            str(project_path),
            "--analysis",
            "room-b",
            "--format",
            "json",
            "--output",
            str(output_path),
        ]
    )

    assert code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema"] == PROJECT_BATCH_SCHEMA
    assert payload["selection"]["analysis_ids"] == ["room-b"]
    assert payload["execution"]["completed_count"] == 1
    json.dumps(payload, allow_nan=False)


def test_project_batch_markdown_summarizes_traceability_without_dumping_result(tmp_path):
    path = save_project_document(tmp_path / "batch.cleanroomx.json", _project())

    batch = run_project_file(path, analysis_ids=["room-a"])
    text = render_project_batch_markdown(batch)

    assert "# CleanroomX project batch" in text
    assert "Source SHA-256" in text
    assert "Room A" in text
    assert "Input SHA-256" in text
    assert '"particle_requirements"' not in text


def test_project_batch_rejects_unknown_analysis_selection(tmp_path):
    path = save_project_document(tmp_path / "batch.cleanroomx.json", _project())

    try:
        run_project_file(path, analysis_ids=["missing"])
    except ValueError as exc:
        assert "unknown project analysis id" in str(exc)
    else:
        raise AssertionError("unknown analysis selection should fail")


def test_project_batch_markdown_escapes_untrusted_structure():
    batch = ProjectBatchRun(
        project_name="Demo\n# injected",
        source_path="folder|name/project.md",
        source_size_bytes=1,
        source_sha256="a" * 64,
        selected_analysis_ids=("id",),
        outcomes=(
            ProjectAnalysisOutcome(
                analysis_id="id",
                analysis_name="Room\n## injected",
                kind="room_verification",
                execution_state="error",
                error_type="Bad*Type",
                error_message="boom\n| injected | row |",
            ),
        ),
        source_stable_during_run=True,
    )

    rendered = render_project_batch_markdown(batch)

    assert "\n# injected" not in rendered
    assert "\n## injected" not in rendered
    assert "\n| injected | row |" not in rendered
    assert "Demo<br># injected" in rendered
    assert "Room<br>## injected" in rendered
    assert "folder\\|name/project.md" in rendered
    assert "Bad\\*Type" in rendered
