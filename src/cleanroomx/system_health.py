from __future__ import annotations

import copy
from importlib import import_module
from pathlib import Path
import platform
import sys
import tempfile
from typing import Any

from . import __version__
from .application import run_analysis, validate_application_registry
from .persistence import atomic_write_text
from .project import load_project_document


QUALIFIED_PYTHON_MINORS = ((3, 11), (3, 12), (3, 13))


def _check(
    check_id: str,
    label: str,
    *,
    required: bool,
    status: str,
    summary: str,
    details: dict[str, Any] | None = None,
    remediation: str | None = None,
) -> dict[str, Any]:
    if status not in {"pass", "warn", "fail"}:
        raise ValueError(f"unsupported system-health status: {status}")
    if status == "pass":
        if remediation is not None:
            raise ValueError("passing system-health checks must not include remediation")
    elif not isinstance(remediation, str) or not remediation.strip():
        raise ValueError("non-passing system-health checks require remediation")
    return {
        "id": check_id,
        "label": label,
        "required": bool(required),
        "status": status,
        "summary": summary,
        "details": {} if details is None else details,
        "remediation": remediation,
    }


def _python_runtime_check() -> dict[str, Any]:
    version = sys.version_info
    ready = version >= (3, 11)
    return _check(
        "python-runtime",
        "Python runtime",
        required=True,
        status="pass" if ready else "fail",
        summary=(
            f"Python {platform.python_version()} satisfies the package requirement >=3.11."
            if ready
            else f"Python {platform.python_version()} is below the package requirement >=3.11."
        ),
        details={
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
        },
        remediation=(
            None
            if ready
            else "Install a supported Python runtime (3.11 or newer) and reinstall CleanroomX into that environment."
        ),
    )


def _python_qualification_check() -> dict[str, Any]:
    minor = tuple(sys.version_info[:2])
    qualified = minor in QUALIFIED_PYTHON_MINORS
    matrix = [f"{major}.{minor_version}" for major, minor_version in QUALIFIED_PYTHON_MINORS]
    return _check(
        "python-release-qualification",
        "Python release qualification",
        required=False,
        status="pass" if qualified else "warn",
        summary=(
            f"Python {minor[0]}.{minor[1]} is in the current release qualification matrix."
            if qualified
            else (
                f"Python {minor[0]}.{minor[1]} satisfies package metadata but is outside "
                "the current release qualification matrix."
            )
        ),
        details={"qualified_minors": matrix},
        remediation=(
            None
            if qualified
            else "For release-qualified operation, run CleanroomX on Python 3.11, 3.12, or 3.13."
        ),
    )


def _registry_checks() -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        registry = validate_application_registry()
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        registry_check = _check(
            "application-registry",
            "Application registry",
            required=True,
            status="fail",
            summary="The analysis registry could not be validated.",
            details={"error_type": type(exc).__name__, "error": str(exc)},
            remediation="Reinstall the CleanroomX package/artifact, then rerun cleanroomx-doctor to verify the built-in analysis registry.",
        )
        plugin_check = _check(
            "plugin-discovery",
            "Analysis plugins",
            required=False,
            status="warn",
            summary="Plugin discovery could not be evaluated because registry validation failed.",
            details={},
            remediation="Resolve the application-registry failure first; plugin readiness cannot be assessed until the registry loads.",
        )
        return registry_check, plugin_check

    registry_ok = registry.get("status") == "ok"
    registry_check = _check(
        "application-registry",
        "Application registry",
        required=True,
        status="pass" if registry_ok else "fail",
        summary=(
            f"{registry.get('analysis_count', 0)} analysis bindings validated."
            if registry_ok
            else "The application registry reported a non-ready state."
        ),
        details={
            "analysis_count": registry.get("analysis_count"),
            "builtin_analysis_count": registry.get("builtin_analysis_count"),
            "plugin_analysis_count": registry.get("plugin_analysis_count"),
            "callable_target_count": registry.get("callable_target_count"),
        },
        remediation=(
            None
            if registry_ok
            else "Inspect the registry validation result, repair or reinstall the affected CleanroomX package/plugin components, then rerun cleanroomx-doctor."
        ),
    )

    issue_count = int(registry.get("plugin_issue_count", 0))
    plugin_check = _check(
        "plugin-discovery",
        "Analysis plugins",
        required=False,
        status="warn" if issue_count else "pass",
        summary=(
            f"{issue_count} installed plugin issue(s) were isolated; built-in analyses remain available."
            if issue_count
            else "No plugin discovery issues were reported."
        ),
        details={
            "plugin_analysis_count": registry.get("plugin_analysis_count"),
            "plugin_issue_count": issue_count,
            "plugin_issues": registry.get("plugin_issues", []),
        },
        remediation=(
            "Review the reported plugin issues and update, repair, or remove the affected plugin packages."
            if issue_count
            else None
        ),
    )
    return registry_check, plugin_check


