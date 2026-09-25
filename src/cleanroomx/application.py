from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from functools import lru_cache
from importlib import import_module
import copy
import hashlib
import json
import os
import platform
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any, Callable

from . import __version__
from .plugins import (
    PLUGIN_API_VERSION,
    PluginOrigin,
    discover_analysis_plugins,
)


BindingTarget = tuple[str, str] | Callable[..., Any]

_RUN_BUNDLE_SCHEMA = "cleanroomx.analysis-run"
_RUN_BUNDLE_SCHEMA_VERSION = 1
_RUN_BUNDLE_CANONICALIZATION = "json-sort-keys-compact-utf8-v1"


def _canonical_json_sha256(payload: dict) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class _FrozenDict(dict):
    """JSON-object snapshot that rejects mutation after run completion."""

    @staticmethod
    def _immutable(*_args, **_kwargs):
        raise TypeError("analysis run snapshots are immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable
    __ior__ = _immutable

    def __deepcopy__(self, memo):
        return self


class _FrozenList(list):
    """JSON-array snapshot that rejects mutation after run completion."""

    @staticmethod
    def _immutable(*_args, **_kwargs):
        raise TypeError("analysis run snapshots are immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    append = _immutable
    clear = _immutable
    extend = _immutable
    insert = _immutable
    pop = _immutable
    remove = _immutable
    reverse = _immutable
    sort = _immutable
    __iadd__ = _immutable
    __imul__ = _immutable

    def __deepcopy__(self, memo):
        return self


def _freeze_json_snapshot(
    value: Any,
    memo: dict[int, Any] | None = None,
) -> Any:
    """Recursively copy JSON-compatible data into immutable container subclasses."""
    if memo is None:
        memo = {}
    if isinstance(value, (dict, list, tuple)):
        identity = id(value)
        if identity in memo:
            return memo[identity]
    if isinstance(value, dict):
        frozen = _FrozenDict(
            (key, _freeze_json_snapshot(item, memo))
            for key, item in value.items()
        )
        memo[id(value)] = frozen
        return frozen
    if isinstance(value, list):
        frozen = _FrozenList(_freeze_json_snapshot(item, memo) for item in value)
        memo[id(value)] = frozen
        return frozen
    if isinstance(value, tuple):
        frozen = tuple(_freeze_json_snapshot(item, memo) for item in value)
        memo[id(value)] = frozen
        return frozen
    return copy.deepcopy(value)


def _thaw_json_snapshot(value: Any) -> Any:
    """Return a detached ordinary-container copy suitable for public serialization."""
    if isinstance(value, dict):
        return {key: _thaw_json_snapshot(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_thaw_json_snapshot(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_thaw_json_snapshot(item) for item in value)
    return copy.deepcopy(value)


@dataclass(frozen=True)
class AnalysisSpec:
    key: str
    title: str
    category: str
    parser: BindingTarget | None
    runner: BindingTarget | None
    reporter: BindingTarget | None
    description: str
    source: str = "builtin"
    plugin_api_version: int | None = None
    plugin_origin: PluginOrigin | None = None


@dataclass(frozen=True)
class AnalysisRun:
    kind: str
    title: str
    status: str
    result: dict
    markdown: str
    diagnostics: dict
    plot: dict | None
    input_snapshot: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        memo: dict[int, Any] = {}
        object.__setattr__(self, "input_snapshot", _freeze_json_snapshot(self.input_snapshot, memo))
        object.__setattr__(self, "result", _freeze_json_snapshot(self.result, memo))
        object.__setattr__(self, "diagnostics", _freeze_json_snapshot(self.diagnostics, memo))
        object.__setattr__(
            self,
            "plot",
            None if self.plot is None else _freeze_json_snapshot(self.plot, memo),
        )

    def to_dict(self) -> dict:
        document = {
            "schema": _RUN_BUNDLE_SCHEMA,
            "schema_version": _RUN_BUNDLE_SCHEMA_VERSION,
            "cleanroomx_version": __version__,
            "kind": self.kind,
            "title": self.title,
            "status": self.status,
            "input_snapshot": _thaw_json_snapshot(self.input_snapshot),
            "result": _thaw_json_snapshot(self.result),
            "markdown": self.markdown,
            "diagnostics": _thaw_json_snapshot(self.diagnostics),
            "plot": None if self.plot is None else _thaw_json_snapshot(self.plot),
        }
        document["integrity"] = {
            "algorithm": "sha256",
            "canonicalization": _RUN_BUNDLE_CANONICALIZATION,
            "sha256": _canonical_json_sha256(document),
        }
        return document


def verify_analysis_run_bundle(document: dict) -> dict:
    """Validate a versioned exported run bundle without re-running the solver."""
    if not isinstance(document, dict):
        raise ValueError("run bundle must be a JSON object")
    if document.get("schema") != _RUN_BUNDLE_SCHEMA:
        raise ValueError(f"unsupported run bundle schema: {document.get('schema')!r}")
    if document.get("schema_version") != _RUN_BUNDLE_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported run bundle schema version: {document.get('schema_version')!r}"
        )

    expected_keys = {
        "schema", "schema_version", "cleanroomx_version", "kind", "title",
        "status", "input_snapshot", "result", "markdown", "diagnostics",
        "plot", "integrity",
    }
    missing_keys = expected_keys - set(document)
    unknown_keys = set(document) - expected_keys
    if missing_keys:
        raise ValueError(
            "run bundle is missing required field(s): " + ", ".join(sorted(missing_keys))
        )
    if unknown_keys:
        raise ValueError(
            "run bundle contains unsupported field(s): " + ", ".join(sorted(unknown_keys))
        )

    bundle_version = document.get("cleanroomx_version")
    if not isinstance(bundle_version, str) or not bundle_version:
        raise ValueError("run bundle cleanroomx_version must be a non-empty string")
    integrity = document.get("integrity")
    if not isinstance(integrity, dict):
        raise ValueError("run bundle integrity record is missing")
    if integrity.get("algorithm") != "sha256":
        raise ValueError("run bundle integrity algorithm must be sha256")
    if integrity.get("canonicalization") != _RUN_BUNDLE_CANONICALIZATION:
        raise ValueError("unsupported run bundle canonicalization")
    expected_digest = integrity.get("sha256")
    if not isinstance(expected_digest, str) or len(expected_digest) != 64:
        raise ValueError("run bundle integrity sha256 must be a 64-character digest")

    unsigned = copy.deepcopy(document)
    unsigned.pop("integrity", None)
    actual_digest = _canonical_json_sha256(unsigned)
    if actual_digest != expected_digest:
        raise ValueError("run bundle integrity check failed: content has changed")

    kind = document.get("kind")
    if not isinstance(kind, str) or not kind:
        raise ValueError("run bundle analysis kind must be a non-empty string")
    if not isinstance(document.get("title"), str) or not document["title"]:
        raise ValueError("run bundle title must be a non-empty string")
    if not isinstance(document.get("status"), str) or not document["status"]:
        raise ValueError("run bundle status must be a non-empty string")
    if not isinstance(document.get("result"), dict):
        raise ValueError("run bundle result must be a JSON object")
    if not isinstance(document.get("markdown"), str):
        raise ValueError("run bundle markdown must be a string")
    if document.get("plot") is not None and not isinstance(document["plot"], dict):
        raise ValueError("run bundle plot must be a JSON object or null")
    input_snapshot = document.get("input_snapshot")
    if not isinstance(input_snapshot, dict):
        raise ValueError("run bundle input_snapshot must be a JSON object")

    diagnostics = document.get("diagnostics")
    if not isinstance(diagnostics, dict):
        raise ValueError("run bundle diagnostics must be a JSON object")
    provenance = diagnostics.get("application_execution_provenance")
    if not isinstance(provenance, dict):
        raise ValueError("run bundle execution provenance is missing")
    if provenance.get("analysis_kind") != kind:
        raise ValueError("run bundle analysis kind disagrees with execution provenance")
    if provenance.get("cleanroomx_version") != bundle_version:
        raise ValueError("run bundle version disagrees with execution provenance")
    if provenance.get("input_canonicalization") != _APPLICATION_INPUT_CANONICALIZATION:
        raise ValueError("unsupported application input canonicalization")
    input_sha256 = _canonical_input_sha256(input_snapshot)
    if provenance.get("input_sha256") != input_sha256:
        raise ValueError("run bundle input snapshot does not match execution provenance")

    dependency_count = provenance.get("external_dependency_count")
    dependencies = provenance.get("external_dependencies")
    if not isinstance(dependency_count, int) or dependency_count < 0:
        raise ValueError("run bundle external dependency count is invalid")
    if not isinstance(dependencies, list) or len(dependencies) != dependency_count:
        raise ValueError("run bundle external dependency manifest is inconsistent")

    return {
        "status": "ok",
        "schema": _RUN_BUNDLE_SCHEMA,
        "schema_version": _RUN_BUNDLE_SCHEMA_VERSION,
        "cleanroomx_version": bundle_version,
        "analysis_kind": kind,
        "input_sha256": input_sha256,
        "bundle_sha256": actual_digest,
        "external_dependency_count": dependency_count,
        "external_dependencies_stable": provenance.get("external_dependencies_stable"),
    }


class ExternalDependencySnapshotError(RuntimeError):
    """Raised when a verified private execution snapshot cannot be materialized."""

    def __init__(self, field: str, declared_path: str, detail: str) -> None:
        self.field = field
        self.declared_path = declared_path
        self.detail = detail
        super().__init__(
            "Could not create a verified private execution snapshot for external "
            f"engineering input {field} ({declared_path}); analysis was not started. "
            f"{detail}"
        )


class RuntimeCodeChangedError(RuntimeError):
    """Raised when CleanroomX Python source changes during one analysis run."""

    def __init__(self, before: dict, after: dict) -> None:
        self.before = copy.deepcopy(before)
        self.after = copy.deepcopy(after)
        super().__init__(
            "CleanroomX runtime code changed during analysis execution; the result "
            "was discarded. Restart the application from one stable installation and "
            "run again "
            f"({before['sha256'][:12]} -> {after['sha256'][:12]})."
        )


class ExternalDependencyChangedError(RuntimeError):
    """Raised when file-backed engineering inputs are not revision-stable."""

    def __init__(self, changes: list[dict]) -> None:
        self.changes = tuple(copy.deepcopy(changes))
        labels = [
            f"{item['field']} ({item['declared_path']})"
            for item in self.changes
        ]
        detail = ", ".join(labels) if labels else "unknown dependency"
        super().__init__(
            "External engineering input changed or became unavailable during "
            "analysis execution; the result was discarded. Stabilize the referenced "
            f"file(s) and run again: {detail}"
        )


class AnalysisInputMutationError(RuntimeError):
    """Raised when application execution mutates its isolated submitted-input snapshot."""

    def __init__(self, kind: str, phase: str) -> None:
        self.kind = kind
        self.phase = phase
        super().__init__(
            f"{kind} mutated its submitted analysis input during {phase}; "
            "the result was discarded to preserve deterministic execution provenance"
        )


@dataclass(frozen=True)
class _PreparedAnalysisInput:
    payload: dict
    parsed: Any | None
    base_dir: Path | None
    input_sha256: str


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

_BUILTIN_ANALYSES = _ANALYSES
_PLUGIN_DISCOVERY = discover_analysis_plugins(
    spec.key for spec in _BUILTIN_ANALYSES
)
_PLUGIN_ANALYSES = tuple(
    AnalysisSpec(
        key=item.plugin.key,
        title=item.plugin.title,
        category=item.plugin.category,
        parser=item.plugin.parser,
        runner=item.plugin.runner,
        reporter=item.plugin.reporter,
        description=item.plugin.description,
        source="plugin",
        plugin_api_version=item.plugin.api_version,
        plugin_origin=item.origin,
    )
    for item in _PLUGIN_DISCOVERY.plugins
)
_ANALYSES = _BUILTIN_ANALYSES + _PLUGIN_ANALYSES
ANALYSIS_SPECS = {item.key: item for item in _ANALYSES}


def analysis_catalog() -> list[dict]:
    catalog: list[dict] = []
    for spec in _ANALYSES:
        item = {
            "key": spec.key,
            "title": spec.title,
            "category": spec.category,
            "description": spec.description,
            "source": spec.source,
        }
        if spec.plugin_origin is not None:
            item["plugin"] = {
                "api_version": spec.plugin_api_version,
                **spec.plugin_origin.to_dict(),
            }
        catalog.append(item)
    return catalog


def plugin_discovery_issues() -> tuple[dict, ...]:
    """Return deterministic plugin discovery problems for diagnostics/UI."""
    return tuple(issue.to_dict() for issue in _PLUGIN_DISCOVERY.issues)


def _load_callable(target: BindingTarget) -> Callable[..., Any]:
    if callable(target):
        return target
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
        if spec.source not in {"builtin", "plugin"}:
            raise RuntimeError(
                f"{spec.key} has unsupported implementation source {spec.source!r}"
            )
        if spec.source == "plugin":
            if spec.plugin_api_version != PLUGIN_API_VERSION:
                raise RuntimeError(
                    f"{spec.key} plugin API version does not match "
                    f"{PLUGIN_API_VERSION}"
                )
            if spec.plugin_origin is None:
                raise RuntimeError(f"{spec.key} plugin origin metadata is missing")
        elif spec.plugin_origin is not None or spec.plugin_api_version is not None:
            raise RuntimeError(f"{spec.key} built-in analysis has plugin metadata")

        if spec.key in _CUSTOM_APPLICATION_ADAPTERS:
            if spec.source != "builtin":
                raise RuntimeError(
                    f"{spec.key} custom adapter cannot be replaced by a plugin"
                )
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
            if callable(target):
                target_label = getattr(target, "__qualname__", repr(target))
            else:
                module_name, function_name = target
                target_label = f"{module_name}.{function_name}"
            try:
                resolved = _load_callable(target)
            except Exception as exc:
                raise RuntimeError(
                    f"{spec.key} {role} binding cannot be resolved: {target_label}"
                ) from exc
            if not callable(resolved):
                raise RuntimeError(
                    f"{spec.key} {role} binding is not callable: {target_label}"
                )
            callable_target_count += 1

    issues = plugin_discovery_issues()
    return {
        "status": "ok",
        "analysis_count": len(_ANALYSES),
        "builtin_analysis_count": len(_BUILTIN_ANALYSES),
        "plugin_api_version": PLUGIN_API_VERSION,
        "plugin_analysis_count": len(_PLUGIN_ANALYSES),
        "plugin_issue_count": len(issues),
        "plugin_issues": list(issues),
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
        system_xs = [float(point["airflow_m3_h"]) for point in system_points]
        if len(system_xs) == len(xs) and all(
            abs(system_x - fan_x) <= 1e-9
            for system_x, fan_x in zip(system_xs, xs)
        ):
            series.append({
                "name": "System curve",
                "x": system_xs,
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


_APPLICATION_INPUT_CANONICALIZATION = "json-sort-keys-compact-utf8-v1"
_APPLICATION_INPUT_EXECUTION_POLICY = "isolated-copy-single-parse-sha256-guard-v1"


def _canonical_input_sha256(payload: dict) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


_RUNTIME_CODE_FINGERPRINT_ALGORITHM = "sha256-python-source-tree-v1"
_RUNTIME_CODE_FINGERPRINT_ATTEMPTS = 3


def _python_tree_manifest(root: Path) -> tuple[tuple[str, int, int, int, int, int], ...]:
    """Return deterministic file identity/size/time evidence for Python source."""

    try:
        sources = sorted(
            (
                path
                for path in root.rglob("*.py")
                if path.is_file()
                and "__pycache__" not in path.relative_to(root).parts
            ),
            key=lambda path: path.relative_to(root).as_posix(),
        )
        manifest = []
        for source in sources:
            metadata = source.stat()
            manifest.append(
                (
                    source.relative_to(root).as_posix(),
                    metadata.st_dev,
                    metadata.st_ino,
                    metadata.st_size,
                    metadata.st_mtime_ns,
                    metadata.st_ctime_ns,
                )
            )
    except OSError as exc:
        raise RuntimeError(f"cannot inspect CleanroomX source tree: {root}") from exc
    return tuple(manifest)


@lru_cache(maxsize=8)
def _hash_python_tree_manifest(
    root_text: str,
    manifest: tuple[tuple[str, int, int, int, int, int], ...],
) -> dict:
    """Hash exact source bytes for one already-observed source-tree manifest."""

    root = Path(root_text)
    digest = hashlib.sha256()
    source: Path | None = None
    try:
        for relative_text, *_metadata in manifest:
            source = root / relative_text
            relative = relative_text.encode("utf-8")
            content = source.read_bytes()
            digest.update(len(relative).to_bytes(4, "big"))
            digest.update(relative)
            digest.update(len(content).to_bytes(8, "big"))
            digest.update(content)
    except OSError as exc:
        raise RuntimeError(f"cannot read CleanroomX source file: {source}") from exc

    if _python_tree_manifest(root) != manifest:
        raise RuntimeError("CleanroomX source tree changed while it was being fingerprinted")

    return {
        "algorithm": _RUNTIME_CODE_FINGERPRINT_ALGORITHM,
        "sha256": digest.hexdigest(),
        "source_file_count": len(manifest),
    }


def _fingerprint_python_tree(root: Path) -> dict:
    """Fingerprint Python source while avoiding repeated unchanged-tree reads."""

    root = Path(root).resolve()
    if not root.is_dir():
        raise RuntimeError(f"CleanroomX source root is unavailable: {root}")

    for _attempt in range(_RUNTIME_CODE_FINGERPRINT_ATTEMPTS):
        manifest = _python_tree_manifest(root)
        if not manifest:
            raise RuntimeError(f"no Python source files found under CleanroomX root: {root}")
        try:
            return copy.deepcopy(_hash_python_tree_manifest(str(root), manifest))
        except RuntimeError as exc:
            if "changed while it was being fingerprinted" not in str(exc):
                raise

    raise RuntimeError(
        "CleanroomX source tree changed repeatedly while capturing runtime provenance"
    )


def _capture_runtime_code_fingerprint() -> dict:
    return _fingerprint_python_tree(Path(__file__).resolve().parent)


def _runtime_environment_provenance() -> dict:
    return {
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "python_cache_tag": getattr(sys.implementation, "cache_tag", None),
        "platform_system": platform.system(),
        "platform_release": platform.release(),
        "platform_machine": platform.machine(),
        "byteorder": sys.byteorder,
        "float_radix": sys.float_info.radix,
        "float_mant_dig": sys.float_info.mant_dig,
    }


def _binding_label(target: BindingTarget | None) -> str | None:
    if target is None:
        return None
    if callable(target):
        module_name = getattr(target, "__module__", None)
        qualified_name = getattr(
            target, "__qualname__", getattr(target, "__name__", type(target).__name__)
        )
        return (
            f"{module_name}:{qualified_name}"
            if isinstance(module_name, str) and module_name
            else str(qualified_name)
        )
    module_name, function_name = target
    return f"cleanroomx.{module_name}:{function_name}"


def _analysis_binding_provenance(kind: str) -> dict:
    spec = ANALYSIS_SPECS[kind]
    return {
        "parser": _binding_label(spec.parser),
        "runner": _binding_label(spec.runner),
        "reporter": (
            _binding_label(spec.reporter)
            if spec.reporter is not None
            else "cleanroomx.application:_fallback_markdown"
        ),
        "custom_adapter": (
            f"cleanroomx.application:_run_{kind}"
            if kind in _CUSTOM_APPLICATION_ADAPTERS
            else None
        ),
    }


def _assert_input_snapshot_unchanged(
    kind: str,
    payload: dict,
    input_sha256: str,
    *,
    phase: str,
) -> None:
    try:
        current_sha256 = _canonical_input_sha256(payload)
    except (TypeError, ValueError) as exc:
        raise AnalysisInputMutationError(kind, phase) from exc
    if current_sha256 != input_sha256:
        raise AnalysisInputMutationError(kind, phase)


def analysis_run_matches_input(run: AnalysisRun, kind: str, payload: dict) -> bool:
    """Return whether a completed run belongs to exactly this analysis input."""
    if run.kind != kind or not isinstance(run.diagnostics, dict):
        return False
    provenance = run.diagnostics.get("application_execution_provenance")
    if not isinstance(provenance, dict):
        return False
    if provenance.get("analysis_kind") != kind:
        return False
    recorded_sha256 = provenance.get("input_sha256")
    if not isinstance(recorded_sha256, str) or len(recorded_sha256) != 64:
        return False
    try:
        current_sha256 = _canonical_input_sha256(payload)
    except (TypeError, ValueError):
        return False
    return recorded_sha256 == current_sha256


def analysis_run_external_dependencies_current(
    run: AnalysisRun,
    *,
    base_dir=None,
) -> bool:
    """Return whether every file-backed run dependency still matches by content."""
    if not isinstance(run, AnalysisRun) or not isinstance(run.diagnostics, dict):
        return False
    provenance = run.diagnostics.get("application_execution_provenance")
    if not isinstance(provenance, dict):
        return False
    if provenance.get("schema") != "cleanroomx.application-execution-provenance":
        return False
    dependencies = provenance.get("external_dependencies")
    if not isinstance(dependencies, list):
        return False
    if provenance.get("external_dependency_count") != len(dependencies):
        return False
    if provenance.get("external_dependencies_stable") is not True:
        return False

    base = Path(base_dir) if base_dir is not None else None
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            return False
        declared_path = dependency.get("declared_path")
        expected_sha256 = dependency.get("sha256_after")
        expected_size = dependency.get("size_bytes_after")
        if (
            not isinstance(dependency.get("field"), str)
            or not dependency["field"]
            or not isinstance(declared_path, str)
            or not declared_path
            or not isinstance(expected_sha256, str)
            or len(expected_sha256) != 64
            or type(expected_size) is not int
            or expected_size < 0
            or dependency.get("stable_during_run") is not True
        ):
            return False
        try:
            current = _stable_file_fingerprint(_resolve_relative(base, declared_path))
        except (OSError, RuntimeError, ValueError):
            return False
        if (
            current["sha256"] != expected_sha256
            or current["size_bytes"] != expected_size
        ):
            return False
    return True


def analysis_run_is_current(
    run: AnalysisRun,
    kind: str,
    payload: dict,
    *,
    base_dir=None,
) -> bool:
    """Fail closed unless submitted JSON and every external dependency are current."""
    return (
        analysis_run_matches_input(run, kind, payload)
        and analysis_run_external_dependencies_current(run, base_dir=base_dir)
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


_DEPENDENCY_FINGERPRINT_ATTEMPTS = 3


def _stable_file_fingerprint(path: Path) -> dict:
    """Capture one stable content revision without accepting a torn read."""
    last_before = None
    last_after = None
    for _ in range(_DEPENDENCY_FINGERPRINT_ATTEMPTS):
        before = path.stat()
        digest = _sha256_file(path)
        after = path.stat()
        last_before = before
        last_after = after
        if (
            before.st_dev == after.st_dev
            and before.st_ino == after.st_ino
            and before.st_size == after.st_size
            and before.st_mtime_ns == after.st_mtime_ns
        ):
            return {
                "size_bytes": after.st_size,
                "mtime_ns": after.st_mtime_ns,
                "sha256": digest,
            }
    assert last_before is not None and last_after is not None
    raise RuntimeError(
        "file changed while its revision fingerprint was being captured "
        f"(size {last_before.st_size}->{last_after.st_size}, "
        f"mtime_ns {last_before.st_mtime_ns}->{last_after.st_mtime_ns})"
    )


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
        try:
            fingerprint = _stable_file_fingerprint(path)
        except (OSError, RuntimeError) as exc:
            raise ExternalDependencyChangedError(
                [{
                    "field": field,
                    "declared_path": declared_path,
                    "status": "unavailable_or_unstable",
                }]
            ) from exc
        records.append(
            {
                "field": field,
                "declared_path": declared_path,
                **fingerprint,
            }
        )
    return records


def _set_external_dependency_reference(
    payload: dict,
    field: str,
    replacement: Path,
) -> None:
    """Rewrite one known file-reference field in an execution-only payload copy."""
    if field.endswith("]") and "[" in field:
        key, index_text = field[:-1].rsplit("[", 1)
        values = payload.get(key)
        try:
            index = int(index_text)
        except ValueError as exc:
            raise RuntimeError(f"invalid external dependency field: {field}") from exc
        if not isinstance(values, list) or not 0 <= index < len(values):
            raise RuntimeError(f"external dependency field is no longer present: {field}")
        values[index] = str(replacement)
        return
    if field not in payload:
        raise RuntimeError(f"external dependency field is no longer present: {field}")
    payload[field] = str(replacement)


def _prepare_external_dependency_snapshot(
    kind: str,
    payload: dict,
    base_dir: Path | None,
    snapshot_dir: Path,
) -> tuple[dict, list[dict], dict[str, str]]:
    """Capture file-backed engineering inputs once into verified private bytes."""
    references = _external_dependency_references(kind, payload)
    if not references:
        return copy.deepcopy(payload), [], {}

    last_changes: list[dict] = []
    for _attempt in range(_DEPENDENCY_FINGERPRINT_ATTEMPTS):
        dependencies_before = _capture_external_dependencies(kind, payload, base_dir)
        if len(dependencies_before) != len(references):
            raise RuntimeError("external dependency reference set changed while snapshotting")

        execution_payload = copy.deepcopy(payload)
        execution_path_aliases: dict[str, str] = {}
        changes: list[dict] = []
        for index, ((field, declared_path), expected) in enumerate(
            zip(references, dependencies_before)
        ):
            if expected["field"] != field or expected["declared_path"] != declared_path:
                raise RuntimeError(
                    "external dependency identity changed while preparing execution snapshot"
                )

            source = _resolve_relative(base_dir, declared_path)
            destination = snapshot_dir / f"dependency-{index:04d}.json"
            try:
                shutil.copyfile(source, destination)
            except OSError as exc:
                try:
                    current = _stable_file_fingerprint(source)
                except (OSError, RuntimeError):
                    changes.append({
                        "field": field,
                        "declared_path": declared_path,
                        "status": "unavailable_or_unstable",
                    })
                    continue
                if (
                    current["sha256"] != expected["sha256"]
                    or current["size_bytes"] != expected["size_bytes"]
                    or current["mtime_ns"] != expected["mtime_ns"]
                ):
                    changes.append({
                        "field": field,
                        "declared_path": declared_path,
                        "status": "changed_while_snapshotting",
                        "sha256_before": expected["sha256"],
                        "snapshot_sha256": current["sha256"],
                        "size_bytes_before": expected["size_bytes"],
                        "snapshot_size_bytes": current["size_bytes"],
                    })
                    continue
                detail = exc.strerror or exc.__class__.__name__
                raise ExternalDependencySnapshotError(
                    field, declared_path, detail
                ) from exc

            try:
                copied = _stable_file_fingerprint(destination)
            except (OSError, RuntimeError) as exc:
                raise ExternalDependencySnapshotError(
                    field,
                    declared_path,
                    "private snapshot verification failed",
                ) from exc
            if (
                copied["sha256"] != expected["sha256"]
                or copied["size_bytes"] != expected["size_bytes"]
            ):
                changes.append({
                    "field": field,
                    "declared_path": declared_path,
                    "status": "changed_while_snapshotting",
                    "sha256_before": expected["sha256"],
                    "snapshot_sha256": copied["sha256"],
                    "size_bytes_before": expected["size_bytes"],
                    "snapshot_size_bytes": copied["size_bytes"],
                })
                continue

            snapshot_path = destination.resolve()
            _set_external_dependency_reference(execution_payload, field, snapshot_path)
            execution_path_aliases[str(snapshot_path)] = declared_path

        if not changes:
            return execution_payload, dependencies_before, execution_path_aliases
        last_changes = changes

    raise ExternalDependencyChangedError(last_changes)


def _verify_external_dependency_snapshot(
    kind: str,
    execution_payload: dict,
    dependencies_before: list[dict],
) -> None:
    """Reject a run if a private execution snapshot changed during execution."""
    references = _external_dependency_references(kind, execution_payload)
    if len(references) != len(dependencies_before):
        raise RuntimeError("execution snapshot dependency set changed during analysis")
    for (field, snapshot_path), expected in zip(references, dependencies_before):
        if field != expected["field"]:
            raise RuntimeError("execution snapshot dependency identity changed during analysis")
        try:
            current = _stable_file_fingerprint(Path(snapshot_path))
        except (OSError, RuntimeError) as exc:
            raise ExternalDependencySnapshotError(
                field,
                expected["declared_path"],
                "private snapshot became unavailable or unstable during backend execution",
            ) from exc
        if (
            current["sha256"] != expected["sha256"]
            or current["size_bytes"] != expected["size_bytes"]
        ):
            raise ExternalDependencySnapshotError(
                field,
                expected["declared_path"],
                "private snapshot changed during backend execution",
            )


def _restore_external_dependency_result_paths(
    kind: str,
    result: Any,
    execution_path_aliases: dict[str, str],
) -> Any:
    """Remove execution-only paths from durable dossier evidence."""
    if kind != "dossier" or not execution_path_aliases:
        return result
    if not isinstance(result, dict):
        raise RuntimeError("dossier backend returned a non-object result")
    source_files = result.get("source_files")
    if not isinstance(source_files, list):
        raise RuntimeError("dossier result is missing source_files")
    restored = 0
    for source in source_files:
        if not isinstance(source, dict):
            continue
        source_path = source.get("path")
        if isinstance(source_path, str) and source_path in execution_path_aliases:
            source["path"] = execution_path_aliases[source_path]
            restored += 1
    if restored != len(execution_path_aliases):
        raise RuntimeError(
            "dossier result did not preserve every execution snapshot source reference"
        )
    return result


def _application_execution_provenance(
    kind: str,
    input_sha256: str,
    dependencies_before: list[dict],
    dependencies_after: list[dict],
    code_before: dict,
    code_after: dict,
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
            and before["mtime_ns"] == after["mtime_ns"]
        )
        dependencies.append(
            {
                "field": before["field"],
                "declared_path": before["declared_path"],
                "sha256_before": before["sha256"],
                "sha256_after": after["sha256"],
                "size_bytes_before": before["size_bytes"],
                "size_bytes_after": after["size_bytes"],
                "mtime_ns_before": before["mtime_ns"],
                "mtime_ns_after": after["mtime_ns"],
                "execution_snapshot_sha256": before["sha256"],
                "execution_snapshot_size_bytes": before["size_bytes"],
                "stable_during_run": stable,
            }
        )

    spec = ANALYSIS_SPECS[kind]
    implementation = {
        "source": spec.source,
        "cleanroomx_version": __version__,
    }
    if spec.plugin_origin is not None:
        implementation = {
            "source": "plugin",
            "plugin_api_version": spec.plugin_api_version,
            **spec.plugin_origin.to_dict(),
        }

    code_stable = (
        code_before["algorithm"] == code_after["algorithm"]
        and code_before["sha256"] == code_after["sha256"]
        and code_before["source_file_count"] == code_after["source_file_count"]
    )

    return {
        "schema": "cleanroomx.application-execution-provenance",
        "schema_version": 1,
        "cleanroomx_version": __version__,
        "analysis_kind": kind,
        "implementation": implementation,
        "execution_binding": _analysis_binding_provenance(kind),
        "runtime_environment": _runtime_environment_provenance(),
        "code_revision": {
            "algorithm": code_before["algorithm"],
            "sha256_before": code_before["sha256"],
            "sha256_after": code_after["sha256"],
            "source_file_count_before": code_before["source_file_count"],
            "source_file_count_after": code_after["source_file_count"],
            "stable_during_run": code_stable,
        },
        "input_canonicalization": _APPLICATION_INPUT_CANONICALIZATION,
        "input_execution_policy": _APPLICATION_INPUT_EXECUTION_POLICY,
        "input_sha256": input_sha256,
        "external_dependency_count": len(dependencies),
        "external_dependency_execution_mode": (
            "immutable_content_snapshot_v1" if dependencies else "not_applicable"
        ),
        "external_dependencies_stable": all(
            item["stable_during_run"] for item in dependencies
        ),
        "external_dependencies": dependencies,
    }


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

def _prepare_analysis_input(
    kind: str,
    payload: dict,
    *,
    base_dir=None,
) -> _PreparedAnalysisInput:
    """Isolate, validate, and parse one exact submitted input revision."""
    if kind not in ANALYSIS_SPECS:
        raise ValueError(f"unsupported analysis kind: {kind}")
    if not isinstance(payload, dict):
        raise ValueError("analysis input must be a JSON object")

    snapshot = copy.deepcopy(payload)
    try:
        input_sha256 = _canonical_input_sha256(snapshot)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "analysis input must contain only strict JSON values"
        ) from exc
    base = Path(base_dir) if base_dir is not None else None
    parsed: Any | None = None

    if kind == "consistency":
        _validate_consistency(snapshot, base)
    elif kind == "dossier":
        _validate_dossier(snapshot, base)
    else:
        spec = ANALYSIS_SPECS[kind]
        assert spec.parser is not None
        parsed = _load_callable(spec.parser)(copy.deepcopy(snapshot))

    _assert_input_snapshot_unchanged(
        kind,
        snapshot,
        input_sha256,
        phase="input validation/parsing",
    )
    return _PreparedAnalysisInput(
        payload=snapshot,
        parsed=parsed,
        base_dir=base,
        input_sha256=input_sha256,
    )


def validate_analysis_input(kind: str, payload: dict, *, base_dir=None) -> None:
    _prepare_analysis_input(kind, payload, base_dir=base_dir)


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
    code_before = _capture_runtime_code_fingerprint()
    prepared = _prepare_analysis_input(kind, payload, base_dir=base_dir)
    spec = ANALYSIS_SPECS[kind]
    references = _external_dependency_references(kind, prepared.payload)

    if references:
        with tempfile.TemporaryDirectory(
            prefix="cleanroomx-analysis-inputs-"
        ) as snapshot_dir_text:
            execution_payload, dependencies_before, execution_path_aliases = (
                _prepare_external_dependency_snapshot(
                    kind,
                    prepared.payload,
                    prepared.base_dir,
                    Path(snapshot_dir_text),
                )
            )
            if kind == "consistency":
                result = _run_consistency(execution_payload, prepared.base_dir)
            elif kind == "dossier":
                result = _run_dossier(execution_payload, prepared.base_dir)
            else:
                raise RuntimeError(
                    "host-managed external dependency snapshots are only defined "
                    "for built-in file-backed analyses"
                )
            _verify_external_dependency_snapshot(
                kind, execution_payload, dependencies_before
            )
            result = _restore_external_dependency_result_paths(
                kind, result, execution_path_aliases
            )
    else:
        dependencies_before = []
        if kind == "consistency":
            result = _run_consistency(prepared.payload, prepared.base_dir)
        elif kind == "dossier":
            result = _run_dossier(prepared.payload, prepared.base_dir)
        else:
            assert spec.runner is not None
            result = _load_callable(spec.runner)(prepared.parsed)

    _assert_input_snapshot_unchanged(
        kind,
        prepared.payload,
        prepared.input_sha256,
        phase="backend execution",
    )
    normalized = _normalize_result(result)
    markdown = (
        _fallback_markdown(spec.title, normalized)
        if spec.reporter is None
        else _load_callable(spec.reporter)(copy.deepcopy(normalized))
    )
    if not isinstance(markdown, str):
        raise TypeError("analysis reporter must return Markdown text as a string")
    dependencies_after = _capture_external_dependencies(
        kind,
        prepared.payload,
        prepared.base_dir,
    )
    diagnostics = diagnostic_summary(normalized)
    code_after = _capture_runtime_code_fingerprint()
    provenance = _application_execution_provenance(
        kind,
        prepared.input_sha256,
        dependencies_before,
        dependencies_after,
        code_before,
        code_after,
    )
    if not provenance["code_revision"]["stable_during_run"]:
        raise RuntimeCodeChangedError(code_before, code_after)
    if not provenance["external_dependencies_stable"]:
        raise ExternalDependencyChangedError(
            [
                {
                    "field": item["field"],
                    "declared_path": item["declared_path"],
                    "status": "changed_during_run",
                    "sha256_before": item["sha256_before"],
                    "sha256_after": item["sha256_after"],
                    "size_bytes_before": item["size_bytes_before"],
                    "size_bytes_after": item["size_bytes_after"],
                    "mtime_ns_before": item["mtime_ns_before"],
                    "mtime_ns_after": item["mtime_ns_after"],
                }
                for item in provenance["external_dependencies"]
                if not item["stable_during_run"]
            ]
        )
    diagnostics["application_execution_provenance"] = provenance
    plot = build_plot_model(prepared.payload, normalized)
    _assert_input_snapshot_unchanged(
        kind,
        prepared.payload,
        prepared.input_sha256,
        phase="result presentation",
    )
    return AnalysisRun(
        kind=kind,
        title=spec.title,
        status=_derive_status(normalized),
        result=normalized,
        markdown=markdown,
        diagnostics=diagnostics,
        plot=plot,
        input_snapshot=copy.deepcopy(prepared.payload),
    )

def application_info() -> dict:
    registry_validation = validate_application_registry()
    return {
        "name": "CleanroomX",
        "version": __version__,
        "analysis_count": len(_ANALYSES),
        "bindings_valid": registry_validation["status"] == "ok",
        "registry_validation": registry_validation,
        "implementation_revision": _capture_runtime_code_fingerprint(),
        "runtime_environment": _runtime_environment_provenance(),
        "analyses": analysis_catalog(),
    }
