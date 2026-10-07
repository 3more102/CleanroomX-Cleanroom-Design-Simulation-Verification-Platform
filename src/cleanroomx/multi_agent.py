from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from threading import RLock
from types import MappingProxyType
from typing import Any
from uuid import uuid4

from .persistence import atomic_write_text
from .strict_json import clone_strict_json, load_strict_json


MULTI_AGENT_WORKSPACE_SCHEMA = "cleanroomx.multi-agent-workspace"
MULTI_AGENT_WORKSPACE_SCHEMA_VERSION = 1

_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_MESSAGE_ROLES = frozenset({"system", "user", "assistant", "tool"})
_EXECUTION_STATES = frozenset({"completed", "error"})


class SessionRevisionConflict(RuntimeError):
    """Raised when a caller tries to mutate a stale chat-session revision."""

    def __init__(self, session_id: str, expected_revision: int, actual_revision: int):
        self.session_id = session_id
        self.expected_revision = expected_revision
        self.actual_revision = actual_revision
        super().__init__(
            f"chat session {session_id!r} changed concurrently "
            f"(expected revision {expected_revision}, found {actual_revision})"
        )


def _validate_id(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not _ID_PATTERN.fullmatch(value):
        raise ValueError(
            f"{label} must match {_ID_PATTERN.pattern!r} and be at most 64 characters"
        )
    return value


def _validate_non_empty_text(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _frozen_json_object(
    value: Mapping[str, Any] | None,
    *,
    path: str,
) -> Mapping[str, Any]:
    raw = {} if value is None else dict(value)
    cloned = clone_strict_json(raw, path=path)
    if type(cloned) is not dict:
        raise ValueError(f"{path} must be a JSON object")
    return MappingProxyType(cloned)


def _thaw_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return clone_strict_json(dict(value))


@dataclass(frozen=True)
class ChatMessage:
    sequence: int
    role: str
    content: str
    agent_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if type(self.sequence) is not int or self.sequence < 1:
            raise ValueError("chat message sequence must be a positive integer")
        if self.role not in _MESSAGE_ROLES:
            raise ValueError(
                "chat message role must be one of: "
                + ", ".join(sorted(_MESSAGE_ROLES))
            )
        if not isinstance(self.content, str):
            raise ValueError("chat message content must be a string")
        if self.agent_id is not None:
            _validate_id(self.agent_id, label="agent id")
        object.__setattr__(
            self,
            "metadata",
            _frozen_json_object(self.metadata, path="$.message.metadata"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "role": self.role,
            "content": self.content,
            "agent_id": self.agent_id,
            "metadata": _thaw_mapping(self.metadata),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ChatMessage":
        if type(raw) is not dict:
            raise ValueError("chat message must be a JSON object")
        expected = {"sequence", "role", "content", "agent_id", "metadata"}
        unknown = set(raw) - expected
        missing = expected - set(raw)
        if unknown or missing:
            if missing:
                raise ValueError(
                    "chat message is missing field(s): "
                    + ", ".join(sorted(missing))
                )
            raise ValueError(
                "chat message contains unsupported field(s): "
                + ", ".join(sorted(unknown))
            )
        return cls(
            sequence=raw["sequence"],
            role=raw["role"],
            content=raw["content"],
            agent_id=raw["agent_id"],
            metadata=raw["metadata"],
        )


@dataclass(frozen=True)
class ChatSession:
    id: str
    title: str
    revision: int
    messages: tuple[ChatMessage, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_id(self.id, label="chat session id")
        _validate_non_empty_text(self.title, label="chat session title")
        if type(self.revision) is not int or self.revision < 0:
            raise ValueError("chat session revision must be a non-negative integer")
        if self.revision != len(self.messages):
            raise ValueError("chat session revision must equal its message count")
        for index, message in enumerate(self.messages, start=1):
            if not isinstance(message, ChatMessage):
                raise ValueError(
                    "chat session messages must contain ChatMessage values"
                )
            if message.sequence != index:
                raise ValueError(
                    "chat message sequences must be contiguous and 1-based"
                )
        object.__setattr__(
            self,
            "metadata",
            _frozen_json_object(self.metadata, path="$.session.metadata"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "revision": self.revision,
            "metadata": _thaw_mapping(self.metadata),
            "messages": [message.to_dict() for message in self.messages],
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ChatSession":
        if type(raw) is not dict:
            raise ValueError("chat session must be a JSON object")
        expected = {"id", "title", "revision", "metadata", "messages"}
        unknown = set(raw) - expected
        missing = expected - set(raw)
        if unknown or missing:
            if missing:
                raise ValueError(
                    "chat session is missing field(s): "
                    + ", ".join(sorted(missing))
                )
            raise ValueError(
                "chat session contains unsupported field(s): "
                + ", ".join(sorted(unknown))
            )
        if type(raw["messages"]) is not list:
            raise ValueError("chat session messages must be a JSON array")
        return cls(
            id=raw["id"],
            title=raw["title"],
            revision=raw["revision"],
            metadata=raw["metadata"],
            messages=tuple(
                ChatMessage.from_dict(item) for item in raw["messages"]
            ),
        )


@dataclass
class _MutableSession:
    id: str
    title: str
    revision: int
    messages: list[ChatMessage]
    metadata: dict[str, Any]


class ChatSessionStore:
    """Thread-safe, revision-checked storage for independent chat histories."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._sessions: dict[str, _MutableSession] = {}

    def create_session(
        self,
        session_id: str,
        title: str,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> ChatSession:
        _validate_id(session_id, label="chat session id")
        _validate_non_empty_text(title, label="chat session title")
        cloned_metadata = clone_strict_json(
            {} if metadata is None else dict(metadata)
        )
        if type(cloned_metadata) is not dict:
            raise ValueError("chat session metadata must be a JSON object")
        with self._lock:
            if session_id in self._sessions:
                raise ValueError(f"chat session {session_id!r} already exists")
            self._sessions[session_id] = _MutableSession(
                id=session_id,
                title=title,
                revision=0,
                messages=[],
                metadata=cloned_metadata,
            )
            return self._snapshot_locked(self._sessions[session_id])

    def delete_session(
        self,
        session_id: str,
        *,
        expected_revision: int | None = None,
    ) -> None:
        with self._lock:
            session = self._require_locked(session_id)
            self._check_revision_locked(session, expected_revision)
            del self._sessions[session_id]

    def list_sessions(self) -> tuple[ChatSession, ...]:
        with self._lock:
            return tuple(
                self._snapshot_locked(item) for item in self._sessions.values()
            )

    def get_session(self, session_id: str) -> ChatSession:
        with self._lock:
            return self._snapshot_locked(self._require_locked(session_id))

    def append_message(
        self,
        session_id: str,
        *,
        role: str,
        content: str,
        agent_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        expected_revision: int | None = None,
    ) -> ChatSession:
        return self.append_messages(
            session_id,
            ((role, content, agent_id, metadata),),
            expected_revision=expected_revision,
        )

    def append_messages(
        self,
        session_id: str,
        messages: Sequence[
            tuple[str, str, str | None, Mapping[str, Any] | None]
        ],
        *,
        expected_revision: int | None = None,
    ) -> ChatSession:
        pending = tuple(messages)
        if not pending:
            raise ValueError("at least one chat message is required")

        with self._lock:
            session = self._require_locked(session_id)
            self._check_revision_locked(session, expected_revision)
            prepared: list[ChatMessage] = []
            next_sequence = session.revision + 1
            for offset, (
                role,
                content,
                agent_id,
                metadata,
            ) in enumerate(pending):
                prepared.append(
                    ChatMessage(
                        sequence=next_sequence + offset,
                        role=role,
                        content=content,
                        agent_id=agent_id,
                        metadata={} if metadata is None else metadata,
                    )
                )
            session.messages.extend(prepared)
            session.revision += len(prepared)
            return self._snapshot_locked(session)

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            payload = {
                "schema": MULTI_AGENT_WORKSPACE_SCHEMA,
                "schema_version": MULTI_AGENT_WORKSPACE_SCHEMA_VERSION,
                "sessions": [
                    self._snapshot_locked(item).to_dict()
                    for item in self._sessions.values()
                ],
            }
        clone_strict_json(payload)
        return payload

    def save(self, path: str | Path) -> Path:
        text = (
            json.dumps(
                self.to_dict(),
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        )
        return atomic_write_text(path, text)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ChatSessionStore":
        if type(raw) is not dict:
            raise ValueError("multi-agent workspace must be a JSON object")
        expected = {"schema", "schema_version", "sessions"}
        unknown = set(raw) - expected
        missing = expected - set(raw)
        if unknown or missing:
            if missing:
                raise ValueError(
                    "multi-agent workspace is missing field(s): "
                    + ", ".join(sorted(missing))
                )
            raise ValueError(
                "multi-agent workspace contains unsupported field(s): "
                + ", ".join(sorted(unknown))
            )
        if raw["schema"] != MULTI_AGENT_WORKSPACE_SCHEMA:
            raise ValueError(
                f"unsupported multi-agent workspace schema: {raw['schema']!r}"
            )
        if raw["schema_version"] != MULTI_AGENT_WORKSPACE_SCHEMA_VERSION:
            raise ValueError(
                "unsupported multi-agent workspace schema version: "
                f"{raw['schema_version']!r}"
            )
        if type(raw["sessions"]) is not list:
            raise ValueError(
                "multi-agent workspace sessions must be a JSON array"
            )

        store = cls()
        with store._lock:
            for raw_session in raw["sessions"]:
                session = ChatSession.from_dict(raw_session)
                if session.id in store._sessions:
                    raise ValueError(
                        f"duplicate chat session id: {session.id!r}"
                    )
                store._sessions[session.id] = _MutableSession(
                    id=session.id,
                    title=session.title,
                    revision=session.revision,
                    messages=[
                        ChatMessage.from_dict(message.to_dict())
                        for message in session.messages
                    ],
                    metadata=_thaw_mapping(session.metadata),
                )
        return store

    @classmethod
    def load(cls, path: str | Path) -> "ChatSessionStore":
        return cls.from_dict(load_strict_json(path))

    def _require_locked(self, session_id: str) -> _MutableSession:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise KeyError(f"unknown chat session: {session_id!r}") from exc

    @staticmethod
    def _check_revision_locked(
        session: _MutableSession,
        expected_revision: int | None,
    ) -> None:
        if expected_revision is None:
            return
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError(
                "expected chat revision must be a non-negative integer"
            )
        if session.revision != expected_revision:
            raise SessionRevisionConflict(
                session.id,
                expected_revision,
                session.revision,
            )

    @staticmethod
    def _snapshot_locked(session: _MutableSession) -> ChatSession:
        return ChatSession(
            id=session.id,
            title=session.title,
            revision=session.revision,
            metadata=clone_strict_json(session.metadata),
            messages=tuple(
                ChatMessage.from_dict(message.to_dict())
                for message in session.messages
            ),
        )


@dataclass(frozen=True)
class AgentReply:
    content: str
    data: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.content, str):
            raise ValueError("agent reply content must be a string")
        object.__setattr__(
            self,
            "data",
            _frozen_json_object(
                self.data,
                path="$.agent_reply.data",
            ),
        )


@dataclass(frozen=True)
class AgentExecution:
    agent_id: str
    state: str
    content: str = ""
    data: Mapping[str, Any] = field(default_factory=dict)
    error_type: str | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        _validate_id(self.agent_id, label="agent id")
        if self.state not in _EXECUTION_STATES:
            raise ValueError(
                "agent execution state must be 'completed' or 'error'"
            )
        if self.state == "completed" and self.error_type is not None:
            raise ValueError(
                "completed agent execution cannot contain an error"
            )
        if self.state == "error" and not self.error_type:
            raise ValueError(
                "failed agent execution must include an error type"
            )
        object.__setattr__(
            self,
            "data",
            _frozen_json_object(
                self.data,
                path="$.agent_execution.data",
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "state": self.state,
            "content": self.content,
            "data": _thaw_mapping(self.data),
            "error": (
                None
                if self.state == "completed"
                else {
                    "type": self.error_type,
                    "message": self.error_message or "",
                }
            ),
        }


@dataclass(frozen=True)
class AgentRequest:
    task_id: str
    phase: str
    session: ChatSession
    prompt: str
    shared_input: Mapping[str, Any]
    peer_results: tuple[AgentExecution, ...] = ()

    def __post_init__(self) -> None:
        _validate_id(self.task_id, label="task id")
        if self.phase not in {"specialist", "synthesis"}:
            raise ValueError(
                "agent request phase must be 'specialist' or 'synthesis'"
            )
        _validate_non_empty_text(
            self.prompt,
            label="agent prompt",
        )
        object.__setattr__(
            self,
            "shared_input",
            _frozen_json_object(
                self.shared_input,
                path="$.agent_request.shared_input",
            ),
        )


AgentHandler = Callable[
    [AgentRequest],
    AgentReply | str | Mapping[str, Any],
]


@dataclass(frozen=True)
class AgentSpec:
    id: str
    title: str
    handler: AgentHandler = field(
        repr=False,
        compare=False,
    )
    capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_id(self.id, label="agent id")
        _validate_non_empty_text(
            self.title,
            label="agent title",
        )
        if not callable(self.handler):
            raise ValueError("agent handler must be callable")
        if any(
            not isinstance(item, str) or not item.strip()
            for item in self.capabilities
        ):
            raise ValueError(
                "agent capabilities must be non-empty strings"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "capabilities": list(self.capabilities),
        }


@dataclass(frozen=True)
class AgentBatchResult:
    task_id: str
    session_id: str
    specialist_agent_ids: tuple[str, ...]
    results: tuple[AgentExecution, ...]
    synthesizer_agent_id: str | None
    synthesis: AgentExecution | None
    commit_state: str
    input_revision: int
    output_revision: int | None

    def __post_init__(self) -> None:
        if self.commit_state not in {"committed", "conflict"}:
            raise ValueError(
                "agent batch commit_state must be 'committed' or 'conflict'"
            )
        if (
            self.commit_state == "committed"
            and self.output_revision is None
        ):
            raise ValueError(
                "committed agent batch must include output_revision"
            )
        if (
            self.commit_state == "conflict"
            and self.output_revision is not None
        ):
            raise ValueError(
                "conflicted agent batch cannot include output_revision"
            )

    @property
    def error_count(self) -> int:
        executions = self.results + (
            ()
            if self.synthesis is None
            else (self.synthesis,)
        )
        return sum(
            item.state == "error"
            for item in executions
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "specialist_agent_ids": list(
                self.specialist_agent_ids
            ),
            "results": [
                result.to_dict()
                for result in self.results
            ],
            "synthesizer_agent_id": self.synthesizer_agent_id,
            "synthesis": (
                None
                if self.synthesis is None
                else self.synthesis.to_dict()
            ),
            "commit_state": self.commit_state,
            "input_revision": self.input_revision,
            "output_revision": self.output_revision,
            "error_count": self.error_count,
        }
        clone_strict_json(payload)
        return payload


class MultiAgentCoordinator:
    """Run specialist agents in parallel while keeping chat histories isolated."""

    def __init__(
        self,
        store: ChatSessionStore,
        *,
        max_workers: int = 8,
    ) -> None:
        if type(max_workers) is not int or max_workers < 1:
            raise ValueError(
                "max_workers must be a positive integer"
            )
        self.store = store
        self.max_workers = max_workers
        self._registry_lock = RLock()
        self._agents: dict[str, AgentSpec] = {}

    def register_agent(
        self,
        agent_id: str,
        handler: AgentHandler,
        *,
        title: str | None = None,
        capabilities: Sequence[str] = (),
    ) -> AgentSpec:
        spec = AgentSpec(
            id=agent_id,
            title=agent_id if title is None else title,
            handler=handler,
            capabilities=tuple(capabilities),
        )
        with self._registry_lock:
            if agent_id in self._agents:
                raise ValueError(
                    f"agent {agent_id!r} is already registered"
                )
            self._agents[agent_id] = spec
        return spec

    def agent_catalog(
        self,
    ) -> tuple[dict[str, Any], ...]:
        with self._registry_lock:
            return tuple(
                spec.to_dict()
                for spec in self._agents.values()
            )

    def run(
        self,
        session_id: str,
        prompt: str,
        *,
        agent_ids: Sequence[str],
        shared_input: Mapping[str, Any] | None = None,
        synthesizer_agent_id: str | None = None,
        task_id: str | None = None,
    ) -> AgentBatchResult:
        _validate_non_empty_text(
            prompt,
            label="agent prompt",
        )
        requested = tuple(agent_ids)
        if not requested:
            raise ValueError(
                "at least one specialist agent is required"
            )
        if len(requested) != len(set(requested)):
            raise ValueError(
                "specialist agent ids must not contain duplicates"
            )
        for agent_id in requested:
            _validate_id(
                agent_id,
                label="agent id",
            )
        if synthesizer_agent_id is not None:
            _validate_id(
                synthesizer_agent_id,
                label="synthesizer agent id",
            )

        generated_task_id = (
            task_id
            or f"task-{uuid4().hex[:16]}"
        )
        _validate_id(
            generated_task_id,
            label="task id",
        )
        shared = clone_strict_json(
            {}
            if shared_input is None
            else dict(shared_input)
        )
        if type(shared) is not dict:
            raise ValueError(
                "shared agent input must be a JSON object"
            )

        specs = self._resolve_specs(
            requested,
            synthesizer_agent_id,
        )
        specialist_specs = tuple(
            specs[agent_id]
            for agent_id in requested
        )
        synthesizer_spec = (
            None
            if synthesizer_agent_id is None
            else specs[synthesizer_agent_id]
        )

        initial = self.store.get_session(
            session_id
        )
        submitted = self.store.append_message(
            session_id,
            role="user",
            content=prompt,
            metadata={
                "multi_agent_task_id": generated_task_id
            },
            expected_revision=initial.revision,
        )

        def specialist_request(
            spec: AgentSpec,
        ) -> AgentExecution:
            request = AgentRequest(
                task_id=generated_task_id,
                phase="specialist",
                session=submitted,
                prompt=prompt,
                shared_input=shared,
            )
            return self._execute(
                spec,
                request,
            )

        worker_count = min(
            self.max_workers,
            len(specialist_specs),
        )
        with ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="cleanroomx-agent",
        ) as executor:
            futures = [
                executor.submit(
                    specialist_request,
                    spec,
                )
                for spec in specialist_specs
            ]
            results = tuple(
                future.result()
                for future in futures
            )

        synthesis: AgentExecution | None = None
        if synthesizer_spec is not None:
            synthesis_request = AgentRequest(
                task_id=generated_task_id,
                phase="synthesis",
                session=submitted,
                prompt=prompt,
                shared_input=shared,
                peer_results=results,
            )
            synthesis = self._execute(
                synthesizer_spec,
                synthesis_request,
            )

        transcript_messages = [
            self._execution_message(
                generated_task_id,
                execution,
                phase="specialist",
            )
            for execution in results
        ]
        if synthesis is not None:
            transcript_messages.append(
                self._execution_message(
                    generated_task_id,
                    synthesis,
                    phase="synthesis",
                )
            )

        try:
            committed = self.store.append_messages(
                session_id,
                transcript_messages,
                expected_revision=submitted.revision,
            )
        except SessionRevisionConflict:
            return AgentBatchResult(
                task_id=generated_task_id,
                session_id=session_id,
                specialist_agent_ids=requested,
                results=results,
                synthesizer_agent_id=synthesizer_agent_id,
                synthesis=synthesis,
                commit_state="conflict",
                input_revision=submitted.revision,
                output_revision=None,
            )

        return AgentBatchResult(
            task_id=generated_task_id,
            session_id=session_id,
            specialist_agent_ids=requested,
            results=results,
            synthesizer_agent_id=synthesizer_agent_id,
            synthesis=synthesis,
            commit_state="committed",
            input_revision=submitted.revision,
            output_revision=committed.revision,
        )

    def _resolve_specs(
        self,
        requested: tuple[str, ...],
        synthesizer_agent_id: str | None,
    ) -> dict[str, AgentSpec]:
        required = set(requested)
        if synthesizer_agent_id is not None:
            required.add(
                synthesizer_agent_id
            )
        with self._registry_lock:
            missing = sorted(
                required - set(self._agents)
            )
            if missing:
                raise ValueError(
                    "unknown agent id(s): "
                    + ", ".join(missing)
                )
            return {
                agent_id: self._agents[agent_id]
                for agent_id in required
            }

    @staticmethod
    def _normalize_reply(
        value: AgentReply | str | Mapping[str, Any],
    ) -> AgentReply:
        if isinstance(value, AgentReply):
            return value
        if isinstance(value, str):
            return AgentReply(
                content=value
            )
        if isinstance(value, Mapping):
            cloned = clone_strict_json(
                dict(value)
            )
            if type(cloned) is not dict:
                raise ValueError(
                    "mapping agent reply must serialize "
                    "to a JSON object"
                )
            return AgentReply(
                content="",
                data=cloned,
            )
        raise TypeError(
            "agent handler must return AgentReply, "
            "str, or a JSON-object mapping"
        )

    @classmethod
    def _execute(
        cls,
        spec: AgentSpec,
        request: AgentRequest,
    ) -> AgentExecution:
        try:
            reply = cls._normalize_reply(
                spec.handler(request)
            )
            return AgentExecution(
                agent_id=spec.id,
                state="completed",
                content=reply.content,
                data=reply.data,
            )
        except Exception as exc:
            return AgentExecution(
                agent_id=spec.id,
                state="error",
                error_type=type(exc).__name__,
                error_message=str(exc),
            )

    @staticmethod
    def _execution_message(
        task_id: str,
        execution: AgentExecution,
        *,
        phase: str,
    ) -> tuple[
        str,
        str,
        str | None,
        Mapping[str, Any] | None,
    ]:
        if execution.state == "completed":
            content = execution.content
        else:
            content = (
                f"Agent execution failed: "
                f"{execution.error_type}: "
                f"{execution.error_message or ''}"
            )
        return (
            "assistant",
            content,
            execution.agent_id,
            {
                "multi_agent_task_id": task_id,
                "phase": phase,
                "execution": execution.to_dict(),
            },
        )
