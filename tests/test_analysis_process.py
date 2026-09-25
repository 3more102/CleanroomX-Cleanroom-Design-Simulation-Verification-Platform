from __future__ import annotations

import json
from pathlib import Path
import time

from cleanroomx.analysis_process import AnalysisProcess


ROOT = Path(__file__).resolve().parents[1]


def _wait_for_terminal(worker: AnalysisProcess, timeout_seconds: float = 10.0):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        message = worker.poll()
        if message is not None:
            return message
        time.sleep(0.01)
    raise AssertionError("analysis worker did not reach a terminal state")


def test_analysis_process_returns_real_application_result():
    payload = json.loads((ROOT / "examples" / "basic_room.json").read_text(encoding="utf-8"))
    worker = AnalysisProcess(cancel_kill_grace_seconds=0.1)
    try:
        worker.start("room_verification", payload, base_dir=ROOT / "examples")
        kind, result = _wait_for_terminal(worker)
    finally:
        worker.shutdown(wait=True)

    assert kind == "success"
    assert result.kind == "room_verification"
    assert result.result
    assert result.diagnostics["application_execution_provenance"]["analysis_kind"] == "room_verification"
    assert worker.active is False


def test_analysis_process_reports_application_error_without_crashing_parent():
    worker = AnalysisProcess(cancel_kill_grace_seconds=0.1)
    try:
        worker.start("not-a-real-analysis", {})
        kind, error = _wait_for_terminal(worker)
    finally:
        worker.shutdown(wait=True)

    assert kind == "error"
    assert "unknown analysis kind" in error
    assert worker.active is False


def test_analysis_process_cancel_discards_even_a_racing_completion():
    payload = json.loads((ROOT / "examples" / "basic_room.json").read_text(encoding="utf-8"))
    worker = AnalysisProcess(cancel_kill_grace_seconds=0.0)
    try:
        worker.start("room_verification", payload, base_dir=ROOT / "examples")
        assert worker.cancel() is True
        kind, payload = _wait_for_terminal(worker)
    finally:
        worker.shutdown(wait=True)

    assert kind == "cancelled"
    assert payload is None
    assert worker.active is False


def test_analysis_process_rejects_overlapping_runs():
    payload = json.loads((ROOT / "examples" / "basic_room.json").read_text(encoding="utf-8"))
    worker = AnalysisProcess(cancel_kill_grace_seconds=0.0)
    try:
        worker.start("room_verification", payload, base_dir=ROOT / "examples")
        try:
            worker.start("room_verification", payload, base_dir=ROOT / "examples")
        except RuntimeError as exc:
            assert "already active" in str(exc)
        else:
            raise AssertionError("overlapping worker start was accepted")
        worker.cancel()
        _wait_for_terminal(worker)
    finally:
        worker.shutdown(wait=True)
