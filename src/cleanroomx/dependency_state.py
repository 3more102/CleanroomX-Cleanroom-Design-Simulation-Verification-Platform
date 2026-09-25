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
        return self._state(_key(key), memo={}, active=set())

    def _state(
        self,
        key: str,
        *,
        memo: dict[str, EvidenceState],
        active: set[str],
    ) -> EvidenceState:
        if key in memo:
            return memo[key]
        node = self._nodes.get(key)
        if node is None:
            return EvidenceState.UNRESOLVED
        if key in active:
            return EvidenceState.INVALID
        if not node.integrity_valid:
            memo[key] = EvidenceState.INVALID
            return memo[key]
        if node.historical:
            memo[key] = EvidenceState.HISTORICAL
            return memo[key]
        if node.revision is None:
            memo[key] = EvidenceState.UNRESOLVED
            return memo[key]
        if not node.dependencies:
            memo[key] = EvidenceState.CURRENT
            return memo[key]

        active.add(key)
        unresolved = False
        stale = False
        for binding in node.dependencies:
            dependency = self._nodes.get(binding.key)
            if dependency is None:
                unresolved = True
                continue
            dependency_state = self._state(binding.key, memo=memo, active=active)
            if dependency_state in {EvidenceState.INVALID, EvidenceState.UNRESOLVED}:
                unresolved = True
                continue
            if dependency_state in {EvidenceState.STALE, EvidenceState.HISTORICAL}:
                stale = True
            if dependency.revision != binding.revision:
                stale = True
        active.remove(key)

        state = (
            EvidenceState.UNRESOLVED
            if unresolved
            else EvidenceState.STALE
            if stale
            else EvidenceState.CURRENT
        )
        memo[key] = state
        return state

    def states(self) -> dict[str, EvidenceState]:
        return {key: self.state(key) for key in sorted(self._nodes)}

    def snapshot(self) -> dict:
        """Return a deterministic strict-JSON-compatible graph description."""
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
                    "state": self.state(node.key).value,
                }
                for node in (self._nodes[key] for key in sorted(self._nodes))
            ],
        }

    def _assert_acyclic(self) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(key: str) -> None:
            if key in visited:
                return
            if key in visiting:
                raise DependencyGraphError(
                    f"dependency graph contains a cycle involving {key!r}"
                )
            visiting.add(key)
            node = self._nodes.get(key)
            if node is not None:
                for binding in node.dependencies:
                    if binding.key in self._nodes:
                        visit(binding.key)
            visiting.remove(key)
            visited.add(key)

        for key in sorted(self._nodes):
            visit(key)
