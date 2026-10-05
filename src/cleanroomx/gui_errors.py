"""Fail-safe desktop error diagnostics for CleanroomX.

This module is deliberately outside engineering/project persistence.  GUI failures are
recorded in per-user application state only; project files, analysis inputs, evidence,
and verification verdicts are never modified by this diagnostic path.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import uuid

from .gui_state import default_gui_layout_state_path


_GUI_LOG_MAX_BYTES = 2 * 1024 * 1024
_GUI_LOG_BACKUP_COUNT = 3


@dataclass(frozen=True)
class GuiErrorReport:
    reference: str
    operation: str
    exception_type: str
    summary: str
    log_path: Path | None

    def user_message(self) -> str:
        detail = self.summary or self.exception_type
        lines = [
            f"{self.operation} did not complete.",
            "",
            detail,
            "",
            f"Error reference: {self.reference}",
        ]
        if self.log_path is not None:
            lines.append(f"Technical log: {self.log_path}")
        else:
            lines.append(
                "Technical logging was unavailable; the error reference is still "
                "valid for this session."
            )
        return "\n".join(lines)


def default_gui_log_path() -> Path:
    """Return the per-user desktop log path without touching engineering data."""
    return default_gui_layout_state_path().parent / "logs" / "gui.log"


def _logger_name(path: Path) -> str:
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
    return f"cleanroomx.gui.{digest}"


def _logger_for(path: Path) -> logging.Logger:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(_logger_name(target))
    logger.setLevel(logging.INFO)
    logger.propagate = False

    resolved = target.resolve(strict=False)
    for handler in logger.handlers:
        if isinstance(handler, RotatingFileHandler):
            try:
                if Path(handler.baseFilename).resolve(strict=False) == resolved:
                    return logger
            except (OSError, ValueError):
                continue

    handler = RotatingFileHandler(
        target,
        maxBytes=_GUI_LOG_MAX_BYTES,
        backupCount=_GUI_LOG_BACKUP_COUNT,
        encoding="utf-8",
        delay=True,
    )
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)sZ %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    logger.addHandler(handler)
    return logger


def record_gui_exception(
    operation: str,
    exc: BaseException,
    *,
    log_path: str | Path | None = None,
) -> GuiErrorReport:
    """Record one GUI-boundary failure and return safe operator-facing metadata.

    Logging is fail-safe: inability to create/write the user log must never replace
    or mask the original application exception.
    """

    operation_text = str(operation or "Operation").strip() or "Operation"
    summary = str(exc).strip() or type(exc).__name__
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    reference = f"CX-{timestamp}-{uuid.uuid4().hex[:8].upper()}"
    target = Path(log_path) if log_path is not None else default_gui_log_path()
    written_path: Path | None = None

    try:
        logger = _logger_for(target)
        logger.error(
            "[%s] operation=%r exception=%s message=%r",
            reference,
            operation_text,
            type(exc).__name__,
            summary,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        written_path = target.expanduser().resolve(strict=False)
    except Exception:
        # Error reporting is a containment boundary.  It must not obscure the
        # original user-visible failure if home storage is unavailable/read-only.
        written_path = None

    return GuiErrorReport(
        reference=reference,
        operation=operation_text,
        exception_type=type(exc).__name__,
        summary=summary,
        log_path=written_path,
    )
