from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from scripts import security_static_gate as gate


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
GATE_SCRIPT = REPOSITORY_ROOT / "scripts" / "security_static_gate.py"


def _scan_source(tmp_path: Path, source: str, monkeypatch):
    monkeypatch.setattr(gate, "REPOSITORY_ROOT", tmp_path)
    candidate = tmp_path / "src" / "candidate.py"
    candidate.parent.mkdir(parents=True)
    candidate.write_text(source, encoding="utf-8")
    return gate._scan_file(candidate)


def test_security_static_gate_passes_current_production_tree() -> None:
    result = subprocess.run(
        [sys.executable, str(GATE_SCRIPT)],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "CleanroomX security static gate: PASS" in result.stdout


def test_security_static_gate_rejects_shell_and_dynamic_execution(
    tmp_path: Path, monkeypatch
) -> None:
    violations = _scan_source(
        tmp_path,
        """
import os as operating
from subprocess import run as launch

operating.system("echo unsafe")
launch("echo unsafe", shell=True)
eval("1 + 1")
""",
        monkeypatch,
    )
    messages = [item.message for item in violations]
    assert any("os.system" in message for message in messages)
    assert any("shell=True" in message for message in messages)
    assert any("eval()" in message for message in messages)


def test_security_static_gate_rejects_unsafe_deserialization_and_archive_helpers(
    tmp_path: Path, monkeypatch
) -> None:
    violations = _scan_source(
        tmp_path,
        """
import pickle as serializer
import tempfile

serializer.loads(b"payload")
tempfile.mktemp()
archive.extractall("output")
""",
        monkeypatch,
    )
    messages = [item.message for item in violations]
    assert any("pickle.loads" in message for message in messages)
    assert any("tempfile.mktemp" in message for message in messages)
    assert any(".extractall()" in message for message in messages)


def test_security_static_gate_allows_safe_subprocess_usage(
    tmp_path: Path, monkeypatch
) -> None:
    violations = _scan_source(
        tmp_path,
        """
import subprocess

subprocess.run(["python", "--version"], check=True, shell=False)
""",
        monkeypatch,
    )
    assert violations == []
