"""Revision-safe project-bound conversations for the CleanroomX AI assistant.

The canonical multi-agent ChatSessionStore is reused for strict, atomic
user-requested save/load. No engineering state is persisted in chat sessions.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from .multi_agent import ChatSession, ChatSessionStore


MAX_HISTORY_MESSAGES = 12
MAX_HISTORY_CHARACTERS = 12000
MAX_SAVED_REPLY_CHARACTERS = 16000


def project_chat_key(
    project_path: str | Path | None, *,
    unsaved_id: str = "desktop-unsaved",
) -> str:
    """Bind a session to a local file identity without recording its path."""
    if project_path is None:
        if not isinstance(unsaved_id, str) or not unsaved_id.strip():
            raise ValueError("an unsaved project identity is required")
        source = "unsaved:" + unsaved_id
    else:
        source = "saved:" + str(Path(project_path).expanduser().resolve(strict=False))
    return sha256(source.encode("utf-8")).hexdigest()


class ProjectChatMismatchError(ValueError):
    """A chat from another project cannot be reused as model conversation history."""


class AssistantConversations:
    """Multiple independent revision-checked chats; persistence is explicit."""

    def __init__(self, store: ChatSessionStore | None = None) -> None:
        self.store = store if store is not None else ChatSessionStore()

    def new(self, project_key: str, title: str = "Engineering review") -> ChatSession:
        self._validate_key(project_key)
        return self.store.create_session(
            "assistant-" + uuid4().hex,
            title,
            metadata={"assistant_project_key": project_key, "assistant_schema": 1},
        )

    @staticmethod
    def _validate_key(value: str) -> None:
        if not isinstance(value, str) or len(value) != 64:
            raise ValueError("project key must be a SHA-256 identifier")
        if any(c not in "0123456789abcdef" for c in value):
            raise ValueError("project key must be lowercase hexadecimal")

    def sessions(self, project_key: str) -> tuple[ChatSession, ...]:
        self._validate_key(project_key)
        return tuple(
            item for item in self.store.list_sessions()
            if item.metadata.get("assistant_project_key") == project_key
            and item.metadata.get("assistant_schema") == 1
        )

    def require_session(self, session_id: str, project_key: str) -> ChatSession:
        self._validate_key(project_key)
        session = self.store.get_session(session_id)
        if (
            session.metadata.get("assistant_project_key") != project_key
            or session.metadata.get("assistant_schema") != 1
        ):
            raise ProjectChatMismatchError(
                "The selected AI conversation belongs to a different project."
            )
        return session

    def model_history(
        self, session_id: str, project_key: str
    ) -> list[dict[str, str]]:
        """Return bounded past Q/A pairs; never forward system/tool/offline items."""
        session = self.require_session(session_id, project_key)
        messages = []
        for message in session.messages:
            if (
                message.role in ("user", "assistant")
                and message.metadata.get("assistant_source") == "ai"
            ):
                messages.append(
                    {"role": message.role, "content": message.content}
                )

        # Preserve *complete* question/answer exchanges from newest backwards.
        pairs = []
        for i in range(0, len(messages) - 1, 2):
            if messages[i]["role"] == "user" and messages[i + 1]["role"] == "assistant":
                pairs.append(messages[i:i + 2])
        retained = []
        remaining = MAX_HISTORY_CHARACTERS
        for pair in reversed(pairs):
            length = sum(len(item["content"]) for item in pair)
            if length > remaining or len(retained) + 2 > MAX_HISTORY_MESSAGES:
                break
            retained[0:0] = pair
            remaining -= length
        return retained

    def commit_exchange(
        self, session_id: str, project_key: str, *,
        question: str,
        answer: str,
        snapshot_sha256: str,
        expected_revision: int,
        expected_instance_id: str,
        provider: str,
        model: str,
        stale_project: bool = False,
    ) -> ChatSession:
        """Atomically commit a model exchange if the chat has not changed."""
        self.require_session(session_id, project_key)
        if not isinstance(question, str) or not question.strip() or len(question) > 4000:
            raise ValueError("question is missing or too long")
        if not isinstance(answer, str) or not answer.strip() or len(answer) > MAX_SAVED_REPLY_CHARACTERS:
            raise ValueError("model response is missing or too long")
        self._validate_key(snapshot_sha256)
        if not provider or not model:
            raise ValueError("model provenance is required")
        metadata = {
            "assistant_source": "ai",
            "snapshot_sha256": snapshot_sha256,
            "provider": provider[:80],
            "model": model[:100],
            "stale_project_on_receipt": bool(stale_project),
            "engineering_evidence": False,
        }
        return self.store.append_messages(
            session_id,
            (
                ("user", question, None, metadata),
                ("assistant", answer, None, metadata),
            ),
            expected_revision=expected_revision,
            expected_instance_id=expected_instance_id,
        )

    def save(self, path: str | Path) -> Path:
        """Explicit local export. This file contains full questions and answers."""
        return self.store.save(path)

    @classmethod
    def load(cls, path: str | Path) -> "AssistantConversations":
        return cls(ChatSessionStore.load(path))
