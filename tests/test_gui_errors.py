from __future__ import annotations

from pathlib import Path

from cleanroomx.gui_errors import (
    default_gui_log_path,
    make_gui_callback_exception_handler,
    record_gui_exception,
)


def test_default_gui_log_path_is_outside_project_data(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    path = default_gui_log_path()

    assert path == tmp_path / ".cleanroomx" / "logs" / "gui.log"


def test_record_gui_exception_writes_reference_and_traceback(tmp_path) -> None:
    log_path = tmp_path / "logs" / "gui.log"
    try:
        raise RuntimeError("synthetic GUI failure")
    except RuntimeError as exc:
        report = record_gui_exception("Open project", exc, log_path=log_path)

    assert report.reference.startswith("CX-")
    assert report.operation == "Open project"
    assert report.exception_type == "RuntimeError"
    assert report.summary == "synthetic GUI failure"
    assert report.log_path == log_path.resolve()

    text = log_path.read_text(encoding="utf-8")
    assert report.reference in text
    assert "operation='Open project'" in text
    assert "RuntimeError" in text
    assert "synthetic GUI failure" in text
    assert "Traceback (most recent call last)" in text


def test_record_gui_exception_is_fail_safe_when_log_path_cannot_be_created(
    tmp_path,
) -> None:
    blocked_parent = tmp_path / "not-a-directory"
    blocked_parent.write_text("file", encoding="utf-8")
    log_path = blocked_parent / "gui.log"

    report = record_gui_exception(
        "Save project",
        ValueError("invalid"),
        log_path=log_path,
    )

    assert report.log_path is None
    message = report.user_message()
    assert report.reference in message
    assert "Technical logging was unavailable" in message


def test_gui_callback_exception_handler_preserves_traceback_and_notifies(tmp_path) -> None:
    log_path = tmp_path / "logs" / "gui.log"
    statuses = []
    reports = []
    handler = make_gui_callback_exception_handler(
        operation="Unhandled GUI callback",
        status_setter=statuses.append,
        notifier=reports.append,
        log_path=log_path,
    )

    try:
        raise RuntimeError("callback exploded")
    except RuntimeError as exc:
        handler(RuntimeError, exc, exc.__traceback__)

    assert len(reports) == 1
    report = reports[0]
    assert report.reference.startswith("CX-")
    assert report.operation == "Unhandled GUI callback"
    assert report.summary == "callback exploded"
    assert statuses == [f"Unhandled GUI callback failed · {report.reference}"]

    text = log_path.read_text(encoding="utf-8")
    assert report.reference in text
    assert "callback exploded" in text
    assert "Traceback (most recent call last)" in text


def test_gui_callback_exception_handler_contains_presentation_failures(tmp_path) -> None:
    log_path = tmp_path / "logs" / "gui.log"

    def broken_status(_message: str) -> None:
        raise RuntimeError("status unavailable")

    def broken_notifier(_report) -> None:
        raise RuntimeError("dialog unavailable")

    handler = make_gui_callback_exception_handler(
        status_setter=broken_status,
        notifier=broken_notifier,
        log_path=log_path,
    )

    handler(ValueError, ValueError("original callback failure"), None)

    text = log_path.read_text(encoding="utf-8")
    assert "original callback failure" in text
    assert "status unavailable" not in text
    assert "dialog unavailable" not in text
