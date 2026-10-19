"""Explicit Foundation v10 runtime selection for Linux and Windows WSL."""
from __future__ import annotations

import importlib.util
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys


DEFAULT_BASHRC = "/opt/openfoam10/etc/bashrc"


def runtime_report() -> dict:
    commands = {name: shutil.which(name) for name in ("blockMesh", "checkMesh", "simpleFoam", "foamToVTK")}
    vtk_available = importlib.util.find_spec("vtk") is not None
    environment = os.environ.get("WM_PROJECT") == "OpenFOAM" and os.environ.get("WM_PROJECT_VERSION") == "10"
    issues = [f"Missing executable: {name}" for name, path in commands.items() if path is None]
    if not environment:
        issues.append("Source OpenFOAM Foundation v10 etc/bashrc (WM_PROJECT=OpenFOAM, WM_PROJECT_VERSION=10)")
    if not vtk_available:
        issues.append("Install vtk in the solver Python environment: python3 -m pip install vtk")
    launch_check = None
    if commands["blockMesh"] and environment:
        try:
            probe = subprocess.run([commands["blockMesh"], "-help"], capture_output=True, text=True, timeout=10)
            launch_check = {"program": "blockMesh -help", "returncode": probe.returncode}
            if probe.returncode:
                issues.append("blockMesh cannot start: " + (probe.stderr or probe.stdout)[-500:])
        except (OSError, subprocess.SubprocessError) as exc:
            launch_check = {"program": "blockMesh -help", "error": str(exc)}
            issues.append("blockMesh cannot start: " + str(exc))
    return {"schema_version": "cleanroomx.openfoam-runtime.v1", "status": "ready" if not issues else "unavailable",
            "project": os.environ.get("WM_PROJECT"), "release": os.environ.get("WM_PROJECT_VERSION"),
            "executables": commands, "vtk_available": vtk_available, "python": sys.executable, "issues": issues,
            "launch_check": launch_check,
            "scope": "Runtime availability; executed stage banners must still verify Foundation v10"}


def runtime_command(command: list[str], *, mode: str = "auto", bashrc: str = "", distribution: str = "",
                    windows: bool | None = None, path_mapper=None, session_token: str | None = None,
                    wsl_python: str = "python3") -> list[str]:
    """Wrap only solver commands; pass paths through argv, never shell interpolation.

    WSL imports this exact installed Python package via the mounted host path.
    Its Python environment needs vtk; the host GUI keeps its own Tk/VTK runtime.
    """
    if mode not in ("auto", "native", "wsl"):
        raise ValueError("Runtime must be auto, native, or wsl")
    use_windows = os.name == "nt" if windows is None else windows
    use_wsl = mode == "wsl" or (mode == "auto" and use_windows)
    if not use_wsl:
        if not bashrc.strip():
            return list(command)
        path = Path(bashrc).expanduser().resolve(strict=True)
        if not path.is_file():
            raise ValueError("Choose the installed Foundation v10 etc/bashrc file")
        bash = shutil.which("bash")
        if not bash:
            raise ValueError("bash is required to load the OpenFOAM environment")
        return [bash, "--noprofile", "--norc", "-c", 'source "$1" >/dev/null && shift && exec "$@"',
                "cleanroomx", str(path), *command]
    wsl = shutil.which("wsl.exe")
    if not wsl:
        raise ValueError("WSL is unavailable. Install Foundation v10 in WSL or select a native Linux runtime")
    if not wsl_python.strip() or "\x00" in wsl_python:
        raise ValueError("Choose the WSL Python 3.11+ executable containing vtk")
    prefix = [wsl] + (["--distribution", distribution.strip()] if distribution.strip() else [])

    def mapped(path: str) -> str:
        if path_mapper is not None:
            return path_mapper(path)
        result = subprocess.run([*prefix, "--exec", "wslpath", "-a", "-u", path],
                                capture_output=True, text=True, timeout=15, check=False,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode or not result.stdout.strip().startswith("/"):
            raise ValueError("WSL cannot access this path: " + path)
        return result.stdout.strip()

    args = list(command[1:])
    # Builders pass: python -m cleanroomx.cfd_pipeline_cli COMMAND PATHS...
    subcommand = args[2] if len(args) > 2 else ""
    path_counts = {"run": 1, "two-room-run": 1, "sync-case": 2, "scalar-run": 1, "runtime-check": 0}
    if subcommand not in path_counts:
        raise ValueError("Unsupported WSL solver command")
    for index in range(3, 3 + path_counts[subcommand]):
        args[index] = mapped(str(Path(args[index]).resolve()))
    for flag in ("--sync-results", "--receipt-directory"):
        if flag in args:
            index = args.index(flag) + 1
            args[index] = mapped(str(Path(args[index]).resolve()))
    source_root = mapped(str(Path(__file__).resolve().parent.parent))
    script = ('source "$1" >/dev/null && export PYTHONPATH="$2${PYTHONPATH:+:$PYTHONPATH}" '
              '&& shift 2 && exec "$@"')
    if session_token is not None:
        if re.fullmatch(r"[0-9a-f]{32}", session_token) is None:
            raise ValueError("Invalid WSL process session token")
        script = f'printf "CLEANROOMX_WSL_PID:{session_token}:%s\\n" "$$"; ' + script
    return [*prefix, "--exec", "setsid", "bash", "--noprofile", "--norc", "-c", script, "cleanroomx",
            bashrc.strip() or DEFAULT_BASHRC, source_root, wsl_python.strip(), "-u", *args]


def wsl_stop_command(launch_command: list[str], process_group: int, *, force: bool = False) -> list[str]:
    """Signal the Linux process group, including solvers, before closing wsl.exe."""
    if type(process_group) is not int or not 1 < process_group < 2**31:
        raise ValueError("Invalid WSL process group")
    marker = launch_command.index("--exec")
    return [*launch_command[:marker], "--exec", "kill", "-KILL" if force else "-TERM", "--", f"-{process_group}"]
