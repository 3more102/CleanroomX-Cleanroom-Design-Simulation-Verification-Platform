from __future__ import annotations

from collections.abc import Sequence
import copy
from dataclasses import dataclass
from pathlib import Path

from .application import run_analysis
from .multi_agent import AgentHandler, AgentReply, AgentRequest, AgentSpec, MultiAgentCoordinator
from .project import (
    ProjectFileRevision,
    capture_project_file_revision,
    load_project_document_with_revision,
    project_file_revision_matches,
)


PROJECT_AGENT_RESULT_SCHEMA = "cleanroomx.multi-agent-project-analysis"
PROJECT_AGENT_RESULT_SCHEMA_VERSION = 1


class ProjectAgentSourceChangedError(RuntimeError):
    """Raised when a project-backed agent no longer sees its loaded source revision."""

    def __init__(
        self,
        analysis_id: str,
        stage: str,
        expected: ProjectFileRevision,
        current: ProjectFileRevision | None,
    ) -> None:
        self.analysis_id = analysis_id
        self.stage = stage
        self.expected = expected
        self.current = current
        detail = ""
        if current is None:
            detail = " (source revision could not be re-read)"
        super().__init__(
            f"project source changed {stage} canonical analysis {analysis_id!r}{detail}"
        )


def _normalized_source(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _require_same_revision(
    source: Path,
    expected: ProjectFileRevision,
    *,
    analysis_id: str,
    stage: str,
) -> None:
    try:
        current = capture_project_file_revision(source)
    except OSError as exc:
        raise ProjectAgentSourceChangedError(
            analysis_id,
            stage,
            expected,
            None,
        ) from exc
    if not project_file_revision_matches(expected, current):
        raise ProjectAgentSourceChangedError(
            analysis_id,
            stage,
            expected,
            current,
        )


@dataclass(frozen=True)
class ProjectAnalysisAgent:
    """Callable agent that delegates one fixed project analysis to CleanroomX."""

    project_path: Path
    analysis_id: str

    def __init__(self, project_path: str | Path, analysis_id: str) -> None:
        if not isinstance(analysis_id, str) or not analysis_id.strip():
            raise ValueError("analysis_id must be a non-empty string")
        object.__setattr__(self, "project_path", _normalized_source(project_path))
        object.__setattr__(self, "analysis_id", analysis_id.strip())

    def __call__(self, request: AgentRequest) -> AgentReply:
        project, revision = load_project_document_with_revision(self.project_path)
        if not revision.exists or revision.size is None or revision.sha256 is None:
            raise OSError("project source is not a readable regular file")

        analysis = next(
            (item for item in project.analyses if item.id == self.analysis_id),
            None,
        )
        if analysis is None:
            raise ValueError(
                f"unknown project analysis id: {self.analysis_id!r}"
            )

        _require_same_revision(
            self.project_path,
            revision,
            analysis_id=self.analysis_id,
            stage="before",
        )

        run = run_analysis(
            analysis.kind,
            copy.deepcopy(analysis.input),
            base_dir=self.project_path.parent,
            project_source_revision=revision.sha256,
        )

        _require_same_revision(
            self.project_path,
            revision,
            analysis_id=self.analysis_id,
            stage="during",
        )

        data = {
            "schema": PROJECT_AGENT_RESULT_SCHEMA,
            "schema_version": PROJECT_AGENT_RESULT_SCHEMA_VERSION,
            "task_id": request.task_id,
            "session_id": request.session.id,
            "project": {
                "name": project.name,
                "source_revision": {
                    "size_bytes": revision.size,
                    "sha256": revision.sha256,
                },
            },
            "analysis": {
                "id": analysis.id,
                "name": analysis.name,
                "kind": analysis.kind,
            },
            "run": run.to_dict(),
        }
        return AgentReply(
            content=f"{analysis.name}: {run.status}",
            data=data,
        )


def make_project_analysis_handler(
    project_path: str | Path,
    analysis_id: str,
) -> AgentHandler:
    """Return an auditable handler pinned to one project analysis id."""

    return ProjectAnalysisAgent(project_path, analysis_id)


def register_project_analysis_agent(
    coordinator: MultiAgentCoordinator,
    agent_id: str,
    *,
    project_path: str | Path,
    analysis_id: str,
    title: str | None = None,
    capabilities: Sequence[str] = (),
) -> AgentSpec:
    """Register a chat specialist backed only by the canonical application service."""

    handler = make_project_analysis_handler(project_path, analysis_id)
    declared_capabilities = tuple(
        dict.fromkeys(
            (
                "cleanroomx.project-analysis",
                "engineering-analysis",
                *tuple(capabilities),
            )
        )
    )
    return coordinator.register_agent(
        agent_id,
        handler,
        title=title or f"Project analysis: {analysis_id}",
        capabilities=declared_capabilities,
    )
