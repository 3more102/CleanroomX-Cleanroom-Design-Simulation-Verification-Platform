"""The CI runner must execute skipped cases without hiding failed assertions."""

import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest


RUNNER = Path(__file__).resolve().parents[1] / "scripts" / "run_desktop_gui_tests.py"


@pytest.mark.parametrize("outcome", ["recover", "skip_again", "unexpected_skip", "assertion"])
def test_desktop_runner_requires_a_real_pass_for_every_case(tmp_path, outcome):
    (tmp_path / "test_native.py").write_text(
        "import os, pytest\n"
        "def test_native():\n"
        + ("    assert False, 'application failure'\n" if outcome == "assertion" else
           "    pytest.skip('explicit unsupported feature')\n" if outcome == "unexpected_skip" else
           ("    if not os.environ.get('CLEANROOMX_GUI_STARTUP_RETRY'):\n"
            if outcome == "recover" else "    if True:\n")
           + "        pytest.skip('Tk display unavailable: invalid command name \"tcl_findLibrary\"')\n"),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--retry-tk-startup", "--junitxml=desktop.xml", "test_native.py"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    if outcome == "recover":
        assert result.returncode == 0, result.stdout + result.stderr
        receipt = json.loads((tmp_path / "desktop.coverage.json").read_text())
        assert (receipt["passed"], receipt["skipped"], receipt["initial_skipped"]) == (1, 0, 1)
        assert len(receipt["tcl_startup_retries"]) == 1
        assert next(ET.parse(tmp_path / "desktop.xml").getroot().iter("testcase")).find("skipped") is not None
        assert next(ET.parse(tmp_path / "desktop.retry-1.xml").getroot().iter("testcase")).find("skipped") is None
    else:
        assert result.returncode != 0
        assert not (tmp_path / "desktop.coverage.json").exists()
        if outcome in {"assertion", "unexpected_skip"}:
            assert not (tmp_path / "desktop.retry-1.xml").exists()
