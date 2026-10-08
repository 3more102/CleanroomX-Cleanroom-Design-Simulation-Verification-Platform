from __future__ import annotations

from dataclasses import dataclass
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from . import __version__
from .application import run_analysis
from .project import (
    ProjectDocument,
    ProjectFileRevision,
    capture_project_file_revision,
    load_project_document_with_revision,
    project_file_revision_matches,
)
from .strict_json import StrictJSONError, clone_strict_json


AGENT_ORCHESTRATION_METADATA_KEY = "agent_orchestration"
AGENT_PLAN_SCHEMA_VERSION = 1
AGENT_RUN_SCHEMA = "cleanroomx.agent-orchestration-run"
AGENT_RUN_SCHEMA_VERSION = 1
AGENT_RUN_CANONICALIZATION = "json-sort-keys-compact-utf8-v1"

PathToken = str | int


class AgentPlanError(ValueError):
    """Raised when a project multi-agent plan is invalid."""


class AgentHandoffError(ValueError):
    """Raised when an explicit agent-to-agent handoff cannot be applied."""


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _strict_snapshot(value: Any, field_name: str) -> Any:
    try:
        return clone_strict_json(value)
    except StrictJSONError as exc:
        raise AgentPlanError(f"{field_name} must be strict JSON: {exc}") from exc


def _nonempty_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AgentPlanError(f"{field_name} must be a non-empty string")
    return value.strip()


def _string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, list):
        raise AgentPlanError(f"{field_name} must be an array of strings")
    result = tuple(
        _nonempty_text(item, f"{field_name}[{index}]")
        for index, item in enumerate(value)
    )
    if len(result) != len(set(result)):
        raise AgentPlanError(f"{field_name} must not contain duplicates")
    return result


def _source_path(value: Any, field_name: str) -> tuple[PathToken, ...]:
    if not isinstance(value, list) or not value:
        raise AgentPlanError(f"{field_name} must be a non-empty array")
    tokens: list[PathToken] = []
    for index, token in enumerate(value):
        token_name = f"{field_name}[{index}]"
        if isinstance(token, bool):
            raise AgentPlanError(f"{token_name} must be a string key or non-negative index")
        if isinstance(token, int):
            if token < 0:
                raise AgentPlanError(f"{token_name} must be a non-negative index")
            tokens.append(token)
            continue
        tokens.append(_nonempty_text(token, token_name))
    return tuple(tokens)


def _target_path(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise AgentPlanError(f"{field_name} must be a non-empty array of object keys")
    return tuple(
        _nonempty_text(token, f"{field_name}[{index}]")
        for index, token in enumerate(value)
    )


@dataclass(frozen=True)
class AgentHandoff:
    source_agent: str
    source_path: tuple[PathToken, ...]
    target_path: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_agent": self.source_agent,
            "source_path": list(self.source_path),
            "target_path": list(self.target_path),
        }


@dataclass(frozen=True)
class AgentSpec:
    id: str
    analysis_id: str
    analysis_kind: str
    depends_on: tuple[str, ...] = ()
    handoffs: tuple[AgentHandoff, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "analysis_id": self.analysis_id,
            "analysis_kind": self.analysis_kind,
            "depends_on": list(self.depends_on),
            "handoffs": [item.to_dict() for item in self.handoffs],
        }


@dataclass(frozen=True)
class AgentPlan:
    agents: tuple[AgentSpec, ...]
    execution_order: tuple[str, ...]
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": AGENT_PLAN_SCHEMA_VERSION,
            "agents": [item.to_dict() for item in self.agents],
            "execution_order": list(self.execution_order),
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class AppliedHandoff:
    source_agent: str
    source_path: tuple[PathToken, ...]
    target_path: tuple[str, ...]
    source_run_sha256: str
    value_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_agent": self.source_agent,
            "source_path": list(self.source_path),
            "target_path": list(self.target_path),
            "source_run_sha256": self.source_run_sha256,
            "value_sha256": self.value_sha256,
        }


