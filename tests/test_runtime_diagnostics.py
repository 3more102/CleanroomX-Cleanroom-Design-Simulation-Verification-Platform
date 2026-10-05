from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

from cleanroomx.runtime_diagnostics import (
    GUI_LOG_FILENAME,
    close_gui_runtime_logging,
    configure_gui_runtime_logging,
    default_gui_log_dir,
    install_tk_exception_handler,
)


def test_default_gui_log_dir_uses_platform_specific_user_state_locations(tmp_path: Path):
    home = tmp_path / "home"

    assert default_gui_log_dir(
        env={"LOCALAPPDATA": str(tmp_path / "local")},
        platform="win32",
        home=home,
    ) == tmp_path / "local" / "CleanroomX" / "Logs"

    assert default_gui_log_dir(
        env={},
        platform="win32",
        home=home,
    ) == home / "AppData" / "Local" / "CleanroomX" / "Logs"

    assert default_gui_log_dir(
        env={},
        platform="darwin",
        home=home,
    ) == home / "Library" / "Logs" / "CleanroomX"

    assert default_gui_log_dir(
        env={"XDG_STATE_HOME": str(tmp_path / "state")},
        platform="linux",
        home=home,
    ) == tmp_path / "state" / "cleanroomx" / "logs"


def test_default_gui_log_dir_honors_explicit_environment_override(tmp_path: Path):
    target = tmp_path / "operator-logs"

    assert default_gui_log_dir(
        env={"CLEANROOMX_LOG_DIR": str(target)},
        platform="win32",
        home=tmp_path / "home",
    ) == target


def test_configure_gui_runtime_logging_writes_bounded_runtime_log(tmp_path: Path):
    logger_name = "cleanroomx.tests.runtime-log"
    logger, log_path = configure_gui_runtime_logging(
        tmp_path,
        logger_name=logger_name,
    )
    try:
        logger.error("diagnostic sentinel")
        for handler in logger.handlers:
            handler.flush()

        assert log_path == (tmp_path / GUI_LOG_FILENAME).resolve(strict=False)
        content = log_path.read_text(encoding="utf-8")
        assert "CleanroomX GUI runtime diagnostics initialized" in content
        assert "diagnostic sentinel" in content
    finally:
        close_gui_runtime_logging(logger)
        logging.Logger.manager.loggerDict.pop(logger_name, None)


def test_tk_exception_handler_logs_traceback_and_suppresses_duplicate_dialogs(
    tmp_path: Path,
):
    root = SimpleNamespace()
    statuses: list[str] = []
    dialogs: list[tuple[str, str]] = []
    logger_name = "cleanroomx.tests.tk-exception"

    log_path = install_tk_exception_handler(
        root,
        status_callback=statuses.append,
        dialog_callback=lambda title, message: dialogs.append((title, message)),
        log_dir=tmp_path,
        logger_name=logger_name,
    )
    assert log_path is not None

    def report(exc: BaseException) -> None:
        try:
            raise exc
        except type(exc) as caught:
            root.report_callback_exception(
                type(caught),
                caught,
                caught.__traceback__,
            )

    try:
        report(ValueError("simulated callback failure"))
        report(ValueError("simulated callback failure"))
        report(RuntimeError("different callback failure"))

        logger = logging.getLogger(logger_name)
        for handler in logger.handlers:
            handler.flush()

        content = log_path.read_text(encoding="utf-8")
        assert content.count("ValueError: simulated callback failure") == 2
        assert "RuntimeError: different callback failure" in content
        assert content.count("Unhandled Tk callback exception incident=") == 3

        assert len(statuses) == 3
        assert all("Internal error " in status for status in statuses)
        assert all(str(log_path) in status for status in statuses)

        assert len(dialogs) == 2
        assert dialogs[0][0] == "CleanroomX internal error"
        assert "Technical details were written to:" in dialogs[0][1]
        assert str(log_path) in dialogs[0][1]
        assert "current project is not marked saved" in dialogs[0][1]
    finally:
        logger = logging.getLogger(logger_name)
        close_gui_runtime_logging(logger)
        logging.Logger.manager.loggerDict.pop(logger_name, None)