def _tk_check() -> dict[str, Any]:
    try:
        tkinter = import_module("tkinter")
    except (ImportError, OSError) as exc:
        return _check(
            "tk-runtime",
            "Tk desktop runtime",
            required=True,
            status="fail",
            summary="Tkinter could not be imported; the desktop application cannot start.",
            details={"error_type": type(exc).__name__, "error": str(exc)},
            remediation="Install or repair the Python Tk/Tcl runtime required by the CleanroomX desktop application.",
        )

    tcl_error = getattr(tkinter, "TclError", RuntimeError)
    try:
        interpreter = tkinter.Tcl()
        tcl_patchlevel = str(interpreter.eval("info patchlevel"))
    except (AttributeError, OSError, RuntimeError, tcl_error) as exc:
        return _check(
            "tk-runtime",
            "Tk desktop runtime",
            required=True,
            status="fail",
            summary=(
                "Tkinter imported, but the Tcl interpreter could not be initialized; "
                "the desktop runtime is not ready."
            ),
            details={
                "tk_version": str(getattr(tkinter, "TkVersion", "unknown")),
                "tcl_version": str(getattr(tkinter, "TclVersion", "unknown")),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "display_probe_performed": False,
            },
            remediation="Repair the Python Tk/Tcl installation, then rerun the health check before launching the desktop application.",
        )

    return _check(
        "tk-runtime",
        "Tk desktop runtime",
        required=True,
        status="pass",
        summary="Tkinter imported and the Tcl interpreter initialized successfully.",
        details={
            "tk_version": str(getattr(tkinter, "TkVersion", "unknown")),
            "tcl_version": str(getattr(tkinter, "TclVersion", "unknown")),
            "tcl_patchlevel": tcl_patchlevel,
            "display_probe_performed": False,
        },
    )