@dataclass(frozen=True)
class AgentOutcome:
    agent_id: str
    analysis_id: str
    analysis_kind: str
    depends_on: tuple[str, ...]
    execution_state: str
    run: dict[str, Any] | None = None
    applied_handoffs: tuple[AppliedHandoff, ...] = ()
    blocked_by: tuple[str, ...] = ()
    error_type: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "analysis_id": self.analysis_id,
            "analysis_kind": self.analysis_kind,
            "depends_on": list(self.depends_on),
            "execution_state": self.execution_state,
            "run": copy.deepcopy(self.run),
            "applied_handoffs": [item.to_dict() for item in self.applied_handoffs],
            "blocked_by": list(self.blocked_by),
            "error": (
                None
                if self.error_type is None
                else {
                    "type": self.error_type,
                    "message": self.error_message or "",
                }
            ),
        }


@dataclass(frozen=True)
class AgentOrchestrationRun:
    project_name: str
    source_path: str
    source_size_bytes: int
    source_sha256: str
    plan: AgentPlan
    outcomes: tuple[AgentOutcome, ...]
    source_stable_during_run: bool
    source_change_stage: str | None = None
    source_change_agent_id: str | None = None
    source_check_error: str | None = None

    @property
    def completed_count(self) -> int:
        return sum(item.execution_state == "completed" for item in self.outcomes)

    @property
    def error_count(self) -> int:
        return sum(item.execution_state == "error" for item in self.outcomes)

    @property
    def blocked_count(self) -> int:
        return sum(item.execution_state == "blocked" for item in self.outcomes)

    @property
    def status(self) -> str:
        if not self.source_stable_during_run:
            return "source_changed"
        if self.error_count:
            return "error"
        if self.blocked_count:
            return "partial"
        if self.completed_count == len(self.plan.agents):
            return "completed"
        return "partial"

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema": AGENT_RUN_SCHEMA,
            "schema_version": AGENT_RUN_SCHEMA_VERSION,
            "cleanroomx_version": __version__,
            "project": {
                "name": self.project_name,
                "source_path": self.source_path,
                "source_revision": {
                    "size_bytes": self.source_size_bytes,
                    "sha256": self.source_sha256,
                },
            },
            "plan": self.plan.to_dict(),
            "execution": {
                "status": self.status,
                "planned_count": len(self.plan.agents),
                "recorded_count": len(self.outcomes),
                "completed_count": self.completed_count,
                "error_count": self.error_count,
                "blocked_count": self.blocked_count,
                "source_stable_during_run": self.source_stable_during_run,
                "source_change_stage": self.source_change_stage,
                "source_change_agent_id": self.source_change_agent_id,
                "source_check_error": self.source_check_error,
            },
            "agents": [item.to_dict() for item in self.outcomes],
        }
        payload["integrity"] = {
            "algorithm": "sha256",
            "canonicalization": AGENT_RUN_CANONICALIZATION,
            "sha256": _canonical_sha256(payload),
        }
        json.dumps(payload, sort_keys=True, allow_nan=False)
        return payload


