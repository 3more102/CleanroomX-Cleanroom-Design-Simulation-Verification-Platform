from pathlib import Path


_WORKFLOW_PATH = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"

_DISPLAY_BOUND_GUI_SUITES = (
    "tests/test_gui_table.py",
    "tests/test_gui_start_center.py",
    "tests/test_gui_command_palette.py",
    "tests/test_gui_project_browser.py",
    "tests/test_spatial_editing_gui.py",
    "tests/test_gui_engineering_panels.py",
    "tests/test_gui_engineering_overlays.py",
    "tests/test_gui_proofgraph_integration.py",
    "tests/test_gui_recovery_revision_workstations.py",
    "tests/test_gui_workstation_dialogs.py",
)


def _workflow_text() -> str:
    return _WORKFLOW_PATH.read_text(encoding="utf-8")


def test_complete_suite_reports_skip_reasons() -> None:
    workflow = _workflow_text()
    assert "- name: Run complete test suite with skip reasons" in workflow
    assert "run: python -m pytest -q -ra" in workflow


def test_python313_replays_display_bound_gui_suites_under_xvfb() -> None:
    workflow = _workflow_text()
    marker = "- name: Run full real-Tk workstation regressions"
    assert marker in workflow
    block = workflow.split(marker, 1)[1].split("\n      - name:", 1)[0]

    assert "if: matrix.python-version == '3.13'" in block
    assert "xvfb-run -a python -m pytest -q" in block
    for suite in _DISPLAY_BOUND_GUI_SUITES:
        assert suite in block
