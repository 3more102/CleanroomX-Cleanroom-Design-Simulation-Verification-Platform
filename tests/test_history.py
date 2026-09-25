from __future__ import annotations

import pytest

from cleanroomx.history import SnapshotHistory


def test_snapshot_history_is_bounded_isolated_and_invalidates_redo():
    history = SnapshotHistory[dict](limit=2)
    before = {"items": [{"value": 1}]}
    after = {"items": [{"value": 2}]}

    assert history.record(before=before, after=after, description="First edit") is True

    before["items"][0]["value"] = 99
    after["items"][0]["value"] = 88

    restored, description = history.undo()
    assert description == "First edit"
    assert restored == {"items": [{"value": 1}]}
    restored["items"][0]["value"] = 77

    replayed, description = history.redo()
    assert description == "First edit"
    assert replayed == {"items": [{"value": 2}]}

    assert history.undo() is not None
    assert history.record(
        before={"value": 1},
        after={"value": 3},
        description="Replacement edit",
    ) is True
    assert history.can_redo is False

    assert history.record(
        before={"value": 3},
        after={"value": 4},
        description="Third edit",
    ) is True
    assert history.record(
        before={"value": 4},
        after={"value": 5},
        description="Fourth edit",
    ) is True

    assert history.undo_description == "Fourth edit"
    assert history.undo() is not None
    oldest_retained, _ = history.undo()
    assert oldest_retained == {"value": 3}
    assert history.undo() is None


def test_snapshot_history_ignores_noop_and_validates_limit():
    history = SnapshotHistory[dict]()
    assert history.record(before={"value": 1}, after={"value": 1}, description="No op") is False
    assert history.can_undo is False

    for invalid in (0, -1, True, 1.5):
        with pytest.raises((TypeError, ValueError)):
            SnapshotHistory(limit=invalid)


def test_snapshot_history_soft_weight_budget_keeps_latest_reversible_edit():
    history = SnapshotHistory[str](
        limit=100,
        max_weight=12,
        measure=lambda value: len(value.encode("utf-8")),
    )

    for index in range(6):
        before = f"b{index:02d}"
        after = f"a{index:02d}"
        assert history.record(
            before=before,
            after=after,
            description=f"Edit {index}",
        ) is True

    assert history.approximate_weight is not None
    assert history.approximate_weight <= 12
    restored, description = history.undo()
    assert description == "Edit 5"
    assert restored == "b05"


def test_snapshot_history_weight_configuration_is_explicit():
    with pytest.raises(ValueError, match="configured together"):
        SnapshotHistory[str](max_weight=10)
    with pytest.raises(ValueError, match="configured together"):
        SnapshotHistory[str](measure=len)
    with pytest.raises(ValueError, match="max_weight"):
        SnapshotHistory[str](max_weight=0, measure=len)
