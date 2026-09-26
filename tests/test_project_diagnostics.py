from __future__ import annotations

import copy
import json
from pathlib import Path

from cleanroomx.application import run_analysis
import cleanroomx.project_diagnostics_cli as diagnostics_cli
from cleanroomx.project import AnalysisDocument, ProjectDocument, save_project_document
from cleanroomx.project_diagnostics import (
    PROJECT_DIAGNOSTICS_SCHEMA,
    analyze_project_diagnostics,
    markdown_project_diagnostics_report,
)
from cleanroomx.project_diagnostics_cli import main as diagnostics_main
from cleanroomx.run_history import append_run_history_record
from cleanroomx.spatial import empty_layout


ROOT = Path(__file__).resolve().parents[1]


def _room_payload() -> dict:
    return json.loads((ROOT / "examples" / "basic_room.json").read_text(encoding="utf-8"))


def _spatial_room(*, room_id: str, name: str, x_m: float, length_m: float = 6.0) -> dict:
    return {
        "id": room_id,
        "name": name,
        "analysis_room_name": name,
        "x_m": x_m,
        "y_m": 0.0,
        "length_m": length_m,
        "width_m": 4.0,
        "height_m": 3.0,
        "floor_elevation_m": 0.0,
    }


def test_project_diagnostics_are_deterministic_and_do_not_mutate_project():
    payload = _room_payload()
    project = ProjectDocument(
        name="Diagnostic demo",
        analyses=[
            AnalysisDocument(
                id="room-1",
                name="Room verification",
                kind="room_verification",
                input=payload,
            )
        ],
        active_analysis_id="room-1",
    )
    before = project.to_dict()

    first = analyze_project_diagnostics(project)
    second = analyze_project_diagnostics(project)

    assert first == second
    assert project.to_dict() == before
    assert first["schema"] == PROJECT_DIAGNOSTICS_SCHEMA
    assert first["summary"] == {
        "status": "pass",
        "complete": True,
        "issue_count": 1,
        "error_count": 0,
        "warning_count": 0,
        "info_count": 1,
    }
    assert first["issues"][0]["rule"] == "run_history.analysis_not_run"
    json.dumps(first, allow_nan=False)


def test_project_diagnostics_reuse_spatial_validation_with_actionable_ids():
    layout = empty_layout()
    layout["rooms"] = [
        _spatial_room(room_id="a", name="A", x_m=0.0),
        _spatial_room(room_id="b", name="B", x_m=5.0),
    ]
    layout["devices"] = [
        {
            "id": "orphan",
            "type": "equipment",
            "name": "Unassigned tool",
            "room_id": None,
            "x_m": 1.0,
            "y_m": 1.0,
            "z_m": 0.0,
            "width_m": 1.0,
            "height_m": 1.0,
            "orientation_deg": 0.0,
        }
    ]
    project = ProjectDocument(
        name="Spatial warnings",
        metadata={"spatial_layout": layout},
    )

    result = analyze_project_diagnostics(project)
    by_rule = {item["rule"]: item for item in result["issues"]}

    assert result["summary"]["status"] == "warning"
    assert by_rule["spatial.room_overlap"]["element"]["id"] == "a"
    assert by_rule["spatial.room_overlap"]["details"]["item_ids"] == ["a", "b"]
    assert by_rule["spatial.device_unassigned"]["element"]["id"] == "orphan"
    assert by_rule["spatial.device_unassigned"]["suggested_action"]


def test_project_diagnostics_report_invalid_analysis_without_aborting_other_rules():
    project = ProjectDocument(
        name="Invalid input",
        analyses=[
            AnalysisDocument(
                id="bad",
                name="Bad room",
                kind="room_verification",
                input={"name": "Incomplete"},
            )
        ],
        active_analysis_id="bad",
    )

    result = analyze_project_diagnostics(project)
    rules = [item["rule"] for item in result["issues"]]

    assert result["summary"]["status"] == "error"
    assert "analysis.input_invalid" in rules
    assert "run_history.analysis_not_run" in rules


