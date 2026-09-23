import json

import pytest

from cleanroomx.dossier import build_dossier, summarize_dossier_components
from cleanroomx.dossier_report import markdown_dossier_report


def test_repository_nonlinear_uncertainty_dossier_builds_end_to_end() -> None:
    result = build_dossier(
        "examples/dossier_variable_friction_uncertainty_demo.json"
    )

    analyses = result["fan_variable_friction_uncertainty_analyses"]
    assert len(analyses) == 1
    analysis = analyses[0]
    assert analysis["status"] == "complete"
    assert analysis["nominal_status"] == "solved"
    assert analysis["corner_count"] == 8
    assert analysis["solved_corner_count"] == 8
    assert analysis["traceability"]["complete"] is True

    component = result["executive_summary"]["components"][
        "fan_variable_friction_uncertainty"
    ]
    assert component["status"] == "screening_complete"
    assert component["analysis_count"] == 1
    assert component["corner_count"] == 8
    assert result["executive_summary"]["state"] == "no_adverse_findings"

    source = next(
        item
        for item in result["source_files"]
        if item["kind"] == "fan_variable_friction_uncertainty_analysis"
    )
    assert source["path"] == "fan_variable_friction_uncertainty_demo.json"
    assert len(source["sha256"]) == 64

    report = markdown_dossier_report(result)
    assert "Fan / variable-friction loop uncertainty analyses" in report
    assert "Variable-friction fan-loop bounded uncertainty" in report
    assert "8" in report


def test_nonlinear_uncertainty_indeterminate_propagates_attention() -> None:
    summary = summarize_dossier_components(
        fan_variable_friction_uncertainty=[
            {
                "status": "indeterminate",
                "corner_count": 4,
                "traceability": {
                    "complete": True,
                    "missing_provenance": [],
                },
            }
        ]
    )

    component = summary["components"]["fan_variable_friction_uncertainty"]
    assert component["status"] == "attention_required"
    assert component["counts"] == {"indeterminate": 1}
    assert summary["adverse_items"][
        "fan_variable_friction_uncertainty_indeterminate"
    ] == 1
    assert summary["state"] == "attention_required"


def test_nonlinear_uncertainty_missing_provenance_is_unresolved() -> None:
    summary = summarize_dossier_components(
        fan_variable_friction_uncertainty=[
            {
                "status": "complete",
                "corner_count": 2,
                "traceability": {
                    "complete": False,
                    "missing_provenance": ["fan_curve"],
                },
            }
        ]
    )

    component = summary["components"]["fan_variable_friction_uncertainty"]
    assert component["status"] == "complete_with_missing_provenance"
    assert component["missing_provenance_analyses"] == 1
    assert summary["unresolved_items"][
        "fan_variable_friction_uncertainty_missing_provenance"
    ] == 1
    assert summary["state"] == "complete_with_unchecked"


def test_missing_nonlinear_uncertainty_source_is_rejected(tmp_path) -> None:
    manifest = tmp_path / "dossier.json"
    manifest.write_text(
        json.dumps(
            {
                "name": "Missing nonlinear uncertainty source",
                "fan_variable_friction_uncertainty_analyses": [
                    "missing.json"
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="source file does not exist"):
        build_dossier(manifest)


def test_nonlinear_uncertainty_dossier_is_deterministic() -> None:
    path = "examples/dossier_variable_friction_uncertainty_demo.json"
    first = build_dossier(path)
    second = build_dossier(path)

    assert first["source_files"] == second["source_files"]
    assert json.dumps(first, sort_keys=True) == json.dumps(
        second,
        sort_keys=True,
    )
