from __future__ import annotations

import argparse
import json
import sys

from .project import ProjectFormatError
from .project_bundle import (
    ProjectBundleError,
    export_project_bundle_from_path,
    extract_project_bundle,
    inspect_project_bundle,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-project-bundle",
        description=(
            "Create, verify, or extract self-contained CleanroomX project bundles "
            "with SHA-256 dependency integrity."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    export_parser = sub.add_parser(
        "export",
        help="Package a saved project and its external analysis dependencies.",
    )
    export_parser.add_argument("project", help="CleanroomX project JSON file")
    export_parser.add_argument("bundle", help="Output .cleanroomx.zip bundle")

    verify_parser = sub.add_parser(
        "verify",
        help="Verify bundle structure, hashes, project schema, and references.",
    )
    verify_parser.add_argument("bundle", help="CleanroomX portable project bundle")

    extract_parser = sub.add_parser(
        "extract",
        help="Verify and extract a bundle into a new or empty directory.",
    )
    extract_parser.add_argument("bundle", help="CleanroomX portable project bundle")
    extract_parser.add_argument("destination", help="New or empty extraction directory")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "export":
            report = export_project_bundle_from_path(args.project, args.bundle)
        elif args.command == "verify":
            report = inspect_project_bundle(args.bundle)
        else:
            project_path = extract_project_bundle(args.bundle, args.destination)
            report = {
                "status": "extracted",
                "project_path": str(project_path),
            }
    except (OSError, ProjectFormatError, ProjectBundleError) as exc:
        print(f"CleanroomX project bundle error: {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            report,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
