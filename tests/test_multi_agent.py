from __future__ import annotations

import copy
import threading
import time

import pytest

from cleanroomx.multi_agent import (
    AgentPlan,
    AgentSpec,
    AgentTask,
    FunctionAgent,
    MultiAgentError,
    MultiAgentOrchestrator,
    agent_plan_from_dict,
    verify_multi_agent_run,
)


def _agent(name, function, *capabilities):
    return FunctionAgent(
        spec=AgentSpec(
            name=name,
            capabilities=tuple(capabilities),
            authority="orchestration",
        ),
        function=function,
    )


def test_multi_agent_executes_dependency_dag_and_preserves_plan_order():
    observed = []

    def first(task, _context):
        observed.append(task.id)
        return {"value": 2}

    def second(task, context):
        observed.append(task.id)
        return {"value": context.dependency_output("first")["value"] + 3}

    plan = AgentPlan(
        id="demo",
        tasks=(
            AgentTask(id="first", agent="producer"),
            AgentTask(
                id="second",
                agent="consumer",
                depends_on=("first",),
            ),
        ),
    )
    orchestrator = MultiAgentOrchestrator(
        (
            _agent("producer", first, "produce"),
            _agent("consumer", second, "consume"),
        )
    )

    run = orchestrator.execute(plan, max_workers=2)

    assert observed == ["first", "second"]
    assert run["status"] == "success"
    assert [item["task_id"] for item in run["results"]] == ["first", "second"]
    assert run["results"][1]["output"] == {"value": 5}
    assert verify_multi_agent_run(run)["verified"] is True


def test_multi_agent_runs_independent_tasks_concurrently_but_serializes_output_order():
    started = set()
    barrier = threading.Barrier(2)

    def worker(task, _context):
        started.add(task.id)
        barrier.wait(timeout=2)
        time.sleep(0.01)
        return {"task": task.id}

    plan = AgentPlan(
        id="parallel",
        tasks=(
            AgentTask(id="a", agent="worker"),
            AgentTask(id="b", agent="worker"),
        ),
    )

    run = MultiAgentOrchestrator(
        (_agent("worker", worker, "work"),)
    ).execute(plan, max_workers=2)

    assert started == {"a", "b"}
    assert [item["task_id"] for item in run["results"]] == ["a", "b"]
    assert run["status"] == "success"


def test_multi_agent_blocks_downstream_task_after_dependency_failure():
    executed = []

    def fail(_task, _context):
        raise ValueError("boom")

    def downstream(task, _context):
        executed.append(task.id)
        return {"unexpected": True}

    plan = AgentPlan(
        id="failure",
        tasks=(
            AgentTask(id="bad", agent="failing"),
            AgentTask(
                id="after",
                agent="downstream",
                depends_on=("bad",),
            ),
        ),
    )

    run = MultiAgentOrchestrator(
        (
            _agent("failing", fail, "work"),
            _agent("downstream", downstream, "work"),
        )
    ).execute(plan)

    assert executed == []
    assert run["status"] == "failed"
    assert run["results"][0]["status"] == "failed"
    assert run["results"][1]["status"] == "blocked"
    assert run["results"][1]["error"]["type"] == "DependencyBlocked"
    assert verify_multi_agent_run(run)["status"] == "failed"


def test_multi_agent_rejects_dependency_cycle():
    with pytest.raises(MultiAgentError, match="dependency cycle"):
        AgentPlan(
            id="cycle",
            tasks=(
                AgentTask(id="a", agent="x", depends_on=("b",)),
                AgentTask(id="b", agent="x", depends_on=("a",)),
            ),
        )


def test_multi_agent_rejects_unregistered_agent():
    plan = AgentPlan(
        id="unknown-agent",
        tasks=(AgentTask(id="a", agent="missing"),),
    )

    with pytest.raises(MultiAgentError, match="unregistered agent"):
        MultiAgentOrchestrator(()).execute(plan)


def test_multi_agent_enforces_declared_capabilities():
    plan = AgentPlan(
        id="capability",
        tasks=(
            AgentTask(
                id="verify",
                agent="worker",
                required_capabilities=("verification",),
            ),
        ),
    )

    with pytest.raises(MultiAgentError, match="lacks required capability"):
        MultiAgentOrchestrator(
            (_agent("worker", lambda _task, _context: {}, "analysis"),)
        ).execute(plan)


def test_multi_agent_rejects_non_strict_json_agent_output():
    plan = AgentPlan(
        id="strict-json",
        tasks=(AgentTask(id="bad-json", agent="worker"),),
    )
    run = MultiAgentOrchestrator(
        (
            _agent(
                "worker",
                lambda _task, _context: {"value": float("nan")},
                "work",
            ),
        )
    ).execute(plan)

    assert run["status"] == "failed"
    assert run["results"][0]["status"] == "failed"
    assert run["results"][0]["error"]["type"] == "MultiAgentError"


def test_multi_agent_verifier_rejects_tampered_task_output():
    plan = AgentPlan(
        id="tamper",
        tasks=(AgentTask(id="one", agent="worker"),),
    )
    run = MultiAgentOrchestrator(
        (_agent("worker", lambda _task, _context: {"value": 1}, "work"),)
    ).execute(plan)
    tampered = copy.deepcopy(run)
    tampered["results"][0]["output"]["value"] = 99

    with pytest.raises(MultiAgentError, match="result digest mismatch"):
        verify_multi_agent_run(tampered)


def test_agent_plan_from_dict_preserves_explicit_routing_and_dependencies():
    plan = agent_plan_from_dict(
        {
            "id": "parsed",
            "tasks": [
                {
                    "id": "diagnostics",
                    "agent": "project-diagnostics",
                    "payload": {"project_path": "demo.cleanroomx.json"},
                    "required_capabilities": ["diagnostics"],
                },
                {
                    "id": "verify",
                    "agent": "project-requirements",
                    "payload": {
                        "project_path": "demo.cleanroomx.json",
                        "analysis_id": "room-a",
                    },
                    "depends_on": ["diagnostics"],
                    "required_capabilities": ["verification", "proofgraph"],
                },
            ],
        }
    )

    assert plan.id == "parsed"
    assert plan.tasks[1].depends_on == ("diagnostics",)
    assert plan.tasks[1].required_capabilities == ("verification", "proofgraph")
    assert len(plan.sha256) == 64
