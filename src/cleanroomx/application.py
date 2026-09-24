from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from importlib import import_module
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable

from . import __version__


@dataclass(frozen=True)
class AnalysisSpec:
    key: str
    title: str
    category: str
    parser: tuple[str, str] | None
    runner: tuple[str, str] | None
    reporter: tuple[str, str] | None
    description: str


@dataclass(frozen=True)
class AnalysisRun:
    kind: str
    title: str
    status: str
    result: dict
    markdown: str
    diagnostics: dict
    plot: dict | None

    def to_dict(self) -> dict:
        return asdict(self)


def _spec(key, title, category, parser, runner, reporter, description):
    return AnalysisSpec(key, title, category, parser, runner, reporter, description)


_ANALYSES = (
    _spec("room_verification", "Room verification", "Verification",
          ("io", "room_from_dict"), ("verification", "verify_room"), None,
          "ACH, differential-pressure, and particle-requirement verification."),
    _spec("project_verification", "Multi-room project verification", "Verification",
          ("io", "project_from_dict"), ("project_verification", "verify_project"), None,
          "Room verification plus configured pressure-cascade requirements."),
    _spec("hvac", "HVAC project", "HVAC",
          ("hvac_io", "hvac_project_from_dict"), ("hvac", "analyze_hvac_project"),
          ("hvac_report", "markdown_hvac_report"),
          "Preliminary HVAC, psychrometric, airflow-balance, duct, and fan-duty analysis."),
    _spec("recovery_test", "Recovery test", "Qualification",
          ("recovery_io", "recovery_test_from_dict"), ("recovery_test", "analyze_recovery_test"),
          ("recovery_report", "markdown_recovery_report"),
          "Measured recovery-test screening and qualification evidence."),
    _spec("room_uncertainty", "Room uncertainty", "Uncertainty",
          ("uncertainty_io", "uncertain_room_from_dict"), ("uncertainty", "analyze_room_uncertainty"),
          ("uncertainty_report", "markdown_uncertainty_report"),
          "Bounded room-input uncertainty and traceability screening."),
    _spec("qualification_uncertainty", "Qualification uncertainty", "Qualification",
          ("qualification_io", "qualification_uncertainty_from_dict"),
          ("qualification", "analyze_qualification_uncertainty"),
          ("qualification_report", "markdown_qualification_report"),
          "Uncertainty-aware cleanroom qualification screening."),
    _spec("parallel_flow", "Parallel-flow network", "Networks",
          ("duct_flow_io", "parallel_flow_network_from_dict"),
          ("duct_flow", "solve_parallel_branch_flows"),
          ("duct_flow_report", "markdown_parallel_flow_report"),
          "Passive parallel-path airflow solution."),
    _spec("loop_flow", "Looped network", "Networks",
          ("loop_network_io", "looped_flow_network_from_dict"),
          ("loop_network", "solve_looped_network"),
          ("loop_network_report", "markdown_looped_network_report"),
          "Fixed-resistance looped airflow-network solution."),
    _spec("variable_friction_loop", "Variable-friction loop network", "Networks",
          ("loop_network_io", "looped_flow_network_from_dict"),
          ("variable_friction_loop", "solve_variable_friction_looped_network"),
          ("variable_friction_loop_report", "markdown_variable_friction_loop_report"),
          "Loop-network solution with airflow-dependent Darcy-friction closure."),
    _spec("thermal_uncertainty", "Thermal uncertainty", "Uncertainty",
          ("thermal_uncertainty_io", "thermal_uncertainty_from_dict"),
          ("thermal_uncertainty", "analyze_thermal_uncertainty"),
          ("thermal_uncertainty_report", "markdown_thermal_uncertainty_report"),
          "Bounded thermal/HVAC uncertainty screening."),
    _spec("psychrometric_uncertainty", "Psychrometric uncertainty", "Uncertainty",
          ("psychrometric_uncertainty_io", "psychrometric_uncertainty_from_dict"),
          ("psychrometric_uncertainty", "analyze_psychrometric_uncertainty"),
          ("psychrometric_uncertainty_report", "markdown_psychrometric_uncertainty_report"),
          "Bounded psychrometric-state uncertainty screening."),
    _spec("fan_operating_point", "Fan/system operating point", "Fans",
          ("fan_curve_io", "fan_operating_point_study_from_dict"),
          ("fan_curve", "solve_fan_operating_point"),
          ("fan_curve_report", "markdown_fan_operating_point_report"),
          "Bounded operating-point solution on supplied fan/system data."),
    _spec("fan_system_uncertainty", "Fan/system uncertainty", "Fans",
          ("fan_uncertainty_io", "fan_system_uncertainty_from_dict"),
          ("fan_uncertainty", "analyze_fan_system_uncertainty"),
          ("fan_uncertainty_report", "markdown_fan_system_uncertainty_report"),
          "Bounded fan/system operating-point uncertainty."),
    _spec("fan_speed", "Fan speed study", "Fans",
          ("fan_speed_io", "fan_speed_study_from_dict"),
          ("fan_speed", "analyze_fan_speed_study"),
          ("fan_speed_report", "markdown_fan_speed_report"),
          "Affinity-law fan-speed screening."),
    _spec("fan_duct_network", "Fan/duct-network study", "Fans",
          ("fan_duct_network_io", "fan_duct_network_study_from_dict"),
          ("fan_duct_network", "analyze_fan_duct_network"),
          ("fan_duct_network_report", "markdown_fan_duct_network_report"),
          "Fan operating point coupled to a duct network."),
    _spec("fan_parallel_network", "Fan/parallel-network study", "Fans",
          ("fan_network_io", "fan_driven_parallel_network_study_from_dict"),
          ("fan_network", "solve_fan_driven_parallel_network"),
          ("fan_network_report", "markdown_fan_driven_parallel_network_report"),
          "Fan-driven passive parallel-network solution."),
    _spec("fan_loop_network", "Fan/loop-network study", "Fans",
          ("fan_loop_network_io", "fan_loop_network_study_from_dict"),
          ("fan_loop_network", "solve_fan_loop_network"),
          ("fan_loop_network_report", "markdown_fan_loop_network_report"),
          "Fan operating point coupled to a fixed-resistance loop network."),
    _spec("fan_loop_uncertainty", "Fan/loop uncertainty", "Uncertainty",
          ("fan_loop_uncertainty_io", "fan_loop_network_uncertainty_from_dict"),
          ("fan_loop_uncertainty", "analyze_fan_loop_network_uncertainty"),
          ("fan_loop_uncertainty_report", "markdown_fan_loop_network_uncertainty_report"),
          "Bounded fan/loop-network uncertainty."),
    _spec("fan_loop_speed", "Fan/loop speed study", "Fans",
          ("fan_loop_speed_io", "fan_loop_speed_study_from_dict"),
          ("fan_loop_speed", "analyze_fan_loop_speed_study"),
          ("fan_loop_speed_report", "markdown_fan_loop_speed_report"),
          "Fan-speed study over a fixed-resistance loop network."),
    _spec("fan_variable_friction_loop", "Fan/variable-friction loop", "Fans",
          ("fan_variable_friction_loop_io", "fan_variable_friction_loop_study_from_dict"),
          ("fan_variable_friction_loop", "solve_fan_variable_friction_loop"),
          ("fan_variable_friction_loop_report", "markdown_fan_variable_friction_loop_report"),
          "Nonlinear fan/variable-friction loop operating-point solution."),
    _spec("fan_variable_friction_speed", "Fan/variable-friction speed study", "Fans",
          ("fan_variable_friction_speed_io", "fan_variable_friction_speed_study_from_dict"),
          ("fan_variable_friction_speed", "analyze_fan_variable_friction_speed_study"),
          ("fan_variable_friction_speed_report", "markdown_fan_variable_friction_speed_report"),
          "Fan-speed study with complete variable-friction loop re-solving."),
    _spec("fan_variable_friction_uncertainty", "Fan/variable-friction uncertainty", "Uncertainty",
          ("fan_variable_friction_uncertainty_io", "fan_variable_friction_loop_uncertainty_from_dict"),
          ("fan_variable_friction_uncertainty", "analyze_fan_variable_friction_loop_uncertainty"),
          ("fan_variable_friction_uncertainty_report", "markdown_fan_variable_friction_loop_uncertainty_report"),
          "Auditable nonlinear fan/variable-friction bounded uncertainty."),
    _spec("damper_study", "Loop damper study", "Networks",
          ("damper_study_io", "loop_damper_study_from_dict"),
          ("damper_study", "solve_loop_damper_study"),
          ("damper_study_report", "markdown_loop_damper_study_report"),
          "Explicit loop resistance/damper scenario study."),
    _spec("consistency", "Verification/HVAC consistency", "Verification",
          None, None, ("consistency_report", "markdown_consistency_report"),
          "Cross-check duplicated room airflow inputs in verification and HVAC files."),
    _spec("dossier", "Engineering dossier", "Reporting",
          None, None, ("dossier_report", "markdown_dossier_report"),
          "Aggregate existing CleanroomX analyses into an auditable engineering dossier."),
)