def test_project_diagnostics_expose_geometry_newer_sync_state():
    payload = _room_payload()
    analysis = AnalysisDocument(
        id="room-1",
        name="Room verification",
        kind="room_verification",
        input=payload,
    )
    layout = empty_layout()
    layout["rooms"] = [
        _spatial_room(
            room_id="room",
            name=payload["name"],
            x_m=0.0,
            length_m=payload["length_m"] + 1.0,
        )
    ]
    layout["engineering_sync"] = {
        "analysis_id": "room-1",
        "rooms": [
            {
                "room_id": "room",
                "analysis_room_name": payload["name"],
                "length_m": payload["length_m"],
                "width_m": payload["width_m"],
                "height_m": payload["height_m"],
            }
        ],
    }
    project = ProjectDocument(
        name="Sync check",
        analyses=[analysis],
        active_analysis_id="room-1",
        metadata={"spatial_layout": layout},
    )

    result = analyze_project_diagnostics(project)
    issue = next(
        item
        for item in result["issues"]
        if item["rule"] == "engineering_sync.geometry_newer"
    )

    assert issue["severity"] == "warning"
    assert issue["element"]["id"] == "room"
    assert "push spatial dimensions" in issue["suggested_action"]


def test_project_diagnostics_distinguish_stale_current_input_from_never_run():
    payload = _room_payload()
    project = ProjectDocument(
        name="Stale result",
        analyses=[
            AnalysisDocument(
                id="room-1",
                name="Room verification",
                kind="room_verification",
                input=copy.deepcopy(payload),
            )
        ],
        active_analysis_id="room-1",
    )
    run = run_analysis("room_verification", payload)
    append_run_history_record(
        project.metadata,
        analysis_id="room-1",
        analysis_name="Room verification",
        analysis_kind="room_verification",
        input_payload=payload,
        run=run,
        completed_at_utc="2026-09-26T00:00:00Z",
    )
    project.analyses[0].input["supply_airflow_m3_h"] += 1.0

    result = analyze_project_diagnostics(project)
    rules = [item["rule"] for item in result["issues"]]

    assert "run_history.current_input_not_run" in rules
    assert "run_history.analysis_not_run" not in rules


def test_project_diagnostics_accept_fresh_retained_run_evidence():
    payload = _room_payload()
    project = ProjectDocument(
        name="Fresh result",
        analyses=[
            AnalysisDocument(
                id="room-1",
                name="Room verification",
                kind="room_verification",
                input=copy.deepcopy(payload),
            )
        ],
        active_analysis_id="room-1",
    )
    run = run_analysis("room_verification", payload)
    append_run_history_record(
        project.metadata,
        analysis_id="room-1",
        analysis_name="Room verification",
        analysis_kind="room_verification",
        input_payload=payload,
        run=run,
        completed_at_utc="2026-09-26T00:00:00Z",
    )

    result = analyze_project_diagnostics(project)

    assert result["summary"]["status"] == "pass"
    assert result["issues"] == []


