from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import sys

from cleanroomx import __version__
from cleanroomx.diagnostics import (
    DIAGNOSTIC_BUNDLE_SCHEMA,
    LOG_SCHEMA,
    build_diagnostic_bundle,
    configure_local_diagnostics,
    default_diagnostics_dir,
    log_event,
    log_exception,
    read_log_tail,
)


def _flush() -> None:
    for handler in logging.getLogger("cleanroomx").handlers:
        handler.flush()


def test_configure_diagnostics_writes_strict_structured_json(tmp_path):
    session = configure_local_diagnostics(tmp_path)
    log_event(
        "project.opened",
        project_path=tmp_path / "demo.cleanroomx.json",
        non_finite=float("nan"),
    )
    _flush()

    record = json.loads(session.log_path.read_text(encoding="utf-8").splitlines()[-1])
    assert record["schema"] == LOG_SCHEMA
    assert record["application_version"] == __version__
    assert record["event"] == "project.opened"
    assert record["fields"]["project_path"].endswith("demo.cleanroomx.json")
    assert record["fields"]["non_finite"] == "nan"
    json.dumps(record, allow_nan=False)


def test_configure_diagnostics_is_idempotent_for_same_path(tmp_path):
    first = configure_local_diagnostics(tmp_path)
    second = configure_local_diagnostics(tmp_path)
    assert first.log_path == second.log_path

    log_event("one.event")
    _flush()

    records = [
        json.loads(line)
        for line in first.log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [record["event"] for record in records] == ["one.event"]


def test_log_exception_records_traceback(tmp_path):
    session = configure_local_diagnostics(tmp_path)
    try:
        raise ValueError("broken callback")
    except ValueError:
        log_exception("gui.callback_exception", *sys.exc_info())
    _flush()

    record = json.loads(session.log_path.read_text(encoding="utf-8").splitlines()[-1])
    assert record["event"] == "gui.callback_exception"
    assert record["exception"]["type"] == "ValueError"
    assert record["exception"]["message"] == "broken callback"
    assert "ValueError: broken callback" in record["exception"]["traceback"]


def test_read_log_tail_is_bounded_to_latest_records(tmp_path):
    session = configure_local_diagnostics(tmp_path)
    for marker in range(10):
        log_event("marker", marker=marker)
    _flush()

    records = read_log_tail(session.log_path, max_bytes=64 * 1024, max_records=3)

    assert [item["fields"]["marker"] for item in records] == [7, 8, 9]


def test_diagnostic_bundle_is_strict_json_and_contains_bounded_context(tmp_path):
    session = configure_local_diagnostics(tmp_path)
    log_event("startup", mode="test")
    bundle = build_diagnostic_bundle(
        session.log_path,
        context={
            "project_path": Path("/tmp/example.cleanroomx.json"),
            "running": False,
            "non_finite": float("inf"),
        },
        max_log_records=20,
    )

    assert bundle["schema"] == DIAGNOSTIC_BUNDLE_SCHEMA
    assert bundle["application_version"] == __version__
    assert bundle["privacy"]["network_transmission"] is False
    assert bundle["context"]["non_finite"] == "inf"
    assert bundle["log"]["records"][-1]["event"] == "startup"
    json.dumps(bundle, allow_nan=False)


def test_default_diagnostics_dir_honors_environment_override(tmp_path, monkeypatch):
    override = tmp_path / "private-diagnostics"
    monkeypatch.setenv("CLEANROOMX_DIAGNOSTICS_DIR", str(override))

    assert default_diagnostics_dir() == override


def test_rotated_active_log_keeps_owner_only_permissions_on_posix(tmp_path):
    if os.name == "nt":
        return
    session = configure_local_diagnostics(tmp_path, max_bytes=1024, backup_count=2)
    for marker in range(80):
        log_event("rotation.marker", marker=marker, payload="x" * 80)
    _flush()

    assert session.log_path.exists()
    assert session.log_path.stat().st_mode & 0o777 == 0o600
    rotated = session.log_path.with_name(session.log_path.name + ".1")
    assert rotated.exists()
    assert rotated.stat().st_mode & 0o777 == 0o600
