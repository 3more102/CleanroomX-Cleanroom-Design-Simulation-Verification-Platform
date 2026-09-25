from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json

from .application import AnalysisRun


DEFAULT_RUN_HISTORY_ENTRIES_PER_ANALYSIS = 8
DEFAULT_RUN_HISTORY_TOTAL_BYTES = 16 * 1024 * 1024


class RunHistoryIntegrityError(ValueError):
    """Raised when a run cannot be represented as trustworthy history evidence."""


@dataclass(frozen=True)
class RunHistoryEntry:
    sequence: int
    analysis_id: str
    recorded_at_utc: str
    kind: str
    title: str
    status: str
    input_sha256: str
    bundle_sha256: str
    size_bytes: int


@dataclass(frozen=True)
class _StoredRun:
    entry: RunHistoryEntry
    canonical_bundle: str


def _canonical_bundle(run: AnalysisRun) -> tuple[str, bytes]:
    try:
        text = json.dumps(
            run.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise RunHistoryIntegrityError(
            "analysis run is not strict-JSON serializable"
        ) from exc
    return text, text.encode("utf-8")


def _input_sha256(run: AnalysisRun) -> str:
    if not isinstance(run.diagnostics, dict):
        raise RunHistoryIntegrityError("analysis run diagnostics must be an object")
    provenance = run.diagnostics.get("application_execution_provenance")
    if not isinstance(provenance, dict):
        raise RunHistoryIntegrityError(
            "analysis run is missing application execution provenance"
        )
    value = provenance.get("input_sha256")
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdefABCDEF" for ch in value)
    ):
        raise RunHistoryIntegrityError(
            "analysis run provenance has an invalid input SHA-256"
        )
    return value.lower()


def _analysis_run_from_bundle(text: str) -> AnalysisRun:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RunHistoryIntegrityError("stored run bundle is invalid JSON") from exc
    required = {
        "kind",
        "title",
        "status",
        "result",
        "markdown",
        "diagnostics",
        "plot",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise RunHistoryIntegrityError("stored run bundle has an invalid shape")
    if (
        not isinstance(payload["kind"], str)
        or not isinstance(payload["title"], str)
        or not isinstance(payload["status"], str)
        or not isinstance(payload["result"], dict)
        or not isinstance(payload["markdown"], str)
        or not isinstance(payload["diagnostics"], dict)
        or (
            payload["plot"] is not None
            and not isinstance(payload["plot"], dict)
        )
    ):
        raise RunHistoryIntegrityError("stored run bundle has invalid field types")
    return AnalysisRun(
        kind=payload["kind"],
        title=payload["title"],
        status=payload["status"],
        result=payload["result"],
        markdown=payload["markdown"],
        diagnostics=payload["diagnostics"],
        plot=payload["plot"],
    )


class AnalysisRunHistory:
    """Bounded in-session archive of immutable, provenance-bearing analysis runs."""

    def __init__(
        self,
        *,
        max_entries_per_analysis: int = DEFAULT_RUN_HISTORY_ENTRIES_PER_ANALYSIS,
        max_total_bytes: int = DEFAULT_RUN_HISTORY_TOTAL_BYTES,
    ) -> None:
        if not isinstance(max_entries_per_analysis, int) or max_entries_per_analysis < 1:
            raise ValueError("max_entries_per_analysis must be an integer >= 1")
        if not isinstance(max_total_bytes, int) or max_total_bytes < 1:
            raise ValueError("max_total_bytes must be an integer >= 1")
        self.max_entries_per_analysis = max_entries_per_analysis
        self.max_total_bytes = max_total_bytes
        self._stored: list[_StoredRun] = []
        self._sequence = 0
        self._total_bytes = 0

    @property
    def total_bytes(self) -> int:
        return self._total_bytes

    def __len__(self) -> int:
        return len(self._stored)

    def record(self, analysis_id: str, run: AnalysisRun) -> RunHistoryEntry | None:
        if not isinstance(analysis_id, str) or not analysis_id.strip():
            raise ValueError("analysis_id must be a non-empty string")
        if not isinstance(run, AnalysisRun):
            raise TypeError("run must be an AnalysisRun")

        input_sha256 = _input_sha256(run)
        canonical, encoded = _canonical_bundle(run)
        size_bytes = len(encoded)
        if size_bytes > self.max_total_bytes:
            return None

        self._sequence += 1
        entry = RunHistoryEntry(
            sequence=self._sequence,
            analysis_id=analysis_id,
            recorded_at_utc=datetime.now(timezone.utc).isoformat(),
            kind=run.kind,
            title=run.title,
            status=run.status,
            input_sha256=input_sha256,
            bundle_sha256=sha256(encoded).hexdigest(),
            size_bytes=size_bytes,
        )
        self._stored.append(_StoredRun(entry=entry, canonical_bundle=canonical))
        self._total_bytes += size_bytes

        analysis_entries = [
            item for item in self._stored if item.entry.analysis_id == analysis_id
        ]
        excess = len(analysis_entries) - self.max_entries_per_analysis
        if excess > 0:
            evict_sequences = {
                item.entry.sequence for item in analysis_entries[:excess]
            }
            self._evict_sequences(evict_sequences)

        while self._total_bytes > self.max_total_bytes and self._stored:
            self._evict_sequences({self._stored[0].entry.sequence})

        return entry if any(
            item.entry.sequence == entry.sequence for item in self._stored
        ) else None

    def entries_for(self, analysis_id: str) -> tuple[RunHistoryEntry, ...]:
        return tuple(
            item.entry
            for item in reversed(self._stored)
            if item.entry.analysis_id == analysis_id
        )

    def load(self, sequence: int) -> AnalysisRun:
        for item in self._stored:
            if item.entry.sequence != sequence:
                continue
            encoded = item.canonical_bundle.encode("utf-8")
            if sha256(encoded).hexdigest() != item.entry.bundle_sha256:
                raise RunHistoryIntegrityError(
                    "stored run bundle failed its SHA-256 integrity check"
                )
            run = _analysis_run_from_bundle(item.canonical_bundle)
            if _input_sha256(run) != item.entry.input_sha256:
                raise RunHistoryIntegrityError(
                    "stored run bundle input provenance no longer matches history metadata"
                )
            return run
        raise KeyError(sequence)

    def clear_analysis(self, analysis_id: str) -> None:
        self._evict_sequences(
            {
                item.entry.sequence
                for item in self._stored
                if item.entry.analysis_id == analysis_id
            }
        )

    def clear(self) -> None:
        self._stored.clear()
        self._total_bytes = 0

    def _evict_sequences(self, sequences: set[int]) -> None:
        if not sequences:
            return
        retained: list[_StoredRun] = []
        total = 0
        for item in self._stored:
            if item.entry.sequence in sequences:
                continue
            retained.append(item)
            total += item.entry.size_bytes
        self._stored = retained
        self._total_bytes = total
