from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from .cli_output import CliStateError, resolve_cli_path
from .bim_ifc import (
    IFC_LINK_METADATA_KEY,
    IfcImportError,
    apply_ifc_semantics_to_project,
    extract_ifc_semantics,
    plan_ifc_semantic_reimport,
    reimport_ifc_semantics_to_project,
)
from .project import (
    ProjectFileBusyError,
    ProjectSaveDurabilityError,
    ProjectWriteConflictError,
    capture_project_file_revision,
    load_project_document_with_revision_info,
    project_file_revision_matches,
    save_project_document_guarded,
)
from .spatial_integrity import SPATIAL_METADATA_KEY


_RESULT_SCHEMA = "cleanroomx.ifc-cli-result"
_RESULT_SCHEMA_VERSION = 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-ifc",
        description=(
            "Safely import, review, and re-import IFC spatial semantics into a "
            "CleanroomX project."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser(
        "import",
        help="Create the initial IFC identity/provenance link.",
    )
    import_parser.add_argument("project", help="CleanroomX project file to update")
    import_parser.add_argument("ifc", help="IFC source file")
    import_parser.add_argument(
        "--replace-existing-layout",
        action="store_true",
        help=(
            "Allow the initial IFC import to replace pre-existing unlinked spatial "
            "metadata. Existing IFC links still require reimport."
        ),
    )

    plan_parser = subparsers.add_parser(
        "plan",
        help="Plan a conflict-aware IFC re-import without changing the project.",
    )
    plan_parser.add_argument("project", help="CleanroomX project file")
    plan_parser.add_argument("ifc", help="Revised IFC source file")

    reimport_parser = subparsers.add_parser(
        "reimport",
        help="Apply a conflict-free IFC re-import and save it atomically.",
    )
    reimport_parser.add_argument("project", help="CleanroomX project file to update")
    reimport_parser.add_argument("ifc", help="Revised IFC source file")
    return parser


def _load_current_project(path: Path):
    project, revision, migration = load_project_document_with_revision_info(path)
    if migration.migrated:
        raise CliStateError(
            "refusing to update a migrated legacy project in place; "
            "open and save it as a current-schema CleanroomX project first"
        )
    return project, revision


def _extract(path: Path) -> tuple[dict, dict[str, str]]:
    semantics, provenance = extract_ifc_semantics(path)
    if provenance.get("source_name") != path.name:
        raise IfcImportError("IFC provenance source_name does not match the input file")
    return semantics, provenance


def _revision_payload(revision) -> dict:
    return {
        "size_bytes": revision.size,
        "sha256": revision.sha256,
    }


def _emit(payload: dict) -> None:
    sys.stdout.write(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def _base_result(
    *,
    action: str,
    project_path: Path,
    ifc_path: Path,
    project_revision,
    provenance: dict[str, str],
) -> dict:
    return {
        "schema": _RESULT_SCHEMA,
        "schema_version": _RESULT_SCHEMA_VERSION,
        "action": action,
        "project": str(project_path),
        "ifc_source": str(ifc_path),
        "ifc_source_sha256": provenance["source_sha256"],
        "project_revision_before": _revision_payload(project_revision),
    }


def _initial_import(args) -> int:
    project_path = resolve_cli_path(args.project, label="project")
    ifc_path = resolve_cli_path(args.ifc, label="IFC source")
    project, revision = _load_current_project(project_path)

    if IFC_LINK_METADATA_KEY in project.metadata:
        raise IfcImportError(
            "project already contains an IFC identity link; use 'cleanroomx-ifc "
            "plan' and 'cleanroomx-ifc reimport' instead of resetting the baseline"
        )
    if (
        SPATIAL_METADATA_KEY in project.metadata
        and not args.replace_existing_layout
    ):
        raise IfcImportError(
            "project already contains spatial_layout metadata; initial IFC import "
            "would replace it. Re-run with --replace-existing-layout only if that "
            "replacement is intentional"
        )

    semantics, provenance = _extract(ifc_path)
    layout = apply_ifc_semantics_to_project(
        project,
        semantics,
        source_name=provenance["source_name"],
        source_sha256=provenance["source_sha256"],
    )
    _, saved_revision = save_project_document_guarded(
        project_path,
        project,
        expected_revision=revision,
    )

    result = _base_result(
        action="import",
        project_path=project_path,
        ifc_path=ifc_path,
        project_revision=revision,
        provenance=provenance,
    )
    result.update(
        {
            "semantic_sha256": semantics["semantic_sha256"],
            "room_count": len(layout["rooms"]),
            "device_count": len(layout["devices"]),
            "project_revision_after": _revision_payload(saved_revision),
        }
    )
    _emit(result)
    return 0


def _plan(args) -> int:
    project_path = resolve_cli_path(args.project, label="project")
    ifc_path = resolve_cli_path(args.ifc, label="IFC source")
    project, revision = _load_current_project(project_path)
    semantics, provenance = _extract(ifc_path)
    report = plan_ifc_semantic_reimport(
        project,
        semantics,
        source_name=provenance["source_name"],
        source_sha256=provenance["source_sha256"],
    )

    current_revision = capture_project_file_revision(project_path)
    if not project_file_revision_matches(revision, current_revision):
        raise CliStateError(
            "project file changed during IFC re-import planning; plan was discarded"
        )

    result = _base_result(
        action="plan",
        project_path=project_path,
        ifc_path=ifc_path,
        project_revision=current_revision,
        provenance=provenance,
    )
    result["plan"] = report
    _emit(result)
    return 0 if report["can_apply"] else 1


def _reimport(args) -> int:
    project_path = resolve_cli_path(args.project, label="project")
    ifc_path = resolve_cli_path(args.ifc, label="IFC source")
    project, revision = _load_current_project(project_path)
    semantics, provenance = _extract(ifc_path)
    report = reimport_ifc_semantics_to_project(
        project,
        semantics,
        source_name=provenance["source_name"],
        source_sha256=provenance["source_sha256"],
    )
    _, saved_revision = save_project_document_guarded(
        project_path,
        project,
        expected_revision=revision,
    )

    result = _base_result(
        action="reimport",
        project_path=project_path,
        ifc_path=ifc_path,
        project_revision=revision,
        provenance=provenance,
    )
    result["plan"] = report
    result["project_revision_after"] = _revision_payload(saved_revision)
    _emit(result)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "import":
            return _initial_import(args)
        if args.command == "plan":
            return _plan(args)
        if args.command == "reimport":
            return _reimport(args)
        raise RuntimeError(f"unsupported IFC command: {args.command}")
    except (
        OSError,
        CliStateError,
        ProjectFileBusyError,
        ProjectSaveDurabilityError,
        ProjectWriteConflictError,
        ValueError,
    ) as exc:
        print(f"cleanroomx-ifc: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
