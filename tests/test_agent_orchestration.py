from __future__ import annotations

import copy

import pytest

import cleanroomx.agent_orchestration as orchestration
from cleanroomx.agent_orchestration import (
    AGENT_ORCHESTRATION_METADATA_KEY,
    AgentPlanError,
    load_agent_plan,
    run_project_agents,
)
from cleanroomx.project import AnalysisDocument, ProjectDocument, save_project_document


class _FakeRun:
    def __init__(self, document):
        self._document = copy.deepcopy(document)

    def to_dict(self):
        return copy.deepcopy(self._document)


def _project(metadata):
    return ProjectDocument(
        name="Agent demo",
        analyses=[
            AnalysisDocument(
                id="requirements",
                name="Requirements",
                kind="requirements-kind",
                input={"seed": 1},
            ),
            AnalysisDocument(
                id="design",
                name="Design",
                kind="design-kind",
                input={"design": {"flow": 0}},
            ),
            AnalysisDocument(
                id="review",
                name="Review",
                kind="review-kind",
                input={"review": True},
            ),
        ],
        metadata={AGENT_ORCHESTRATION_METADATA_KEY: metadata},
    )


def test_agent_plan_topologically_orders_declared_dag_deterministically():
    project = _project(
        {
            "schema_version": 1,
            "agents": [
                {"id": "design-agent", "analysis_id": "design", "depends_on": ["requirements-agent"]},
                {"id": "review-agent", "analysis_id": "review"},
                {"id": "requirements-agent", "analysis_id": "requirements"},
            ],
        }
    )

    plan = load_agent_plan(project)

    assert plan.execution_order == (
        "review-agent",
        "requirements-agent",
        "design-agent",
    )
    assert len(plan.sha256) == 64


def test_agent_plan_rejects_dependency_cycle():
    project = _project(
        {
            "schema_version": 1,
            "agents": [
                {"id": "a", "analysis_id": "requirements", "depends_on": ["b"]},
                {"id": "b", "analysis_id": "design", "depends_on": ["a"]},
            ],
        }
    )

    with pytest.raises(AgentPlanError, match="dependency cycle"):
        load_agent_plan(project)


def test_agent_plan_requires_handoff_source_to_be_explicit_dependency():
    project = _project(
        {
            "schema_version": 1,
            "agents": [
                {"id": "requirements-agent", "analysis_id": "requirements"},
                {
                    "id": "design-agent",
                    "analysis_id": "design",
                    "handoffs": [
                        {
                            "source_agent": "requirements-agent",
                            "source_path": ["result", "flow"],
                            "target_path": ["design", "flow"],
                        }
                    ],
                },
            ],
        }
    )

    with pytest.raises(AgentPlanError, match="must also appear in depends_on"):
        load_agent_plan(project)


def test_project_agents_apply_explicit_handoff_and_record_hashes(tmp_path, monkeypatch):
    path = save_project_document(
        tmp_path / "agents.cleanroomx.json",
        _project(
            {
                "schema_version": 1,
                "agents": [
                    {"id": "requirements-agent", "analysis_id": "requirements"},
                    {
                        "id": "design-agent",
                        "analysis_id": "design",
                        "depends_on": ["requirements-agent"],
                        "handoffs": [
                            {
                                "source_agent": "requirements-agent",
                                "source_path": ["result", "flow"],
                                "target_path": ["design", "flow"],
                            }
                        ],
                    },
                ],
            }
        ),
    )
    calls = []

    def fake_run(kind, payload, *, base_dir=None, project_source_revision=None):
        calls.append((kind, copy.deepcopy(payload), project_source_revision))
        if kind == "requirements-kind":
            return _FakeRun(
                {
                    "result": {"flow": 1250.0},
                    "integrity": {"sha256": "a" * 64},
                }
            )
        assert payload["design"]["flow"] == 1250.0
        return _FakeRun(
            {
                "result": {"accepted_flow": payload["design"]["flow"]},
                "integrity": {"sha256": "b" * 64},
            }
        )

    monkeypatch.setattr(orchestration, "run_analysis", fake_run)

    run = run_project_agents(path)

    assert run.status == "completed"
    assert run.completed_count == 2
    assert [call[0] for call in calls] == ["requirements-kind", "design-kind"]
    assert all(call[2] == run.source_sha256 for call in calls)
    handoff = run.outcomes[1].applied_handoffs[0]
    assert handoff.source_run_sha256 == "a" * 64
    assert len(handoff.value_sha256) == 64
    assert run.outcomes[1].run["result"]["accepted_flow"] == 1250.0


def test_continue_on_error_blocks_dependents_but_runs_independent_agents(
    tmp_path, monkeypatch
):
    path = save_project_document(
        tmp_path / "agents.cleanroomx.json",
        _project(
            {
                "schema_version": 1,
                "agents": [
                    {"id": "requirements-agent", "analysis_id": "requirements"},
                    {
                        "id": "design-agent",
                        "analysis_id": "design",
                        "depends_on": ["requirements-agent"],
                    },
                    {"id": "review-agent", "analysis_id": "review"},
                ],
            }
        ),
    )
    calls = []

    def fake_run(kind, payload, *, base_dir=None, project_source_revision=None):
        calls.append(kind)
        if kind == "requirements-kind":
            raise RuntimeError("requirements failed")
        return _FakeRun(
            {
                "result": {"kind": kind},
                "integrity": {"sha256": "c" * 64},
            }
        )

    monkeypatch.setattr(orchestration, "run_analysis", fake_run)

    run = run_project_agents(path, fail_fast=False)

    states = {item.agent_id: item.execution_state for item in run.outcomes}
    assert states == {
        "requirements-agent": "error",
        "design-agent": "blocked",
        "review-agent": "completed",
    }
    assert calls == ["requirements-kind", "review-kind"]
    assert run.error_count == 1
    assert run.blocked_count == 1


def test_fail_fast_stops_after_first_agent_error(tmp_path, monkeypatch):
    path = save_project_document(
        tmp_path / "agents.cleanroomx.json",
        _project(
            {
                "schema_version": 1,
                "agents": [
                    {"id": "requirements-agent", "analysis_id": "requirements"},
                    {"id": "review-agent", "analysis_id": "review"},
                ],
            }
        ),
    )

    def fail_run(kind, payload, *, base_dir=None, project_source_revision=None):
        raise RuntimeError("stop")

    monkeypatch.setattr(orchestration, "run_analysis", fail_run)

    run = run_project_agents(path, fail_fast=True)

    assert len(run.outcomes) == 1
    assert run.outcomes[0].execution_state == "error"
    assert run.status == "error"