ANALYSIS_SPECS = {item.key: item for item in _ANALYSES}


def analysis_catalog() -> list[dict]:
    return [
        {"key": spec.key, "title": spec.title, "category": spec.category,
         "description": spec.description}
        for spec in _ANALYSES
    ]


def _load_callable(target: tuple[str, str]) -> Callable[..., Any]:
    module_name, function_name = target
    module = import_module(f".{module_name}", __package__)
    return getattr(module, function_name)


_CUSTOM_APPLICATION_ADAPTERS = frozenset({"consistency", "dossier"})


def validate_application_registry() -> dict:
    """Validate catalog uniqueness, adapter contracts, and every declared binding."""
    keys = [spec.key for spec in _ANALYSES]
    duplicate_keys = sorted({key for key in keys if keys.count(key) > 1})
    if duplicate_keys:
        raise RuntimeError(
            "duplicate application analysis keys: " + ", ".join(duplicate_keys)
        )

    mapping_keys = set(ANALYSIS_SPECS)
    catalog_keys = set(keys)
    if mapping_keys != catalog_keys or len(ANALYSIS_SPECS) != len(_ANALYSES):
        raise RuntimeError("application analysis mapping is inconsistent with the catalog")

    callable_target_count = 0
    fallback_reporter_count = 0
    for spec in _ANALYSES:
        if spec.key in _CUSTOM_APPLICATION_ADAPTERS:
            if spec.parser is not None or spec.runner is not None:
                raise RuntimeError(
                    f"{spec.key} must use its registered custom application adapter"
                )
        elif spec.parser is None or spec.runner is None:
            raise RuntimeError(
                f"{spec.key} must define both parser and runner targets"
            )

        if spec.reporter is None:
            fallback_reporter_count += 1

        for role, target in (
            ("parser", spec.parser),
            ("runner", spec.runner),
            ("reporter", spec.reporter),
        ):
            if target is None:
                continue
            module_name, function_name = target
            try:
                resolved = _load_callable(target)
            except Exception as exc:
                raise RuntimeError(
                    f"{spec.key} {role} binding cannot be resolved: "
                    f"{module_name}.{function_name}"
                ) from exc
            if not callable(resolved):
                raise RuntimeError(
                    f"{spec.key} {role} binding is not callable: "
                    f"{module_name}.{function_name}"
                )
            callable_target_count += 1

    return {
        "status": "ok",
        "analysis_count": len(_ANALYSES),
        "callable_target_count": callable_target_count,
        "custom_adapter_count": len(_CUSTOM_APPLICATION_ADAPTERS),
        "custom_adapters": sorted(_CUSTOM_APPLICATION_ADAPTERS),
        "fallback_reporter_count": fallback_reporter_count,
    }


