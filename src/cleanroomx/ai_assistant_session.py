"""Deterministic assistant session history with project-revision isolation.

History is in memory only. No model or user content is persisted implicitly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

Role = Literal["user", "assistant"]
MAX_MESSAGES = 30
MAX_CONTENT = 8000


@dataclass(frozen=True)
class AssistantMessage:
    role: Role
    content: str
    snapshot_sha256: str
    created_at_utc: str

    def __post_init__(self) -> None:
        if self.role not in ("user", "assistant"):
            raise ValueError("Invalid assistant message role")
        if not isinstance(self.content, str) or not self.content.strip():
            raise ValueError("Assistant message content cannot be empty")
        if len(self.content) > MAX_CONTENT:
            raise ValueError("Assistant message content too long")
        if len(self.snapshot_sha256) != 64 or any(
            char not in "0123456789abcdef" for char in self.snapshot_sha256
        ):
            raise ValueError("Invalid project snapshot SHA-256")


@dataclass
class AssistantSession:
    """Bounded chat history, never shared across project snapshot identities."""

    snapshot_sha256: str
    messages: list[AssistantMessage] = field(default_factory=list)

    def __post_init__(self) -> None:
        if len(self.snapshot_sha256) != 64 or any(
            char not in "0123456789abcdef" for char in self.snapshot_sha256
        ):
            raise ValueError("Invalid project snapshot SHA-256")

    def append(self, role: Role, content: str) -> AssistantMessage:
        item = AssistantMessage(
            role=role,
            content=content,
            snapshot_sha256=self.snapshot_sha256,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
        )
        self.messages.append(item)
        self.messages = self.messages[-MAX_MESSAGES:]
        return item

    def recent(self, limit: int = 10) -> list[dict[str, str]]:
        if not 1 <= limit <= MAX_MESSAGES:
            raise ValueError("Invalid history limit")
        return [
            {"role": item.role, "content": item.content}
            for item in self.messages[-limit:]
        ]

    def reset_for_project(self, snapshot_sha256: str) -> bool:
        """Clear old context whenever the project content changes."""
        if len(snapshot_sha256) != 64 or any(
            char not in "0123456789abcdef" for char in snapshot_sha256
        ):
            raise ValueError("Invalid project snapshot SHA-256")
        if snapshot_sha256 == self.snapshot_sha256:
            return False
        self.snapshot_sha256 = snapshot_sha256
        self.messages.clear()
        return True
