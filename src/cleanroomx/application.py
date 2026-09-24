from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from importlib import import_module
import json
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


def build_plot_model(payload: dict, result: dict) -> dict | None:
    curve = _find_fan_curve(payload) or _find_fan_curve(result)
    if curve is None:
        return None
    xs = [float(point["airflow_m3_h"]) for point in curve["points"]]
    ys = [
        float(point.get("pressure_pa", point.get("fan_pressure_pa")))
        for point in curve["points"]
    ]
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
        "series": [{"name": "Fan curve", "x": xs, "y": ys}],
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


def _validate_dossier(payload: dict, base_dir: Path | None) -> None:
    if not isinstance(payload.get("name"), str) or not payload["name"].strip():
        raise ValueError("dossier name must be a non-empty string")
    for key in _DOSSIER_SINGLE_PATH_KEYS:
        value = payload.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} must be a path string")
        path = _resolve_relative(base_dir, value)
        if not path.is_file():
            raise ValueError(f"{key} does not exist: {path}")
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
    if base_dir is None:
        raise ValueError(
            "dossier execution requires a saved project/base directory so relative references remain reproducible"
        )
    base_dir.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".json",
        prefix=".cleanroomx-dossier-", dir=base_dir, delete=False,
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
    spec = ANALYSIS_SPECS[kind]
    base = Path(base_dir) if base_dir is not None else None

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
    return AnalysisRun(
        kind=kind,
        title=spec.title,
        status=_derive_status(normalized),
        result=normalized,
        markdown=markdown,
        diagnostics=diagnostic_summary(normalized),
        plot=build_plot_model(payload, normalized),
    )


def application_info() -> dict:
    return {
        "name": "CleanroomX",
        "version": __version__,
        "analysis_count": len(_ANALYSES),
        "analyses": analysis_catalog(),
    }