def _normalize_result(value: Any) -> dict:
    if isinstance(value, dict):
        result = value
    elif hasattr(value, "to_dict"):
        result = value.to_dict()
    elif is_dataclass(value):
        result = asdict(value)
    else:
        raise TypeError("analysis result must be a dictionary, dataclass, or expose to_dict()")
    json.dumps(result, sort_keys=True, allow_nan=False)
    return result


def _derive_status(result: dict) -> str:
    for key in ("status", "overall_status", "executive_state", "criterion_status"):
        value = result.get(key)
        if value is not None:
            return str(value)
    executive_summary = result.get("executive_summary")
    if isinstance(executive_summary, dict):
        value = executive_summary.get("state")
        if value is not None:
            return str(value)
    if isinstance(result.get("passed"), bool):
        return "pass" if result["passed"] else "fail"
    return "complete"


def _fallback_markdown(title: str, result: dict) -> str:
    status = _derive_status(result)
    payload = json.dumps(result, indent=2, sort_keys=True, allow_nan=False)
    indented = "\n".join("    " + line for line in payload.splitlines())
    return f"# {title}\n\nStatus: **{status}**\n\nJSON result:\n\n{indented}\n"


_DIAGNOSTIC_TERMS = (
    "audit", "integrity", "trace", "provenance", "diagnostic",
    "convergence", "residual", "tolerance", "iteration", "coverage",
)


