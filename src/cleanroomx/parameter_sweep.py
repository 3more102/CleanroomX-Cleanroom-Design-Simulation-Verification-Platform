from __future__ import annotations

from dataclasses import dataclass
import copy
from hashlib import sha256
from itertools import product
import json
import math
from pathlib import Path
from typing import Any

from . import __version__
from .application import (
    ANALYSIS_SPECS,
    AnalysisRun,
    ExternalDependencyChangedError,
    analysis_run_matches_input,
    run_analysis,
)


PARAMETER_SWEEP_SCHEMA = "cleanroomx.parameter-sweep"
PARAMETER_SWEEP_SCHEMA_VERSION = 1
DEFAULT_MAX_SWEEP_CASES = 1000
HARD_MAX_SWEEP_CASES = 10000

PathSegment = str | int


class ParameterSweepFormatError(ValueError):
    """Raised when a parameter-sweep definition is malformed."""


class ParameterSweepDependencyChangedError(RuntimeError):
    """Raised when file-backed engineering evidence changes across sweep cases."""


@dataclass(frozen=True)
class SweepParameter:
    path: tuple[PathSegment, ...]
    values: tuple[Any, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": list(self.path),
            "values": copy.deepcopy(list(self.values)),
        }


@dataclass(frozen=True)
class ParameterSweepSpec:
    name: str
    analysis_kind: str
    base_input: dict[str, Any]
    parameters: tuple[SweepParameter, ...]
    max_cases: int = DEFAULT_MAX_SWEEP_CASES
    fail_fast: bool = False

    @property
    def planned_case_count(self) -> int:
        count = 1
        for parameter in self.parameters:
            count *= len(parameter.values)
        return count

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PARAMETER_SWEEP_SCHEMA,
            "schema_version": PARAMETER_SWEEP_SCHEMA_VERSION,
            "name": self.name,
            "analysis_kind": self.analysis_kind,
            "base_input": copy.deepcopy(self.base_input),
            "parameters": [parameter.to_dict() for parameter in self.parameters],
            "max_cases": self.max_cases,
            "fail_fast": self.fail_fast,
        }


def _strict_json_value(value: Any, path: str = "$", active: set[int] | None = None) -> None:
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ParameterSweepFormatError(f"{path} must not contain NaN or infinity")
        return
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ParameterSweepFormatError(f"{path} must contain valid UTF-8 text") from exc
        return

    if active is None:
        active = set()
    if isinstance(value, list):
        identity = id(value)
        if identity in active:
            raise ParameterSweepFormatError(f"{path} contains a cyclic list")
        active.add(identity)
        try:
            for index, item in enumerate(value):
                _strict_json_value(item, f"{path}[{index}]", active)
        finally:
            active.remove(identity)
        return
    if isinstance(value, dict):
        identity = id(value)
        if identity in active:
            raise ParameterSweepFormatError(f"{path} contains a cyclic object")
        active.add(identity)
        try:
            for key, item in value.items():
                if not isinstance(key, str):
                    raise ParameterSweepFormatError(
                        f"{path} object keys must be strings, got {type(key).__name__}"
                    )
                _strict_json_value(item, f"{path}.{key}", active)
        finally:
            active.remove(identity)
        return
    raise ParameterSweepFormatError(
        f"{path} contains unsupported non-JSON value type {type(value).__name__}"
    )


def _canonical_json(value: Any) -> str:
    _strict_json_value(value)
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )


