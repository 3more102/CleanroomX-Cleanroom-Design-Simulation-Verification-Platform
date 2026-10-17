from copy import deepcopy

import pytest

from scripts.openfoam_v10_tutorial_smoke import (
    SCHEMA,
    UPSTREAM_CASE,
    UPSTREAM_COMMIT,
    UPSTREAM_REPOSITORY,
    validate_receipt,
)


def passing_receipt():
    return {
        "schema": SCHEMA,
        "status": "PASS",
        "case_type": "upstream_foundation_tutorial",
        "upstream_repository": UPSTREAM_REPOSITORY,
        "upstream_commit": UPSTREAM_COMMIT,
        "source_case_path": UPSTREAM_CASE,
        "stages": {
            "blockMesh": {"returncode": 0, "log_sha256": "a" * 64},
            "checkMesh": {"returncode": 0, "log_sha256": "b" * 64},
            "simpleFoam": {"returncode": 0, "log_sha256": "c" * 64},
        },
        "mesh_ok": True,
        "solver_log_completed": True,
        "result_sync": {
            "status": "results_synced",
            "record_count": 2,
            "times": ["0", "100"],
            "manifest_sha256": "d" * 64,
        },
        "solver_build": "10-test-build",
        "foamToVTK_build": "10-test-build",
        "environment": {
            "WM_PROJECT": "OpenFOAM",
            "WM_PROJECT_VERSION": "10",
            "openfoam_package_version": "10-test",
            "simpleFoam_executable": "/opt/openfoam10/bin/simpleFoam",
            "foamToVTK_executable": "/opt/openfoam10/bin/foamToVTK",
        },
        "scientific_validation": "BLOCKED",
    }


def test_pinned_upstream_tutorial_receipt_requires_complete_runtime_and_sync_evidence():
    validate_receipt(passing_receipt())


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("upstream_commit", "0" * 40, "source commit"),
        ("mesh_ok", False, "Mesh OK"),
        ("solver_log_completed", False, "did not end with End"),
        ("scientific_validation", "PASS", "cannot declare physical validation"),
    ],
)
def test_tutorial_receipt_rejects_missing_provenance_or_overstated_validation(
    field, value, message
):
    receipt = passing_receipt()
    receipt[field] = value
    with pytest.raises(ValueError, match=message):
        validate_receipt(receipt)


def test_tutorial_receipt_requires_a_nonzero_time_result():
    receipt = passing_receipt()
    receipt["result_sync"]["times"] = ["0"]
    with pytest.raises(ValueError, match="nonzero-time result"):
        validate_receipt(receipt)


def test_tutorial_receipt_rejects_a_failed_stage_even_when_other_evidence_is_present():
    receipt = deepcopy(passing_receipt())
    receipt["stages"]["simpleFoam"]["returncode"] = 1
    with pytest.raises(ValueError, match="simpleFoam did not complete"):
        validate_receipt(receipt)
