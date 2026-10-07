from __future__ import annotations

import copy
from importlib import import_module
from importlib import metadata
from pathlib import Path, PurePosixPath, PureWindowsPath
import platform
import sys
import tempfile
from typing import Any

from . import __version__
from .application import run_analysis, validate_application_registry
from .persistence import atomic_write_text
from .project import load_project_document


QUALIFIED_PYTHON_MINORS = ((3, 11), (3, 12), (3, 13))
_LOCAL_PATH_DETAIL_KEYS = frozenset({"path", "executable"})


def _redacted_path_text(value: str) -> str:
    """Reduce Windows or POSIX path text to a basename-only support-safe form."""
    candidates = [
        PureWindowsPath(value).name,
        PurePosixPath(value).name,
    ]
    names = [name for name in candidates if name and name != value]
    name = min(names, key=len) if names else next(
        (candidate for candidate in candidates if candidate),
        "",
    )
    return f"<redacted>/{name}" if name else "<redacted>"


def _redact_path_fields(value: Any, *, key: str | None = None) -> Any:
    if isinstance(value, dict):
        return {
            item_key: _redact_path_fields(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_redact_path_fields(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_path_fields(item) for item in value)
    if (
        isinstance(value, str)
        and key is not None
        and (key in _LOCAL_PATH_DETAIL_KEYS or key.endswith("_path"))
    ):
        return _redacted_path_text(value)
    return value


def redact_system_health_paths(report: dict[str, Any]) -> dict[str, Any]:
    """Return a non-mutating copy with explicit local path fields redacted."""
    if not isinstance(report, dict):
        raise TypeError("system health report must be a dictionary")
    redacted = _redact_path_fields(report)
    redacted["privacy"] = {"local_paths_redacted": True}
    return redacted


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


def _python_qualification_check(*, required: bool = False) -> dict[str, Any]:
    minor = tuple(sys.version_info[:2])
    qualified = minor in QUALIFIED_PYTHON_MINORS
    matrix = [f"{major}.{minor_version}" for major, minor_version in QUALIFIED_PYTHON_MINORS]
    return _check(
        "python-release-qualification",
        "Python release qualification",
        required=required,
        status="pass" if qualified else ("fail" if required else "warn"),
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


def _distribution_identity_check(*, required: bool = False) -> dict[str, Any]:
    """Verify installed metadata, code origin, and distribution ownership."""
    module_path = Path(__file__).resolve()
    package_initializer_path = module_path.with_name("__init__.py")
    try:
        distribution_version = metadata.version("cleanroomx")
    except metadata.PackageNotFoundError:
        return _check(
            "distribution-identity",
            "Installed CleanroomX distribution",
            required=required,
            status="fail" if required else "warn",
            summary=(
                "CleanroomX distribution metadata is not available in the active Python environment."
            ),
            details={
                "metadata_available": False,
                "module_version": __version__,
                "distribution_version": None,
                "module_path": str(module_path),
                "package_initializer_path": str(package_initializer_path),
                "distribution_path": None,
                "origin_matches_distribution": None,
                "ownership_manifest_available": None,
                "module_owned_by_distribution": None,
                "package_initializer_owned_by_distribution": None,
            },
            remediation=(
                "Install CleanroomX into the active Python environment before release or deployment "
                "qualification, then rerun cleanroomx-doctor."
            ),
        )

    version_matches = distribution_version == __version__
    distribution_path: Path | None = None
    origin_matches_distribution: bool | None = None
    ownership_manifest_available: bool | None = None
    module_owned_by_distribution: bool | None = None
    package_initializer_owned_by_distribution: bool | None = None

    if version_matches:
        try:
            distribution = metadata.distribution("cleanroomx")
            distribution_path = Path(distribution.locate_file("")).resolve()
        except metadata.PackageNotFoundError:
            return _check(
                "distribution-identity",
                "Installed CleanroomX distribution",
                required=required,
                status="fail" if required else "warn",
                summary=(
                    "CleanroomX distribution metadata disappeared while its install origin "
                    "was being resolved."
                ),
                details={
                    "metadata_available": False,
                    "module_version": __version__,
                    "distribution_version": distribution_version,
                    "module_path": str(module_path),
                    "package_initializer_path": str(package_initializer_path),
                    "distribution_path": None,
                    "origin_matches_distribution": None,
                    "ownership_manifest_available": None,
                    "module_owned_by_distribution": None,
                    "package_initializer_owned_by_distribution": None,
                },
                remediation=(
                    "Repair or reinstall CleanroomX in the active Python environment, then rerun "
                    "cleanroomx-doctor before release or deployment qualification."
                ),
            )

        origin_matches_distribution = module_path.is_relative_to(distribution_path)
        distribution_files = distribution.files
        ownership_manifest_available = distribution_files is not None
        if distribution_files is not None:
            owned_paths = {
                Path(distribution.locate_file(file)).resolve()
                for file in distribution_files
            }
            module_owned_by_distribution = module_path in owned_paths
            package_initializer_owned_by_distribution = (
                package_initializer_path in owned_paths
            )

    consistent = (
        version_matches
        and origin_matches_distribution is True
        and module_owned_by_distribution is True
        and package_initializer_owned_by_distribution is True
    )
    if consistent:
        summary = (
            f"Imported CleanroomX {__version__} matches installed distribution metadata, "
            "originates from the installed distribution, and its active module and package "
            "initializer are owned by the distribution file manifest."
        )
        remediation = None
    elif not version_matches:
        summary = (
            f"Imported CleanroomX {__version__} does not match installed distribution "
            f"metadata {distribution_version}."
        )
        remediation = (
            "Reinstall CleanroomX into the active Python environment and remove stale or "
            "duplicate installations so imported code and distribution metadata agree."
        )
    elif origin_matches_distribution is not True:
        summary = (
            "Imported CleanroomX reports the installed distribution version, but its code "
            "origin is outside the installed distribution location."
        )
        remediation = (
            "Run CleanroomX from the intended installed environment and remove source-checkout, "
            "PYTHONPATH, or stale-package shadowing before release or deployment qualification."
        )
    elif ownership_manifest_available is False:
        summary = (
            "Imported CleanroomX is under the installed distribution location, but installed "
            "metadata does not expose a file ownership manifest."
        )
        remediation = (
            "Reinstall CleanroomX from a standard wheel or other installation that preserves "
            "distribution file metadata, then rerun cleanroomx-doctor before release qualification."
        )
    elif module_owned_by_distribution is not True:
        summary = (
            "Imported CleanroomX is under the installed distribution location, but the imported "
            "system-health module is not owned by the installed distribution file manifest."
        )
        remediation = (
            "Remove stray or shadowing CleanroomX modules and reinstall the intended distribution "
            "so the active system-health module is recorded as part of that installed artifact."
        )
    else:
        summary = (
            "The active CleanroomX system-health module is distribution-owned, but the package "
            "initializer that supplies package identity is not owned by the installed distribution."
        )
        remediation = (
            "Remove stray or shadowing CleanroomX package initializer files and reinstall the "
            "intended distribution so package identity and diagnostics come from the same artifact."
        )

    return _check(
        "distribution-identity",
        "Installed CleanroomX distribution",
        required=required,
        status="pass" if consistent else ("fail" if required else "warn"),
        summary=summary,
        details={
            "metadata_available": True,
            "module_version": __version__,
            "distribution_version": distribution_version,
            "module_path": str(module_path),
            "package_initializer_path": str(package_initializer_path),
            "distribution_path": (
                None if distribution_path is None else str(distribution_path)
            ),
            "origin_matches_distribution": origin_matches_distribution,
            "ownership_manifest_available": ownership_manifest_available,
            "module_owned_by_distribution": module_owned_by_distribution,
            "package_initializer_owned_by_distribution": (
                package_initializer_owned_by_distribution
            ),
        },
        remediation=remediation,
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



_HEALTH_STATUS_RANK = {"pass": 0, "warn": 1, "fail": 2}
_HEALTH_PROFILE_KEYS = (
    "require_qualified_python",
    "require_installed_distribution",
    "require_bim",
    "require_desktop",
    "deep",
)


def _health_profile(report: dict[str, Any], *, label: str) -> dict[str, bool]:
    profile: dict[str, bool] = {}
    for key in _HEALTH_PROFILE_KEYS:
        value = report.get(key, False)
        if type(value) is not bool:
            raise ValueError(f"{label} report {key} must be boolean")
        profile[key] = value
    return profile


def _health_check_map(
    report: dict[str, Any],
    *,
    label: str,
) -> dict[str, dict[str, Any]]:
    if not isinstance(report, dict):
        raise ValueError(f"{label} system-health report must be a JSON object")
    if report.get("schema") != "cleanroomx.system-health":
        raise ValueError(f"{label} report is not a cleanroomx.system-health document")
    schema_version = report.get("schema_version")
    if type(schema_version) is not int or schema_version != 1:
        raise ValueError(
            f"{label} report uses unsupported system-health schema version "
            f"{schema_version!r}"
        )
    if type(report.get("required_ready")) is not bool:
        raise ValueError(f"{label} report required_ready must be boolean")

    checks = report.get("checks")
    if type(checks) is not list:
        raise ValueError(f"{label} report checks must be an array")

    indexed: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(checks):
        if type(item) is not dict:
            raise ValueError(f"{label} report checks[{index}] must be an object")
        check_id = item.get("id")
        if not isinstance(check_id, str) or not check_id.strip():
            raise ValueError(f"{label} report checks[{index}].id must be a non-empty string")
        if check_id in indexed:
            raise ValueError(f"{label} report contains duplicate check id {check_id!r}")
        status = item.get("status")
        if not isinstance(status, str) or status not in _HEALTH_STATUS_RANK:
            raise ValueError(
                f"{label} report check {check_id!r} has unsupported status {status!r}"
            )
        if type(item.get("required")) is not bool:
            raise ValueError(
                f"{label} report check {check_id!r} required must be boolean"
            )
        remediation = item.get("remediation")
        if status == "pass":
            if remediation is not None:
                raise ValueError(
                    f"{label} report check {check_id!r} passing remediation must be null"
                )
        elif not isinstance(remediation, str) or not remediation.strip():
            raise ValueError(
                f"{label} report check {check_id!r} non-passing remediation must be non-empty"
            )
        indexed[check_id] = item

    expected_required_ready = not any(
        item["required"] and item["status"] == "fail"
        for item in indexed.values()
    )
    if report["required_ready"] is not expected_required_ready:
        raise ValueError(
            f"{label} report required_ready is inconsistent with its required checks"
        )

    expected_counts = {
        status: sum(item["status"] == status for item in indexed.values())
        for status in ("pass", "warn", "fail")
    }
    summary = report.get("summary")
    if type(summary) is not dict:
        raise ValueError(f"{label} report summary must be an object")
    expected_summary = {**expected_counts, "check_count": len(indexed)}
    for key, expected in expected_summary.items():
        observed = summary.get(key)
        if type(observed) is not int or observed != expected:
            raise ValueError(
                f"{label} report summary.{key} must equal {expected}"
            )

    expected_status = (
        "not_ready"
        if not expected_required_ready
        else "ready_with_warnings"
        if expected_counts["warn"]
        else "ready"
    )
    if report.get("status") != expected_status:
        raise ValueError(
            f"{label} report status must be {expected_status!r} for its checks"
        )
    return indexed


def compare_system_health_reports(
    baseline: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any]:
    """Compare compatible system-health reports and identify deterministic drift."""
    baseline_checks = _health_check_map(baseline, label="baseline")
    current_checks = _health_check_map(current, label="current")

    baseline_profile = _health_profile(baseline, label="baseline")
    current_profile = _health_profile(current, label="current")
    if baseline_profile != current_profile:
        raise ValueError(
            "system-health baseline profile does not match the current probe "
            f"(baseline={baseline_profile}, current={current_profile})"
        )

    regressions: list[dict[str, Any]] = []
    improvements: list[dict[str, Any]] = []
    for check_id in sorted(set(baseline_checks) & set(current_checks)):
        before = baseline_checks[check_id]
        after = current_checks[check_id]
        before_rank = _HEALTH_STATUS_RANK[before["status"]]
        after_rank = _HEALTH_STATUS_RANK[after["status"]]
        if before_rank == after_rank:
            continue
        change = {
            "id": check_id,
            "label": after.get("label") or before.get("label") or check_id,
            "from": before["status"],
            "to": after["status"],
            "required": bool(after["required"]),
            "summary": after.get("summary"),
            "remediation": after.get("remediation"),
        }
        if after_rank > before_rank:
            regressions.append(change)
        else:
            improvements.append(change)

    requirement_changes = []
    for check_id in sorted(set(baseline_checks) & set(current_checks)):
        before = baseline_checks[check_id]
        after = current_checks[check_id]
        if before["required"] == after["required"]:
            continue
        requirement_changes.append(
            {
                "id": check_id,
                "label": after.get("label") or before.get("label") or check_id,
                "from_required": bool(before["required"]),
                "to_required": bool(after["required"]),
                "direction": "promoted" if after["required"] else "downgraded",
                "status": after["status"],
            }
        )

    added_checks = [
        {
            "id": check_id,
            "status": current_checks[check_id]["status"],
            "required": bool(current_checks[check_id]["required"]),
        }
        for check_id in sorted(set(current_checks) - set(baseline_checks))
    ]
    removed_checks = [
        {
            "id": check_id,
            "status": baseline_checks[check_id]["status"],
            "required": bool(baseline_checks[check_id]["required"]),
        }
        for check_id in sorted(set(baseline_checks) - set(current_checks))
    ]

    readiness_regressed = bool(
        baseline["required_ready"] and not current["required_ready"]
    )
    readiness_improved = bool(
        not baseline["required_ready"] and current["required_ready"]
    )
    coverage_regressed = any(item["required"] for item in removed_checks) or any(
        item["direction"] == "downgraded" for item in requirement_changes
    )
    coverage_expanded = any(item["required"] for item in added_checks) or any(
        item["direction"] == "promoted" for item in requirement_changes
    )
    regressed = bool(regressions) or readiness_regressed or coverage_regressed
    improved = bool(improvements) or readiness_improved or coverage_expanded
    state = "regressed" if regressed else "improved" if improved else "stable"

    def application_version(report: dict[str, Any]) -> str | None:
        application = report.get("application")
        if not isinstance(application, dict):
            return None
        version = application.get("version")
        return version if isinstance(version, str) else None

    return {
        "schema": "cleanroomx.system-health-comparison",
        "schema_version": 1,
        "state": state,
        "regressed": regressed,
        "improved": improved,
        "profile": current_profile,
        "baseline_application_version": application_version(baseline),
        "current_application_version": application_version(current),
        "required_readiness": {
            "baseline": bool(baseline["required_ready"]),
            "current": bool(current["required_ready"]),
            "regressed": readiness_regressed,
            "improved": readiness_improved,
        },
        "summary": {
            "regression_count": len(regressions),
            "improvement_count": len(improvements),
            "added_check_count": len(added_checks),
            "removed_check_count": len(removed_checks),
            "requirement_change_count": len(requirement_changes),
            "required_check_coverage_regressed": coverage_regressed,
            "required_check_coverage_expanded": coverage_expanded,
        },
        "regressions": regressions,
        "improvements": improvements,
        "added_checks": added_checks,
        "removed_checks": removed_checks,
        "requirement_changes": requirement_changes,
    }


def build_system_health_report(
    *,
    require_qualified_python: bool = False,
    require_installed_distribution: bool = False,
    require_bim: bool = False,
    require_desktop: bool = False,
    deep: bool = False,
) -> dict[str, Any]:
    """Build a deterministic, non-mutating CleanroomX workstation health report."""
    registry_check, plugin_check = _registry_checks()
    checks = [
        _python_runtime_check(),
        _python_qualification_check(required=require_qualified_python),
        _distribution_identity_check(required=require_installed_distribution),
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
        "require_qualified_python": bool(require_qualified_python),
        "require_installed_distribution": bool(require_installed_distribution),
        "require_bim": bool(require_bim),
        "require_desktop": bool(require_desktop),
        "deep": bool(deep),
        "summary": {
            **counts,
            "check_count": len(checks),
        },
        "checks": checks,
    }
