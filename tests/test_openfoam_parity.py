"""The checked-in v14 matrix is broad, pinned and scored fail-closed."""
from pathlib import Path

import pytest

from cleanroomx.openfoam_parity import FIELDS, read_matrix, score_rows, validate_rows


MATRIX = Path(__file__).resolve().parents[1] / "docs" / "OPENFOAM_V14_CAPABILITY_MATRIX.csv"


def test_pinned_release_inventory_counts_and_current_scores():
    rows = read_matrix(MATRIX)
    assert len(rows) == 2147
    assert sum(r["inventory_source"].startswith("solver_binary ") for r in rows) == 5
    assert sum(r["inventory_source"].startswith("utility_binary ") for r in rows) == 134
    assert sum(r["inventory_source"] == "applications/modules package" for r in rows) == 24
    assert sum(r["inventory_source"] == "top-level src library package" for r in rows) == 43
    assert sum(r["inventory_source"] == "executable tutorial Allrun script" for r in rows) == 208
    assert sum(r["inventory_source"] == "OpenFOAM v14 User Guide table of contents" for r in rows) == 288
    assert sum(r["inventory_source"].startswith("literal add") for r in rows) == 1338
    assert sum(r["inventory_source"].startswith("executable script ") for r in rows) == 91
    scores = score_rows(rows)
    assert (scores["native"]["complete"], scores["native"]["denominator"]) == (0, 1595)
    assert (scores["integration"]["complete"], scores["integration"]["denominator"]) == (0, 2130)
    assert (scores["workflow"]["complete"], scores["workflow"]["denominator"]) == (0, 16)
    assert any(row["integration_status"] == "partial" for row in rows if row["integration_scope"] == "true")


def test_only_complete_rows_with_path_and_test_evidence_score():
    base = {field: "not applicable" for field in FIELDS}
    base.update({
        "capability_id": "test/a", "category": "test", "capability": "a capability",
        "inventory_source": "test", "upstream_reference": "https://example.invalid/reference",
        "native_scope": "false", "native_status": "not_applicable",
        "integration_scope": "true", "integration_status": "partial",
        "integration_path": "implementation.py", "integration_test_evidence": "synthetic test",
        "integration_gap": "release-level run still missing",
        "workflow_scope": "false", "workflow_status": "not_applicable",
    })
    second = dict(base, capability_id="test/b", integration_status="unsupported")
    scores = score_rows([base, second])
    assert (scores["integration"]["complete"], scores["integration"]["denominator"]) == (0, 2)
    invalid_complete = dict(base, integration_status="complete", integration_test_evidence="none")
    with pytest.raises(ValueError, match="needs an implementation path and passing evidence"):
        validate_rows([invalid_complete])


def test_integration_and_workflow_scores_reject_synthetic_evidence():
    base = {
        "capability_id": "test/real-integration", "category": "test",
        "capability": "real release integration", "inventory_source": "test",
        "upstream_reference": "https://example.invalid/reference",
        "native_scope": "false", "native_status": "not_applicable",
        "native_implementation": "not in this score", "native_test_evidence": "not in this score",
        "native_gap": "not in this score", "integration_scope": "true",
        "integration_status": "complete", "integration_path": "solver.py",
        "integration_test_evidence": "PASS: mocked OpenFOAM Foundation v14 run",
        "integration_gap": "none", "workflow_scope": "false",
        "workflow_status": "not_applicable", "workflow_path": "not in this score",
        "workflow_test_evidence": "not in this score", "workflow_gap": "not in this score",
    }
    with pytest.raises(ValueError, match="synthetic or mocked evidence"):
        score_rows([base])
    real = dict(base, integration_test_evidence="PASS: OpenFOAM Foundation v14 foamRun output and archived log")
    score = score_rows([real])
    assert (score["integration"]["complete"], score["integration"]["denominator"]) == (1, 1)

    workflow = dict(real, capability_id="test/real-workflow", integration_scope="false",
                    integration_status="not_applicable", integration_path="not in this score",
                    integration_test_evidence="not in this score", integration_gap="not in this score",
                    workflow_scope="true", workflow_status="complete", workflow_path="validation.py",
                    workflow_test_evidence="PASS: simulated measurement correlation", workflow_gap="none")
    with pytest.raises(ValueError, match="synthetic or mocked evidence"):
        score_rows([workflow])
