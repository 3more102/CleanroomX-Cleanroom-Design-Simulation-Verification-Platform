"""Fail-closed Windows -> WSL OpenFOAM Foundation v10 execution bridge.

The existing Windows GUI can generate a connected case locally. This opt-in
bridge runs that *same* case through the verified Linux solver workflow, with
recorded outputs staying in the shared Windows directory for GUI import.

This does not install OpenFOAM, claim numerical convergence or certify a room.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Callable

_DISTRO = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")

# Fixed Bash code: dynamic Windows paths, distro, and CLI inputs are passed as
# argv, never spliced into the shell source.
_WSL_ENTRYPOINT = r'''
set -euo pipefail
repo="$1"
case_dir="$2"
mode="$3"
timeout="$4"
foam_bashrc="${5:-}"
if [[ ! -f "$repo/scripts/with_openfoam10.sh" || ! -d "$repo/src/cleanroomx" ]]; then
    echo "CleanroomX repository is not accessible inside WSL: $repo" >&2
    exit 2
fi
cd "$repo"
export PYTHONPATH="$repo/src${PYTHONPATH:+:$PYTHONPATH}"
if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
    echo "CleanroomX requires Python 3.11+ inside the selected WSL distribution." >&2
    exit 2
fi
if [[ -n "$foam_bashrc" ]]; then
    export CLEANROOMX_OPENFOAM_BASHRC="$foam_bashrc"
fi
if [[ "$mode" == probe ]]; then
    exec bash "$repo/scripts/with_openfoam10.sh" python3 -c \
        'import cleanroomx.cfd_pipeline_cli; print("CleanroomX + OpenFOAM Foundation v10 probe: READY")'
elif [[ "$mode" == run ]]; then
    if [[ ! -d "$case_dir" || ! -f "$case_dir/manifest.json" ]]; then
        echo "Connected case directory or manifest unavailable inside WSL: $case_dir" >&2
        exit 2
    fi
    exec bash "$repo/scripts/with_openfoam10.sh" python3 -m \
        cleanroomx.cfd_pipeline_cli multizone-run "$case_dir" \
        --timeout-seconds "$timeout"
else
    echo "Unsupported CleanroomX bridge mode" >&2
    exit 2
fi
'''


def _validate_distribution(distribution: str) -> str:
    if not isinstance(distribution, str) or not _DISTRO.fullmatch(distribution):
        raise ValueError("WSL distribution must be a simple installed distribution name")
    return distribution


def _existing_directory(path: str | Path, description: str) -> Path:
    location = Path(path).expanduser().resolve(strict=True)
    if not location.is_dir():
        raise ValueError(f"{description} is not a directory: {location}")
    return location


def _convert_to_wsl(path: Path, distribution: str, *, executable: str) -> str:
    """Ask the selected installed WSL distribution to translate a Windows path."""
    process = subprocess.run(
        [executable, "--distribution", distribution, "--exec", "wslpath",
         "-a", "-u", str(path)],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if process.returncode:
        detail=(process.stderr or process.stdout or "").strip()
        raise RuntimeError(f"WSL path conversion failed for {path}: {detail}")
    lines=process.stdout.splitlines()
    if (len(lines)!=1 or not lines[0].startswith("/") or
            any(ord(ch)<32 or ord(ch)==127 for ch in lines[0])):
        raise RuntimeError("WSL returned an invalid Unix path; refusing to execute")
    return lines[0]


def run_wsl_bridge(
    *, repository: str | Path, distribution: str = "Ubuntu",
    mode: str = "probe", case_directory: str | Path | None = None,
    timeout_seconds: int = 3600, executable: str = "wsl.exe",
    openfoam_bashrc: str | None = None,
    diagnostic_callback: Callable[[str], None] | None = None,
) -> int:
    """Execute a verified native Linux OpenFOAM run from Windows.

    No solver success is inferred from process start: the original
    multizone-run command verifies its own input hashes, runtime, and stages.
    """
    if os.name != "nt":
        raise RuntimeError("The Windows-to-WSL bridge must run on Windows")
    distro = _validate_distribution(distribution)
    if mode not in ("probe", "run"):
        raise ValueError("Mode must be probe or run")
    if type(timeout_seconds) is not int or not 60 <= timeout_seconds <= 86400:
        raise ValueError("timeout_seconds must be an integer in [60,86400]")
    if not executable or not isinstance(executable, str):
        raise ValueError("A WSL executable is required")
    if openfoam_bashrc is not None and (
        not isinstance(openfoam_bashrc, str) or not openfoam_bashrc.startswith("/")
        or any(ord(ch)<32 or ord(ch)==127 for ch in openfoam_bashrc)
    ):
        raise ValueError("OpenFOAM bashrc must be an absolute Linux path inside WSL (for example /mnt/d/OpenFOAM/OpenFOAM-10/etc/bashrc)")

    repo = _existing_directory(repository, "Repository")
    if not (repo / "scripts" / "with_openfoam10.sh").is_file() or not (
        repo / "src" / "cleanroomx"
    ).is_dir():
        raise ValueError("Repository must contain scripts/with_openfoam10.sh and src/cleanroomx")
    if mode == "run":
        if case_directory is None:
            raise ValueError("Run mode requires --case-directory")
        case = _existing_directory(case_directory, "Connected CFD case")
        if not (case / "manifest.json").is_file():
            raise ValueError("Connected CFD case manifest.json is missing")
    elif case_directory is not None:
        raise ValueError("Probe mode must not specify a case directory")
    else:
        case = repo

    linux_repo = _convert_to_wsl(repo, distro, executable=executable)
    linux_case = (linux_repo if mode == "probe" else
                  _convert_to_wsl(case, distro, executable=executable))
    # bash -c uses argv[0] as $0, then argv[1..] as $1,...; all user paths
    # remain distinct arguments even if they contain spaces or shell syntax.
    command = [
        executable, "--distribution", distro, "--exec", "bash", "-c",
        _WSL_ENTRYPOINT, "cleanroomx-wsl-bridge",
        linux_repo, linux_case, mode, str(timeout_seconds),
    ]
    if openfoam_bashrc is not None:
        command.append(openfoam_bashrc)
    # Four OpenFOAM stages each use timeout_seconds in the Linux runner.
    # Bound the outer WSL handoff as well; a hung distro startup cannot leave
    # the GUI worker blocked indefinitely.
    overall_timeout = 180 if mode=="probe" else 4*timeout_seconds+180
    if diagnostic_callback is None:
        return subprocess.run(command, check=False, timeout=overall_timeout).returncode
    # A file avoids holding unbounded WSL startup/solver chatter in memory.
    # The GUI receives actual diagnostics, including on timeouts, on its queue.
    with tempfile.TemporaryFile() as output:
        try:
            return subprocess.run(
                command, check=False, timeout=overall_timeout,
                stdout=output, stderr=subprocess.STDOUT,
            ).returncode
        finally:
            size = output.tell()
            output.seek(max(0, size - 64*1024))
            detail = output.read().decode("utf-8", errors="replace")
            if detail:
                diagnostic_callback(("[Earlier diagnostics truncated]\n" if size>64*1024 else "") + detail)


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(
        description="Run an existing CleanroomX connected CFD case in a verified WSL Foundation v10 environment"
    )
    parser.add_argument("--mode", choices=("probe", "run"), default="probe")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--case-directory")
    parser.add_argument("--distribution", default="Ubuntu")
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    parser.add_argument("--openfoam-bashrc", help="Optional absolute Linux etc/bashrc path inside WSL; otherwise discover installations")
    args=parser.parse_args(argv)
    try:
        return run_wsl_bridge(
            repository=args.repository, distribution=args.distribution,
            mode=args.mode, case_directory=args.case_directory,
            timeout_seconds=args.timeout_seconds,
            openfoam_bashrc=args.openfoam_bashrc,
        )
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"CleanroomX WSL bridge: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