def diagnostic_summary(result: dict) -> dict:
    def visit(value: Any) -> Any:
        if isinstance(value, dict):
            selected: dict[str, Any] = {}
            for key, item in value.items():
                if any(term in key.lower() for term in _DIAGNOSTIC_TERMS):
                    selected[key] = item
                else:
                    nested = visit(item)
                    if nested not in ({}, [], None):
                        selected[key] = nested
            return selected
        if isinstance(value, list):
            nested_items = [visit(item) for item in value]
            return [item for item in nested_items if item not in ({}, [], None)]
        return None

    selected = visit(result)
    return selected if isinstance(selected, dict) else {}


def _find_fan_curve(value: Any) -> dict | None:
    if isinstance(value, dict):
        points = value.get("points")
        if isinstance(points, list) and len(points) >= 2 and all(
            isinstance(item, dict)
            and "airflow_m3_h" in item
            and ("pressure_pa" in item or "fan_pressure_pa" in item)
            for item in points
        ):
            return value
        for key in ("fan_curve", "reference_fan_curve", "curve"):
            found = _find_fan_curve(value.get(key))
            if found is not None:
                return found
        for item in value.values():
            found = _find_fan_curve(item)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_fan_curve(item)
            if found is not None:
                return found
    return None


def _find_operating_point(value: Any) -> dict | None:
    if isinstance(value, dict):
        if "airflow_m3_h" in value and any(
            key in value for key in ("system_pressure_pa", "fan_pressure_pa", "pressure_pa")
        ):
            return value
        for key in ("operating_point", "fan_operating_point", "nominal_result"):
            found = _find_operating_point(value.get(key))
            if found is not None:
                return found
        for item in value.values():
            found = _find_operating_point(item)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_operating_point(item)
            if found is not None:
                return found
    return None



def _find_system_curve_points(value: Any) -> list[dict] | None:
    if isinstance(value, dict):
        points = value.get("curve_point_checks")
        if isinstance(points, list) and len(points) >= 2 and all(
            isinstance(item, dict)
            and "airflow_m3_h" in item
            and "system_pressure_pa" in item
            for item in points
        ):
            return points
        for item in value.values():
            found = _find_system_curve_points(item)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_system_curve_points(item)
            if found is not None:
                return found
    return None

def build_plot_model(payload: dict, result: dict) -> dict | None:
    curve = _find_fan_curve(payload) or _find_fan_curve(result)
    if curve is None:
        return None
    xs = [float(point["airflow_m3_h"]) for point in curve["points"]]
    ys = [
        float(point.get("pressure_pa", point.get("fan_pressure_pa")))
        for point in curve["points"]
    ]
    series = [{"name": "Fan curve", "x": xs, "y": ys}]
    system_points = _find_system_curve_points(result)
    if system_points is not None:
        series.append({
            "name": "System curve",
            "x": [float(point["airflow_m3_h"]) for point in system_points],
            "y": [float(point["system_pressure_pa"]) for point in system_points],
        })

    marker = _find_operating_point(result)
    markers: list[dict] = []
    if marker is not None:
        y_value = marker.get(
            "system_pressure_pa",
            marker.get("fan_pressure_pa", marker.get("pressure_pa")),
        )
        if y_value is not None:
            markers.append({
                "name": "Operating point",
                "x": float(marker["airflow_m3_h"]),
                "y": float(y_value),
            })
    return {
        "title": str(curve.get("name", "Fan curve")),
        "x_label": "Airflow (m³/h)",
        "y_label": "Pressure (Pa)",
        "series": series,
        "markers": markers,
    }


