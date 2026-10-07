from pathlib import Path


_WORKFLOW_PATH = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"


def _workflow_text() -> str:
    return _WORKFLOW_PATH.read_text(encoding="utf-8")


def test_complete_suites_report_skip_reasons() -> None:
    workflow = _workflow_text()

    assert "- name: Run complete test suite with skip reasons" in workflow
    assert "run: python -m pytest -q -ra" in workflow
    assert "- name: Run complete test suite with real Tk and skip reasons" in workflow
    assert "run: timeout --signal=TERM --kill-after=30s 20m xvfb-run -a python -m pytest -vv -ra --maxfail=1" in workflow


def test_ci_matrix_has_a_bounded_job_timeout() -> None:
    workflow = _workflow_text()
    assert "timeout-minutes: 30" in workflow


def test_python313_runs_entire_complete_suite_under_xvfb() -> None:
    workflow = _workflow_text()
    marker = "- name: Run complete test suite with real Tk and skip reasons"
    assert marker in workflow
    block = workflow.split(marker, 1)[1].split("\n      - name:", 1)[0]

    assert "if: matrix.python-version == '3.13'" in block
    assert "timeout --signal=TERM --kill-after=30s 20m xvfb-run -a python -m pytest -vv -ra --maxfail=1" in block
