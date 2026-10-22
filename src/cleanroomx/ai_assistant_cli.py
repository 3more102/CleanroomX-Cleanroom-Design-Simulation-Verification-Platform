"""Command-line entry point for the read-only CleanroomX AI advisor."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from .ai_assistant import OpenAIResponsesClient, register_project_advice_agent
from .multi_agent import ChatSessionStore, MultiAgentCoordinator


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-ai",
        description="Review saved project definitions; AI advice is not verified CFD evidence.",
    )
    parser.add_argument("project", help="Path to an existing CleanroomX project JSON")
    parser.add_argument("question", help="Question about the saved project")
    parser.add_argument(
        "--provider",
        choices=("offline", "openai"),
        default="offline",
        help="OpenAI mode explicitly sends limited project metadata and the question",
    )
    parser.add_argument("--model", default="gpt-4.1-mini")
    parser.add_argument("--workspace", type=Path, help="Optional separate saved chat workspace")
    parser.add_argument("--session-id", default="project-review")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    if args.workspace is not None and (
        args.workspace.expanduser().resolve(strict=False)
        == Path(args.project).expanduser().resolve(strict=False)
    ):
        parser.error("chat workspace must not overwrite the engineering project")

    try:
        if args.workspace is not None and args.workspace.is_file():
            store = ChatSessionStore.load(args.workspace)
        else:
            store = ChatSessionStore()
        try:
            store.get_session(args.session_id)
        except KeyError:
            store.create_session(args.session_id, "CleanroomX project review")

        client = (
            OpenAIResponsesClient(model=args.model)
            if args.provider == "openai"
            else None
        )
        coordinator = MultiAgentCoordinator(store)
        register_project_advice_agent(
            coordinator,
            project_path=args.project,
            client=client,
        )
        batch = coordinator.run(
            args.session_id,
            args.question,
            agent_ids=["project-advisor"],
        )
        if batch.commit_state != "committed":
            print("cleanroomx-ai: concurrent chat edit; advice was not committed", file=sys.stderr)
            return 3
        result = batch.results[0]
        if result.state != "completed":
            print(
                f"cleanroomx-ai: {result.error_type}: {result.error_message}",
                file=sys.stderr,
            )
            return 2
        if args.workspace is not None:
            store.save(args.workspace)
        if args.format == "json":
            print(json.dumps(batch.to_dict(), ensure_ascii=False, indent=2, allow_nan=False))
        else:
            print("ADVISORY ONLY — NOT VALIDATED ENGINEERING EVIDENCE")
            print(result.content)
        return 0
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f"cleanroomx-ai: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
