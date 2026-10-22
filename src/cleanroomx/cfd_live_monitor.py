"""Bounded, incremental log preview. Never supplies verified CFD evidence."""
from __future__ import annotations

from collections import deque
import math
import os
from pathlib import Path
import re


PREVIEW_SCHEMA = "cleanroomx.unverified-live-residual-preview.v1"
_TIME = re.compile(r"Time\s*=\s*(\S+)\s*")
_RESIDUAL = re.compile(
    r"Solving for ([A-Za-z][A-Za-z0-9_]*), Initial residual = ([^,\s]+), "
    r"Final residual = ([^,\s]+)(?:,|\s|$)")
_CONTINUITY = re.compile(
    r"time step continuity errors\s*:\s*sum local = ([^,\s]+), "
    r"global = ([^,\s]+), cumulative = ([^,\s]+)")


def _number(token, *, nonnegative=False):
    try:
        value = float(token)
    except ValueError as exc:
        raise ValueError("Invalid numeric value in solver log preview") from exc
    if not math.isfinite(value) or (nonnegative and value < 0):
        raise ValueError("Nonfinite or negative value in solver log preview")
    return value


class LiveSolverMonitor:
    """Consume complete lines once, retaining a bounded number of whole iterations.

    Partial final lines stay pending. An invalid numeric record stops the
    preview until explicitly reset; it never changes execution or import.
    These bytes have not passed receipt, log or field provenance checks.
    """

    def __init__(self, *, max_samples=4000, max_line_bytes=16384):
        if type(max_samples) is not int or not 4 <= max_samples <= 20000:
            raise ValueError("Preview sample limit must be an integer 4..20000")
        if type(max_line_bytes) is not int or not 128 <= max_line_bytes <= 65536:
            raise ValueError("Preview line limit must be an integer 128..65536")
        self.max_samples = max_samples
        self.max_line_bytes = max_line_bytes
        self.history = deque()
        self.pending = b""
        self.iteration = None
        self.continuity = None
        self.latest = {}
        self.total_samples = 0
        self.discarded_samples = 0
        self.error = None
        self.revision = 0

    def feed(self, data):
        """Append a bounded binary chunk. Return whether complete records changed."""
        if type(data) is not bytes or len(data) > 128 * 1024:
            raise ValueError("Preview requires binary chunks of at most 128 KiB")
        before = self.revision
        if self.error is not None:
            return False
        lines = (self.pending + data).split(b"\n")
        self.pending = lines.pop()
        try:
            for raw in lines:
                if len(raw) > self.max_line_bytes:
                    raise ValueError("Solver log preview line exceeds the bounded line limit")
                self._line(raw.decode("utf-8", errors="replace").rstrip("\r"))
            if len(self.pending) > self.max_line_bytes:
                raise ValueError("Solver log preview line exceeds the bounded line limit")
        except ValueError as exc:
            self.error = str(exc)
            self.pending = b""
            self.revision += 1
        return self.revision != before

    def _line(self, line):
        match = _TIME.fullmatch(line)
        if re.match(r"Time\s*=", line) and match is None:
            raise ValueError("Malformed iteration in solver log preview")
        if match:
            token = match[1]
            value = _number(token[:-1] if token.endswith("s") else token, nonnegative=True)
            if self.iteration is not None and value < self.iteration:
                raise ValueError("Solver iterations decreased; preview requires a new run")
            self.iteration = value
            self.revision += 1
        if "Solving for " in line:
            match = _RESIDUAL.search(line)
            if match is None or self.iteration is None:
                raise ValueError("Incomplete solver residual record or missing iteration")
            field = match[1]
            if field not in self.latest and len(self.latest) >= 32:
                raise ValueError("Too many distinct fields in solver log preview")
            row = {"iteration": self.iteration, "field": field,
                   "initial": _number(match[2], nonnegative=True),
                   "final": _number(match[3], nonnegative=True)}
            self.history.append(row)
            self.latest[field] = row
            self.total_samples += 1
            if len(self.history) > self.max_samples:
                first = self.history[0]["iteration"]
                if first == self.iteration:
                    raise ValueError("A single iteration exceeds the preview sample limit")
                # Retain complete iterations so repeated-solve indices remain honest.
                while self.history and self.history[0]["iteration"] == first:
                    self.history.popleft()
                    self.discarded_samples += 1
            self.revision += 1
        if "time step continuity errors" in line:
            match = _CONTINUITY.search(line)
            if match is None or self.iteration is None:
                raise ValueError("Incomplete solver continuity record or missing iteration")
            self.continuity = {"iteration": self.iteration, **dict(zip(
                ("sum_local", "global", "cumulative"),
                (_number(match[i]) for i in (1, 2, 3))))}
            self.revision += 1

    def plot_snapshot(self):
        """A plot-only copy, deliberately lacking saved-field or convergence verdicts."""
        if self.error is not None or not self.history:
            return None
        return {"schema": PREVIEW_SCHEMA,
                "residual_history": [dict(row) for row in self.history],
                "residual_log_offset": self.discarded_samples,
                "observed_sample_count": self.total_samples,
                "numerics": {"fields": {}}, "time_name": None}


class LiveLogFollower:
    """Read at most 128 KiB per poll; clear history after replacement/truncation."""

    def __init__(self, path, *, allow_existing=True):
        self.path = Path(path)
        self._preexisting = not allow_existing and self.path.exists()
        self.monitor = LiveSolverMonitor()
        self.offset = 0
        self.identity = None
        self.notice = ""
        self.error = None

    def poll(self):
        if self.error is not None or self.monitor.error is not None:
            return False
        try:
            if self._preexisting:
                raise ValueError("An existing solver log cannot be attributed to a fresh run")
            if self.path.is_symlink():
                raise ValueError("Symbolic solver logs are not followed in the live preview")
            if self.path.exists() and not self.path.is_file():
                raise ValueError("Only regular solver log files may be previewed")
            with self.path.open("rb") as stream:
                stat = os.fstat(stream.fileno())
                identity = (stat.st_dev, stat.st_ino)
                reset = (self.identity is not None and (
                    self.identity != identity or stat.st_size < self.offset))
                if reset:
                    self.monitor = LiveSolverMonitor()
                    self.offset = 0
                    self.notice = "Log replaced or truncated; previous preview cleared."
                self.identity = identity
                stream.seek(self.offset)
                data = stream.read(128 * 1024)
                self.offset = stream.tell()
            self.monitor.feed(data)
            return bool(data) or reset
        except FileNotFoundError:
            if self.identity is not None:
                self.monitor = LiveSolverMonitor()
                self.offset = 0
                self.identity = None
                self.notice = "Log removed; previous preview cleared."
                return True
            return False
        except (OSError, ValueError) as exc:
            self.error = str(exc)
            return True
