from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any

from .application import AnalysisRun, analysis_run_matches_input

RUN_HISTORY_METADATA_KEY = "cleanroomx.analysis_run_history"
RUN_HISTORY_SCHEMA = "cleanroomx.analysis-run-history"
RUN_HISTORY_SCHEMA_VERSION = 1
RUN_HISTORY_ENTRY_SCHEMA = "cleanroomx.analysis-run-history-entry"
RUN_HISTORY_ENTRY_SCHEMA_VERSION = 1
RUN_HISTORY_CANONICALIZATION = "json-sort-keys-compact-utf8-v1"

DEFAULT_RUN_HISTORY_LIMIT = 25
DEFAULT_RUN_HISTORY_PER_ANALYSIS_LIMIT = 5
DEFAULT_RUN_HISTORY_MAX_BYTES = 8 * 1024 * 1024


class RunHistoryError(ValueError):
    """Raised when persisted analysis-run history is malformed or unsafe to update."""


@dataclass(frozen=True)
class RunHistoryIssue:
    location: str
    error: str


@dataclass(frozen=True)
class RunHistoryEntry:
    recorded_at_utc: str
    analysis_id: str
    analysis_name: str
    analysis_kind: str
    input_snapshot: dict[str, Any]
    run: AnalysisRun
    sha256: str
    raw: dict[str, Any]


@dataclass(frozen=True)
class RunHistoryScan:
    entries: tuple[RunHistoryEntry, ...]
    issues: tuple[RunHistoryIssue, ...]


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise RunHistoryError("run history must contain only strict JSON values") from exc


