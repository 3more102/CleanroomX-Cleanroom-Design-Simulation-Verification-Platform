from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence


MULTI_AGENT_SCHEMA = "cleanroomx.multi-agent-run"
MULTI_AGENT_SCHEMA_VERSION = 1

AGENT_TASK_STATUSES = frozenset({"success", "failed", "blocked"})


class MultiAgentError(RuntimeError):
    """Raised when a multi-agent plan or run cannot be trusted."""


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
        raise MultiAgentError(f"value is not strict JSON: {exc}") from exc


def _strict_json_clone(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _nonempty(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MultiAgentError(f"{name} must be a non-empty string")
    return value


def _string_tuple(values: Sequence[str], name: str) -> tuple[str, ...]:
    normalized = tuple(values)
    if any(not isinstance(value, str) or not value.strip() for value in normalized):
        raise MultiAgentError(f"{name} must contain non-empty strings")
    if len(set(normalized)) != len(normalized):
        raise MultiAgentError(f"{name} must not contain duplicates")
    return normalized


@dataclass(frozen=True, kw_only=True)
class AgentSpec:
    """Static identity and authority boundary for one agent implementation."""

    name: str
    capabilities: tuple[str, ...]
    description: str = ""
    authority: str = "advisory"

    def __post_init__(self) -> None:
        _nonempty(self.name, "agent_spec.name")
        object.__setattr__(
            self,
            "capabilities",
            _string_tuple(self.capabilities, "agent_spec.capabilities"),
        )
        if self.authority not in {"advisory", "orchestration", "canonical-service"}:
            raise MultiAgentError(
                "agent_spec.authority must be advisory, orchestration, or canonical-service"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "capabilities": list(self.capabilities),
            "description": self.description,
            "authority": self.authority,
        }


@dataclass(frozen=True, kw_only=True)
class AgentTask:
    """One explicit unit of work routed to a named agent."""

    id: str
    agent: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    depends_on: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _nonempty(self.id, "agent_task.id")
        _nonempty(self.agent, "agent_task.agent")
        object.__setattr__(self, "payload", _strict_json_clone(dict(self.payload)))
        object.__setattr__(
            self,
            "depends_on",
            _string_tuple(self.depends_on, "agent_task.depends_on"),
        )
        object.__setattr__(
            self,
            "required_capabilities",
            _string_tuple(
                self.required_capabilities,
                "agent_task.required_capabilities",
            ),
        )
        if self.id in self.depends_on:
            raise MultiAgentError(f"task {self.id!r} cannot depend on itself")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent": self.agent,
            "payload": _strict_json_clone(self.payload),
            "depends_on": list(self.depends_on),
            "required_capabilities": list(self.required_capabilities),
        }


@dataclass(frozen=True, kw_only=True)
class AgentPlan:
    """Deterministic task DAG. Routing is explicit rather than guessed at runtime."""

    id: str
    tasks: tuple[AgentTask, ...]

    def __post_init__(self) -> None:
        _nonempty(self.id, "agent_plan.id")
        object.__setattr__(self, "tasks", tuple(self.tasks))
        task_ids = [task.id for task in self.tasks]
        if len(set(task_ids)) != len(task_ids):
            raise MultiAgentError("agent_plan.tasks contains duplicate task ids")

        task_id_set = set(task_ids)
        for task in self.tasks:
            unknown = set(task.depends_on) - task_id_set
            if unknown:
                names = ", ".join(sorted(unknown))
                raise MultiAgentError(
                    f"task {task.id!r} depends on unknown task(s): {names}"
                )

        _topological_waves(self.tasks)

    @property
    def sha256(self) -> str:
        return _sha256(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tasks": [task.to_dict() for task in self.tasks],
        }


@dataclass(frozen=True, kw_only=True)
class AgentContext:
    """Immutable-by-contract dependency view supplied to one agent."""

    plan_id: str
    task_id: str
    dependency_results: Mapping[str, Any]
    source_revision: str | None = None

    def dependency_output(self, task_id: str) -> Any:
        try:
            value = self.dependency_results[task_id]
        except KeyError as exc:
            raise MultiAgentError(
                f"dependency result {task_id!r} is not available to task {self.task_id!r}"
            ) from exc
        return _strict_json_clone(value)


class Agent(Protocol):
    spec: AgentSpec

    def run(self, task: AgentTask, context: AgentContext) -> Mapping[str, Any]:
        ...


AgentFunction = Callable[[AgentTask, AgentContext], Mapping[str, Any]]


@dataclass(frozen=True)
class FunctionAgent:
    """Adapter that turns an existing deterministic service into an agent."""

    spec: AgentSpec
    function: AgentFunction

    def run(self, task: AgentTask, context: AgentContext) -> Mapping[str, Any]:
        return self.function(task, context)


def _topological_waves(tasks: Sequence[AgentTask]) -> tuple[tuple[AgentTask, ...], ...]:
    by_id = {task.id: task for task in tasks}
    order = {task.id: index for index, task in enumerate(tasks)}
    remaining = set(by_id)
    completed: set[str] = set()
    waves: list[tuple[AgentTask, ...]] = []

    while remaining:
        ready_ids = [
            task_id
            for task_id in remaining
            if set(by_id[task_id].depends_on) <= completed
        ]
        if not ready_ids:
            cycle = ", ".join(sorted(remaining))
            raise MultiAgentError(
                f"agent plan contains a dependency cycle involving: {cycle}"
            )
        ready_ids.sort(key=order.__getitem__)
        wave = tuple(by_id[task_id] for task_id in ready_ids)
        waves.append(wave)
        completed.update(ready_ids)
        remaining.difference_update(ready_ids)

    return tuple(waves)


def _task_result_identity(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "task_id": result["task_id"],
        "agent": result["agent"],
        "status": result["status"],
        "depends_on": result["depends_on"],
        "dependency_result_sha256": result["dependency_result_sha256"],
        "output": result["output"],
        "error": result["error"],
    }


def _seal_task_result(result: dict[str, Any]) -> dict[str, Any]:
    sealed = _strict_json_clone(result)
    sealed["result_sha256"] = _sha256(_task_result_identity(sealed))
    return sealed


class MultiAgentOrchestrator:
    """Dependency-aware, replayable coordinator for CleanroomX agent adapters."""

    def __init__(self, agents: Sequence[Agent]) -> None:
        registry: dict[str, Agent] = {}
        for agent in agents:
            name = agent.spec.name
            if name in registry:
                raise MultiAgentError(f"duplicate agent registration: {name!r}")
            registry[name] = agent
        self._agents = registry

    @property
    def agent_specs(self) -> tuple[AgentSpec, ...]:
        return tuple(self._agents[name].spec for name in sorted(self._agents))

    def execute(
        self,
        plan: AgentPlan,
        *,
        max_workers: int = 4,
        source_revision: str | None = None,
    ) -> dict[str, Any]:
        if (
            not isinstance(max_workers, int)
            or isinstance(max_workers, bool)
            or max_workers < 1
        ):
            raise MultiAgentError("max_workers must be an integer >= 1")
        if source_revision is not None:
            _nonempty(source_revision, "source_revision")

        for task in plan.tasks:
            agent = self._agents.get(task.agent)
            if agent is None:
                raise MultiAgentError(
                    f"task {task.id!r} references unregistered agent {task.agent!r}"
                )
            missing = set(task.required_capabilities) - set(agent.spec.capabilities)
            if missing:
                names = ", ".join(sorted(missing))
                raise MultiAgentError(
                    f"agent {task.agent!r} lacks required capability/capabilities: {names}"
                )

        results: dict[str, dict[str, Any]] = {}
        waves = _topological_waves(plan.tasks)

        for wave in waves:
            runnable: list[AgentTask] = []
            for task in wave:
                blocked_by = [
                    dependency
                    for dependency in task.depends_on
                    if results[dependency]["status"] != "success"
                ]
                if blocked_by:
                    dependency_hashes = {
                        dependency: results[dependency]["result_sha256"]
                        for dependency in task.depends_on
                    }
                    results[task.id] = _seal_task_result(
                        {
                            "task_id": task.id,
                            "agent": task.agent,
                            "status": "blocked",
                            "depends_on": list(task.depends_on),
                            "dependency_result_sha256": dependency_hashes,
                            "output": None,
                            "error": {
                                "type": "DependencyBlocked",
                                "message": (
                                    "blocked by unsuccessful dependency/dependencies: "
                                    + ", ".join(blocked_by)
                                ),
                            },
                        }
                    )
                else:
                    runnable.append(task)

            if not runnable:
                continue

            workers = min(max_workers, len(runnable))
            if workers == 1:
                for task in runnable:
                    results[task.id] = self._execute_task(
                        plan,
                        task,
                        results,
                        source_revision=source_revision,
                    )
                continue

            with ThreadPoolExecutor(
                max_workers=workers,
                thread_name_prefix="cleanroomx-agent",
            ) as executor:
                future_to_task = {
                    executor.submit(
                        self._execute_task,
                        plan,
                        task,
                        results,
                        source_revision=source_revision,
                    ): task
                    for task in runnable
                }
                for future in as_completed(future_to_task):
                    task = future_to_task[future]
                    results[task.id] = future.result()

        ordered_results = [results[task.id] for task in plan.tasks]
        status = (
            "success"
            if all(result["status"] == "success" for result in ordered_results)
            else "failed"
        )
        run = {
            "schema": MULTI_AGENT_SCHEMA,
            "schema_version": MULTI_AGENT_SCHEMA_VERSION,
            "plan": plan.to_dict(),
            "plan_sha256": plan.sha256,
            "source_revision": source_revision,
            "agents": [spec.to_dict() for spec in self.agent_specs],
            "results": ordered_results,
            "status": status,
        }
        run["run_sha256"] = _sha256(_run_identity(run))
        return _strict_json_clone(run)

    def _execute_task(
        self,
        plan: AgentPlan,
        task: AgentTask,
        results: Mapping[str, Mapping[str, Any]],
        *,
        source_revision: str | None,
    ) -> dict[str, Any]:
        dependency_outputs = {
            dependency: _strict_json_clone(results[dependency]["output"])
            for dependency in task.depends_on
        }
        dependency_hashes = {
            dependency: results[dependency]["result_sha256"]
            for dependency in task.depends_on
        }
        context = AgentContext(
            plan_id=plan.id,
            task_id=task.id,
            dependency_results=dependency_outputs,
            source_revision=source_revision,
        )
        agent = self._agents[task.agent]
        try:
            output = _strict_json_clone(dict(agent.run(task, context)))
        except Exception as exc:
            return _seal_task_result(
                {
                    "task_id": task.id,
                    "agent": task.agent,
                    "status": "failed",
                    "depends_on": list(task.depends_on),
                    "dependency_result_sha256": dependency_hashes,
                    "output": None,
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                }
            )

        return _seal_task_result(
            {
                "task_id": task.id,
                "agent": task.agent,
                "status": "success",
                "depends_on": list(task.depends_on),
                "dependency_result_sha256": dependency_hashes,
                "output": output,
                "error": None,
            }
        )


def _run_identity(run: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": run["schema"],
        "schema_version": run["schema_version"],
        "plan_sha256": run["plan_sha256"],
        "source_revision": run.get("source_revision"),
        "agents": run["agents"],
        "results": run["results"],
        "status": run["status"],
    }


def verify_multi_agent_run(run: Mapping[str, Any]) -> dict[str, Any]:
    """Verify orchestration integrity without re-running engineering services."""

    document = _strict_json_clone(dict(run))
    if document.get("schema") != MULTI_AGENT_SCHEMA:
        raise MultiAgentError("multi-agent run schema is invalid")
    if document.get("schema_version") != MULTI_AGENT_SCHEMA_VERSION:
        raise MultiAgentError("multi-agent run schema version is unsupported")

    raw_plan = document.get("plan")
    if not isinstance(raw_plan, dict):
        raise MultiAgentError("multi-agent run plan must be an object")
    raw_tasks = raw_plan.get("tasks")
    if not isinstance(raw_tasks, list):
        raise MultiAgentError("multi-agent run plan tasks must be an array")

    parsed_tasks: list[AgentTask] = []
    for item in raw_tasks:
        if not isinstance(item, dict):
            raise MultiAgentError("multi-agent run plan tasks must contain objects")
        parsed_tasks.append(
            AgentTask(
                id=item.get("id"),
                agent=item.get("agent"),
                payload=item.get("payload", {}),
                depends_on=tuple(item.get("depends_on", ())),
                required_capabilities=tuple(item.get("required_capabilities", ())),
            )
        )
    plan = AgentPlan(id=raw_plan.get("id"), tasks=tuple(parsed_tasks))
    if document.get("plan_sha256") != plan.sha256:
        raise MultiAgentError("multi-agent run plan digest mismatch")

    raw_results = document.get("results")
    if not isinstance(raw_results, list) or len(raw_results) != len(plan.tasks):
        raise MultiAgentError("multi-agent run results do not match plan task count")

    expected_task_ids = [task.id for task in plan.tasks]
    actual_task_ids = [
        result.get("task_id") if isinstance(result, dict) else None
        for result in raw_results
    ]
    if actual_task_ids != expected_task_ids:
        raise MultiAgentError("multi-agent run result order/identity disagrees with plan")

    result_by_id: dict[str, dict[str, Any]] = {}
    for task, result in zip(plan.tasks, raw_results):
        if not isinstance(result, dict):
            raise MultiAgentError("multi-agent run result must be an object")
        if result.get("agent") != task.agent:
            raise MultiAgentError(
                f"multi-agent result agent mismatch for task {task.id!r}"
            )
        if result.get("status") not in AGENT_TASK_STATUSES:
            raise MultiAgentError(
                f"multi-agent result status is invalid for task {task.id!r}"
            )
        if result.get("depends_on") != list(task.depends_on):
            raise MultiAgentError(
                f"multi-agent result dependency list mismatch for task {task.id!r}"
            )
        expected_dependency_hashes = {
            dependency: result_by_id[dependency]["result_sha256"]
            for dependency in task.depends_on
        }
        if result.get("dependency_result_sha256") != expected_dependency_hashes:
            raise MultiAgentError(
                f"multi-agent dependency digest mismatch for task {task.id!r}"
            )
        expected_result_hash = _sha256(_task_result_identity(result))
        if result.get("result_sha256") != expected_result_hash:
            raise MultiAgentError(
                f"multi-agent result digest mismatch for task {task.id!r}"
            )
        result_by_id[task.id] = result

    expected_status = (
        "success"
        if all(result["status"] == "success" for result in raw_results)
        else "failed"
    )
    if document.get("status") != expected_status:
        raise MultiAgentError("multi-agent aggregate status mismatch")

    expected_run_hash = _sha256(_run_identity(document))
    if document.get("run_sha256") != expected_run_hash:
        raise MultiAgentError("multi-agent run digest mismatch")

    return {
        "schema": MULTI_AGENT_SCHEMA,
        "schema_version": MULTI_AGENT_SCHEMA_VERSION,
        "verified": True,
        "plan_sha256": plan.sha256,
        "run_sha256": expected_run_hash,
        "status": expected_status,
        "task_count": len(plan.tasks),
    }


def agent_plan_from_dict(data: Mapping[str, Any]) -> AgentPlan:
    """Parse a strict JSON-compatible agent plan."""

    document = _strict_json_clone(dict(data))
    raw_tasks = document.get("tasks")
    if not isinstance(raw_tasks, list):
        raise MultiAgentError("agent plan tasks must be an array")

    tasks: list[AgentTask] = []
    for index, item in enumerate(raw_tasks):
        if not isinstance(item, dict):
            raise MultiAgentError(
                f"agent plan task at index {index} must be an object"
            )
        depends_on = item.get("depends_on", [])
        required_capabilities = item.get("required_capabilities", [])
        payload = item.get("payload", {})
        if not isinstance(depends_on, list):
            raise MultiAgentError(
                f"agent plan task {item.get('id')!r} depends_on must be an array"
            )
        if not isinstance(required_capabilities, list):
            raise MultiAgentError(
                f"agent plan task {item.get('id')!r} required_capabilities must be an array"
            )
        if not isinstance(payload, dict):
            raise MultiAgentError(
                f"agent plan task {item.get('id')!r} payload must be an object"
            )
        tasks.append(
            AgentTask(
                id=item.get("id"),
                agent=item.get("agent"),
                payload=payload,
                depends_on=tuple(depends_on),
                required_capabilities=tuple(required_capabilities),
            )
        )
    return AgentPlan(id=document.get("id"), tasks=tuple(tasks))


def _load_project_for_agent(path_value: Any):
    from .project import load_project_document_with_revision_info

    if not isinstance(path_value, str) or not path_value.strip():
        raise MultiAgentError("project_path must be a non-empty string")
    source = Path(path_value).expanduser().resolve(strict=False)
    project, revision, _migration = load_project_document_with_revision_info(source)
    if not revision.exists or revision.sha256 is None:
        raise MultiAgentError("agent requires a saved project file")
    return source, project, revision


def _project_diagnostics_agent(
    task: AgentTask,
    _context: AgentContext,
) -> Mapping[str, Any]:
    from .project import capture_project_file_revision, project_file_revision_matches
    from .project_diagnostics import analyze_project_diagnostics

    source, project, revision = _load_project_for_agent(
        task.payload.get("project_path")
    )
    result = analyze_project_diagnostics(project, base_dir=source.parent)
    current = capture_project_file_revision(source)
    if not project_file_revision_matches(revision, current):
        raise MultiAgentError(
            "project source changed during diagnostics agent execution"
        )
    return {
        "project_path": str(source),
        "source_revision": revision.sha256,
        "diagnostics": result,
    }


def _project_requirements_agent(
    task: AgentTask,
    _context: AgentContext,
) -> Mapping[str, Any]:
    from .project_requirements_workflow import run_project_requirements_workflow

    project_path = task.payload.get("project_path")
    analysis_id = task.payload.get("analysis_id")
    if not isinstance(project_path, str) or not project_path.strip():
        raise MultiAgentError("project_path must be a non-empty string")
    if not isinstance(analysis_id, str) or not analysis_id.strip():
        raise MultiAgentError("analysis_id must be a non-empty string")
    workflow = run_project_requirements_workflow(project_path, analysis_id)
    return workflow.to_dict()


def _analysis_agent(
    task: AgentTask,
    _context: AgentContext,
) -> Mapping[str, Any]:
    from .application import run_analysis

    kind = task.payload.get("kind")
    analysis_input = task.payload.get("input")
    base_dir = task.payload.get("base_dir")
    if not isinstance(kind, str) or not kind.strip():
        raise MultiAgentError("kind must be a non-empty string")
    if not isinstance(analysis_input, dict):
        raise MultiAgentError("input must be an object")
    if base_dir is not None and not isinstance(base_dir, str):
        raise MultiAgentError("base_dir must be a string or null")

    result = run_analysis(
        kind,
        copy.deepcopy(analysis_input),
        base_dir=base_dir,
    )
    return result.to_dict()


def built_in_agents() -> tuple[FunctionAgent, ...]:
    """Return adapters for existing canonical CleanroomX services.

    Agent orchestration does not replace engineering equations, diagnostics,
    requirement comparisons, or ProofGraph semantics.
    """

    return (
        FunctionAgent(
            spec=AgentSpec(
                name="analysis",
                capabilities=("analysis", "engineering-service"),
                description="Execute one canonical CleanroomX application analysis.",
                authority="canonical-service",
            ),
            function=_analysis_agent,
        ),
        FunctionAgent(
            spec=AgentSpec(
                name="project-diagnostics",
                capabilities=("project", "diagnostics"),
                description=(
                    "Run the canonical read-only project diagnostics service."
                ),
                authority="canonical-service",
            ),
            function=_project_diagnostics_agent,
        ),
        FunctionAgent(
            spec=AgentSpec(
                name="project-requirements",
                capabilities=(
                    "project",
                    "requirements",
                    "verification",
                    "proofgraph",
                ),
                description=(
                    "Run saved-project requirements through canonical evidence "
                    "binding, verification, and ProofGraph projection."
                ),
                authority="canonical-service",
            ),
            function=_project_requirements_agent,
        ),
    )
