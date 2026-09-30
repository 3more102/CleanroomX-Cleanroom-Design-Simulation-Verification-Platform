from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class DependencyGraphError(ValueError):
    """Raised when an explicit engineering dependency graph is structurally invalid."""


class EvidenceState(str, Enum):
    CURRENT = "current"
    STALE = "stale"
    HISTORICAL = "historical"
    UNRESOLVED = "unresolved"
    INVALID = "invalid"


@dataclass(frozen=True, order=True)
class DependencyBinding:
    key: str
    revision: str


@dataclass(frozen=True)
class DependencyNode:
    key: str
    revision: str | None
    dependencies: tuple[DependencyBinding, ...] = ()
    historical: bool = False
    integrity_valid: bool = True


def _key(value: str, field: str = "key") -> str:
    if not isinstance(value, str) or not value.strip():
        raise DependencyGraphError(f"{field} must be a non-empty string")
    return value.strip()


def _revision(value: str | None, *, allow_unresolved: bool) -> str | None:
    if value is None and allow_unresolved:
        return None
    if not isinstance(value, str) or not value.strip():
        raise DependencyGraphError("revision must be a non-empty string")
    return value.strip()


class DependencyGraph:
    """Explicit revision graph for engineering evidence freshness.

    Only caller-declared edges are modeled. CleanroomX never infers scientific
    dependency merely because two analyses coexist in one project.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, DependencyNode] = {}

    def set_source(self, key: str, revision: str | None) -> None:
        """Register an authoritative input revision. None means unresolved."""
        normalized_key = _key(key)
        self._nodes[normalized_key] = DependencyNode(
            key=normalized_key,
            revision=_revision(revision, allow_unresolved=True),
        )
        self._assert_acyclic()

    def set_artifact(
        self,
        key: str,
        revision: str,
        *,
        dependencies: Mapping[str, str],
        historical: bool = False,
        integrity_valid: bool = True,
    ) -> None:
        """Bind one artifact to exact dependency revisions."""
        normalized_key = _key(key)
        if not isinstance(dependencies, Mapping):
            raise DependencyGraphError("dependencies must be a mapping")
        bindings: list[DependencyBinding] = []
        for dependency_key, dependency_revision in dependencies.items():
            dep_key = _key(dependency_key, "dependency key")
            if dep_key == normalized_key:
                raise DependencyGraphError("a dependency node cannot depend on itself")
            bindings.append(
                DependencyBinding(
                    dep_key,
                    _revision(dependency_revision, allow_unresolved=False),
                )
            )
        bindings.sort()
        previous = self._nodes.get(normalized_key)
        self._nodes[normalized_key] = DependencyNode(
            key=normalized_key,
            revision=_revision(revision, allow_unresolved=False),
            dependencies=tuple(bindings),
            historical=bool(historical),
            integrity_valid=bool(integrity_valid),
        )
        try:
            self._assert_acyclic()
        except Exception:
            if previous is None:
                self._nodes.pop(normalized_key, None)
            else:
                self._nodes[normalized_key] = previous
            raise

    def remove(self, key: str) -> None:
        self._nodes.pop(_key(key), None)

    def node(self, key: str) -> DependencyNode | None:
        return self._nodes.get(_key(key))

    def state(self, key: str) -> EvidenceState:
        normalized_key = _key(key)
        memo: dict[str, EvidenceState] = {}
        return self._state(normalized_key, memo=memo)

    def _state(
        self,
        key: str,
        *,
        memo: dict[str, EvidenceState],
    ) -> EvidenceState:
        if key in memo:
            return memo[key]

        processing: set[str] = set()
        stack: list[tuple[str, bool]] = [(key, False)]
        while stack:
            current_key, expanded = stack.pop()
            if current_key in memo:
                continue

            node = self._nodes.get(current_key)
            if node is None:
                memo[current_key] = EvidenceState.UNRESOLVED
                continue
            if not node.integrity_valid:
                memo[current_key] = EvidenceState.INVALID
                continue
            if node.historical:
                memo[current_key] = EvidenceState.HISTORICAL
                continue
            if node.revision is None:
                memo[current_key] = EvidenceState.UNRESOLVED
                continue
            if not node.dependencies:
                memo[current_key] = EvidenceState.CURRENT
                continue

            if not expanded:
                if current_key in processing:
                    memo[current_key] = EvidenceState.INVALID
                    continue
                processing.add(current_key)
                stack.append((current_key, True))
                for binding in reversed(node.dependencies):
                    if binding.key not in memo:
                        stack.append((binding.key, False))
                continue

            processing.discard(current_key)
            unresolved = False
            stale = False
            for binding in node.dependencies:
                dependency = self._nodes.get(binding.key)
                dependency_state = memo.get(
                    binding.key,
                    EvidenceState.UNRESOLVED,
                )
                if dependency is None or dependency_state in {
                    EvidenceState.INVALID,
                    EvidenceState.UNRESOLVED,
                }:
                    unresolved = True
                    continue
                if dependency_state in {
                    EvidenceState.STALE,
                    EvidenceState.HISTORICAL,
                }:
                    stale = True
                if dependency.revision != binding.revision:
                    stale = True

            memo[current_key] = (
                EvidenceState.UNRESOLVED
                if unresolved
                else EvidenceState.STALE
                if stale
                else EvidenceState.CURRENT
            )

        return memo.get(key, EvidenceState.UNRESOLVED)

    def states(self) -> dict[str, EvidenceState]:
        memo: dict[str, EvidenceState] = {}
        for key in sorted(self._nodes):
            self._state(key, memo=memo)
        return {key: memo[key] for key in sorted(self._nodes)}

    def snapshot(self) -> dict:
        """Return a deterministic strict-JSON-compatible graph description."""
        states = self.states()
        return {
            "schema": "cleanroomx.dependency-graph",
            "schema_version": 1,
            "nodes": [
                {
                    "key": node.key,
                    "revision": node.revision,
                    "historical": node.historical,
                    "integrity_valid": node.integrity_valid,
                    "dependencies": [
                        {"key": binding.key, "revision": binding.revision}
                        for binding in node.dependencies
                    ],
                    "state": states[node.key].value,
                }
                for node in (self._nodes[key] for key in sorted(self._nodes))
            ],
        }

    def _assert_acyclic(self) -> None:
        states: dict[str, int] = {}

        for root_key in sorted(self._nodes):
            if states.get(root_key, 0) == 2:
                continue

            stack: list[tuple[str, int]] = [(root_key, 0)]
            path: list[str] = []
            path_index: dict[str, int] = {}

            while stack:
                current_key, next_dependency_index = stack[-1]
                if states.get(current_key, 0) == 0:
                    states[current_key] = 1
                    path_index[current_key] = len(path)
                    path.append(current_key)

                node = self._nodes[current_key]
                dependencies = tuple(
                    binding.key
                    for binding in node.dependencies
                    if binding.key in self._nodes
                )
                if next_dependency_index >= len(dependencies):
                    stack.pop()
                    states[current_key] = 2
                    path_index.pop(current_key)
                    path.pop()
                    continue

                dependency_key = dependencies[next_dependency_index]
                stack[-1] = (current_key, next_dependency_index + 1)
                dependency_state = states.get(dependency_key, 0)
                if dependency_state == 2:
                    continue
                if dependency_state == 1:
                    start = path_index[dependency_key]
                    cycle = path[start:] + [dependency_key]
                    raise DependencyGraphError(
                        "dependency graph contains a cycle: " + " -> ".join(cycle)
                    )
                stack.append((dependency_key, 0))
