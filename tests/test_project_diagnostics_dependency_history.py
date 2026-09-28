from __future__ import annotations

import copy
from pathlib import Path

from cleanroomx.application import run_analysis
from cleanroomx.project import AnalysisDocument, ProjectDocument
from cleanroomx.project_diagnostics import analyze_project_diagnostics
from cleanroomx.run_history import append_run_history_record


ROOT = Path(__file__).resolve().parents[1]


def test_project_diagnostics_accepts_restored_older_dependency_revision(tmp_path):
    for name in ("facility_project.json", "consistency_hvac_demo.json"):
        (tmp_path / name).write_bytes((ROOT / "examples" / name).read_bytes())

    payload = {
        "verification_project": "facility_project.json",
        "hvac_project": "consistency_hvac_demo.json",
        "room_airflow_abs_tolerance_m3_h": 0.0,
        "require_same_room_set": True,
    }
    project = ProjectDocument(
        name="Restored dependency freshness",
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
    dependency = tmp_path / "consistency_hvac_demo.json"
    original_bytes = dependency.read_bytes()

    original_run = run_analysis("consistency", payload, base_dir=tmp_path)
    append_run_history_record(
        project.metadata,
        analysis_id="consistency",
        analysis_name="Consistency",
        analysis_kind="consistency",
        input_payload=payload,
        run=original_run,
        completed_at_utc="2026-09-26T00:00:00Z",
    )

    dependency.write_bytes(original_bytes + b"\n")
    modified_run = run_analysis("consistency", payload, base_dir=tmp_path)
    append_run_history_record(
        project.metadata,
        analysis_id="consistency",
        analysis_name="Consistency",
        analysis_kind="consistency",
        input_payload=payload,
        run=modified_run,
        completed_at_utc="2026-09-26T00:01:00Z",
    )

    dependency.write_bytes(original_bytes)
    result = analyze_project_diagnostics(project, base_dir=tmp_path)

    assert result["summary"]["status"] == "pass"
    assert result["issues"] == []
