from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from .autosave import RecoveryCandidate, restore_recovery_artifact
from .project import AnalysisDocument, ProjectDocument, load_project_document


@dataclass(frozen=True)
class RecoveryComparison:
    """Deterministic semantic comparison between a recovery and its current source."""

    source_state: str
    source_path: Path | None
    source_error: str | None
    changed_project_fields: tuple[str, ...]
    added_analysis_ids: tuple[str, ...]
    removed_analysis_ids: tuple[str, ...]
    modified_analysis_ids: tuple[str, ...]
    active_analysis_changed: bool
    editor_analysis_id: str | None
    editor_draft_state: str
    recovered_analysis_count: int
    source_analysis_count: int | None

    @property
    def comparable(self) -> bool:
        return self.source_state == "available"

    @property
    def has_changes(self) -> bool:
        return bool(
            self.changed_project_fields
            or self.added_analysis_ids
            or self.removed_analysis_ids
            or self.modified_analysis_ids
            or self.active_analysis_changed
            or self.editor_draft_state in {"differs", "invalid", "analysis_missing"}
        )


def _analysis_map(project: ProjectDocument) -> dict[str, AnalysisDocument]:
    return {analysis.id: analysis for analysis in project.analyses}


def _analysis_changed(left: AnalysisDocument, right: AnalysisDocument) -> bool:
    return (
        left.name != right.name
        or left.kind != right.kind
        or left.input != right.input
    )


def _draft_state(
    recovered_project: ProjectDocument,
    source_project: ProjectDocument | None,
    ui_state: dict,
) -> tuple[str | None, str]:
    editor_id = ui_state.get("editor_analysis_id")
    if not isinstance(editor_id, str) or not editor_id:
        return None, "absent"

    editor_text = ui_state.get("editor_text")
    if not isinstance(editor_text, str) or not editor_text.strip():
        return editor_id, "absent"

    editor_valid = ui_state.get("editor_json_valid")
    if editor_valid is False:
        return editor_id, "invalid"

    try:
        parsed = json.loads(editor_text)
    except (TypeError, json.JSONDecodeError):
        return editor_id, "invalid"
    if not isinstance(parsed, dict):
        return editor_id, "invalid"

    if source_project is None:
        return editor_id, "uncomparable"

    source = _analysis_map(source_project).get(editor_id)
    if source is None:
        return editor_id, "analysis_missing"

    recovered = _analysis_map(recovered_project).get(editor_id)
    # The raw editor draft is authoritative recovery evidence even when the
    # autosaved project model still contains the last committed editor value.
    baseline_input = source.input
    if recovered is not None and recovered.input == parsed and source.input == parsed:
        return editor_id, "matches"
    return editor_id, "matches" if parsed == baseline_input else "differs"