def _desktop_display_check() -> dict[str, Any]:
    """Create and destroy a hidden Tk root to prove the desktop display path."""
    try:
        tkinter = import_module("tkinter")
    except (ImportError, OSError) as exc:
        return _check(
            "desktop-display",
            "Tk desktop display",
            required=True,
            status="fail",
            summary="Tkinter could not be imported; the desktop display cannot initialize.",
            details={
                "display_probe_performed": True,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
            remediation="Install or repair the Python Tk/Tcl runtime before requiring desktop-display readiness.",
        )

    tcl_error = getattr(tkinter, "TclError", RuntimeError)
    root = None
    try:
        root = tkinter.Tk()
        root.withdraw()
        root.update_idletasks()
        root.destroy()
        root = None
    except (AttributeError, OSError, RuntimeError, tcl_error) as exc:
        if root is not None:
            try:
                root.destroy()
            except (AttributeError, OSError, RuntimeError, tcl_error):
                pass
        return _check(
            "desktop-display",
            "Tk desktop display",
            required=True,
            status="fail",
            summary="A hidden Tk desktop root could not complete its initialization lifecycle.",
            details={
                "display_probe_performed": True,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
            remediation="Verify that a graphical display session is available and that the native Tk libraries can create a window, then rerun with --require-desktop.",
        )

    return _check(
        "desktop-display",
        "Tk desktop display",
        required=True,
        status="pass",
        summary="A hidden Tk desktop root initialized, settled idle layout work, and closed cleanly.",
        details={"display_probe_performed": True},
    )


def _packaged_demo_check() -> dict[str, Any]:
    path = Path(__file__).resolve().parent / "demo" / "gui_demo.cleanroomx.json"
    try:
        project = load_project_document(path)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError) as exc:
        return _check(
            "packaged-demo",
            "Packaged demonstration project",
            required=True,
            status="fail",
            summary="The packaged demonstration project could not be loaded.",
            details={
                "path": str(path),
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
            remediation="Reinstall the CleanroomX package/artifact so the packaged demonstration project and companion data are restored.",
        )

    analysis_count = len(project.analyses)
    if analysis_count < 1:
        return _check(
            "packaged-demo",
            "Packaged demonstration project",
            required=True,
            status="fail",
            summary="The packaged demonstration project contains no analyses.",
            details={"path": str(path), "analysis_count": analysis_count},
            remediation="Reinstall the CleanroomX package/artifact; the packaged demonstration project is incomplete.",
        )

    return _check(
        "packaged-demo",
        "Packaged demonstration project",
        required=True,
        status="pass",
        summary=f"Packaged demonstration project loaded with {analysis_count} analysis workflow(s).",
        details={
            "path": str(path),
            "project_name": project.name,
            "analysis_count": analysis_count,
        },
    )



def _demo_analysis_check() -> dict[str, Any]:
    """Execute one packaged demo analysis without mutating the loaded project."""
    path = Path(__file__).resolve().parent / "demo" / "gui_demo.cleanroomx.json"
    try:
        project = load_project_document(path)
        analysis_id = project.active_analysis_id
        if not analysis_id:
            return _check(
                "packaged-demo-analysis",
                "Packaged demo analysis",
                required=True,
                status="fail",
                summary="The packaged demonstration project has no active analysis.",
                details={"path": str(path)},
                remediation="Reinstall the CleanroomX package/artifact so the packaged demo metadata is restored.",
            )
        analysis = project.analysis_by_id(analysis_id)
        original_input = copy.deepcopy(analysis.input)
        run = run_analysis(
            analysis.kind,
            copy.deepcopy(analysis.input),
            base_dir=path.parent,
        )
        if analysis.input != original_input:
            return _check(
                "packaged-demo-analysis",
                "Packaged demo analysis",
                required=True,
                status="fail",
                summary="The deep health probe detected unexpected project-input mutation.",
                details={
                    "path": str(path),
                    "analysis_id": analysis.id,
                    "analysis_kind": analysis.kind,
                },
                remediation="Treat this as a runtime-integrity failure; capture the doctor report and avoid relying on the affected analysis path until investigated.",
            )
    except (ImportError, OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return _check(
            "packaged-demo-analysis",
            "Packaged demo analysis",
            required=True,
            status="fail",
            summary="The packaged demo active analysis could not execute end-to-end.",
            details={
                "path": str(path),
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
            remediation="Run the shallow doctor first, then inspect the reported exception and repair or reinstall the affected analysis/runtime dependency.",
        )

    if not isinstance(run.result, dict) or not run.result:
        return _check(
            "packaged-demo-analysis",
            "Packaged demo analysis",
            required=True,
            status="fail",
            summary="The packaged demo active analysis completed without a result payload.",
            details={
                "path": str(path),
                "analysis_id": analysis.id,
                "analysis_kind": analysis.kind,
            },
            remediation="Capture the report and investigate the packaged demo analysis runner; a successful execution must return a non-empty result payload.",
        )

    return _check(
        "packaged-demo-analysis",
        "Packaged demo analysis",
        required=True,
        status="pass",
        summary=(
            f"Active demo analysis {analysis.id!r} executed successfully "
            f"with engineering status {run.status!r}."
        ),
        details={
            "path": str(path),
            "analysis_id": analysis.id,
            "analysis_kind": analysis.kind,
            "engineering_status": run.status,
            "result_key_count": len(run.result),
        },
    )

def _persistence_check() -> dict[str, Any]:
    try:
        with tempfile.TemporaryDirectory(prefix="cleanroomx-doctor-") as directory:
            target = Path(directory) / "atomic-write-probe.txt"
            expected = "cleanroomx-doctor\n"
            atomic_write_text(target, expected)
            observed = target.read_text(encoding="utf-8")
            if observed != expected:
                return _check(
                    "atomic-persistence",
                    "Atomic persistence",
                    required=True,
                    status="fail",
                    summary="Atomic persistence probe completed with unexpected content.",
                    details={"bytes_expected": len(expected), "bytes_observed": len(observed)},
                    remediation="Verify local temporary-storage integrity and filesystem behavior before relying on project persistence.",
                )
    except OSError as exc:
        return _check(
            "atomic-persistence",
            "Atomic persistence",
            required=True,
            status="fail",
            summary="Atomic persistence probe failed.",
            details={"error_type": type(exc).__name__, "error": str(exc)},
            remediation="Verify write permissions, available disk space, antivirus/file-locking behavior, and temporary-directory access.",
        )

    return _check(
        "atomic-persistence",
        "Atomic persistence",
        required=True,
        status="pass",
        summary="Atomic create/read persistence probe passed.",
        details={},
    )


def _bim_check(*, required: bool) -> dict[str, Any]:
    try:
        module = import_module("ifcopenshell")
    except (ImportError, OSError, RuntimeError) as exc:
        return _check(
            "native-bim",
            "Native IFC/BIM runtime",
            required=required,
            status="fail" if required else "warn",
            summary=(
                "IfcOpenShell is required but unavailable or unloadable."
                if required
                else "IfcOpenShell is not available; IFC/BIM workflows are optional for this check."
            ),
            details={"available": False, "error_type": type(exc).__name__, "error": str(exc)},
            remediation='Install or repair the qualified BIM dependency, for example: python -m pip install "cleanroomx[bim]".',
        )

    version = getattr(module, "__version__", None)
    if version is None:
        version = getattr(module, "version", None)
    return _check(
        "native-bim",
        "Native IFC/BIM runtime",
        required=required,
        status="pass",
        summary="IfcOpenShell imported successfully.",
        details={"available": True, "version": None if version is None else str(version)},
    )


def build_system_health_report(*, require_bim: bool = False, require_desktop: bool = False, deep: bool = False) -> dict[str, Any]:
    """Build a deterministic, non-mutating CleanroomX workstation health report."""
    registry_check, plugin_check = _registry_checks()
    checks = [
        _python_runtime_check(),
        _python_qualification_check(),
        registry_check,
        plugin_check,
        _tk_check(),
    ]
    if require_desktop:
        checks.append(_desktop_display_check())
    checks.append(_packaged_demo_check())
    if deep:
        checks.append(_demo_analysis_check())
    checks.extend(
        [
            _persistence_check(),
            _bim_check(required=require_bim),
        ]
    )

    counts = {
        status: sum(1 for item in checks if item["status"] == status)
        for status in ("pass", "warn", "fail")
    }
    required_ready = not any(
        item["required"] and item["status"] == "fail"
        for item in checks
    )
    status = (
        "not_ready"
        if not required_ready
        else "ready_with_warnings"
        if counts["warn"]
        else "ready"
    )
    return {
        "schema": "cleanroomx.system-health",
        "schema_version": 1,
        "application": {
            "name": "CleanroomX",
            "version": __version__,
        },
        "runtime": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "status": status,
        "required_ready": required_ready,
        "require_bim": bool(require_bim),
        "require_desktop": bool(require_desktop),
        "deep": bool(deep),
        "summary": {
            **counts,
            "check_count": len(checks),
        },
        "checks": checks,
    }