def _parse_handoffs(raw: Any, *, agent_id: str) -> tuple[AgentHandoff, ...]:
    if not isinstance(raw, list):
        raise AgentPlanError(f"agent {agent_id!r} handoffs must be an array")

    handoffs: list[AgentHandoff] = []
    target_paths: set[tuple[str, ...]] = set()
    for index, item in enumerate(raw):
        field = f"agent {agent_id!r} handoffs[{index}]"
        if not isinstance(item, dict):
            raise AgentPlanError(f"{field} must be an object")
        unknown = sorted(set(item) - {"source_agent", "source_path", "target_path"})
        if unknown:
            raise AgentPlanError(
                f"{field} contains unsupported field(s): {', '.join(unknown)}"
            )
        handoff = AgentHandoff(
            source_agent=_nonempty_text(
                item.get("source_agent"), f"{field}.source_agent"
            ),
            source_path=_source_path(item.get("source_path"), f"{field}.source_path"),
            target_path=_target_path(item.get("target_path"), f"{field}.target_path"),
        )
        if handoff.target_path in target_paths:
            dotted = ".".join(handoff.target_path)
            raise AgentPlanError(
                f"agent {agent_id!r} writes target path {dotted!r} more than once"
            )
        for prior in handoffs:
            prior_path = prior.target_path
            if (
                handoff.target_path[: len(prior_path)] == prior_path
                or prior_path[: len(handoff.target_path)] == handoff.target_path
            ):
                raise AgentPlanError(
                    f"agent {agent_id!r} handoff target paths "
                    f"{'.'.join(prior_path)!r} and "
                    f"{'.'.join(handoff.target_path)!r} overlap"
                )
        target_paths.add(handoff.target_path)
        handoffs.append(handoff)
    return tuple(handoffs)


def load_agent_plan(project: ProjectDocument) -> AgentPlan:
    """Validate and normalize the multi-agent DAG stored in project metadata."""
    raw = project.metadata.get(AGENT_ORCHESTRATION_METADATA_KEY)
    if not isinstance(raw, dict):
        raise AgentPlanError(
            f"project.metadata.{AGENT_ORCHESTRATION_METADATA_KEY} must be an object"
        )
    raw = _strict_snapshot(raw, f"project.metadata.{AGENT_ORCHESTRATION_METADATA_KEY}")
    unknown = sorted(set(raw) - {"schema_version", "agents"})
    if unknown:
        raise AgentPlanError(
            "agent orchestration contains unsupported field(s): " + ", ".join(unknown)
        )
    version = raw.get("schema_version")
    if type(version) is not int or version != AGENT_PLAN_SCHEMA_VERSION:
        raise AgentPlanError(
            f"agent orchestration schema_version must be {AGENT_PLAN_SCHEMA_VERSION}"
        )
    raw_agents = raw.get("agents")
    if not isinstance(raw_agents, list) or not raw_agents:
        raise AgentPlanError("agent orchestration agents must be a non-empty array")

    analyses = {analysis.id: analysis for analysis in project.analyses}
    if len(analyses) != len(project.analyses):
        raise AgentPlanError("project analysis ids must be unique before agent orchestration")

    agents: list[AgentSpec] = []
    seen_ids: set[str] = set()
    seen_analysis_ids: set[str] = set()
    for index, item in enumerate(raw_agents):
        field = f"agent orchestration agents[{index}]"
        if not isinstance(item, dict):
            raise AgentPlanError(f"{field} must be an object")
        unknown = sorted(set(item) - {"id", "analysis_id", "depends_on", "handoffs"})
        if unknown:
            raise AgentPlanError(
                f"{field} contains unsupported field(s): {', '.join(unknown)}"
            )

        agent_id = _nonempty_text(item.get("id"), f"{field}.id")
        analysis_id = _nonempty_text(item.get("analysis_id"), f"{field}.analysis_id")
        if agent_id in seen_ids:
            raise AgentPlanError(f"duplicate agent id: {agent_id}")
        if analysis_id in seen_analysis_ids:
            raise AgentPlanError(
                f"analysis {analysis_id!r} is assigned to more than one agent"
            )
        if analysis_id not in analyses:
            raise AgentPlanError(
                f"agent {agent_id!r} references unknown analysis id {analysis_id!r}"
            )

        seen_ids.add(agent_id)
        seen_analysis_ids.add(analysis_id)
        agents.append(
            AgentSpec(
                id=agent_id,
                analysis_id=analysis_id,
                analysis_kind=analyses[analysis_id].kind,
                depends_on=_string_tuple(
                    item.get("depends_on", []), f"{field}.depends_on"
                ),
                handoffs=_parse_handoffs(item.get("handoffs", []), agent_id=agent_id),
            )
        )

    ids = {item.id for item in agents}
    for agent in agents:
        for dependency in agent.depends_on:
            if dependency == agent.id:
                raise AgentPlanError(f"agent {agent.id!r} cannot depend on itself")
            if dependency not in ids:
                raise AgentPlanError(
                    f"agent {agent.id!r} depends on unknown agent {dependency!r}"
                )
        for handoff in agent.handoffs:
            if handoff.source_agent not in agent.depends_on:
                raise AgentPlanError(
                    f"agent {agent.id!r} handoff source {handoff.source_agent!r} "
                    "must also appear in depends_on"
                )

    ordered: list[str] = []
    emitted: set[str] = set()
    while len(ordered) < len(agents):
        progress = False
        for agent in agents:
            if agent.id in emitted:
                continue
            if all(dependency in emitted for dependency in agent.depends_on):
                ordered.append(agent.id)
                emitted.add(agent.id)
                progress = True
        if not progress:
            unresolved = [agent.id for agent in agents if agent.id not in emitted]
            raise AgentPlanError(
                "agent orchestration dependency cycle detected among: "
                + ", ".join(unresolved)
            )

    normalized = {
        "schema_version": AGENT_PLAN_SCHEMA_VERSION,
        "agents": [item.to_dict() for item in agents],
        "execution_order": ordered,
    }
    return AgentPlan(
        agents=tuple(agents),
        execution_order=tuple(ordered),
        sha256=_canonical_sha256(normalized),
    )


