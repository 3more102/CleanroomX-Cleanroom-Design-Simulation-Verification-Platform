from __future__ import annotations

import copy
from collections import deque
from dataclasses import dataclass
from typing import Iterable

from .application import AnalysisRun


DEFAULT_RUN_HISTORY_LIMIT = 100


@dataclass(frozen=True)
class RunHistoryEntry:
    """Immutable ownership record for one accepted desktop analysis run."""

    sequence: int
    analysis_id: str
    analysis_name: str
    run: AnalysisRun

    @property
    def input_sha256(self) -> str | None:
        diagnostics = self.run.diagnostics
        if not isinstance(diagnostics, dict):
            return None
        provenance = diagnostics.get("application_execution_provenance")
        if not isinstance(provenance, dict):
            return None
        value = provenance.get("input_sha256")
        if isinstance(value, str) and len(value) == 64:
            return value
        return None

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

    Stored runs are deep-copied on ingress and egress so callers cannot mutate
    retained engineering evidence through nested dictionaries or plot data.
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

    def entries(self, analysis_id: str | None = None) -> tuple[RunHistoryEntry, ...]:
        selected: Iterable[RunHistoryEntry] = self._entries
        if analysis_id is not None:
            selected = (
                entry for entry in self._entries if entry.analysis_id == analysis_id
            )
        return tuple(copy.deepcopy(entry) for entry in selected)

    def get(self, sequence: int) -> RunHistoryEntry:
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise KeyError(sequence)
        for entry in self._entries:
            if entry.sequence == sequence:
                return copy.deepcopy(entry)
        raise KeyError(sequence)

    def clear(self) -> None:
        self._entries.clear()
        self._next_sequence = 1
