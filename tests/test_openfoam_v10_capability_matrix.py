import csv
import json
import subprocess
import sys
import pytest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs" / "openfoam_foundation_v10_capabilities.csv"
INVENTORY = ROOT / "docs" / "openfoam_foundation_v10_source_inventory.csv"
SCORER = ROOT / "scripts" / "openfoam_v10_parity_score.py"


def load(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def test_matrix_is_unique_traceable_and_covers_pinned_source_inventory():
    rows = load(MATRIX)
    inventory = load(INVENTORY)
    ids = [row["id"] for row in rows]

    assert len(ids) == len(set(ids))
    assert all(row["upstream_reference"].startswith("https://") for row in rows)
    assert all(row["remaining_gap"].strip() for row in rows)
    assert {row["inventory_type"] for row in inventory} == {
        "solver Make/files build units",
        "utility Make/files build units",
        "src Make/files library/API build units",
        "tutorial cases containing system/controlDict",
    }
    counts = {}
    for row in inventory:
        counts[row["inventory_type"]] = counts.get(row["inventory_type"], 0) + 1
    assert counts == {
        "solver Make/files build units": 72,
        "utility Make/files build units": 151,
        "src Make/files library/API build units": 94,
        "tutorial cases containing system/controlDict": 240,
    }
    assert len([row for row in rows if row["id"].startswith("OF10-SOLVER-")]) == 49
    assert len([row for row in rows if row["id"].startswith("OF10-UTILITY-")]) == 149
    assert len([row for row in rows if row["id"].startswith("OF10-API-")]) == 94
    assert len([row for row in rows if row["id"].startswith("OF10-TUTORIAL-CASE-")]) == 240
    assert len([row for row in rows if row["id"].startswith("OF10-TURB-")]) == 53
    assert len([row for row in rows if row["id"].startswith("OF10-BC-GEOM-")]) == 9
    assert len([row for row in rows if row["id"].startswith("OF10-BC-BASIC-")]) == 6
    assert len([row for row in rows if row["id"].startswith("OF10-BC-DERIVED-")]) == 6
    assert len([row for row in rows if row["id"].startswith("OF10-BC-WALL-")]) == 5
    assert len([row for row in rows if row["id"].startswith("OF10-FV-SCHEME-TERM-")]) == 7
    assert len([row for row in rows if row["id"].startswith("OF10-TIME-SCHEME-")]) == 6
    assert len([row for row in rows if row["id"].startswith("OF10-LINSOLVER-")]) == 6
    matrix_refs = {row["upstream_reference"] for row in rows}
    for inventory_type in (
        "src Make/files library/API build units",
        "tutorial cases containing system/controlDict",
    ):
        assert all(
            row["upstream_reference"] in matrix_refs
            for row in inventory
            if row["inventory_type"] == inventory_type
        )


def test_scoring_counts_only_complete_rows_and_reports_all_three_tracks():
    result = subprocess.run(
        [sys.executable, str(SCORER), "--format", "json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(result.stdout)
    assert report["rows"] == 723
    assert set(report["tracks"]) == {"native_status", "integration_status", "cleanroom_status"}
    assert report["tracks"]["native_status"]["complete"] == 0
    assert report["tracks"]["integration_status"]["complete"] == 0
    assert report["tracks"]["cleanroom_status"]["complete"] == 0
    assert report["tracks"]["native_status"]["denominator"] == 192
    assert report["tracks"]["integration_status"]["denominator"] == 717
    assert report["tracks"]["cleanroom_status"]["denominator"] == 21
    summary = (ROOT / "docs" / "OPENFOAM_FOUNDATION_V10_PARITY.md").read_text(encoding="utf-8")
    assert "| Native solver capability parity | 0 | 192 | 0.00% |" in summary
    assert "| End-to-end OpenFOAM integration coverage | 0 | 717 | 0.00% |" in summary
    assert "| Validated cleanroom engineering workflows | 0 | 21 | 0.00% |" in summary

@pytest.mark.parametrize(
    ("track", "evidence", "expected_error"),
    [
        ("native_status", "synthetic fixture passed", "PASS:"),
        ("integration_status", "PASS: OpenFOAM Foundation v10 synthetic fixture", "non-synthetic"),
        ("cleanroom_status", "PASS: measured values only", "uncertainty"),
    ],
)
def test_complete_status_requires_scope_appropriate_passing_evidence(track, evidence, expected_error):
    rows = load(MATRIX)
    row = rows[0]
    row[track] = "complete"
    row["implementation_path"] = "src/cleanroomx/example.py"
    row["test_evidence"] = evidence
    row["remaining_gap"] = "none"

    # The CLI reads the checked-in matrix, so exercise validator on a temporary copy.
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        matrix_path = Path(directory) / "matrix.csv"
        with matrix_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        checked = subprocess.run(
            [sys.executable, str(SCORER), "--matrix", str(matrix_path), "--inventory", str(INVENTORY)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    assert checked.returncode == 2
    assert expected_error in checked.stderr


def test_complete_native_row_can_score_with_pass_evidence_and_no_remaining_gap():
    rows = load(MATRIX)
    inventory = load(INVENTORY)
    row = rows[0]
    row.update(
        native_status="complete",
        implementation_path="src/cleanroomx/example.py",
        test_evidence="PASS: independently verified numerical comparison",
        remaining_gap="none",
    )
    from scripts.openfoam_v10_parity_score import validate

    validate(rows, inventory)


def test_run_54_evidence_is_partial_and_keeps_parity_scope():
    rows = {row["id"]: row for row in load(MATRIX)}
    simple_foam = rows["OF10-SOLVER-simpleFoam"]
    runner = rows["OF10-EXTERNAL-RUNNER"]
    report = "docs/OPENFOAM_V10_RUN_38675919475_TRIAGE.md"

    assert simple_foam["integration_status"] == "partial"
    assert "Run 54" in simple_foam["test_evidence"]
    assert "synthetic" in simple_foam["test_evidence"]
    assert "no project flux-balance criterion is set" in simple_foam["test_evidence"]
    assert report in simple_foam["test_evidence"]

    assert runner["integration_status"] == "partial"
    assert runner["cleanroom_status"] == "partial"
    assert "Run 54" in runner["test_evidence"]
    assert "synthetic" in runner["test_evidence"]
    assert report in runner["test_evidence"]

    result = subprocess.run(
        [sys.executable, str(SCORER), "--format", "json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    report_json = json.loads(result.stdout)
    assert report_json["tracks"]["native_status"]["complete"] == 0
    assert report_json["tracks"]["integration_status"]["complete"] == 0
    assert report_json["tracks"]["cleanroom_status"]["complete"] == 0


def test_run_61_vtk_field_parity_evidence_is_partial_and_keeps_parity_scope():
    rows = {row["id"]: row for row in load(MATRIX)}
    report = "docs/OPENFOAM_V10_RUN_38768856636_NATIVE_U_P_VTK_PARITY.md"
    for capability_id in ("OF10-UTILITY-foamToVTK", "OF10-VTK-IMPORT"):
        row = rows[capability_id]
        assert row["integration_status"] == "partial"
        assert "run 61" in row["test_evidence"].lower()
        assert "synthetic" in row["test_evidence"].lower()
        assert report in row["test_evidence"]
        assert "11989364311" in row["test_evidence"]
        assert "fd348a923c6f46b8d656700c029bfdce13187a8eeb7d2f5a6926581a02bd05ba" in row["test_evidence"]
        assert "47,304" in row["test_evidence"]
        assert row["remaining_gap"] != "none"

    result = subprocess.run(
        [sys.executable, str(SCORER), "--format", "json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(result.stdout)
    assert report["tracks"]["integration_status"]["complete"] == 0
    assert report["tracks"]["native_status"]["complete"] == 0
    assert report["tracks"]["cleanroom_status"]["complete"] == 0


def test_run_63_vtk_patch_parity_evidence_is_partial_and_keeps_counts_zero():
    rows = {row["id"]: row for row in load(MATRIX)}
    report = "docs/OPENFOAM_V10_RUN_38772855917_NATIVE_VTK_PATCH_PARITY.md"
    for capability_id in ("OF10-UTILITY-foamToVTK", "OF10-VTK-IMPORT"):
        row = rows[capability_id]
        assert row["integration_status"] == "partial"
        assert "run 63" in row["test_evidence"].lower()
        assert "synthetic" in row["test_evidence"].lower()
        assert report in row["test_evidence"]
        assert "11992892011" in row["test_evidence"]
        assert "d40b603f871758be1dc4b05f6c78eeb4302e96f4ec6fd0af841b618c688e54c9" in row["test_evidence"]
        assert "13,608" in row["test_evidence"]
        assert row["remaining_gap"] != "none"

    result = subprocess.run(
        [sys.executable, str(SCORER), "--format", "json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    report_json = json.loads(result.stdout)
    assert report_json["tracks"]["integration_status"]["complete"] == 0
    assert report_json["tracks"]["native_status"]["complete"] == 0
    assert report_json["tracks"]["cleanroom_status"]["complete"] == 0
