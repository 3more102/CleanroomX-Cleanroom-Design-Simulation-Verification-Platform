import pytest

from cleanroomx.gui_tasks import EngineeringTask, normalized_task_state, task_state_label


def test_task_state_normalization_uses_explicit_terminal_semantics():
    assert normalized_task_state("success") == "completed"
    assert normalized_task_state("ERROR") == "failed"
    assert normalized_task_state("cancelled") == "abandoned"
    assert normalized_task_state("abandon requested") == "abandon_requested"
    assert task_state_label("completed_with_warning") == "COMPLETED · WARNING"


def test_engineering_task_terminal_states_are_distinct():
    running = EngineeringTask(
        task_id="1",
        name="ACH Study",
        category="Analysis",
        state="running",
        stage="Solving",
        started_at="10:00:00",
    )
    completed = EngineeringTask(
        task_id="2",
        name="Pressure",
        category="Analysis",
        state="completed",
        stage="Finished",
        started_at="10:00:00",
        elapsed_s=2.5,
    )
    discarded = EngineeringTask(
        task_id="3",
        name="Airflow",
        category="Analysis",
        state="discarded",
        stage="Result discarded",
        started_at="10:00:00",
    )

    assert running.terminal is False
    assert completed.terminal is True
    assert discarded.terminal is True
