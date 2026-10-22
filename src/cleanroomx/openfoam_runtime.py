"""Read-only OpenFOAM environment discovery, independent of the working directory.

Directory names are hints, not verified runtime versions. Discovery never
sources shell scripts. The existing runner must still verify executables and
the actual simpleFoam identity before executing any case.
"""
from __future__ import annotations

import argparse
import json
from itertools import islice
import os
from pathlib import Path
import re
import sys
from typing import Mapping, Sequence

ENVIRONMENT_VARIABLE = "CLEANROOMX_OPENFOAM_BASHRC"
INSTALLATION_GUIDE = "https://openfoam.org/download/10-ubuntu/"
WSL_GUIDE = "https://openfoam.org/download/windows/"
_RELEASE = re.compile(r"openfoam[-_]?v?([0-9]+|dev)\Z", re.IGNORECASE)
_DEFAULT_ROOTS = ("/opt", "/usr/lib/openfoam", "/usr/share/openfoam", "/usr/share", "/usr/local")
_MAX_ENTRIES_PER_ROOT = 512


def discover_openfoam_environments(
    *, env: Mapping[str, str] | None = None,
    search_roots: Sequence[str | Path] | None = None,
    home: Path | None = None,
) -> dict:
    """Inspect bounded, nonrecursive installation locations without executing them.

    An explicit override is authoritative: a bad override never silently falls
    back to another installation. Only v10 directory hints (or an explicit
    choice) are eligible; actual compatibility is checked after sourcing.
    """
    environment = os.environ if env is None else env
    roots = [Path(p) for p in (_DEFAULT_ROOTS if search_roots is None else search_roots)]
    roots.append((Path.home() if home is None else home) / "OpenFOAM")
    candidates: list[tuple[Path, str]] = []
    issues = []
    override = environment.get(ENVIRONMENT_VARIABLE, "").strip()
    if override:
        candidates.append((Path(override).expanduser(), "explicit_override"))
    active = environment.get("WM_PROJECT_DIR", "").strip()
    if active:
        candidates.append((Path(active).expanduser() / "etc/bashrc", "active_environment"))
    for root in roots:
        candidates.append((root / "etc/bashrc", "installation_directory"))
        try:
            # Inspect a fixed root one level deep; never walk drives or cases.
            children = list(islice(root.iterdir(), _MAX_ENTRIES_PER_ROOT + 1))
            if len(children) > _MAX_ENTRIES_PER_ROOT:
                issues.append(f"Inspection limit reached in {root}; configure an explicit bashrc path.")
            for child in sorted(children[:_MAX_ENTRIES_PER_ROOT]):
                if _RELEASE.fullmatch(child.name):
                    candidates.append((child / "etc/bashrc", "installation_directory"))
        except OSError as exc:
            if root.exists():
                issues.append(f"Cannot inspect {root}: {exc}")
    discovered = []
    seen = set()
    for path, origin in candidates:
        try:
            if not path.is_file():
                continue
            absolute = str(path.resolve())
        except OSError as exc:
            issues.append(f"Cannot inspect {path}: {exc}")
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        hint = _RELEASE.fullmatch(path.parent.parent.name)
        release = hint.group(1).lower() if hint else None
        # A custom active path requires its declared version as an additional
        # hint. It still cannot bypass the real executable version check.
        if release is None and origin == "active_environment":
            release = environment.get("WM_PROJECT_VERSION") or None
        discovered.append({
            "bashrc": absolute, "origin": origin, "release_hint": release,
            "runtime_verified": False,
        })
    selected = None
    error = None
    if override:
        explicit = next((x for x in discovered if x["origin"] == "explicit_override"), None)
        if not Path(override).expanduser().is_absolute():
            error = f"{ENVIRONMENT_VARIABLE} must be an absolute Linux path: {override}"
        elif explicit is None:
            error = f"Configured OpenFOAM environment is missing or unreadable: {override}"
        else:
            selected = explicit["bashrc"]
    else:
        match = next((x for x in discovered if x["release_hint"] == "10"), None)
        if match:
            selected = match["bashrc"]
        else:
            error = "No candidate Foundation v10 environment found in the inspected locations."
    return {
        "schema": "cleanroomx.openfoam-environments.v1",
        "case_runtime_requirement": "OpenFOAM Foundation v10 / simpleFoam",
        "searched_roots": [str(p) for p in roots],
        "environments": discovered, "selected_bashrc": selected,
        "selection_error": error, "inspection_issues": issues,
        "runtime_verified": False,
        "remediation": (
            f"Set {ENVIRONMENT_VARIABLE} to the absolute Linux etc/bashrc path "
            "for your installation, then probe it. Current case templates require "
            "Foundation v10; another detected release is not automatically compatible. "
            f"Installation: {INSTALLATION_GUIDE} WSL: {WSL_GUIDE}"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--select", action="store_true", help="Print an eligible bashrc path or fail")
    group.add_argument("--json", action="store_true", help="Print the discovery inventory (default)")
    args = parser.parse_args(argv)
    report = discover_openfoam_environments()
    if args.select:
        if report["selection_error"]:
            print(report["selection_error"], file=sys.stderr)
            for candidate in report["environments"]:
                print(f"Detected unverified environment: {candidate['bashrc']} "
                      f"(release hint {candidate['release_hint']})", file=sys.stderr)
            print(report["remediation"], file=sys.stderr)
            return 2
        print(report["selected_bashrc"])
    else:
        print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
