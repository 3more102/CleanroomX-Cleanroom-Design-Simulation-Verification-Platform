from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .agent_orchestration import AgentOrchestrationRun, run_project_agents
from .markdown import markdown_text


def render_agent_orchestration_markdown(run: AgentOrchestrationRun) -> str:
    lines = [
        "# CleanroomX multi-agent orchestration",
        "",
        f"- Project: {markdown_text(run.project_name)}",
        f"- Source SHA-256: `{run.source_sha256}`",
        f"- Plan SHA-256: `{run.plan.sha256}`",
        f"- Status: **{run.status}**",
        f"- Completed: {run.completed_count}/{len(run.plan.agents)}",
        f"- Errors: {run.error_count}",
        f"- Blocked: {run.blocked_count}",
        "",
        "| Agent | Analysis | State | Dependencies |",
        "|---|---|---|---|",
    ]
    by_id = {item.agent_id: item for item in run.outcomes}
    for agent_id in run.plan.execution_order:
        spec = next(item for item in run.plan.agents if item.id == agent_id)
        outcome = by_id.get(agent_id)
        state = outcome.execution_state if outcome is not None else "not_started"
        dependencies = ", ".join(spec.depends_on) if spec.depends_on else "-"
        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_text(spec.id),
                    markdown_text(spec.analysis_id),
                    markdown_text(state),
                    markdown_text(dependencies),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def agent_orchestration_exit_code(run: AgentOrchestrationRun) -> int:
    if not run.source_stable_during_run:
        return 3
    if run.error_count or run.blocked_count or run.completed_count != len(run.plan.agents):
        return 4
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-project-agents",
        description=(
            "Run the explicit dependency-aware multi-agent plan stored in "
            "project.metadata.agent_orchestration."
        ),
    )
    parser.add_argument("project", help="CleanroomX project JSON file")
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue independent agents after an agent error.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format written to stdout.",
    )
    args = parser.parse_args(argv)

    try:
        run = run_project_agents(
            args.project,
            fail_fast=not args.continue_on_error,
        )
    except (OSError, ValueError) as exc:
        print(f"cleanroomx-project-agents: {exc}", file=sys.stderr)
        return 2

    if args.format == "markdown":
        sys.stdout.write(render_agent_orchestration_markdown(run))
    else:
        print(json.dumps(run.to_dict(), indent=2, sort_keys=True, allow_nan=False))
    return agent_orchestration_exit_code(run)


if __name__ == "__main__":
    raise SystemExit(main())
