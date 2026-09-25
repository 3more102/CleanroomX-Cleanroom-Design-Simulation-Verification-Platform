from __future__ import annotations

import json
from pathlib import Path

import pytest

import cleanroomx.gui as gui_module
from cleanroomx.application import run_analysis
from cleanroomx.gui import CleanroomXApp
from cleanroomx.project import AnalysisDocument
from cleanroomx.run_history import RunHistory


ROOT = Path(__file__).resolve().parents[1]


def _room_payload():
    return json.loads(
        (ROOT / "examples" / "basic_room.json").read_text(encoding="utf-8")
    )


def _room_run():
    return run_analysis("room_verification", _room_payload())


def test_run_history_is_bounded_and_sequences_are_deterministic():
    run = _room_run()
    history = RunHistory(limit=2)

    history.append("a", "Room A", run)
    second = history.append("a", "Room A", run)
    third = history.append("b", "Room B", run)

    assert [entry.sequence for entry in history.entries()] == [
        second.sequence,
        third.sequence,
    ]
    assert [entry.analysis_id for entry in history.entries("a")] == ["a"]

    history.clear()
    assert len(history) == 0
    assert history.append("a", "Room A", run).sequence == 1


def test_run_history_detaches_nested_run_data_on_ingress_and_egress():
    run = _room_run()
    history = RunHistory()
    retained = history.append("analysis-1", "Room", run)

    run.result["caller_mutation"] = True
    assert "caller_mutation" not in history.get(retained.sequence).run.result

    exported = history.get(retained.sequence)
    exported.run.result["egress_mutation"] = True
    assert "egress_mutation" not in history.get(retained.sequence).run.result

    assert retained.input_sha256 is not None
    assert history.get(retained.sequence).input_sha256 == retained.input_sha256


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_run_history_rejects_invalid_limits(limit):
    with pytest.raises(ValueError, match="positive integer"):
        RunHistory(limit=limit)


def test_run_history_rejects_invalid_entry_ownership():
    history = RunHistory()
    run = _room_run()

    with pytest.raises(ValueError, match="analysis_id"):
        history.append("", "Room", run)
    with pytest.raises(ValueError, match="analysis_name"):
        history.append("a", "   ", run)
    with pytest.raises(TypeError, match="AnalysisRun"):
        history.append("a", "Room", object())


def test_run_history_lightweight_summary_and_input_match_do_not_expose_payload():
    payload = _room_payload()
    run = run_analysis("room_verification", payload)
    history = RunHistory()
    summary = history.append("a", "Room", run)

    assert not hasattr(summary, "run")
    assert summary.input_sha256
    reordered = dict(reversed(list(payload.items())))
    assert history.matches_input(summary.sequence, "room_verification", reordered) is True

    changed = dict(payload)
    changed["_history_probe"] = True
    assert history.matches_input(summary.sequence, "room_verification", changed) is False


def test_run_history_pruning_makes_evicted_sequence_unavailable():
    run = _room_run()
    history = RunHistory(limit=1)
    first = history.append("a", "Room", run)
    second = history.append("a", "Room", run)

    assert second.sequence > first.sequence
    with pytest.raises(KeyError):
        history.get(first.sequence)


def test_gui_records_each_accepted_run_without_replacing_history():
    run = _room_run()
    app = CleanroomXApp.__new__(CleanroomXApp)
    app._runs_by_analysis = {}
    app.last_run = None
    app.last_run_analysis_id = None
    app._run_history = RunHistory(limit=5)
    app._refresh_run_history = lambda: None
    analysis = AnalysisDocument(
        id="analysis-1",
        name="Room verification",
        kind="room_verification",
        input={},
    )

    app._record_completed_run(analysis, run)
    app._record_completed_run(analysis, run)

    assert app._runs_by_analysis["analysis-1"] is run
    assert app.last_run is run
    assert app.last_run_analysis_id == "analysis-1"
    entries = app._run_history.entries()
    assert [entry.sequence for entry in entries] == [1, 2]
    assert all(entry.analysis_id == "analysis-1" for entry in entries)


def test_gui_project_run_state_reset_clears_current_and_historical_runs():
    run = _room_run()
    app = CleanroomXApp.__new__(CleanroomXApp)
    app._runs_by_analysis = {"analysis-1": run}
    app.last_run = run
    app.last_run_analysis_id = "analysis-1"
    app._run_history = RunHistory()
    app._run_history.append("analysis-1", "Room", run)
    app._clear_rendered_run = lambda: None
    app._refresh_run_history = lambda: None

    app._clear_run_cache()

    assert app._runs_by_analysis == {}
    assert len(app._run_history) == 0


def test_historical_run_export_uses_retained_snapshot_without_current_freshness(
    tmp_path, monkeypatch
):
    run = _room_run()
    history = RunHistory()
    entry = history.append("analysis-1", "Room", run)
    run.result["mutated_after_history"] = True

    class Tree:
        def selection(self):
            return (f"run-{entry.sequence}",)

    app = CleanroomXApp.__new__(CleanroomXApp)
    app._run_history = history
    app.history_tree = Tree()
    app.root = object()

    destination = tmp_path / "historical-run.json"
    monkeypatch.setattr(
        gui_module.filedialog,
        "asksaveasfilename",
        lambda **kwargs: str(destination),
    )
    written = {}

    def capture(path, content, *, label):
        written["path"] = path
        written["content"] = content
        written["label"] = label
        return True

    app._write_export_file = capture

    app.export_history_run_bundle_json()

    payload = json.loads(written["content"])
    assert written["path"] == str(destination)
    assert written["label"] == "Historical run bundle"
    assert "mutated_after_history" not in payload["result"]
    assert payload == history.get(entry.sequence).run.to_dict()
