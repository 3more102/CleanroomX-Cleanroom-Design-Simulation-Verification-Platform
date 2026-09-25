from __future__ import annotations

import copy
from collections import deque
from dataclasses import dataclass
from typing import Iterable

from .application import AnalysisRun, analysis_run_matches_input


DEFAULT_RUN_HISTORY_LIMIT = 100


def _input_sha256(run: AnalysisRun) -> str | None:
    diagnostics = run.diagnostics
    if not isinstance(diagnostics, dict):
        return None
    provenance = diagnostics.get("application_execution_provenance")
    if not isinstance(provenance, dict):
        return None
    value = provenance.get("input_sha256")
    if isinstance(value, str) and len(value) == 64:
        return value
    return None


@dataclass(frozen=True)
class RunHistorySummary:
    sequence: int
    analysis_id: str
    analysis_name: str
    kind: str
    title: str
    status: str
    input_sha256: str | None


@dataclass(frozen=True)
class RunHistoryEntry:
    """Immutable ownership record for one accepted desktop analysis run."""

    sequence: int
    analysis_id: str
    analysis_name: str
    run: AnalysisRun

    @property
    def input_sha256(self) -> str | None:
        return _input_sha256(self.run)

    def summary(self) -> RunHistorySummary:
        return RunHistorySummary(
            sequence=self.sequence,
            analysis_id=self.analysis_id,
            analysis_name=self.analysis_name,
            kind=self.run.kind,
            title=self.run.title,
            status=self.run.status,
            input_sha256=self.input_sha256,
        )

    def to_dict(self) -> dict:
        return {
            "sequence": self.sequence,
            "analysis_id": self.analysis_id,
            "analysis_name": self.analysis_name,
            "input_sha256": self.input_sha256,
            "run": self.run.to_dict(),
        }


class RunHistory:
    """Bounded in-memory history of accepted analysis runs.

    Stored runs are deep-copied on ingress and full-entry egress so callers
    cannot mutate retained engineering evidence through nested result, diagnostic,
    or plot structures. Lightweight frozen summaries avoid copying large result
    payloads when the desktop only needs to refresh the history index.
    Sequence numbers are deterministic within one project/path-context session.
    """

    def __init__(self, limit: int = DEFAULT_RUN_HISTORY_LIMIT) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("run history limit must be a positive integer")
        self._limit = limit
        self._entries: deque[RunHistoryEntry] = deque(maxlen=limit)
        self._next_sequence = 1

    @property
    def limit(self) -> int:
        return self._limit

    def __len__(self) -> int:
        return len(self._entries)

    def _entry(self, sequence: int) -> RunHistoryEntry:
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise KeyError(sequence)
        for entry in self._entries:
            if entry.sequence == sequence:
                return entry
        raise KeyError(sequence)

    def append(
        self,
        analysis_id: str,
        analysis_name: str,
        run: AnalysisRun,
    ) -> RunHistoryEntry:
        if not isinstance(analysis_id, str) or not analysis_id.strip():
            raise ValueError("analysis_id must be a non-empty string")
        if not isinstance(analysis_name, str) or not analysis_name.strip():
            raise ValueError("analysis_name must be a non-empty string")
        if not isinstance(run, AnalysisRun):
            raise TypeError("run history accepts AnalysisRun instances only")

        entry = RunHistoryEntry(
            sequence=self._next_sequence,
            analysis_id=analysis_id,
            analysis_name=analysis_name,
            run=copy.deepcopy(run),
        )
        self._next_sequence += 1
        self._entries.append(entry)
        return copy.deepcopy(entry)

    def summaries(self) -> tuple[RunHistorySummary, ...]:
        return tuple(entry.summary() for entry in self._entries)

    def summary(self, sequence: int) -> RunHistorySummary:
        return self._entry(sequence).summary()

    def matches_input(self, sequence: int, kind: str, payload: dict) -> bool:
        return analysis_run_matches_input(self._entry(sequence).run, kind, payload)

    def entries(self, analysis_id: str | None = None) -> tuple[RunHistoryEntry, ...]:
        selected: Iterable[RunHistoryEntry] = self._entries
        if analysis_id is not None:
            selected = (
                entry for entry in self._entries if entry.analysis_id == analysis_id
            )
        return tuple(copy.deepcopy(entry) for entry in selected)

    def get(self, sequence: int) -> RunHistoryEntry:
        return copy.deepcopy(self._entry(sequence))

    def clear(self) -> None:
        self._entries.clear()
        self._next_sequence = 1
