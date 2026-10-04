from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from .cli_output import CliStateError
from .project import (
    atomic_write_text,
    capture_project_file_revision,
    load_project_document_with_revision,
    project_file_revision_matches,
)
from .project_diagnostics_cli import (
    _assert_project_output_is_safe,
    _assert_project_publication_safe,
)
from .project_dossier import (
    build_project_engineering_dossier,
    markdown_project_engineering_dossier,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-project-dossier",
        description=(
            "Generate a deterministic project-native engineering dossier from a "
            "saved CleanroomX project."
        ),
    )
    parser.add_argument("project", help="CleanroomX project file")
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        dest="output_format",
        help="Output format (default: json)",
    )
    parser.add_argument(
        "--output",
        help="Write the dossier atomically to this path instead of stdout",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = Path(args.project).expanduser().resolve(strict=False)
    try:
        project, revision_before = load_project_document_with_revision(source)
        if args.output:
            _assert_project_output_is_safe(
                project,
                source=source,
                output=args.output,
            )

        dossier = build_project_engineering_dossier(
            project,
            source_project_revision=revision_before.sha256,
            base_dir=source.parent,
        )
        text = (
            json.dumps(
                dossier,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
            if args.output_format == "json"
            else markdown_project_engineering_dossier(dossier)
        )

        revision_after = capture_project_file_revision(source)
        if not project_file_revision_matches(revision_before, revision_after):
            raise CliStateError(
                "project file changed during dossier generation; output was discarded"
            )

        if args.output:
            _assert_project_publication_safe(
                project,
                source=source,
                revision=revision_before,
                output=args.output,
                output_guard=_assert_project_output_is_safe,
            )
            atomic_write_text(
                args.output,
                text,
                before_replace=lambda: _assert_project_publication_safe(
                    project,
                    source=source,
                    revision=revision_before,
                    output=args.output,
                    output_guard=_assert_project_output_is_safe,
                ),
            )
        else:
            sys.stdout.write(text)
        return 0
    except (OSError, CliStateError, ValueError) as exc:
        print(f"cleanroomx-project-dossier: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
