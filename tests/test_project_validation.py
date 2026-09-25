from __future__ import annotations

import copy
import json

from cleanroomx.project import AnalysisDocument, ProjectDocument, save_project_document
from cleanroomx.project_validation import (
    markdown_project_validation_report,
    validate_project,
)
from cleanroomx.project_validation_cli import main as validation_cli_main


def _valid_room(name: str = "Process") -> dict:
    return {
        "name": name,
        "length_m": 5.0,
        "width_m": 4.0,
        "height_m": 3.0,
        "supply_airflow_m3_h": 1200.0,
    }


def _analysis(analysis_id: str, payload: dict) -> AnalysisDocument:
    return AnalysisDocument(
        id=analysis_id,
        name=f"Analysis {analysis_id}",
        kind="room_verification",
        input=payload,
    )


def test_project_validation_passes_all_valid_analyses_and_is_deterministic():
    first = ProjectDocument(
        name="Validated",
        analyses=[
            _analysis("room-a", _valid_room("A")),
            _analysis("room-b", _valid_room("B")),
        ],
        active_analysis_id="room-a",
        metadata={"b": 2, "a": 1},
    )
    second = ProjectDocument(
        name="Validated",
        analyses=[
            _analysis("room-a", _valid_room("A")),
            _analysis("room-b", _valid_room("B")),
        ],
        active_analysis_id="room-a",
        metadata={"a": 1, "b": 2},
    )

    report = validate_project(first)
    repeated = validate_project(second)

    assert report.status == "pass"
    assert report.passed is True
    assert report.analyses_checked == 2
    assert report.valid_analyses == 2
    assert report.invalid_analyses == 0
    assert report.findings == ()
    assert report.project_sha256 == repeated.project_sha256
    assert report.to_dict() == repeated.to_dict()


def test_project_validation_aggregates_invalid_analyses_without_stopping():
    project = ProjectDocument(
        name="Invalid inputs",
        analyses=[
            _analysis("missing-dimensions", {"name": "Broken A"}),
            _analysis("missing-airflow", {
                "name": "Broken B",
                "length_m": 5.0,
                "width_m": 4.0,
                "height_m": 3.0,
            }),
        ],
        active_analysis_id="missing-dimensions",
    )

    report = validate_project(project)

    assert report.status == "fail"
    assert report.error_count == 2
    assert report.analyses_checked == 2
    assert report.valid_analyses == 0
    assert report.invalid_analyses == 2
    assert [item.analysis_id for item in report.findings] == [
        "missing-dimensions",
        "missing-airflow",
    ]
    assert all(item.code == "analysis_input_invalid" for item in report.findings)


def test_project_validation_reports_empty_project_as_warning():
    report = validate_project(ProjectDocument(name="Draft"))

    assert report.status == "warning"
    assert report.passed is True
    assert report.error_count == 0
    assert report.warning_count == 1
    assert report.findings[0].code == "project_has_no_analyses"


def test_project_validation_reports_spatial_integrity_before_advisory_geometry():
    project = ProjectDocument(
        name="Spatial integrity",
        analyses=[_analysis("room-a", _valid_room())],
        active_analysis_id="room-a",
        metadata={
            "spatial_layout": {
                "version": 1,
                "grid_m": 0.5,
                "rooms": [
                    {
                        "id": "room-1",
                        "name": "A",
                        "x_m": 0.0,
                        "y_m": 0.0,
                        "length_m": 4.0,
                        "width_m": 4.0,
                        "height_m": 3.0,
                    },
                    {
                        "id": "room-1",
                        "name": "B",
                        "x_m": 1.0,
                        "y_m": 1.0,
                        "length_m": 4.0,
                        "width_m": 4.0,
                        "height_m": 3.0,
                    },
                ],
                "devices": [],
            }
        },
    )

    report = validate_project(project)

    assert report.status == "fail"
    assert report.spatial_checked is True
    assert [item.code for item in report.findings] == ["spatial_duplicate_room_id"]
    assert report.findings[0].item_ids == ("room-1",)


