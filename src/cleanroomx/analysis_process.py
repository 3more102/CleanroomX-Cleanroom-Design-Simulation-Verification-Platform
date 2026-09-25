from __future__ import annotations

import multiprocessing
from multiprocessing.connection import Connection
from pathlib import Path
import time
from typing import Any

from .application import AnalysisRun, run_analysis


DEFAULT_CANCEL_KILL_GRACE_SECONDS = 1.0
WorkerMessage = tuple[str, AnalysisRun | str | None]


def _send_terminal_message(connection: Connection, message: WorkerMessage) -> None:
    try:
        connection.send(message)
    except (BrokenPipeError, EOFError, OSError):
        # The parent may have cancelled/closed while the child was finishing.
        pass


def _analysis_process_main(
    connection: Connection,
    kind: str,
    payload: dict[str, Any],
    base_dir: str | None,
) -> None:
    """Execute one validated application analysis in an isolated child process."""
    try:
        run = run_analysis(
            kind,
            payload,
            base_dir=Path(base_dir) if base_dir is not None else None,
        )
        _send_terminal_message(connection, ("success", run))
    except Exception as exc:
        _send_terminal_message(connection, ("error", str(exc)))
    finally:
        connection.close()


class AnalysisProcess:
    """Single-run process boundary for interactive desktop analyses.

    The desktop owns project state and persistence.  The child receives only an
    immutable input snapshot plus base-directory context, executes one analysis,
    and sends one terminal result back.  Cancellation terminates that isolated
    computation without permitting overlapping workers.
    """

    def __init__(
        self,
        *,
        context=None,
        cancel_kill_grace_seconds: float = DEFAULT_CANCEL_KILL_GRACE_SECONDS,
    ) -> None:
        if cancel_kill_grace_seconds < 0:
            raise ValueError("cancel_kill_grace_seconds must be zero or greater")
        self._context = context or multiprocessing.get_context("spawn")
        self._cancel_kill_grace_seconds = float(cancel_kill_grace_seconds)
        self._process = None
        self._connection: Connection | None = None
        self._message: WorkerMessage | None = None
        self._cancelling = False
        self._terminate_requested_at: float | None = None
        self._kill_sent = False

    @property
    def active(self) -> bool:
        return self._process is not None

    @property
    def cancelling(self) -> bool:
        return self._cancelling

    @property
    def pid(self) -> int | None:
        process = self._process
        return process.pid if process is not None else None

    def start(
        self,
        kind: str,
        payload: dict[str, Any],
        *,
        base_dir: Path | str | None = None,
    ) -> None:
        if self.active:
            raise RuntimeError("an analysis worker is already active")

        receive_connection, send_connection = self._context.Pipe(duplex=False)
        process = self._context.Process(
            target=_analysis_process_main,
            args=(
                send_connection,
                kind,
                payload,
                str(base_dir) if base_dir is not None else None,
            ),
            name=f"CleanroomX analysis: {kind}",
        )
        process.daemon = True
        try:
            process.start()
        except Exception:
            receive_connection.close()
            send_connection.close()
            raise
        finally:
            # Once start() succeeds the child owns its duplicated sending end.
            if process.pid is not None:
                send_connection.close()

        self._process = process
        self._connection = receive_connection
        self._message = None
        self._cancelling = False
        self._terminate_requested_at = None
        self._kill_sent = False

    def cancel(self) -> bool:
        process = self._process
        if process is None or self._cancelling:
            return False

        self._cancelling = True
        self._terminate_requested_at = time.monotonic()
        if process.is_alive():
            process.terminate()
        return True

    def poll(self) -> WorkerMessage | None:
        process = self._process
        connection = self._connection
        if process is None or connection is None:
            return None

        if self._message is None and connection.poll():
            try:
                self._message = connection.recv()
            except EOFError:
                self._message = None

        if process.is_alive():
            if (
                self._cancelling
                and not self._kill_sent
                and self._terminate_requested_at is not None
                and time.monotonic() - self._terminate_requested_at
                >= self._cancel_kill_grace_seconds
            ):
                kill = getattr(process, "kill", None)
                if callable(kill):
                    kill()
                    self._kill_sent = True
            return None

        # The process has exited. Any complete pipe message is now readable.
        if self._message is None and connection.poll():
            try:
                self._message = connection.recv()
            except EOFError:
                self._message = None

        process.join(timeout=0)
        exitcode = process.exitcode
        message = self._message
        cancelling = self._cancelling
        self._reset()

        if cancelling:
            return ("cancelled", None)
        if message is not None:
            return message
        return (
            "error",
            f"Analysis worker exited unexpectedly (exit code {exitcode}).",
        )

    def shutdown(self, *, wait: bool = False) -> None:
        process = self._process
        if process is None:
            return

        if process.is_alive():
            process.terminate()
        if wait:
            process.join(timeout=self._cancel_kill_grace_seconds)
            if process.is_alive():
                kill = getattr(process, "kill", None)
                if callable(kill):
                    kill()
                    process.join(timeout=self._cancel_kill_grace_seconds)
        else:
            process.join(timeout=0)
        self._reset()

    def _reset(self) -> None:
        if self._connection is not None:
            self._connection.close()
        self._process = None
        self._connection = None
        self._message = None
        self._cancelling = False
        self._terminate_requested_at = None
        self._kill_sent = False