def _resolve_relative(base_dir: Path | None, path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    if base_dir is None:
        raise ValueError("relative file references require a saved project or explicit base directory")
    return base_dir / path


def _validate_consistency(payload: dict, base_dir: Path | None) -> None:
    for key in ("verification_project", "hvac_project"):
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} must be a non-empty path string")
        path = _resolve_relative(base_dir, value)
        if not path.is_file():
            raise ValueError(f"{key} does not exist: {path}")
    tolerance = float(payload.get("room_airflow_abs_tolerance_m3_h", 0.0))
    if tolerance < 0:
        raise ValueError("room_airflow_abs_tolerance_m3_h must be >= 0")
    if not isinstance(payload.get("require_same_room_set", False), bool):
        raise ValueError("require_same_room_set must be a boolean")


_DOSSIER_SINGLE_PATH_KEYS = ("verification_project", "hvac_project")
_DOSSIER_LIST_PATH_KEYS = (
    "recovery_tests", "qualification_analyses", "uncertainty_rooms",
    "thermal_uncertainty_analyses", "psychrometric_uncertainty_analyses",
    "fan_operating_point_studies", "fan_system_uncertainty_analyses",
    "fan_duct_network_studies", "fan_parallel_network_studies",
    "fan_loop_network_studies", "fan_loop_uncertainty_analyses",
    "damper_studies", "fan_speed_studies", "fan_loop_speed_studies",
    "fan_variable_friction_loop_studies", "fan_variable_friction_speed_studies",
    "fan_variable_friction_uncertainty_analyses",
)



_APPLICATION_INPUT_CANONICALIZATION = "json-sort-keys-compact-utf8-v1"