def _canonical_sha256(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _validate_path(raw: Any, parameter_index: int) -> tuple[PathSegment, ...]:
    label = f"parameters[{parameter_index}].path"
    if not isinstance(raw, list) or not raw:
        raise ParameterSweepFormatError(f"{label} must be a non-empty array")
    path: list[PathSegment] = []
    for segment_index, segment in enumerate(raw):
        if isinstance(segment, str):
            if not segment:
                raise ParameterSweepFormatError(
                    f"{label}[{segment_index}] must not be an empty string"
                )
            path.append(segment)
        elif type(segment) is int and segment >= 0:
            path.append(segment)
        else:
            raise ParameterSweepFormatError(
                f"{label}[{segment_index}] must be a string key or non-negative integer index"
            )
    return tuple(path)


def _resolve_parent(root: Any, path: tuple[PathSegment, ...]) -> tuple[Any, PathSegment]:
    current = root
    for depth, segment in enumerate(path[:-1]):
        prefix = list(path[: depth + 1])
        if isinstance(segment, str):
            if not isinstance(current, dict) or segment not in current:
                raise ParameterSweepFormatError(
                    f"parameter path does not exist at segment {prefix!r}"
                )
            current = current[segment]
        else:
            if not isinstance(current, list) or segment >= len(current):
                raise ParameterSweepFormatError(
                    f"parameter path does not exist at segment {prefix!r}"
                )
            current = current[segment]

    leaf = path[-1]
    if isinstance(leaf, str):
        if not isinstance(current, dict) or leaf not in current:
            raise ParameterSweepFormatError(
                f"parameter path does not exist at segment {list(path)!r}"
            )
    elif not isinstance(current, list) or leaf >= len(current):
        raise ParameterSweepFormatError(
            f"parameter path does not exist at segment {list(path)!r}"
        )
    return current, leaf


def _set_existing_path(root: Any, path: tuple[PathSegment, ...], value: Any) -> None:
    parent, leaf = _resolve_parent(root, path)
    parent[leaf] = copy.deepcopy(value)


def _paths_overlap(left: tuple[PathSegment, ...], right: tuple[PathSegment, ...]) -> bool:
    shorter = min(len(left), len(right))
    return left[:shorter] == right[:shorter]


def parameter_sweep_from_dict(data: Any) -> ParameterSweepSpec:
    if not isinstance(data, dict):
        raise ParameterSweepFormatError("parameter sweep must contain a JSON object")
    _strict_json_value(data)

    allowed = {
        "schema",
        "schema_version",
        "name",
        "analysis_kind",
        "base_input",
        "parameters",
        "max_cases",
        "fail_fast",
    }
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ParameterSweepFormatError(
            "unsupported parameter-sweep field(s): " + ", ".join(unknown)
        )
    if data.get("schema") != PARAMETER_SWEEP_SCHEMA:
        raise ParameterSweepFormatError(
            f"schema must be {PARAMETER_SWEEP_SCHEMA!r}"
        )
    version = data.get("schema_version")
    if type(version) is not int or version != PARAMETER_SWEEP_SCHEMA_VERSION:
        raise ParameterSweepFormatError(
            f"schema_version must be {PARAMETER_SWEEP_SCHEMA_VERSION}"
        )

    name = data.get("name", "Parameter sweep")
    if not isinstance(name, str) or not name.strip():
        raise ParameterSweepFormatError("name must be a non-empty string")
    name = name.strip()

    analysis_kind = data.get("analysis_kind")
    if not isinstance(analysis_kind, str) or analysis_kind not in ANALYSIS_SPECS:
        raise ParameterSweepFormatError(
            f"analysis_kind must name a supported CleanroomX analysis, got {analysis_kind!r}"
        )

    base_input = data.get("base_input")
    if not isinstance(base_input, dict):
        raise ParameterSweepFormatError("base_input must be a JSON object")
    base_input = copy.deepcopy(base_input)

    max_cases = data.get("max_cases", DEFAULT_MAX_SWEEP_CASES)
    if type(max_cases) is not int or not (1 <= max_cases <= HARD_MAX_SWEEP_CASES):
        raise ParameterSweepFormatError(
            f"max_cases must be an integer from 1 to {HARD_MAX_SWEEP_CASES}"
        )
    fail_fast = data.get("fail_fast", False)
    if not isinstance(fail_fast, bool):
        raise ParameterSweepFormatError("fail_fast must be a boolean")

    raw_parameters = data.get("parameters")
    if not isinstance(raw_parameters, list) or not raw_parameters:
        raise ParameterSweepFormatError("parameters must be a non-empty array")

    parameters: list[SweepParameter] = []
    for index, raw_parameter in enumerate(raw_parameters):
        if not isinstance(raw_parameter, dict):
            raise ParameterSweepFormatError(f"parameters[{index}] must be an object")
        if set(raw_parameter) != {"path", "values"}:
            raise ParameterSweepFormatError(
                f"parameters[{index}] must contain exactly path and values"
            )
        path = _validate_path(raw_parameter["path"], index)
        _resolve_parent(base_input, path)
        raw_values = raw_parameter["values"]
        if not isinstance(raw_values, list) or not raw_values:
            raise ParameterSweepFormatError(
                f"parameters[{index}].values must be a non-empty array"
            )

        values: list[Any] = []
        canonical_values: set[str] = set()
        for value_index, value in enumerate(raw_values):
            if isinstance(value, (dict, list)):
                raise ParameterSweepFormatError(
                    f"parameters[{index}].values[{value_index}] must be a JSON scalar"
                )
            canonical = _canonical_json(value)
            if canonical in canonical_values:
                raise ParameterSweepFormatError(
                    f"parameters[{index}].values contains duplicate value {value!r}"
                )
            canonical_values.add(canonical)
            values.append(copy.deepcopy(value))
        parameters.append(SweepParameter(path=path, values=tuple(values)))

    for left_index, left in enumerate(parameters):
        for right in parameters[left_index + 1 :]:
            if _paths_overlap(left.path, right.path):
                raise ParameterSweepFormatError(
                    "parameter paths must be distinct and non-overlapping: "
                    f"{list(left.path)!r} and {list(right.path)!r}"
                )

    spec = ParameterSweepSpec(
        name=name,
        analysis_kind=analysis_kind,
        base_input=base_input,
        parameters=tuple(parameters),
        max_cases=max_cases,
        fail_fast=fail_fast,
    )
    if spec.planned_case_count > spec.max_cases:
        raise ParameterSweepFormatError(
            f"sweep expands to {spec.planned_case_count} cases, exceeding max_cases={spec.max_cases}"
        )
    return spec


def _reject_json_constant(value: str) -> Any:
    raise ParameterSweepFormatError(f"non-finite JSON constant is not allowed: {value}")


def _reject_duplicate_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ParameterSweepFormatError(f"duplicate JSON object key is not allowed: {key!r}")
        result[key] = value
    return result


def load_parameter_sweep(path: str | Path) -> ParameterSweepSpec:
    source = Path(path)
    try:
        data = json.loads(
            source.read_text(encoding="utf-8"),
            parse_constant=_reject_json_constant,
            object_pairs_hook=_reject_duplicate_object_pairs,
        )
    except json.JSONDecodeError as exc:
        raise ParameterSweepFormatError(
            f"invalid parameter-sweep JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    return parameter_sweep_from_dict(data)


def _dependency_revision(run: AnalysisRun) -> tuple[tuple[Any, ...], ...]:
    provenance = run.diagnostics.get("application_execution_provenance")
    if not isinstance(provenance, dict):
        raise RuntimeError("analysis run is missing application execution provenance")
    dependencies = provenance.get("external_dependencies")
    if not isinstance(dependencies, list):
        raise RuntimeError("analysis run has malformed external dependency provenance")
    revision: list[tuple[Any, ...]] = []
    for item in dependencies:
        if not isinstance(item, dict) or item.get("stable_during_run") is not True:
            raise RuntimeError("analysis run has unstable external dependency provenance")
        revision.append(
            (
                item.get("field"),
                item.get("declared_path"),
                item.get("sha256_after"),
                item.get("size_bytes_after"),
            )
        )
    return tuple(sorted(revision, key=lambda item: (str(item[0]), str(item[1]))))


def _dependency_records(revision: tuple[tuple[Any, ...], ...]) -> list[dict[str, Any]]:
    return [
        {
            "field": field,
            "declared_path": declared_path,
            "sha256": digest,
            "size_bytes": size_bytes,
        }
        for field, declared_path, digest, size_bytes in revision
    ]


def run_parameter_sweep(
    spec: ParameterSweepSpec,
    *,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    if not isinstance(spec, ParameterSweepSpec):
        raise TypeError("spec must be a ParameterSweepSpec")

    cases: list[dict[str, Any]] = []
    dependency_revision: tuple[tuple[Any, ...], ...] | None = None
    completed_count = 0
    error_count = 0

    value_sets = [parameter.values for parameter in spec.parameters]
    for case_index, selected_values in enumerate(product(*value_sets)):
        case_input = copy.deepcopy(spec.base_input)
        assignments: list[dict[str, Any]] = []
        for parameter, value in zip(spec.parameters, selected_values):
            _set_existing_path(case_input, parameter.path, value)
            assignments.append(
                {"path": list(parameter.path), "value": copy.deepcopy(value)}
            )

        input_snapshot = copy.deepcopy(case_input)
        input_sha256 = _canonical_sha256(input_snapshot)
        case_record: dict[str, Any] = {
            "index": case_index,
            "assignments": assignments,
            "input": input_snapshot,
            "input_sha256": input_sha256,
        }

        try:
            run = run_analysis(
                spec.analysis_kind,
                copy.deepcopy(input_snapshot),
                base_dir=base_dir,
            )
        except ExternalDependencyChangedError as exc:
            raise ParameterSweepDependencyChangedError(
                f"external engineering dependency changed during sweep case {case_index}; "
                "the sweep result was discarded"
            ) from exc
        except Exception as exc:
            error_count += 1
            case_record.update(
                {
                    "execution_status": "error",
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                }
            )
            cases.append(case_record)
            if spec.fail_fast:
                break
            continue

        if not analysis_run_matches_input(run, spec.analysis_kind, input_snapshot):
            raise RuntimeError(
                f"analysis provenance does not match immutable sweep input for case {case_index}"
            )
        current_dependency_revision = _dependency_revision(run)
        if dependency_revision is None:
            dependency_revision = current_dependency_revision
        elif current_dependency_revision != dependency_revision:
            raise ParameterSweepDependencyChangedError(
                "external engineering dependency content changed between successful "
                f"sweep cases; detected at case {case_index}. Run the study again "
                "against a stable dependency set."
            )

        completed_count += 1
        case_record.update(
            {
                "execution_status": "completed",
                "analysis_status": run.status,
                "run": run.to_dict(),
            }
        )
        cases.append(case_record)

    executed_count = len(cases)
    if error_count == 0 and executed_count == spec.planned_case_count:
        execution_status = "completed"
    elif spec.fail_fast and error_count:
        execution_status = "stopped_on_error"
    else:
        execution_status = "completed_with_errors"

    definition = spec.to_dict()
    return {
        "schema": "cleanroomx.parameter-sweep-result",
        "schema_version": 1,
        "cleanroomx_version": __version__,
        "name": spec.name,
        "analysis_kind": spec.analysis_kind,
        "execution_status": execution_status,
        "definition_sha256": _canonical_sha256(definition),
        "base_input_sha256": _canonical_sha256(spec.base_input),
        "planned_case_count": spec.planned_case_count,
        "executed_case_count": executed_count,
        "completed_case_count": completed_count,
        "error_case_count": error_count,
        "external_dependencies": _dependency_records(dependency_revision or ()),
        "definition": definition,
        "cases": cases,
    }


def parameter_sweep_markdown(result: dict[str, Any]) -> str:
    if not isinstance(result, dict) or result.get("schema") != "cleanroomx.parameter-sweep-result":
        raise ValueError("result must be a CleanroomX parameter-sweep result")

    lines = [
        f"# {result['name']}",
        "",
        f"- Analysis kind: \`{result['analysis_kind']}\`",
        f"- Execution status: \`{result['execution_status']}\`",
        f"- Planned cases: {result['planned_case_count']}",
        f"- Executed cases: {result['executed_case_count']}",
        f"- Completed cases: {result['completed_case_count']}",
        f"- Case execution errors: {result['error_case_count']}",
        f"- Definition SHA-256: \`{result['definition_sha256']}\`",
        f"- Base input SHA-256: \`{result['base_input_sha256']}\`",
        "",
        "| Case | Parameters | Execution | Analysis status | Input SHA-256 |",
        "|---:|---|---|---|---|",
    ]
    for case in result["cases"]:
        assignments = "; ".join(
            f"{json.dumps(item['path'], ensure_ascii=False)}={json.dumps(item['value'], ensure_ascii=False)}"
            for item in case["assignments"]
        ).replace("|", "\\|")
        execution = str(case["execution_status"]).replace("|", "\\|")
        analysis_status = str(case.get("analysis_status", "—")).replace("|", "\\|")
        lines.append(
            f"| {case['index']} | {assignments} | {execution} | "
            f"{analysis_status} | \`{case['input_sha256']}\` |"
        )
        if case["execution_status"] == "error":
            error = case["error"]
            message = str(error["message"]).replace("|", "\\|").replace("\n", " ")
            lines.append(
                f"|  | Error | {error['type']} | {message} |  |"
            )
    return "\n".join(lines) + "\n"