def compare_recovery_to_source(candidate: RecoveryCandidate) -> RecoveryComparison:
    recovered = restore_recovery_artifact(candidate.path)
    source_path = recovered.source_path

    if source_path is None:
        editor_id, draft_state = _draft_state(recovered.project, None, recovered.ui_state)
        return RecoveryComparison(
            source_state="unsaved",
            source_path=None,
            source_error=None,
            changed_project_fields=(),
            added_analysis_ids=(),
            removed_analysis_ids=(),
            modified_analysis_ids=(),
            active_analysis_changed=False,
            editor_analysis_id=editor_id,
            editor_draft_state=draft_state,
            recovered_analysis_count=len(recovered.project.analyses),
            source_analysis_count=None,
        )

    if not source_path.exists():
        editor_id, draft_state = _draft_state(recovered.project, None, recovered.ui_state)
        return RecoveryComparison(
            source_state="missing",
            source_path=source_path,
            source_error=None,
            changed_project_fields=(),
            added_analysis_ids=(),
            removed_analysis_ids=(),
            modified_analysis_ids=(),
            active_analysis_changed=False,
            editor_analysis_id=editor_id,
            editor_draft_state=draft_state,
            recovered_analysis_count=len(recovered.project.analyses),
            source_analysis_count=None,
        )

    try:
        source = load_project_document(source_path)
    except (OSError, ValueError) as exc:
        editor_id, draft_state = _draft_state(recovered.project, None, recovered.ui_state)
        return RecoveryComparison(
            source_state="unreadable",
            source_path=source_path,
            source_error=str(exc),
            changed_project_fields=(),
            added_analysis_ids=(),
            removed_analysis_ids=(),
            modified_analysis_ids=(),
            active_analysis_changed=False,
            editor_analysis_id=editor_id,
            editor_draft_state=draft_state,
            recovered_analysis_count=len(recovered.project.analyses),
            source_analysis_count=None,
        )

    recovered_project = recovered.project
    changed_fields = tuple(
        field
        for field in ("name", "description", "metadata")
        if getattr(recovered_project, field) != getattr(source, field)
    )

    recovered_map = _analysis_map(recovered_project)
    source_map = _analysis_map(source)
    recovered_ids = set(recovered_map)
    source_ids = set(source_map)
    added = tuple(sorted(recovered_ids - source_ids))
    removed = tuple(sorted(source_ids - recovered_ids))
    modified = tuple(
        analysis_id
        for analysis_id in sorted(recovered_ids & source_ids)
        if _analysis_changed(recovered_map[analysis_id], source_map[analysis_id])
    )
    editor_id, draft_state = _draft_state(
        recovered_project,
        source,
        recovered.ui_state,
    )

    return RecoveryComparison(
        source_state="available",
        source_path=source_path,
        source_error=None,
        changed_project_fields=changed_fields,
        added_analysis_ids=added,
        removed_analysis_ids=removed,
        modified_analysis_ids=modified,
        active_analysis_changed=(
            recovered_project.active_analysis_id != source.active_analysis_id
        ),
        editor_analysis_id=editor_id,
        editor_draft_state=draft_state,
        recovered_analysis_count=len(recovered_project.analyses),
        source_analysis_count=len(source.analyses),
    )


def format_recovery_comparison(
    comparison: RecoveryComparison,
) -> tuple[str, tuple[str, ...]]:
    """Return a compact operator summary plus deterministic detail lines."""

    if comparison.source_state == "unsaved":
        detail = "No explicit source project existed when this recovery was captured."
        if comparison.editor_draft_state == "invalid":
            detail += " An invalid/incomplete editor draft is preserved."
        return "No source file is available for semantic comparison.", (detail,)

    if comparison.source_state == "missing":
        detail = "The recorded source path no longer exists; no automatic reconstruction is attempted."
        return "The original source file is missing.", (detail,)

    if comparison.source_state == "unreadable":
        error = comparison.source_error or "unknown read/validation error"
        return (
            "The current source file cannot be parsed safely.",
            (f"Source validation error: {error}",),
        )

    details: list[str] = []
    if comparison.changed_project_fields:
        details.append(
            "Project fields changed: " + ", ".join(comparison.changed_project_fields)
        )
    if comparison.added_analysis_ids:
        details.append(
            "Recovery-only analyses: " + ", ".join(comparison.added_analysis_ids)
        )
    if comparison.removed_analysis_ids:
        details.append(
            "Source-only analyses: " + ", ".join(comparison.removed_analysis_ids)
        )
    if comparison.modified_analysis_ids:
        details.append(
            "Modified analyses: " + ", ".join(comparison.modified_analysis_ids)
        )
    if comparison.active_analysis_changed:
        details.append("Active analysis selection changed.")
    if comparison.editor_draft_state == "differs":
        details.append(
            f"Recovered editor draft for {comparison.editor_analysis_id!r} differs from the current source input."
        )
    elif comparison.editor_draft_state == "invalid":
        details.append(
            f"Recovered editor draft for {comparison.editor_analysis_id!r} is invalid/incomplete JSON and is preserved verbatim."
        )
    elif comparison.editor_draft_state == "analysis_missing":
        details.append(
            f"Recovered editor draft targets {comparison.editor_analysis_id!r}, which is absent from the current source."
        )

    if not details:
        return (
            "No semantic project differences detected against the current source file.",
            ("The recovery may still carry session/UI evidence such as timestamps or draft state.",),
        )

    changed_groups = sum(
        bool(value)
        for value in (
            comparison.changed_project_fields,
            comparison.added_analysis_ids,
            comparison.removed_analysis_ids,
            comparison.modified_analysis_ids,
        )
    )
    changed_groups += int(comparison.active_analysis_changed)
    changed_groups += int(
        comparison.editor_draft_state in {"differs", "invalid", "analysis_missing"}
    )
    return (
        f"Recovery differs from the current source in {changed_groups} semantic area(s).",
        tuple(details),
    )