def _canonical_input_sha256(payload: dict) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _external_dependency_references(kind: str, payload: dict) -> list[tuple[str, str]]:
    references: list[tuple[str, str]] = []
    if kind == "consistency":
        for key in ("verification_project", "hvac_project"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                references.append((key, value))
    elif kind == "dossier":
        for key in _DOSSIER_SINGLE_PATH_KEYS:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                references.append((key, value))
        for key in _DOSSIER_LIST_PATH_KEYS:
            values = payload.get(key, [])
            if isinstance(values, list):
                for index, value in enumerate(values):
                    if isinstance(value, str) and value.strip():
                        references.append((f"{key}[{index}]", value))
    return references


def _capture_external_dependencies(
    kind: str, payload: dict, base_dir: Path | None
) -> list[dict]:
    records: list[dict] = []
    for field, declared_path in _external_dependency_references(kind, payload):
        path = _resolve_relative(base_dir, declared_path)
        records.append(
            {
                "field": field,
                "declared_path": declared_path,
                "size_bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    return records


def _application_execution_provenance(
    kind: str,
    input_sha256: str,
    dependencies_before: list[dict],
    dependencies_after: list[dict],
) -> dict:
    if len(dependencies_before) != len(dependencies_after):
        raise RuntimeError("external dependency set changed during analysis execution")

    dependencies: list[dict] = []
    for before, after in zip(dependencies_before, dependencies_after):
        if (
            before["field"] != after["field"]
            or before["declared_path"] != after["declared_path"]
        ):
            raise RuntimeError("external dependency identity changed during analysis execution")
        stable = (
            before["sha256"] == after["sha256"]
            and before["size_bytes"] == after["size_bytes"]
        )
        dependencies.append(
            {
                "field": before["field"],
                "declared_path": before["declared_path"],
                "sha256_before": before["sha256"],
                "sha256_after": after["sha256"],
                "size_bytes_before": before["size_bytes"],
                "size_bytes_after": after["size_bytes"],
                "stable_during_run": stable,
            }
        )

    return {
        "schema": "cleanroomx.application-execution-provenance",
        "schema_version": 1,
        "cleanroomx_version": __version__,
        "analysis_kind": kind,
        "input_canonicalization": _APPLICATION_INPUT_CANONICALIZATION,
        "input_sha256": input_sha256,
        "external_dependency_count": len(dependencies),
        "external_dependencies_stable": all(
            item["stable_during_run"] for item in dependencies
        ),
        "external_dependencies": dependencies,
    }



def rebase_analysis_file_references(
    kind: str,
    payload: dict,
    *,
    source_base: str | Path,
    target_base: str | Path | None,
) -> dict:
    """Preserve external-file referents when analysis JSON changes directory context."""
    rebased = copy.deepcopy(payload)
    if kind not in {"consistency", "dossier"}:
        return rebased

    source = Path(os.path.abspath(source_base))
    target = None if target_base is None else Path(os.path.abspath(target_base))

    def convert(value: Any) -> Any:
        if not isinstance(value, str) or not value.strip():
            return value
        path = Path(value)
        if path.is_absolute():
            return value
        absolute = Path(os.path.abspath(source / path))
        if target is None:
            return str(absolute)
        try:
            return os.path.relpath(absolute, start=target)
        except ValueError:
            return str(absolute)

    if kind == "consistency":
        for key in ("verification_project", "hvac_project"):
            if key in rebased:
                rebased[key] = convert(rebased[key])
        return rebased

    for key in _DOSSIER_SINGLE_PATH_KEYS:
        if key in rebased:
            rebased[key] = convert(rebased[key])
    for key in _DOSSIER_LIST_PATH_KEYS:
        values = rebased.get(key)
        if isinstance(values, list):
            rebased[key] = [convert(value) for value in values]
    return rebased

def _validate_dossier(payload: dict, base_dir: Path | None) -> None:
    if not isinstance(payload.get("name"), str) or not payload["name"].strip():
        raise ValueError("dossier name must be a non-empty string")

    source_count = 0
    for key in _DOSSIER_SINGLE_PATH_KEYS:
        value = payload.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} must be a path string")
        path = _resolve_relative(base_dir, value)
        if not path.is_file():
            raise ValueError(f"{key} does not exist: {path}")
        source_count += 1

    for key in _DOSSIER_LIST_PATH_KEYS:
        values = payload.get(key, [])
        if not isinstance(values, list):
            raise ValueError(f"{key} must be an array of path strings")
        for value in values:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{key} entries must be non-empty path strings")
            path = _resolve_relative(base_dir, value)
            if not path.is_file():
                raise ValueError(f"{key} reference does not exist: {path}")
            source_count += 1

    if source_count == 0:
        raise ValueError("dossier must reference at least one analysis input file")

    consistency_checks = payload.get("consistency_checks", {})
    if not isinstance(consistency_checks, dict):
        raise ValueError("consistency_checks must be an object when provided")

    verification_hvac = consistency_checks.get("verification_hvac_airflow")
    if verification_hvac is not None:
        if not isinstance(verification_hvac, dict):
            raise ValueError(
                "verification_hvac_airflow consistency configuration must be an object"
            )
        allowed = {"room_airflow_abs_tolerance_m3_h", "require_same_room_set"}
        unknown = set(verification_hvac) - allowed
        if unknown:
            raise ValueError(
                "unsupported verification_hvac_airflow option(s): "
                + ", ".join(sorted(unknown))
            )
        if payload.get("verification_project") is None or payload.get("hvac_project") is None:
            raise ValueError(
                "verification_hvac_airflow consistency requires both "
                "verification_project and hvac_project"
            )

    hvac_fan = consistency_checks.get("hvac_fan_operating_airflow")
    if hvac_fan is not None:
        if not isinstance(hvac_fan, dict):
            raise ValueError(
                "hvac_fan_operating_airflow consistency configuration must be an object"
            )
        allowed = {"airflow_abs_tolerance_m3_h"}
        unknown = set(hvac_fan) - allowed
        if unknown:
            raise ValueError(
                "unsupported hvac_fan_operating_airflow option(s): "
                + ", ".join(sorted(unknown))
            )
        if payload.get("hvac_project") is None:
            raise ValueError(
                "hvac_fan_operating_airflow consistency requires hvac_project"
            )

def validate_analysis_input(kind: str, payload: dict, *, base_dir=None) -> None:
    if kind not in ANALYSIS_SPECS:
        raise ValueError(f"unsupported analysis kind: {kind}")
    if not isinstance(payload, dict):
        raise ValueError("analysis input must be a JSON object")
    base = Path(base_dir) if base_dir is not None else None
    if kind == "consistency":
        _validate_consistency(payload, base)
        return
    if kind == "dossier":
        _validate_dossier(payload, base)
        return
    spec = ANALYSIS_SPECS[kind]
    assert spec.parser is not None
    _load_callable(spec.parser)(payload)


def _run_consistency(payload: dict, base_dir: Path | None) -> dict:
    from .consistency import analyze_project_consistency
    from .hvac_io import load_hvac_project
    from .io import load_project

    return analyze_project_consistency(
        load_project(_resolve_relative(base_dir, payload["verification_project"])),
        load_hvac_project(_resolve_relative(base_dir, payload["hvac_project"])),
        room_airflow_abs_tolerance_m3_h=payload.get("room_airflow_abs_tolerance_m3_h", 0.0),
        require_same_room_set=payload.get("require_same_room_set", False),
    )


def _run_dossier(payload: dict, base_dir: Path | None) -> dict:
    from .dossier import build_dossier

    # Validation rejects relative references when no base directory is available.
    # Absolute references are location-independent, so an unsaved desktop project
    # can execute them using a temporary manifest outside the project tree.
    temp_dir = None
    if base_dir is not None:
        base_dir.mkdir(parents=True, exist_ok=True)
        temp_dir = base_dir

    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".json",
        prefix=".cleanroomx-dossier-", dir=temp_dir, delete=False,
    )
    temp_path = Path(handle.name)
    try:
        with handle:
            json.dump(payload, handle, indent=2, allow_nan=False)
        return build_dossier(temp_path)
    finally:
        temp_path.unlink(missing_ok=True)


def run_analysis(kind: str, payload: dict, *, base_dir=None) -> AnalysisRun:
    validate_analysis_input(kind, payload, base_dir=base_dir)
    input_sha256 = _canonical_input_sha256(payload)
    spec = ANALYSIS_SPECS[kind]
    base = Path(base_dir) if base_dir is not None else None
    dependencies_before = _capture_external_dependencies(kind, payload, base)

    if kind == "consistency":
        result = _run_consistency(payload, base)
    elif kind == "dossier":
        result = _run_dossier(payload, base)
    else:
        assert spec.parser is not None and spec.runner is not None
        result = _load_callable(spec.runner)(_load_callable(spec.parser)(payload))

    normalized = _normalize_result(result)
    markdown = (
        _fallback_markdown(spec.title, normalized)
        if spec.reporter is None
        else _load_callable(spec.reporter)(normalized)
    )
    dependencies_after = _capture_external_dependencies(kind, payload, base)
    diagnostics = diagnostic_summary(normalized)
    diagnostics["application_execution_provenance"] = _application_execution_provenance(
        kind,
        input_sha256,
        dependencies_before,
        dependencies_after,
    )
    return AnalysisRun(
        kind=kind,
        title=spec.title,
        status=_derive_status(normalized),
        result=normalized,
        markdown=markdown,
        diagnostics=diagnostics,
        plot=build_plot_model(payload, normalized),
    )


def application_info() -> dict:
    registry_validation = validate_application_registry()
    return {
        "name": "CleanroomX",
        "version": __version__,
        "analysis_count": len(_ANALYSES),
        "bindings_valid": registry_validation["status"] == "ok",
        "registry_validation": registry_validation,
        "analyses": analysis_catalog(),
    }
