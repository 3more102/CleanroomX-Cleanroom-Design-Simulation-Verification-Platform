from __future__ import annotations

import copy

from cleanroomx.multi_agent import ChatSessionStore, MultiAgentCoordinator
import cleanroomx.multi_agent_project as project_agent
from cleanroomx.multi_agent_project import register_project_analysis_agent
from cleanroomx.project import AnalysisDocument, ProjectDocument, save_project_document


class _FakeRun:
    status = "pass"

    def __init__(self, payload):
        self._payload = copy.deepcopy(payload)

    def to_dict(self):
        return copy.deepcopy(self._payload)


def _save_project(tmp_path):
    path = tmp_path / "agent-project.cleanroomx.json"
    save_project_document(
        path,
        ProjectDocument(
            name="Agent project",
            analyses=[
                AnalysisDocument(
                    id="airflow",
                    name="Airflow",
                    kind="air_system_design",
                    input={"design": {"airflow_m3_h": 1200}},
                )
            ],
        ),
    )
    return path


def test_project_analysis_agent_uses_canonical_application_boundary(
    tmp_path,
    monkeypatch,
):
    path = _save_project(tmp_path)
    calls = []

    def fake_run(kind, payload, *, base_dir=None, project_source_revision=None):
        calls.append(
            {
                "kind": kind,
                "payload": copy.deepcopy(payload),
                "base_dir": base_dir,
                "project_source_revision": project_source_revision,
            }
        )
        return _FakeRun(
            {
                "schema": "cleanroomx.analysis-run",
                "status": "pass",
                "integrity": {"sha256": "a" * 64},
            }
        )

    monkeypatch.setattr(project_agent, "run_analysis", fake_run)

    store = ChatSessionStore()
    store.create_session("chat", "Canonical bridge")
    coordinator = MultiAgentCoordinator(store)
    spec = register_project_analysis_agent(
        coordinator,
        "airflow-agent",
        project_path=path,
        analysis_id="airflow",
    )

    batch = coordinator.run(
        "chat",
        "run the stored airflow analysis",
        agent_ids=["airflow-agent"],
        task_id="task-project-analysis",
    )

    assert spec.capabilities == (
        "cleanroomx.project-analysis",
        "engineering-analysis",
    )
    assert batch.commit_state == "committed"
    assert batch.error_count == 0
    assert len(calls) == 1
    assert calls[0]["kind"] == "air_system_design"
    assert calls[0]["payload"] == {"design": {"airflow_m3_h": 1200}}
    assert calls[0]["base_dir"] == path.parent.resolve()
    assert len(calls[0]["project_source_revision"]) == 64

    execution = batch.results[0]
    assert execution.state == "completed"
    assert execution.data["schema"] == "cleanroomx.multi-agent-project-analysis"
    assert execution.data["analysis"]["id"] == "airflow"
    assert (
        execution.data["project"]["source_revision"]["sha256"]
        == calls[0]["project_source_revision"]
    )
    assert execution.data["run"]["integrity"]["sha256"] == "a" * 64


def test_project_analysis_agent_rejects_source_change_during_solver(
    tmp_path,
    monkeypatch,
):
    path = _save_project(tmp_path)

    def fake_run(kind, payload, *, base_dir=None, project_source_revision=None):
        raw = path.read_text(encoding="utf-8")
        path.write_text(raw + " ", encoding="utf-8")
        return _FakeRun(
            {
                "schema": "cleanroomx.analysis-run",
                "status": "pass",
                "integrity": {"sha256": "b" * 64},
            }
        )

    monkeypatch.setattr(project_agent, "run_analysis", fake_run)

    store = ChatSessionStore()
    store.create_session("chat", "Drift")
    coordinator = MultiAgentCoordinator(store)
    register_project_analysis_agent(
        coordinator,
        "airflow-agent",
        project_path=path,
        analysis_id="airflow",
    )

    batch = coordinator.run(
        "chat",
        "run",
        agent_ids=["airflow-agent"],
        task_id="task-drift",
    )

    execution = batch.results[0]
    assert execution.state == "error"
    assert execution.error_type == "ProjectAgentSourceChangedError"
    assert "changed during canonical analysis" in execution.error_message


def test_project_analysis_agent_rejects_unknown_analysis_before_solver(
    tmp_path,
    monkeypatch,
):
    path = _save_project(tmp_path)
    called = False

    def fake_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("solver must not run")

    monkeypatch.setattr(project_agent, "run_analysis", fake_run)

    store = ChatSessionStore()
    store.create_session("chat", "Unknown")
    coordinator = MultiAgentCoordinator(store)
    register_project_analysis_agent(
        coordinator,
        "missing-agent",
        project_path=path,
        analysis_id="missing",
    )

    batch = coordinator.run(
        "chat",
        "run",
        agent_ids=["missing-agent"],
        task_id="task-missing",
    )

    assert called is False
    assert batch.results[0].state == "error"
    assert batch.results[0].error_type == "ValueError"
    assert "unknown project analysis id" in batch.results[0].error_message


def test_project_analysis_agent_copies_persisted_input_before_solver(
    tmp_path,
    monkeypatch,
):
    path = _save_project(tmp_path)

    def fake_run(kind, payload, *, base_dir=None, project_source_revision=None):
        payload["design"]["airflow_m3_h"] = 9999
        return _FakeRun(
            {
                "schema": "cleanroomx.analysis-run",
                "status": "pass",
                "integrity": {"sha256": "c" * 64},
            }
        )

    monkeypatch.setattr(project_agent, "run_analysis", fake_run)

    store = ChatSessionStore()
    store.create_session("chat", "Input isolation")
    coordinator = MultiAgentCoordinator(store)
    register_project_analysis_agent(
        coordinator,
        "airflow-agent",
        project_path=path,
        analysis_id="airflow",
    )
    batch = coordinator.run(
        "chat",
        "run",
        agent_ids=["airflow-agent"],
        task_id="task-copy",
    )

    assert batch.results[0].state == "completed"

    project, _revision = project_agent.load_project_document_with_revision(path)
    assert project.analyses[0].input == {"design": {"airflow_m3_h": 1200}}
