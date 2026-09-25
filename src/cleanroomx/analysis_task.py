from __future__ import annotations

from dataclasses import dataclass
import json
import multiprocessing
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any

from .application import AnalysisRun, run_analysis
from .project import atomic_write_text


ANALYSIS_CANCEL_KILL_GRACE_SECONDS = 1.0
ANALYSIS_SHUTDOWN_JOIN_SECONDS = 0.25


@dataclass(frozen=True)
class AnalysisTaskOutcome:
    """Terminal state produced by an isolated desktop analysis task."""

    status: str
    run: AnalysisRun | None = None
    error: str | None = None
    error_type: str | None = None
    exit_code: int | None = None


def _strict_json_load(path: Path) -> dict[str, Any]:
    def reject_constant(value: str):
        raise ValueError(f"non-finite JSON constant is not allowed: {value}")

    payload = json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=reject_constant,
    )
    if not isinstance(payload, dict):
        raise ValueError("analysis worker outcome must be a JSON object")
    return payload


def _analysis_worker_entry(
    outcome_path: str,
    kind: str,
    payload: dict[str, Any],
    base_dir: str | None,
) -> None:
    """Execute one analysis in a child process and emit a strict-JSON outcome."""

    destination = Path(outcome_path)
    try:
        run = run_analysis(
            kind,
            payload,
            base_dir=Path(base_dir) if base_dir is not None else None,
        )
        outcome = {
            "status": "success",
            "run": run.to_dict(),
        }
    except BaseException as exc:  # process isolation boundary
        outcome = {
            "status": "error",
            "error_type": type(exc).__name__,
            "error": str(exc) or type(exc).__name__,
        }

    outcome_text = json.dumps(
        outcome,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"
    atomic_write_text(destination, outcome_text)


class AnalysisTask:
    """Lifecycle wrapper for one isolated GUI analysis process.

    The engineering backend remains synchronous and unchanged. This wrapper is
    strictly an application-shell concern: it gives the desktop UI a process
    boundary that can be cancelled without overlapping runs or mutating the
    authoritative project model.
    """

    def __init__(
        self,
        *,
        process,
        outcome_path: Path,
        work_dir: Path,
    ) -> None:
        self._process = process
        self._outcome_path = outcome_path
        self._work_dir = work_dir
        self._cancel_requested = False
        self._kill_deadline: float | None = None
        self._outcome: AnalysisTaskOutcome | None = None

    @classmethod
    def start(
        cls,
        kind: str,
        payload: dict[str, Any],
        *,
        base_dir: str | Path | None = None,
        _context=None,
    ) -> "AnalysisTask":
        """Start one analysis using a spawn context for cross-platform parity."""

        work_dir = Path(tempfile.mkdtemp(prefix="cleanroomx-analysis-"))
        outcome_path = work_dir / "outcome.json"
        context = _context or multiprocessing.get_context("spawn")
        try:
            process = context.Process(
                target=_analysis_worker_entry,
                args=(
                    str(outcome_path),
                    kind,
                    payload,
                    str(Path(base_dir)) if base_dir is not None else None,
                ),
                name=f"CleanroomX analysis: {kind}",
            )
            process.start()
        except BaseException:
            shutil.rmtree(work_dir, ignore_errors=True)
            raise
        return cls(
            process=process,
            outcome_path=outcome_path,
            work_dir=work_dir,
        )

    @property
    def cancel_requested(self) -> bool:
        return self._cancel_requested

    @property
    def is_alive(self) -> bool:
        return self._outcome is None and bool(self._process.is_alive())

    def cancel(self) -> bool:
        """Request prompt termination without blocking the GUI thread."""

        if self._outcome is not None or self._cancel_requested:
            return False
        self._cancel_requested = True
        self._kill_deadline = time.monotonic() + ANALYSIS_CANCEL_KILL_GRACE_SECONDS
        if self._process.is_alive():
            self._process.terminate()
        return True

    def poll(self) -> AnalysisTaskOutcome | None:
        """Return a terminal outcome when ready; otherwise return None."""

        if self._outcome is not None:
            return self._outcome

        if self._process.is_alive():
            if (
                self._cancel_requested
                and self._kill_deadline is not None
                and time.monotonic() >= self._kill_deadline
            ):
                self._process.kill()
                self._kill_deadline = None
            return None

        self._process.join(timeout=0)
        exit_code = self._process.exitcode

        if self._cancel_requested:
            self._outcome = AnalysisTaskOutcome(
                status="cancelled",
                exit_code=exit_code,
            )
            self._cleanup()
            return self._outcome

        try:
            payload = _strict_json_load(self._outcome_path)
            status = payload.get("status")
            if status == "success":
                if exit_code not in (0, None):
                    raise ValueError(
                        f"analysis worker reported success but exited with code {exit_code}"
                    )
                run_payload = payload.get("run")
                if not isinstance(run_payload, dict):
                    raise ValueError("successful analysis outcome is missing run data")
                self._outcome = AnalysisTaskOutcome(
                    status="success",
                    run=AnalysisRun(**run_payload),
                    exit_code=exit_code,
                )
            elif status == "error":
                error = payload.get("error")
                error_type = payload.get("error_type")
                if not isinstance(error, str) or not error:
                    raise ValueError("analysis worker error outcome is missing a message")
                if error_type is not None and not isinstance(error_type, str):
                    raise ValueError("analysis worker error_type must be a string or null")
                self._outcome = AnalysisTaskOutcome(
                    status="error",
                    error=error,
                    error_type=error_type,
                    exit_code=exit_code,
                )
            else:
                raise ValueError(f"unsupported analysis worker status {status!r}")
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self._outcome = AnalysisTaskOutcome(
                status="error",
                error=(
                    "Analysis worker exited without a readable outcome "
                    f"(exit code {exit_code}): {exc}"
                ),
                error_type=type(exc).__name__,
                exit_code=exit_code,
            )

        self._cleanup()
        return self._outcome

    def shutdown(self) -> None:
        """Terminate any live worker and release its temporary outcome directory."""

        if self._outcome is None and self._process.is_alive():
            self._cancel_requested = True
            self._process.terminate()
            self._process.join(timeout=ANALYSIS_SHUTDOWN_JOIN_SECONDS)
            if self._process.is_alive():
                self._process.kill()
                self._process.join(timeout=ANALYSIS_SHUTDOWN_JOIN_SECONDS)
        elif self._outcome is None:
            self._process.join(timeout=0)
        self._cleanup()

    def _cleanup(self) -> None:
        shutil.rmtree(self._work_dir, ignore_errors=True)