def _digest(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _validate_utc_timestamp(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise RunHistoryError("recorded_at_utc must be a non-empty string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RunHistoryError("recorded_at_utc must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise RunHistoryError("recorded_at_utc must include a timezone")
    return value


def _validated_nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RunHistoryError(f"{field} must be a non-empty string")
    return value


def _run_from_dict(data: Any) -> AnalysisRun:
    if not isinstance(data, dict):
        raise RunHistoryError("entry.run must be an object")
    required = {"kind", "title", "status", "result", "markdown", "diagnostics", "plot"}
    if set(data) != required:
        missing = sorted(required - set(data))
        unknown = sorted(set(data) - required)
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unknown:
            details.append("unknown " + ", ".join(unknown))
        suffix = ": " + "; ".join(details) if details else ""
        raise RunHistoryError("entry.run fields are invalid" + suffix)

    kind = _validated_nonempty_string(data["kind"], "entry.run.kind")
    title = _validated_nonempty_string(data["title"], "entry.run.title")
    status = _validated_nonempty_string(data["status"], "entry.run.status")
    markdown = data["markdown"]
    if not isinstance(markdown, str):
        raise RunHistoryError("entry.run.markdown must be a string")
    result = data["result"]
    diagnostics = data["diagnostics"]
    plot = data["plot"]
    if not isinstance(result, dict):
        raise RunHistoryError("entry.run.result must be an object")
    if not isinstance(diagnostics, dict):
        raise RunHistoryError("entry.run.diagnostics must be an object")
    if plot is not None and not isinstance(plot, dict):
        raise RunHistoryError("entry.run.plot must be an object or null")
    _canonical_json(data)
    return AnalysisRun(
        kind=kind,
        title=title,
        status=status,
        result=copy.deepcopy(result),
        markdown=markdown,
        diagnostics=copy.deepcopy(diagnostics),
        plot=copy.deepcopy(plot),
    )


def _entry_payload(
    *,
    analysis_id: str,
    analysis_name: str,
    analysis_kind: str,
    input_snapshot: dict[str, Any],
    run: AnalysisRun,
    recorded_at_utc: str,
) -> dict[str, Any]:
    base = {
        "schema": RUN_HISTORY_ENTRY_SCHEMA,
        "schema_version": RUN_HISTORY_ENTRY_SCHEMA_VERSION,
        "recorded_at_utc": _validate_utc_timestamp(recorded_at_utc),
        "analysis": {
            "id": _validated_nonempty_string(analysis_id, "analysis.id"),
            "name": _validated_nonempty_string(analysis_name, "analysis.name"),
            "kind": _validated_nonempty_string(analysis_kind, "analysis.kind"),
        },
        "input": copy.deepcopy(input_snapshot),
        "run": copy.deepcopy(run.to_dict()),
    }
    if not isinstance(base["input"], dict):
        raise RunHistoryError("analysis input snapshot must be an object")
    _canonical_json(base)
    if not analysis_run_matches_input(run, analysis_kind, base["input"]):
        raise RunHistoryError(
            "analysis run does not match the exact analysis kind/input provenance"
        )
    return {
        **base,
        "integrity": {
            "algorithm": "sha256",
            "canonicalization": RUN_HISTORY_CANONICALIZATION,
            "sha256": _digest(base),
        },
    }


def _parse_entry(data: Any, *, index: int) -> RunHistoryEntry:
    if not isinstance(data, dict):
        raise RunHistoryError(f"entries[{index}] must be an object")
    required = {
        "schema",
        "schema_version",
        "recorded_at_utc",
        "analysis",
        "input",
        "run",
        "integrity",
    }
    if set(data) != required:
        raise RunHistoryError(f"entries[{index}] has unsupported fields")
    if data.get("schema") != RUN_HISTORY_ENTRY_SCHEMA:
        raise RunHistoryError(
            f"entries[{index}].schema must be {RUN_HISTORY_ENTRY_SCHEMA!r}"
        )
    if data.get("schema_version") != RUN_HISTORY_ENTRY_SCHEMA_VERSION:
        raise RunHistoryError(
            f"entries[{index}] has unsupported schema_version "
            f"{data.get('schema_version')!r}"
        )

    analysis = data.get("analysis")
    if not isinstance(analysis, dict) or set(analysis) != {"id", "name", "kind"}:
        raise RunHistoryError(f"entries[{index}].analysis is invalid")
    analysis_id = _validated_nonempty_string(
        analysis.get("id"), f"entries[{index}].analysis.id"
    )
    analysis_name = _validated_nonempty_string(
        analysis.get("name"), f"entries[{index}].analysis.name"
    )
    analysis_kind = _validated_nonempty_string(
        analysis.get("kind"), f"entries[{index}].analysis.kind"
    )

    input_snapshot = data.get("input")
    if not isinstance(input_snapshot, dict):
        raise RunHistoryError(f"entries[{index}].input must be an object")
    run = _run_from_dict(data.get("run"))

    integrity = data.get("integrity")
    if not isinstance(integrity, dict) or set(integrity) != {
        "algorithm",
        "canonicalization",
        "sha256",
    }:
        raise RunHistoryError(f"entries[{index}].integrity is invalid")
    if integrity.get("algorithm") != "sha256":
        raise RunHistoryError(f"entries[{index}] uses an unsupported integrity algorithm")
    if integrity.get("canonicalization") != RUN_HISTORY_CANONICALIZATION:
        raise RunHistoryError(f"entries[{index}] uses an unsupported canonicalization")
    recorded_digest = integrity.get("sha256")
    if not isinstance(recorded_digest, str) or len(recorded_digest) != 64:
        raise RunHistoryError(f"entries[{index}].integrity.sha256 is invalid")

    unsigned = {
        key: copy.deepcopy(value) for key, value in data.items() if key != "integrity"
    }
    recomputed = _digest(unsigned)
    if recorded_digest != recomputed:
        raise RunHistoryError(
            f"entries[{index}] integrity mismatch; persisted evidence was modified"
        )
    recorded_at = _validate_utc_timestamp(data.get("recorded_at_utc"))
    if run.kind != analysis_kind:
        raise RunHistoryError(
            f"entries[{index}] run kind does not match its analysis kind"
        )
    if not analysis_run_matches_input(run, analysis_kind, input_snapshot):
        raise RunHistoryError(
            f"entries[{index}] run provenance does not match its stored input snapshot"
        )

    return RunHistoryEntry(
        recorded_at_utc=recorded_at,
        analysis_id=analysis_id,
        analysis_name=analysis_name,
        analysis_kind=analysis_kind,
        input_snapshot=copy.deepcopy(input_snapshot),
        run=run,
        sha256=recorded_digest,
        raw=copy.deepcopy(data),
    )


def _validate_limits(
    *,
    max_entries: int,
    max_entries_per_analysis: int,
    max_bytes: int,
) -> None:
    if not isinstance(max_entries, int) or isinstance(max_entries, bool) or max_entries < 1:
        raise ValueError("max_entries must be a positive integer")
    if (
        not isinstance(max_entries_per_analysis, int)
        or isinstance(max_entries_per_analysis, bool)
        or max_entries_per_analysis < 1
    ):
        raise ValueError("max_entries_per_analysis must be a positive integer")
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1024:
        raise ValueError("max_bytes must be an integer >= 1024")


def _history_document(
    entries: list[dict[str, Any]],
    *,
    max_entries: int,
    max_entries_per_analysis: int,
    max_bytes: int,
) -> dict[str, Any]:
    unsigned = {
        "schema": RUN_HISTORY_SCHEMA,
        "schema_version": RUN_HISTORY_SCHEMA_VERSION,
        "policy": {
            "max_entries": max_entries,
            "max_entries_per_analysis": max_entries_per_analysis,
            "max_bytes": max_bytes,
        },
        "entries": copy.deepcopy(entries),
    }
    return {
        **unsigned,
        "integrity": {
            "algorithm": "sha256",
            "canonicalization": RUN_HISTORY_CANONICALIZATION,
            "sha256": _digest(unsigned),
        },
    }


def _parse_history_document(data: Any) -> RunHistoryScan:
    if not isinstance(data, dict):
        return RunHistoryScan(
            entries=(),
            issues=(RunHistoryIssue("history", "run-history metadata must be an object"),),
        )
    required = {"schema", "schema_version", "policy", "entries", "integrity"}
    if set(data) != required:
        return RunHistoryScan(
            entries=(),
            issues=(RunHistoryIssue("history", "run-history metadata has unsupported fields"),),
        )
    if data.get("schema") != RUN_HISTORY_SCHEMA:
        return RunHistoryScan(
            entries=(),
            issues=(
                RunHistoryIssue(
                    "history", f"run-history schema must be {RUN_HISTORY_SCHEMA!r}"
                ),
            ),
        )
    if data.get("schema_version") != RUN_HISTORY_SCHEMA_VERSION:
        return RunHistoryScan(
            entries=(),
            issues=(
                RunHistoryIssue(
                    "history",
                    f"unsupported run-history schema version {data.get('schema_version')!r}",
                ),
            ),
        )

    policy = data.get("policy")
    if not isinstance(policy, dict) or set(policy) != {
        "max_entries",
        "max_entries_per_analysis",
        "max_bytes",
    }:
        return RunHistoryScan(
            entries=(),
            issues=(RunHistoryIssue("history.policy", "run-history policy is invalid"),),
        )
    try:
        _validate_limits(
            max_entries=policy["max_entries"],
            max_entries_per_analysis=policy["max_entries_per_analysis"],
            max_bytes=policy["max_bytes"],
        )
    except (KeyError, ValueError) as exc:
        return RunHistoryScan(
            entries=(),
            issues=(RunHistoryIssue("history.policy", str(exc)),),
        )

    raw_entries = data.get("entries")
    if not isinstance(raw_entries, list):
        return RunHistoryScan(
            entries=(),
            issues=(RunHistoryIssue("history.entries", "run-history entries must be an array"),),
        )
    if len(raw_entries) > policy["max_entries"]:
        return RunHistoryScan(
            entries=(),
            issues=(
                RunHistoryIssue(
                    "history.entries",
                    "run-history entry count exceeds its persisted maximum",
                ),
            ),
        )
    counts: dict[str, int] = {}
    for item in raw_entries:
        if isinstance(item, dict):
            analysis = item.get("analysis")
            if isinstance(analysis, dict) and isinstance(analysis.get("id"), str):
                analysis_id = analysis["id"]
                counts[analysis_id] = counts.get(analysis_id, 0) + 1
    if any(count > policy["max_entries_per_analysis"] for count in counts.values()):
        return RunHistoryScan(
            entries=(),
            issues=(
                RunHistoryIssue(
                    "history.entries",
                    "run-history per-analysis entry count exceeds its persisted maximum",
                ),
            ),
        )

    integrity = data.get("integrity")
    if not isinstance(integrity, dict) or set(integrity) != {
        "algorithm",
        "canonicalization",
        "sha256",
    }:
        return RunHistoryScan(
            entries=(),
            issues=(RunHistoryIssue("history.integrity", "run-history integrity block is invalid"),),
        )
    if integrity.get("algorithm") != "sha256":
        return RunHistoryScan(
            entries=(),
            issues=(RunHistoryIssue("history.integrity", "unsupported integrity algorithm"),),
        )
    if integrity.get("canonicalization") != RUN_HISTORY_CANONICALIZATION:
        return RunHistoryScan(
            entries=(),
            issues=(RunHistoryIssue("history.integrity", "unsupported canonicalization"),),
        )
    expected_digest = integrity.get("sha256")
    if not isinstance(expected_digest, str) or len(expected_digest) != 64:
        return RunHistoryScan(
            entries=(),
            issues=(RunHistoryIssue("history.integrity", "run-history SHA-256 is invalid"),),
        )
    unsigned = {
        key: copy.deepcopy(value) for key, value in data.items() if key != "integrity"
    }
    if expected_digest != _digest(unsigned):
        return RunHistoryScan(
            entries=(),
            issues=(
                RunHistoryIssue(
                    "history.integrity",
                    "run-history integrity mismatch; history may be incomplete or modified",
                ),
            ),
        )
    if len(_canonical_json(data).encode("utf-8")) > policy["max_bytes"]:
        return RunHistoryScan(
            entries=(),
            issues=(
                RunHistoryIssue(
                    "history",
                    "run-history serialized size exceeds its persisted maximum",
                ),
            ),
        )

    parsed: list[RunHistoryEntry] = []
    issues: list[RunHistoryIssue] = []
    for index, item in enumerate(raw_entries):
        try:
            parsed.append(_parse_entry(item, index=index))
        except RunHistoryError as exc:
            issues.append(RunHistoryIssue(f"entries[{index}]", str(exc)))
    if issues:
        return RunHistoryScan(entries=(), issues=tuple(issues))
    return RunHistoryScan(entries=tuple(parsed), issues=())


def scan_run_history(project: Any) -> RunHistoryScan:
    metadata = getattr(project, "metadata", None)
    if not isinstance(metadata, dict):
        return RunHistoryScan(
            entries=(),
            issues=(RunHistoryIssue("project.metadata", "project metadata must be an object"),),
        )
    data = metadata.get(RUN_HISTORY_METADATA_KEY)
    if data is None:
        return RunHistoryScan(entries=(), issues=())
    try:
        return _parse_history_document(copy.deepcopy(data))
    except RunHistoryError as exc:
        return RunHistoryScan(
            entries=(),
            issues=(RunHistoryIssue("history", str(exc)),),
        )


def _bounded_entries(
    entries: list[dict[str, Any]],
    *,
    analysis_id: str,
    max_entries: int,
    max_entries_per_analysis: int,
) -> list[dict[str, Any]]:
    matching_indices = [
        index
        for index, item in enumerate(entries)
        if isinstance(item, dict)
        and isinstance(item.get("analysis"), dict)
        and item["analysis"].get("id") == analysis_id
    ]
    excess_for_analysis = max(0, len(matching_indices) - max_entries_per_analysis)
    remove = set(matching_indices[:excess_for_analysis])
    bounded = [item for index, item in enumerate(entries) if index not in remove]
    if len(bounded) > max_entries:
        bounded = bounded[-max_entries:]
    return bounded


def append_run_history(
    project: Any,
    analysis: Any,
    run: AnalysisRun,
    *,
    max_entries: int = DEFAULT_RUN_HISTORY_LIMIT,
    max_entries_per_analysis: int = DEFAULT_RUN_HISTORY_PER_ANALYSIS_LIMIT,
    max_bytes: int = DEFAULT_RUN_HISTORY_MAX_BYTES,
    recorded_at_utc: str | None = None,
) -> RunHistoryEntry:
    """Append one immutable-by-contract, integrity-checked run record transactionally."""
    _validate_limits(
        max_entries=max_entries,
        max_entries_per_analysis=max_entries_per_analysis,
        max_bytes=max_bytes,
    )
    metadata = getattr(project, "metadata", None)
    if not isinstance(metadata, dict):
        raise RunHistoryError("project metadata must be an object")

    scan = scan_run_history(project)
    if scan.issues:
        detail = "; ".join(f"{item.location}: {item.error}" for item in scan.issues)
        raise RunHistoryError(
            "existing run history is invalid; refusing to overwrite preserved evidence: "
            + detail
        )

    entry_payload = _entry_payload(
        analysis_id=getattr(analysis, "id", None),
        analysis_name=getattr(analysis, "name", None),
        analysis_kind=getattr(analysis, "kind", None),
        input_snapshot=getattr(analysis, "input", None),
        run=run,
        recorded_at_utc=recorded_at_utc or _utc_now_text(),
    )
    entries = [copy.deepcopy(item.raw) for item in scan.entries]
    entries.append(entry_payload)
    entries = _bounded_entries(
        entries,
        analysis_id=entry_payload["analysis"]["id"],
        max_entries=max_entries,
        max_entries_per_analysis=max_entries_per_analysis,
    )

    document = _history_document(
        entries,
        max_entries=max_entries,
        max_entries_per_analysis=max_entries_per_analysis,
        max_bytes=max_bytes,
    )
    while (
        len(_canonical_json(document).encode("utf-8")) > max_bytes
        and len(entries) > 1
    ):
        entries.pop(0)
        document = _history_document(
            entries,
            max_entries=max_entries,
            max_entries_per_analysis=max_entries_per_analysis,
            max_bytes=max_bytes,
        )
    if len(_canonical_json(document).encode("utf-8")) > max_bytes:
        raise RunHistoryError(
            "completed run is too large for embedded project history; "
            "export the run bundle separately"
        )

    validation = _parse_history_document(document)
    if validation.issues or not validation.entries:
        detail = "; ".join(
            f"{item.location}: {item.error}" for item in validation.issues
        ) or "new run record was not retained"
        raise RunHistoryError(f"refusing to persist invalid run history: {detail}")

    project.metadata[RUN_HISTORY_METADATA_KEY] = document
    return validation.entries[-1]


def restore_matching_run_cache(
    project: Any,
) -> tuple[dict[str, AnalysisRun], tuple[RunHistoryIssue, ...]]:
    """Restore only latest history entries that exactly match current analysis inputs."""
    scan = scan_run_history(project)
    if scan.issues:
        return {}, scan.issues

    analyses = {
        getattr(item, "id", None): item
        for item in getattr(project, "analyses", ())
        if isinstance(getattr(item, "id", None), str)
    }
    restored: dict[str, AnalysisRun] = {}
    for entry in scan.entries:
        analysis = analyses.get(entry.analysis_id)
        if analysis is None:
            continue
        if (
            getattr(analysis, "kind", None) == entry.analysis_kind
            and analysis_run_matches_input(
                entry.run,
                entry.analysis_kind,
                getattr(analysis, "input", None),
            )
        ):
            restored[entry.analysis_id] = entry.run
    return restored, ()


def latest_matching_run(project: Any, analysis_id: str) -> AnalysisRun | None:
    cache, issues = restore_matching_run_cache(project)
    if issues:
        return None
    return cache.get(analysis_id)


def validated_run_history_document(project: Any) -> dict[str, Any] | None:
    """Return a deep-copied history document only when every integrity check passes."""
    metadata = getattr(project, "metadata", None)
    if not isinstance(metadata, dict):
        raise RunHistoryError("project metadata must be an object")
    data = metadata.get(RUN_HISTORY_METADATA_KEY)
    if data is None:
        return None
    scan = scan_run_history(project)
    if scan.issues:
        detail = "; ".join(f"{item.location}: {item.error}" for item in scan.issues)
        raise RunHistoryError("run history failed integrity validation: " + detail)
    return copy.deepcopy(data)
