from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
from types import TracebackType
from typing import Callable, Mapping
import uuid


GUI_LOG_DIR_ENV = "CLEANROOMX_LOG_DIR"
GUI_LOG_FILENAME = "cleanroomx-gui.log"
GUI_LOG_MAX_BYTES = 4 * 1024 * 1024
GUI_LOG_BACKUP_COUNT = 3
_RUNTIME_HANDLER_MARKER = "_cleanroomx_runtime_log_handler"


def default_gui_log_dir(
    *,
    env: Mapping[str, str] | None = None,
    platform: str | None = None,
    home: Path | None = None,
) -> Path:
    """Return the per-user GUI diagnostic-log directory."""

    environment = os.environ if env is None else env
    override = environment.get(GUI_LOG_DIR_ENV, "").strip()
    if override:
        return Path(override).expanduser()

    platform_name = sys.platform if platform is None else platform
    home_dir = Path.home() if home is None else Path(home)

    if platform_name.startswith("win"):
        local_app_data = environment.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            return Path(local_app_data) / "CleanroomX" / "Logs"
        return home_dir / "AppData" / "Local" / "CleanroomX" / "Logs"

    if platform_name == "darwin":
        return home_dir / "Library" / "Logs" / "CleanroomX"

    xdg_state_home = environment.get("XDG_STATE_HOME", "").strip()
    state_home = Path(xdg_state_home) if xdg_state_home else home_dir / ".local" / "state"
    return state_home / "cleanroomx" / "logs"


def configure_gui_runtime_logging(
    log_dir: str | Path | None = None,
    *,
    logger_name: str = "cleanroomx.gui.runtime",
) -> tuple[logging.Logger, Path]:
    """Configure one bounded per-user GUI runtime log."""

    directory = (
        default_gui_log_dir()
        if log_dir is None
        else Path(log_dir).expanduser()
    )
    directory.mkdir(parents=True, exist_ok=True)
    log_path = (directory / GUI_LOG_FILENAME).resolve(strict=False)

    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for handler in list(logger.handlers):
        if getattr(handler, _RUNTIME_HANDLER_MARKER, False):
            logger.removeHandler(handler)
            handler.close()

    handler = RotatingFileHandler(
        log_path,
        maxBytes=GUI_LOG_MAX_BYTES,
        backupCount=GUI_LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    setattr(handler, _RUNTIME_HANDLER_MARKER, True)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)sZ %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    logger.addHandler(handler)
    logger.info("CleanroomX GUI runtime diagnostics initialized")
    return logger, log_path


def close_gui_runtime_logging(logger: logging.Logger) -> None:
    """Close only handlers owned by the CleanroomX GUI diagnostics layer."""

    for handler in list(logger.handlers):
        if getattr(handler, _RUNTIME_HANDLER_MARKER, False):
            logger.removeHandler(handler)
            handler.close()


def install_tk_exception_handler(
    root,
    *,
    status_callback: Callable[[str], None] | None = None,
    dialog_callback: Callable[[str, str], None] | None = None,
    log_dir: str | Path | None = None,
    logger_name: str = "cleanroomx.gui.runtime",
) -> Path | None:
    """Persist unexpected Tk callback failures and present concise operator feedback."""

    try:
        logger, log_path = configure_gui_runtime_logging(
            log_dir,
            logger_name=logger_name,
        )
    except OSError as setup_error:
        logger = logging.getLogger(logger_name)
        logger.error(
            "Persistent GUI diagnostics log is unavailable: %s",
            setup_error,
        )
        log_path = None

    seen_signatures: list[tuple[str, str]] = []

    def report_callback_exception(
        exc_type: type[BaseException],
        exc_value: BaseException,
        traceback: TracebackType | None,
    ) -> None:
        incident_id = uuid.uuid4().hex[:12].upper()
        logger.error(
            "Unhandled Tk callback exception incident=%s",
            incident_id,
            exc_info=(exc_type, exc_value, traceback),
        )

        if log_path is not None:
            status = f"Internal error {incident_id}; details logged to {log_path}"
            detail = (
                f"CleanroomX encountered an unexpected internal error.\n\n"
                f"Incident: {incident_id}\n"
                f"Technical details were written to:\n{log_path}\n\n"
                "The current project is not marked saved by this error. "
                "If the operation did not complete, review the project state before continuing."
            )
        else:
            status = f"Internal error {incident_id}; persistent log unavailable"
            detail = (
                f"CleanroomX encountered an unexpected internal error.\n\n"
                f"Incident: {incident_id}\n"
                "The persistent runtime log could not be opened; technical details "
                "were sent to the process error stream.\n\n"
                "If the operation did not complete, review the project state before continuing."
            )

        if status_callback is not None:
            try:
                status_callback(status)
            except Exception:
                logger.exception(
                    "Failed to update GUI status for incident=%s",
                    incident_id,
                )

        signature = (exc_type.__qualname__, str(exc_value))
        should_show_dialog = signature not in seen_signatures
        if should_show_dialog:
            seen_signatures.append(signature)
            if len(seen_signatures) > 32:
                del seen_signatures[0]

        if not should_show_dialog:
            return

        try:
            if dialog_callback is not None:
                dialog_callback("CleanroomX internal error", detail)
            else:
                from tkinter import messagebox

                messagebox.showerror(
                    "CleanroomX internal error",
                    detail,
                    parent=root,
                )
        except Exception:
            logger.exception(
                "Failed to present GUI error dialog for incident=%s",
                incident_id,
            )

    root.report_callback_exception = report_callback_exception
    return log_path
