from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Any

from .design_requirements import (
    DesignRequirementsProject,
    analyze_design_requirements,
    design_requirements_from_dict,
)
from .input_contracts import reject_unknown_fields
from .markdown import markdown_text
from .pressure_network import RoomPressureNetwork, solve_room_pressure_network
from .pressure_network_io import pressure_network_from_dict
from .verification import aggregate_verification_status


_ALLOWED_INPUT_KEYS = frozenset(
    {
        "name",
        "requirements",
        "pressure_network",
        "mappings",
        "pressure_abs_tolerance_pa",
        "require_all_configured_targets_mapped",
    }
)
_ALLOWED_MAPPING_KEYS = frozenset({"room", "node", "reference_node"})


def _nonnegative_finite(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a finite number >= 0")
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{field_name} must be a finite number >= 0")
    return number


def _nonempty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


@dataclass(frozen=True)
class PressureRequirementMapping:
    room: str
    node: str
    reference_node: str

    def __post_init__(self) -> None:
        for field_name in ("room", "node", "reference_node"):
            object.__setattr__(
                self,
                field_name,
                _nonempty_string(getattr(self, field_name), field_name),
            )
        if self.node == self.reference_node:
            raise ValueError("mapping node and reference_node must be different")


@dataclass(frozen=True)
class PressureDesignConsistencyStudy:
    name: str
    requirements: DesignRequirementsProject
    pressure_network: RoomPressureNetwork
    mappings: tuple[PressureRequirementMapping, ...]
    pressure_abs_tolerance_pa: float = 0.0
    require_all_configured_targets_mapped: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("pressure-design-consistency study name cannot be empty")
        object.__setattr__(
            self,
            "pressure_abs_tolerance_pa",
            _nonnegative_finite(
                self.pressure_abs_tolerance_pa,
                "pressure_abs_tolerance_pa",
            ),
        )
        if not isinstance(self.require_all_configured_targets_mapped, bool):
            raise ValueError("require_all_configured_targets_mapped must be a boolean")

        room_names = {room.name for room in self.requirements.rooms}
        node_names = {node.name for node in self.pressure_network.nodes}
        mapped_rooms = [mapping.room for mapping in self.mappings]
        if len(mapped_rooms) != len(set(mapped_rooms)):
            raise ValueError("mappings must contain at most one entry per requirements room")

        for mapping in self.mappings:
            if mapping.room not in room_names:
                raise ValueError(
                    f"mapping room {mapping.room!r} is not present in design requirements"
                )
            if mapping.node not in node_names:
                raise ValueError(
                    f"mapping node {mapping.node!r} is not present in pressure network"
                )
            if mapping.reference_node not in node_names:
                raise ValueError(
                    f"mapping reference_node {mapping.reference_node!r} is not present in pressure network"
                )


def pressure_design_consistency_from_dict(
    data: dict,
) -> PressureDesignConsistencyStudy:
    if not isinstance(data, dict):
        raise ValueError("pressure design consistency input must be an object")
    reject_unknown_fields(
        data,
        _ALLOWED_INPUT_KEYS,
        context="pressure design consistency input",
    )

    name = _nonempty_string(data.get("name"), "name")
    requirements_data = data.get("requirements")
    if not isinstance(requirements_data, dict):
        raise ValueError("requirements must be a design-requirements object")
    network_data = data.get("pressure_network")
    if not isinstance(network_data, dict):
        raise ValueError("pressure_network must be a pressure-network object")

    raw_mappings = data.get("mappings", [])
    if not isinstance(raw_mappings, list):
        raise ValueError("mappings must be an array")
    mappings: list[PressureRequirementMapping] = []
    for index, item in enumerate(raw_mappings):
        if not isinstance(item, dict):
            raise ValueError(f"mappings[{index}] must be an object")
        reject_unknown_fields(
            item,
            _ALLOWED_MAPPING_KEYS,
            context=f"mappings[{index}]",
        )
        missing = sorted(_ALLOWED_MAPPING_KEYS - set(item))
        if missing:
            raise ValueError(
                f"mappings[{index}] is missing required field(s): {', '.join(missing)}"
            )
        mappings.append(
            PressureRequirementMapping(
                room=item["room"],
                node=item["node"],
                reference_node=item["reference_node"],
            )
        )

    require_all = data.get("require_all_configured_targets_mapped", True)
    if not isinstance(require_all, bool):
        raise ValueError("require_all_configured_targets_mapped must be a boolean")

    return PressureDesignConsistencyStudy(
        name=name,
        requirements=design_requirements_from_dict(requirements_data),
        pressure_network=pressure_network_from_dict(network_data),
        mappings=tuple(mappings),
        pressure_abs_tolerance_pa=data.get("pressure_abs_tolerance_pa", 0.0),
        require_all_configured_targets_mapped=require_all,
    )


def _finding(
    *,
    room: str,
    status: str,
    message: str,
    expected: float | None,
    actual: float | None,
    delta: float | None,
    tolerance: float,
    mapping: PressureRequirementMapping | None,
    provenance: dict[str, Any] | None,
) -> dict[str, Any]:
    if status not in {"pass", "fail", "not_checked"}:
        raise ValueError(f"unsupported pressure-design-consistency status: {status!r}")
    return {
        "code": "requirements.pressure_target_pa",
        "room": room,
        "status": status,
        "message": message,
        "expected": expected,
        "actual": actual,
        "delta": delta,
        "tolerance": tolerance,
        "unit": "Pa",
        "mapping": (
            None
            if mapping is None
            else {
                "node": mapping.node,
                "reference_node": mapping.reference_node,
            }
        ),
        "provenance": dict(provenance or {}),
    }


def analyze_pressure_design_consistency(
    study: PressureDesignConsistencyStudy,
) -> dict:
    requirements_result = analyze_design_requirements(study.requirements)
    network_result = solve_room_pressure_network(study.pressure_network)

    requirements_by_name = {room.name: room for room in study.requirements.rooms}
    mappings_by_room = {mapping.room: mapping for mapping in study.mappings}
    pressures = {
        item["name"]: item["pressure_pa"]
        for item in network_result["nodes"]
    }

    findings: list[dict[str, Any]] = []
    for room_name in sorted(requirements_by_name):
        room = requirements_by_name[room_name]
        mapping = mappings_by_room.get(room_name)
        provenance = room.origins.get("pressure_target_pa")

        if mapping is None:
            if room.pressure_target_pa is None:
                findings.append(
                    _finding(
                        room=room_name,
                        status="not_checked",
                        message=(
                            "No room pressure target is configured and no explicit "
                            "pressure-network mapping is supplied."
                        ),
                        expected=None,
                        actual=None,
                        delta=None,
                        tolerance=study.pressure_abs_tolerance_pa,
                        mapping=None,
                        provenance=provenance,
                    )
                )
            elif study.require_all_configured_targets_mapped:
                findings.append(
                    _finding(
                        room=room_name,
                        status="fail",
                        message=(
                            "A room pressure target is configured, but no explicit "
                            "pressure-network node/reference mapping is supplied."
                        ),
                        expected=room.pressure_target_pa,
                        actual=None,
                        delta=None,
                        tolerance=study.pressure_abs_tolerance_pa,
                        mapping=None,
                        provenance=provenance,
                    )
                )
            else:
                findings.append(
                    _finding(
                        room=room_name,
                        status="not_checked",
                        message=(
                            "A room pressure target is configured but intentionally "
                            "left unmapped because complete target mapping is disabled."
                        ),
                        expected=room.pressure_target_pa,
                        actual=None,
                        delta=None,
                        tolerance=study.pressure_abs_tolerance_pa,
                        mapping=None,
                        provenance=provenance,
                    )
                )
            continue

        observed = pressures[mapping.node] - pressures[mapping.reference_node]
        if room.pressure_target_pa is None:
            findings.append(
                _finding(
                    room=room_name,
                    status="not_checked",
                    message=(
                        "The network pressure difference is retained as evidence, "
                        "but no room pressure target is configured."
                    ),
                    expected=None,
                    actual=observed,
                    delta=None,
                    tolerance=study.pressure_abs_tolerance_pa,
                    mapping=mapping,
                    provenance=provenance,
                )
            )
            continue

        delta = observed - room.pressure_target_pa
        passed = abs(delta) <= study.pressure_abs_tolerance_pa
        findings.append(
            _finding(
                room=room_name,
                status="pass" if passed else "fail",
                message=(
                    "The solved pressure difference matches the configured room "
                    "pressure target within the absolute tolerance."
                    if passed
                    else "The solved pressure difference differs from the configured "
                    "room pressure target by more than the absolute tolerance."
                ),
                expected=room.pressure_target_pa,
                actual=observed,
                delta=delta,
                tolerance=study.pressure_abs_tolerance_pa,
                mapping=mapping,
                provenance=provenance,
            )
        )

    counts = {
        status: sum(1 for finding in findings if finding["status"] == status)
        for status in ("pass", "fail", "not_checked")
    }
    status = aggregate_verification_status(
        finding["status"] for finding in findings
    )
    configured_targets = sum(
        room.pressure_target_pa is not None for room in study.requirements.rooms
    )
    mapped_configured_targets = sum(
        room.pressure_target_pa is not None and room.name in mappings_by_room
        for room in study.requirements.rooms
    )

    return {
        "study": study.name,
        "status": status,
        "complete": bool(findings) and counts["not_checked"] == 0,
        "passed": counts["fail"] == 0,
        "summary": {
            "finding_count": len(findings),
            "pass_count": counts["pass"],
            "fail_count": counts["fail"],
            "not_checked_count": counts["not_checked"],
            "requirements_room_count": len(study.requirements.rooms),
            "configured_pressure_target_count": configured_targets,
            "mapped_pressure_target_count": mapped_configured_targets,
        },
        "tolerances": {
            "pressure_abs_tolerance_pa": study.pressure_abs_tolerance_pa,
        },
        "mapping_policy": {
            "require_all_configured_targets_mapped": (
                study.require_all_configured_targets_mapped
            ),
            "interpretation": (
                "pressure_target_pa is compared only to node pressure minus "
                "reference_node pressure from an explicit room mapping"
            ),
        },
        "findings": findings,
        "source_analyses": {
            "design_requirements": {
                "name": requirements_result["project"],
                "status": requirements_result["status"],
                "warning_count": requirements_result["warning_count"],
                "warnings": list(requirements_result["warnings"]),
            },
            "pressure_network": {
                "name": network_result["network"],
                "status": network_result["status"],
                "solver": dict(network_result["solver"]),
                "target_summary": dict(network_result["target_summary"]),
            },
        },
        "engineering_note": (
            "This read-only cross-check compares each configured room pressure target "
            "only against a solved node-to-reference pressure difference selected by "
            "an explicit mapping. It does not infer reference rooms, leakage data, "
            "standards limits, or regulatory criteria. Pressure-network target checks "
            "remain independent evidence and are reported but are not silently "
            "reinterpreted as design-requirement mappings."
        ),
    }


def _md(value: Any) -> str:
    if value is None:
        text = "—"
    elif isinstance(value, str):
        text = value
    else:
        text = json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
    return markdown_text(text)


def markdown_pressure_design_consistency_report(result: dict) -> str:
    summary = result["summary"]
    network = result["source_analyses"]["pressure_network"]
    lines = [
        "# CleanroomX Pressure Design Consistency",
        "",
        f"- Study: {_md(result['study'])}",
        f"- Status: **{_md(result['status'])}**",
        f"- Complete defined comparisons: **{'YES' if result['complete'] else 'NO'}**",
        (
            "- Pass / Fail / Not checked: "
            f"{summary['pass_count']} / {summary['fail_count']} / "
            f"{summary['not_checked_count']}"
        ),
        (
            "- Pressure-network source: "
            f"{_md(network['name'])} / {_md(network['status'])}"
        ),
        (
            "- Absolute pressure tolerance: "
            f"{_md(result['tolerances']['pressure_abs_tolerance_pa'])} Pa"
        ),
        "",
        "| Room | Node | Reference | Expected Pa | Actual Pa | Delta Pa | Status |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for finding in result["findings"]:
        mapping = finding["mapping"] or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    _md(finding["room"]),
                    _md(mapping.get("node")),
                    _md(mapping.get("reference_node")),
                    _md(finding["expected"]),
                    _md(finding["actual"]),
                    _md(finding["delta"]),
                    _md(finding["status"]),
                ]
            )
            + " |"
        )

    unresolved = [
        finding for finding in result["findings"]
        if finding["status"] != "pass"
    ]
    lines.extend(["", "## Non-pass evidence", ""])
    if unresolved:
        for finding in unresolved:
            lines.append(
                f"- {_md(finding['room'])}: **{_md(finding['status'])}** — "
                f"{_md(finding['message'])}"
            )
    else:
        lines.append("No failed or unresolved pressure-target comparisons are present.")

    lines.extend(["", _md(result["engineering_note"])])
    return "\n".join(lines) + "\n"