def test_project_diagnostics_detect_changed_external_dependency(tmp_path):
    for name in ("facility_project.json", "consistency_hvac_demo.json"):
        (tmp_path / name).write_bytes((ROOT / "examples" / name).read_bytes())
    payload = {
        "verification_project": "facility_project.json",
        "hvac_project": "consistency_hvac_demo.json",
        "room_airflow_abs_tolerance_m3_h": 0.0,
        "require_same_room_set": True,
    }
    project = ProjectDocument(
        name="Dependency freshness",
        analyses=[
            AnalysisDocument(
                id="consistency",
                name="Consistency",
                kind="consistency",
                input=copy.deepcopy(payload),
            )
        ],
        active_analysis_id="consistency",
    )
    run = run_analysis("consistency", payload, base_dir=tmp_path)
    append_run_history_record(
        project.metadata,
        analysis_id="consistency",
        analysis_name="Consistency",
        analysis_kind="consistency",
        input_payload=payload,
        run=run,
        completed_at_utc="2026-09-26T00:00:00Z",
    )
    dependency = tmp_path / "consistency_hvac_demo.json"
    dependency.write_text(
        dependency.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    result = analyze_project_diagnostics(project, base_dir=tmp_path)
    issue = next(
        item
        for item in result["issues"]
        if item["rule"] == "run_history.external_dependency_stale"
    )

    assert issue["severity"] == "warning"
    assert issue["details"]["external_dependency_count"] == 2


def test_project_diagnostics_report_escapes_markdown():
    project = ProjectDocument(name="Plant | <A>")
    result = analyze_project_diagnostics(project)

    markdown = markdown_project_diagnostics_report(result)

    assert "Plant \\| &lt;A&gt;" in markdown


def test_project_diagnostics_cli_writes_revision_bound_strict_json(tmp_path):
    project_path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        ProjectDocument(name="CLI clean project"),
    )
    output_path = tmp_path / "diagnostics.json"

    exit_code = diagnostics_main(
        [str(project_path), "--format", "json", "--output", str(output_path)]
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["schema"] == PROJECT_DIAGNOSTICS_SCHEMA
    assert payload["summary"]["status"] == "pass"
    assert payload["source"]["stable_during_check"] is True
    assert len(payload["source"]["sha256"]) == 64
    json.dumps(payload, allow_nan=False)


def test_project_diagnostics_cli_discards_output_if_source_changes_during_check(
    tmp_path, monkeypatch
):
    project_path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        ProjectDocument(name="Revision guard"),
    )
    output_path = tmp_path / "diagnostics.json"
    output_path.write_text("previous-valid-report\n", encoding="utf-8")
    real_analyze = diagnostics_cli.analyze_project_diagnostics

    def mutate_source(project, *, base_dir=None):
        result = real_analyze(project, base_dir=base_dir)
        project_path.write_text(
            project_path.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
        return result

    monkeypatch.setattr(
        diagnostics_cli,
        "analyze_project_diagnostics",
        mutate_source,
    )

    exit_code = diagnostics_cli.main(
        [str(project_path), "--output", str(output_path)]
    )

    assert exit_code == 2
    assert output_path.read_text(encoding="utf-8") == "previous-valid-report\n"


def test_project_diagnostics_cli_refuses_to_overwrite_source_project(tmp_path):
    project_path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        ProjectDocument(name="Protect source project"),
    )
    original_bytes = project_path.read_bytes()

    exit_code = diagnostics_main(
        [str(project_path), "--output", str(project_path)]
    )

    assert exit_code == 2
    assert project_path.read_bytes() == original_bytes


def test_project_diagnostics_cli_refuses_to_overwrite_external_dependency(tmp_path):
    verification = tmp_path / "facility_project.json"
    dependency = tmp_path / "consistency_hvac_demo.json"
    verification.write_bytes((ROOT / "examples" / "facility_project.json").read_bytes())
    dependency.write_bytes(
        (ROOT / "examples" / "consistency_hvac_demo.json").read_bytes()
    )
    original_dependency = dependency.read_bytes()
    project_path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        ProjectDocument(
            name="Protect external dependency",
            analyses=[
                AnalysisDocument(
                    id="consistency",
                    name="Consistency",
                    kind="consistency",
                    input={
                        "verification_project": verification.name,
                        "hvac_project": dependency.name,
                        "room_airflow_abs_tolerance_m3_h": 0.0,
                        "require_same_room_set": True,
                    },
                )
            ],
            active_analysis_id="consistency",
        ),
    )

    exit_code = diagnostics_main(
        [str(project_path), "--output", str(dependency)]
    )

    assert exit_code == 2
    assert dependency.read_bytes() == original_dependency


def test_project_diagnostics_cli_returns_one_for_actionable_findings(tmp_path):
    project_path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        ProjectDocument(
            name="Invalid CLI project",
            analyses=[
                AnalysisDocument(
                    id="bad",
                    name="Bad",
                    kind="room_verification",
                    input={"name": "Incomplete"},
                )
            ],
            active_analysis_id="bad",
        ),
    )

    exit_code = diagnostics_main([str(project_path)])

    assert exit_code == 1