def _read_source_path(value: Any, path: tuple[PathToken, ...]) -> Any:
    current = value
    for token in path:
        if isinstance(token, int):
            if not isinstance(current, list) or token >= len(current):
                raise AgentHandoffError(
                    f"source path index {token} is not available"
                )
            current = current[token]
            continue
        if not isinstance(current, dict) or token not in current:
            raise AgentHandoffError(
                f"source path key {token!r} is not available"
            )
        current = current[token]
    return copy.deepcopy(current)


def _write_target_path(payload: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    current: dict[str, Any] = payload
    for token in path[:-1]:
        if token not in current:
            child: dict[str, Any] = {}
            current[token] = child
            current = child
            continue
        existing = current[token]
        if not isinstance(existing, dict):
            raise AgentHandoffError(
                f"target path cannot descend through non-object key {token!r}"
            )
        current = existing
    current[path[-1]] = copy.deepcopy(value)


def _run_bundle_sha256(run: dict[str, Any]) -> str:
    """Verify the upstream run's canonical content identity before handoff."""
    integrity = run.get("integrity")
    if not isinstance(integrity, dict) or set(integrity) != {
        "algorithm", "canonicalization", "sha256"
    }:
        raise AgentHandoffError("upstream run integrity record is invalid")
    if (
        integrity["algorithm"] != "sha256"
        or integrity["canonicalization"] != AGENT_RUN_CANONICALIZATION
    ):
        raise AgentHandoffError("upstream run integrity algorithm is unsupported")
    digest = integrity["sha256"]
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise AgentHandoffError("upstream run integrity SHA-256 must be lowercase hex")
    unsigned = {key: value for key, value in run.items() if key != "integrity"}
    if _canonical_sha256(unsigned) != digest:
        raise AgentHandoffError("upstream run integrity check failed: content has changed")
    return digest

def _source_revision_state(
    path: Path,
    expected: ProjectFileRevision,
) -> tuple[bool, str | None]:
    try:
        current = capture_project_file_revision(path)
    except OSError as exc:
        return False, str(exc)
    return project_file_revision_matches(expected, current), None


def run_project_agents(
    path: str | Path,
    *,
    fail_fast: bool = True,
) -> AgentOrchestrationRun:
    """Execute one explicit project multi-agent DAG against one stable revision."""
    source = Path(path).expanduser().resolve(strict=False)
    project, revision = load_project_document_with_revision(source)
    if not revision.exists or revision.size is None or revision.sha256 is None:
        raise OSError(f"project source is not a readable regular file: {source}")

    plan = load_agent_plan(project)
    specs = {item.id: item for item in plan.agents}
    analyses = {analysis.id: analysis for analysis in project.analyses}
    outcomes: list[AgentOutcome] = []
    outcome_by_id: dict[str, AgentOutcome] = {}
    source_stable = True
    change_stage: str | None = None
    change_agent_id: str | None = None
    source_check_error: str | None = None

    for agent_id in plan.execution_order:
        spec = specs[agent_id]
        blocked_by = tuple(
            dependency
            for dependency in spec.depends_on
            if dependency not in outcome_by_id
            or outcome_by_id[dependency].execution_state != "completed"
        )
        if blocked_by:
            outcome = AgentOutcome(
                agent_id=spec.id,
                analysis_id=spec.analysis_id,
                analysis_kind=spec.analysis_kind,
                depends_on=spec.depends_on,
                execution_state="blocked",
                blocked_by=blocked_by,
            )
            outcomes.append(outcome)
            outcome_by_id[spec.id] = outcome
            continue

        matches, check_error = _source_revision_state(source, revision)
        if not matches:
            source_stable = False
            change_stage = "before-agent"
            change_agent_id = spec.id
            source_check_error = check_error
            break

        analysis = analyses[spec.analysis_id]
        payload = copy.deepcopy(analysis.input)
        applied_handoffs: list[AppliedHandoff] = []
        failed = False
        try:
            for handoff in spec.handoffs:
                source_outcome = outcome_by_id[handoff.source_agent]
                if source_outcome.run is None:
                    raise AgentHandoffError(
                        f"source agent {handoff.source_agent!r} has no completed run"
                    )
                upstream_sha256 = _run_bundle_sha256(source_outcome.run)
                value = _read_source_path(source_outcome.run, handoff.source_path)
                value = _strict_snapshot(
                    value,
                    f"handoff from {handoff.source_agent!r}",
                )
                _write_target_path(payload, handoff.target_path, value)
                applied_handoffs.append(
                    AppliedHandoff(
                        source_agent=handoff.source_agent,
                        source_path=handoff.source_path,
                        target_path=handoff.target_path,
                        source_run_sha256=upstream_sha256,
                        value_sha256=_canonical_sha256(value),
                    )
                )

            run = run_analysis(
                analysis.kind,
                payload,
                base_dir=source.parent,
                project_source_revision=revision.sha256,
            )
            run_document = _strict_snapshot(
                run.to_dict(),
                f"agent {spec.id!r} run bundle",
            )
        except Exception as exc:
            failed = True
            outcome = AgentOutcome(
                agent_id=spec.id,
                analysis_id=spec.analysis_id,
                analysis_kind=spec.analysis_kind,
                depends_on=spec.depends_on,
                execution_state="error",
                applied_handoffs=tuple(applied_handoffs),
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
        else:
            outcome = AgentOutcome(
                agent_id=spec.id,
                analysis_id=spec.analysis_id,
                analysis_kind=spec.analysis_kind,
                depends_on=spec.depends_on,
                execution_state="completed",
                run=run_document,
                applied_handoffs=tuple(applied_handoffs),
            )

        outcomes.append(outcome)
        outcome_by_id[spec.id] = outcome

        matches, check_error = _source_revision_state(source, revision)
        if not matches:
            source_stable = False
            change_stage = "after-agent"
            change_agent_id = spec.id
            source_check_error = check_error
            break
        if failed and fail_fast:
            break

    if source_stable:
        matches, check_error = _source_revision_state(source, revision)
        if not matches:
            source_stable = False
            change_stage = "final"
            change_agent_id = None
            source_check_error = check_error

    return AgentOrchestrationRun(
        project_name=project.name,
        source_path=str(source),
        source_size_bytes=revision.size,
        source_sha256=revision.sha256,
        plan=plan,
        outcomes=tuple(outcomes),
        source_stable_during_run=source_stable,
        source_change_stage=change_stage,
        source_change_agent_id=change_agent_id,
        source_check_error=source_check_error,
    )
