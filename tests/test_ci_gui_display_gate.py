from pathlib import Path


_WORKFLOW_PATH = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"


def _workflow_text() -> str:
    return _WORKFLOW_PATH.read_text(encoding="utf-8")


def test_complete_suites_report_skip_reasons() -> None:
    workflow = _workflow_text()

    assert "- name: Run complete test suite with skip reasons" in workflow
    assert "run: python -m pytest -q -ra" in workflow
    assert "- name: Run complete test suite with real Tk and skip reasons" in workflow
    assert "run: xvfb-run -a python -m pytest -q -ra" in workflow


def test_python313_runs_entire_complete_suite_under_xvfb() -> None:
    workflow = _workflow_text()
    marker = "- name: Run complete test suite with real Tk and skip reasons"
    assert marker in workflow
    block = workflow.split(marker, 1)[1].split("\n      - name:", 1)[0]

    assert "if: matrix.python-version == '3.13'" in block
    assert "xvfb-run -a python -m pytest -q -ra" in block


def test_virtual_display_is_provisioned_before_full_python313_suite() -> None:
    workflow = _workflow_text()

    provision = workflow.index("- name: Install virtual display for GUI release gates")
    full_suite = workflow.index("- name: Run complete test suite with real Tk and skip reasons")
    gui_smoke = workflow.index("- name: Run v0.100 desktop GUI smoke from installed wheel")

    assert provision < full_suite < gui_smoke
