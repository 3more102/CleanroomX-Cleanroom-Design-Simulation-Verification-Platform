"""Explicit CLI for advisory AI review of canonical project analyses."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .ai_assistant import register_local_ai_reviewer
from .multi_agent import ChatSessionStore, MultiAgentCoordinator
from .multi_agent_project import register_project_analysis_agent


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-ai-review",
        description=(
            "Run canonical project analyses, then ask a local Ollama model for "
            "a read-only advisory explanation. No automatic design changes."
        ),
    )
    parser.add_argument("project", help="Path to existing CleanroomX project JSON")
    parser.add_argument(
        "--analysis-id", action="append", required=True,
        help="Existing project analysis id; repeat for each analysis to review",
    )
    parser.add_argument("--question", required=True, help="Engineering question")
    parser.add_argument("--model", required=True, help="Installed local Ollama model id")
    parser.add_argument("--port", type=int, default=11434, help="Local Ollama port")
    parser.add_argument(
        "--timeout", type=float, default=60.0, help="Model request timeout in seconds"
    )
    parser.add_argument(
        "--format", choices=("text", "json"), default="text",
        help="Text advisory or full auditable multi-agent JSON",
    )
    args = parser.parse_args(argv)

    if len(args.analysis_id) != len(set(args.analysis_id)):
        parser.error("--analysis-id values must be unique")

    try:
        store = ChatSessionStore()
        store.create_session("project-review", "Local AI engineering review")
        coordinator = MultiAgentCoordinator(store)
        specialist_ids = []
        for index, analysis_id in enumerate(args.analysis_id):
            agent_id = f"analysis-{index + 1}"
            register_project_analysis_agent(
                coordinator, agent_id, project_path=args.project,
                analysis_id=analysis_id,
            )
            specialist_ids.append(agent_id)
        register_local_ai_reviewer(
            coordinator, model=args.model, port=args.port, timeout=args.timeout
        )
        batch = coordinator.run(
            "project-review",
            args.question,
            agent_ids=specialist_ids,
            synthesizer_agent_id="ai-reviewer",
        )
    except (OSError, ValueError) as exc:
        print(f"cleanroomx-ai-review: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(batch.to_dict(), indent=2, sort_keys=True, allow_nan=False))
    else:
        for analysis_id, result in zip(args.analysis_id, batch.results):
            print(f"Analysis {analysis_id}: {result.state}")
            if result.state == "error":
                print(f"  Error: {result.error_type}: {result.error_message}")
        if batch.synthesis is not None:
            if batch.synthesis.state == "completed":
                print("\n" + batch.synthesis.content)
                print(
                    "\nEvidence SHA-256: "
                    + str(batch.synthesis.data["evidence_sha256"])
                )
                print(
                    "Project source SHA-256: "
                    + str(batch.synthesis.data["project_sha256"])
                )
            else:
                print(
                    f"Review unavailable: {batch.synthesis.error_type}: "
                    f"{batch.synthesis.error_message}",
                    file=sys.stderr,
                )
    if (
        batch.commit_state != "committed"
        or batch.error_count
        or batch.synthesis is None
        or batch.synthesis.state != "completed"
    ):
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
