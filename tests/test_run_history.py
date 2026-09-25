from __future__ import annotations

import json
from pathlib import Path

import pytest

from cleanroomx.application import AnalysisRun, run_analysis
from cleanroomx.run_history import AnalysisRunHistory, RunHistoryIntegrityError


ROOT = Path(__file__).resolve().parents[1]


def _room_run():
    payload = json.loads(
        (ROOT / "examples" / "basic_room.json").read_text(encoding="utf-8")
    )
    return payload, run_analysis("room_verification", payload)


def test_run_history_preserves_immutable_bundle_snapshot():
    _payload, run = _room_run()
    history = AnalysisRunHistory(max_entries_per_analysis=4, max_total_bytes=2_000_000)

    entry = history.record("room-a", run)
    assert entry is not None
    assert entry.input_sha256 == run.diagnostics[
        "application_execution_provenance"
    ]["input_sha256"]

    run.result["_history_mutation_probe"] = "changed after record"
    restored = history.load(entry.sequence)

    assert "_history_mutation_probe" not in restored.result
    assert restored.kind == "room_verification"
    assert restored.to_dict() != run.to_dict()


def test_run_history_is_newest_first_and_bounded_per_analysis():
    _payload, run = _room_run()
    history = AnalysisRunHistory(max_entries_per_analysis=2, max_total_bytes=2_000_000)

    first = history.record("room-a", run)
    second = history.record("room-a", run)
    third = history.record("room-a", run)

    assert first is not None and second is not None and third is not None
    entries = history.entries_for("room-a")
    assert [item.sequence for item in entries] == [third.sequence, second.sequence]
    with pytest.raises(KeyError):
        history.load(first.sequence)


def test_run_history_evicts_oldest_globally_to_respect_byte_budget():
    _payload, run = _room_run()
    probe = AnalysisRunHistory(max_entries_per_analysis=8, max_total_bytes=2_000_000)
    sample = probe.record("probe", run)
    assert sample is not None

    budget = sample.size_bytes * 2 + 8
    history = AnalysisRunHistory(max_entries_per_analysis=8, max_total_bytes=budget)
    first = history.record("a", run)
    second = history.record("b", run)
    third = history.record("c", run)

    assert first is not None and second is not None and third is not None
    assert history.total_bytes <= budget
    with pytest.raises(KeyError):
        history.load(first.sequence)
    assert history.load(second.sequence).kind == run.kind
    assert history.load(third.sequence).kind == run.kind


def test_run_history_skips_single_bundle_larger_than_total_budget():
    _payload, run = _room_run()
    history = AnalysisRunHistory(max_entries_per_analysis=2, max_total_bytes=1)

    assert history.record("room-a", run) is None
    assert len(history) == 0
    assert history.total_bytes == 0


def test_run_history_fails_closed_without_execution_provenance():
    _payload, run = _room_run()
    history = AnalysisRunHistory()
    untraceable = AnalysisRun(
        kind=run.kind,
        title=run.title,
        status=run.status,
        result=run.result,
        markdown=run.markdown,
        diagnostics={},
        plot=run.plot,
    )

    with pytest.raises(RunHistoryIntegrityError, match="execution provenance"):
        history.record("room-a", untraceable)


def test_clear_analysis_does_not_remove_other_analysis_history():
    _payload, run = _room_run()
    history = AnalysisRunHistory(max_entries_per_analysis=4, max_total_bytes=2_000_000)
    a = history.record("a", run)
    b = history.record("b", run)
    assert a is not None and b is not None

    history.clear_analysis("a")

    assert history.entries_for("a") == ()
    assert [entry.sequence for entry in history.entries_for("b")] == [b.sequence]
    assert history.load(b.sequence).to_dict() == run.to_dict()


def test_run_history_constructor_rejects_unbounded_invalid_limits():
    with pytest.raises(ValueError, match="max_entries_per_analysis"):
        AnalysisRunHistory(max_entries_per_analysis=0)
    with pytest.raises(ValueError, match="max_total_bytes"):
        AnalysisRunHistory(max_total_bytes=0)