def test_project_validation_surfaces_advisory_spatial_overlap_as_warning():
    project = ProjectDocument(
        name="Spatial advisory",
        analyses=[_analysis("room-a", _valid_room())],
        active_analysis_id="room-a",
        metadata={
            "spatial_layout": {
                "version": 1,
                "grid_m": 0.5,
                "rooms": [
                    {
                        "id": "room-a",
                        "name": "A",
                        "x_m": 0.0,
                        "y_m": 0.0,
                        "length_m": 4.0,
                        "width_m": 4.0,
                        "height_m": 3.0,
                    },
                    {
                        "id": "room-b",
                        "name": "B",
                        "x_m": 3.0,
                        "y_m": 2.0,
                        "length_m": 4.0,
                        "width_m": 3.0,
                        "height_m": 3.0,
                    },
                ],
                "devices": [],
            }
        },
    )

    report = validate_project(project)

    assert report.status == "warning"
    assert report.error_count == 0
    assert [item.code for item in report.findings] == ["spatial_room_overlap"]


def test_project_validation_checks_relative_external_references(tmp_path):
    project = ProjectDocument(
        name="References",
        analyses=[
            AnalysisDocument(
                id="consistency-a",
                name="Consistency",
                kind="consistency",
                input={
                    "verification_project": "missing-verification.json",
                    "hvac_project": "missing-hvac.json",
                },
            )
        ],
        active_analysis_id="consistency-a",
    )

    report = validate_project(project, base_dir=tmp_path)

    assert report.status == "fail"
    assert report.invalid_analyses == 1
    assert "does not exist" in report.findings[0].message


def test_markdown_project_validation_report_contains_traceability_and_findings():
    project = ProjectDocument(
        name="Markdown",
        analyses=[_analysis("bad", {"name": "Broken"})],
        active_analysis_id="bad",
    )
    report = validate_project(project)

    text = markdown_project_validation_report(report)

    assert "# CleanroomX project validation" in text
    assert "Status: FAIL" in text
    assert report.project_sha256 in text
    assert "analysis_input_invalid" in text
    assert "Analysis bad" in text


def test_project_validation_cli_returns_nonzero_and_strict_json_for_invalid_project(
    tmp_path, capsys
):
    project = ProjectDocument(
        name="CLI invalid",
        analyses=[_analysis("bad", {"name": "Broken"})],
        active_analysis_id="bad",
    )
    path = save_project_document(tmp_path / "invalid.cleanroomx.json", project)

    exit_code = validation_cli_main([str(path), "--format", "json"])

    assert exit_code == 2
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["status"] == "fail"
    assert payload["summary"]["invalid_analyses"] == 1
    json.dumps(payload, sort_keys=True, allow_nan=False)


def test_project_validation_cli_writes_atomic_markdown_report(tmp_path):
    project = ProjectDocument(
        name="CLI valid",
        analyses=[_analysis("room-a", _valid_room())],
        active_analysis_id="room-a",
    )
    path = save_project_document(tmp_path / "valid.cleanroomx.json", project)
    output = tmp_path / "validation.md"

    exit_code = validation_cli_main(
        [str(path), "--format", "markdown", "--output", str(output)]
    )

    assert exit_code == 0
    assert "Status: PASS" in output.read_text(encoding="utf-8")
    assert list(tmp_path.glob(f".{output.name}.*.tmp")) == []


def test_project_validation_does_not_mutate_invalid_spatial_state():
    project = ProjectDocument(
        name="No mutation",
        analyses=[_analysis("room-a", _valid_room())],
        active_analysis_id="room-a",
        metadata={
            "spatial_layout": {
                "version": 1,
                "grid_m": 0.5,
                "rooms": [
                    {
                        "id": "",
                        "name": "Room",
                        "x_m": "not-a-number",
                        "y_m": 0.0,
                        "length_m": 4.0,
                        "width_m": 4.0,
                        "height_m": 3.0,
                    }
                ],
                "devices": [],
            }
        },
    )
    before = copy.deepcopy(project.to_dict())

    report = validate_project(project)

    assert report.status == "fail"
    assert project.to_dict() == before
    assert {item.code for item in report.findings} >= {
        "spatial_room_id_invalid",
        "spatial_room_coordinate_invalid",
    }


def test_project_validation_handles_large_analysis_collection_deterministically():
    project = ProjectDocument(
        name="Large validation",
        analyses=[
            _analysis(f"room-{index:03d}", _valid_room(f"Room {index:03d}"))
            for index in range(250)
        ],
        active_analysis_id="room-000",
    )

    first = validate_project(project)
    second = validate_project(project)

    assert first.status == "pass"
    assert first.analyses_checked == 250
    assert first.valid_analyses == 250
    assert first.invalid_analyses == 0
    assert first.to_dict() == second.to_dict()
