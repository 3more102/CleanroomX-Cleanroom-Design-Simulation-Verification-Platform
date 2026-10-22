"""Manage native CFD subprocess lifetime without touching unrelated processes."""
from __future__ import annotations

import os
import math
from pathlib import Path
import signal
import subprocess
import threading
import time
from typing import IO, Sequence


class CFDRunCancelled(Exception):
    """The operator cancelled a native operation; this is never CFD evidence."""


def _terminate_process_tree(process: subprocess.Popen) -> None:
    """Reap the child and stop its dedicated POSIX group, including descendants.

    Only children started with start_new_session=True may use this path. WSL
    requires a separate Linux-side mechanism; killing wsl.exe is insufficient.
    """
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            pass
        # A wrapper may exit before a descendant, including one ignoring TERM.
        # Address the original isolated group even when its leader has exited.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        # Native Windows descendant cleanup is not supported by this helper.
        # Its cancellation/timeout contract is therefore restricted to POSIX.
        process.kill()
    process.wait()


def run_native_cfd_process(
    arguments: Sequence[str], *, cwd: str | Path, output: IO,
    timeout_seconds: float, cancel_event: threading.Event | None = None,
) -> subprocess.CompletedProcess:
    """Run a native POSIX command; cancellation/timeout reaps its process group.

    The caller owns the log file and records a failed/cancelled run receipt.
    No shell is used. Output streams directly to disk, not a memory pipe.
    """
    if os.name != "posix":
        raise RuntimeError("Native CFD execution requires Linux; use the Windows-to-WSL bridge")
    if (type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0):
        raise ValueError("Native CFD process timeout must be finite and positive")
    if cancel_event is not None and cancel_event.is_set():
        raise CFDRunCancelled("Native CFD run cancelled before starting the next process")
    process = subprocess.Popen(
        list(arguments), cwd=cwd, stdout=output, stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    deadline = time.monotonic() + timeout_seconds
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise CFDRunCancelled("Native CFD run cancelled by the operator")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(list(arguments), timeout_seconds)
            try:
                returncode = process.wait(timeout=min(0.05, remaining))
                return subprocess.CompletedProcess(list(arguments), returncode)
            except subprocess.TimeoutExpired:
                continue
    except BaseException:
        _terminate_process_tree(process)
        raise
