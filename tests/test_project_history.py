from __future__ import annotations

from cleanroomx.project_history import ProjectEditHistory, ProjectEditState


def _state(value: int, *, selected: str | None = "a", editor_text: str = "{}"):
    return ProjectEditState(
        analyses=[
            {
                "id": "a",
                "name": "A",
                "kind": "room_verification",
                "input": {"value": value},
            }
        ],
        active_analysis_id=selected,
        editor_analysis_id=selected,
        editor_text=editor_text,
    )


def test_project_edit_history_round_trip_is_bounded_and_snapshot_isolated():
    history = ProjectEditHistory(limit=2)
    before = _state(1)
    after = _state(2)

    assert history.record(before=before, after=after, description="Edit input") is True
    before.analyses[0]["input"]["value"] = 99
    after.analyses[0]["input"]["value"] = 88

    restored, description = history.undo()
    assert description == "Edit input"
    assert restored.analyses[0]["input"]["value"] == 1
    assert history.can_redo is True

    restored, description = history.redo()
    assert description == "Edit input"
    assert restored.analyses[0]["input"]["value"] == 2

    assert history.record(before=_state(2), after=_state(3), description="Three")
    assert history.record(before=_state(3), after=_state(4), description="Four")
    assert history.record(before=_state(4), after=_state(5), description="Five")
    assert history.undo_description == "Five"
    history.undo()
    assert history.undo_description == "Four"
    history.undo()
    assert history.can_undo is False


def test_project_edit_history_ignores_selection_only_changes():
    history = ProjectEditHistory()
    before = _state(1, selected="a", editor_text='{"draft": 1}')
    after = _state(1, selected=None, editor_text='{"draft": 2}')

    assert history.record(before=before, after=after, description="Selection") is False
    assert history.can_undo is False
    assert history.can_redo is False


def test_project_edit_history_new_edit_invalidates_redo():
    history = ProjectEditHistory()
    assert history.record(before=_state(1), after=_state(2), description="First")
    assert history.undo() is not None
    assert history.can_redo is True

    assert history.record(before=_state(1), after=_state(3), description="Divergent")
    assert history.can_redo is False
    assert history.undo_description == "Divergent"


def test_project_edit_history_rejects_invalid_limit():
    for value in (0, -1, True, 1.5):
        try:
            ProjectEditHistory(limit=value)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected invalid history limit: {value!r}")
