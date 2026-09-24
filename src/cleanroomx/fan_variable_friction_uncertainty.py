from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from itertools import product
from math import prod

from .fan_curve import FanCurve
from .fan_speed import scale_fan_curve_for_speed
from .fan_variable_friction_loop import (
    FanVariableFrictionLoopStudy,
    solve_fan_variable_friction_loop,
)
from .loop_network import LoopedFlowNetwork, QuadraticFlowEdge
from .loop_resistance import LoopedDuctResistanceInput, derive_loop_edge_resistance
from .pressure_power import FanPowerEfficiencies
from .uncertainty_models import Provenance, UncertainValue


def _canonical_result_sha256(payload: dict) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class FanCurveScenario:
    name: str
    fan_curve: FanCurve
    provenance: Provenance | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("fan-curve scenario name cannot be empty")


@dataclass(frozen=True)
class FanVariableFrictionLoopUncertaintyStudy:
    name: str
    fan_curve: FanCurve
    loop_network: LoopedFlowNetwork
    fan_discharge_node: str
    fan_suction_node: str
    fixed_pressure_pa: UncertainValue
    edge_local_loss_coefficient: dict[str, UncertainValue]
    edge_absolute_roughness_m: dict[str, UncertainValue] = field(
        default_factory=dict
    )
    edge_kinematic_viscosity_m2_s: dict[str, UncertainValue] = field(
        default_factory=dict
    )
    edge_air_density_kg_m3: dict[str, UncertainValue] = field(
        default_factory=dict
    )
    edge_length_m: dict[str, UncertainValue] = field(default_factory=dict)
    edge_circular_diameter_m: dict[str, UncertainValue] = field(
        default_factory=dict
    )
    edge_rectangular_width_m: dict[str, UncertainValue] = field(
        default_factory=dict
    )
    edge_rectangular_height_m: dict[str, UncertainValue] = field(
        default_factory=dict
    )
    fan_curve_pressure_pa: dict[float, UncertainValue] = field(
        default_factory=dict
    )
    fan_curve_airflow_m3_h: dict[int, UncertainValue] = field(
        default_factory=dict
    )
    fan_curve_scenarios: tuple[FanCurveScenario, ...] = ()
    fan_speed_ratio: UncertainValue | None = None
    fan_curve_provenance: Provenance | None = None
    max_corner_cases: int = 256
    power_efficiencies: FanPowerEfficiencies | None = None
    resistance_relative_tolerance: float = 1e-6
    relaxation: float = 0.5
    near_zero_airflow_m3_h: float = 1e-6
    max_outer_iterations: int = 50
    mass_balance_tolerance_m3_h: float = 1e-6
    max_newton_iterations: int = 100
    operating_pressure_tolerance_pa: float = 1e-6
    max_operating_iterations: int = 80

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError(
                "fan/variable-friction uncertainty study name cannot be empty"
            )
        if self.fixed_pressure_pa.unit != "Pa":
            raise ValueError("fixed_pressure_pa unit must be 'Pa'")
        if self.fixed_pressure_pa.lower < 0:
            raise ValueError(
                "fixed_pressure_pa lower uncertainty bound must remain >= 0"
            )
        if self.fan_speed_ratio is not None:
            if self.fan_speed_ratio.unit != "1":
                raise ValueError("fan_speed_ratio unit must be '1'")
            if self.fan_speed_ratio.lower <= 0:
                raise ValueError(
                    "fan_speed_ratio lower uncertainty bound must remain > 0"
                )
        if (
            isinstance(self.max_corner_cases, bool)
            or not isinstance(self.max_corner_cases, int)
            or self.max_corner_cases <= 0
        ):
            raise ValueError("max_corner_cases must be an integer > 0")

        scenarios = tuple(self.fan_curve_scenarios)
        object.__setattr__(self, "fan_curve_scenarios", scenarios)
        scenario_names: set[str] = set()
        for scenario in scenarios:
            if scenario.name == "nominal":
                raise ValueError(
                    "fan-curve scenario name 'nominal' is reserved"
                )
            if scenario.name in scenario_names:
                raise ValueError(
                    f"duplicate fan-curve scenario name {scenario.name!r}"
                )
            scenario_names.add(scenario.name)
        if scenarios and (
            self.fan_curve_pressure_pa or self.fan_curve_airflow_m3_h
        ):
            raise ValueError(
                "fan-curve scenarios cannot be combined with independent "
                "fan-curve pressure or airflow-coordinate uncertainty"
            )

        normalized_fan_airflow: dict[int, UncertainValue] = {}
        for point_index, item in self.fan_curve_airflow_m3_h.items():
            if (
                isinstance(point_index, bool)
                or not isinstance(point_index, int)
                or point_index < 0
                or point_index >= len(self.fan_curve.points)
            ):
                raise ValueError(
                    "fan-curve airflow uncertainty point index must identify "
                    "an existing supplied fan-curve point"
                )
            point = self.fan_curve.points[point_index]
            if item.unit != "m3/h":
                raise ValueError(
                    "fan-curve airflow uncertainty must use unit 'm3/h'"
                )
            if item.lower < 0:
                raise ValueError(
                    "fan-curve airflow lower uncertainty bound must remain "
                    f">= 0 at point index {point_index}"
                )
            if not math.isclose(
                item.value,
                point.airflow_m3_h,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                raise ValueError(
                    "fan-curve airflow uncertainty nominal must match the "
                    f"supplied curve airflow at point index {point_index}"
                )
            normalized_fan_airflow[point_index] = item
        object.__setattr__(
            self,
            "fan_curve_airflow_m3_h",
            normalized_fan_airflow,
        )

        for point_index, (left, right) in enumerate(
            zip(self.fan_curve.points, self.fan_curve.points[1:])
        ):
            left_uncertain = self.fan_curve_airflow_m3_h.get(point_index)
            right_uncertain = self.fan_curve_airflow_m3_h.get(
                point_index + 1
            )
            left_upper = (
                left_uncertain.upper
                if left_uncertain is not None
                else left.airflow_m3_h
            )
            right_lower = (
                right_uncertain.lower
                if right_uncertain is not None
                else right.airflow_m3_h
            )
            if left_upper >= right_lower:
                raise ValueError(
                    "fan-curve airflow uncertainty can create non-increasing "
                    "airflow coordinates between supplied point indices "
                    f"{point_index} and {point_index + 1}"
                )

        fan_points_by_airflow = {
            float(point.airflow_m3_h): point for point in self.fan_curve.points
        }
        normalized_fan_pressure: dict[float, UncertainValue] = {}
        for airflow_m3_h, item in self.fan_curve_pressure_pa.items():
            airflow = float(airflow_m3_h)
            point = fan_points_by_airflow.get(airflow)
            if point is None:
                raise ValueError(
                    "fan-curve pressure uncertainty references an unknown "
                    f"supplied airflow point {airflow!r} m3/h"
                )
            if item.unit != "Pa":
                raise ValueError(
                    "fan-curve pressure uncertainty must use unit 'Pa'"
                )
            if item.lower < 0:
                raise ValueError(
                    "fan-curve pressure lower uncertainty bound must remain "
                    f">= 0 at {airflow:g} m3/h"
                )
            if not math.isclose(
                item.value,
                point.pressure_pa,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                raise ValueError(
                    "fan-curve pressure uncertainty nominal must match the "
                    f"supplied curve pressure at {airflow:g} m3/h"
                )
            normalized_fan_pressure[airflow] = item
        object.__setattr__(
            self,
            "fan_curve_pressure_pa",
            normalized_fan_pressure,
        )

        for left, right in zip(self.fan_curve.points, self.fan_curve.points[1:]):
            left_uncertain = self.fan_curve_pressure_pa.get(
                float(left.airflow_m3_h)
            )
            right_uncertain = self.fan_curve_pressure_pa.get(
                float(right.airflow_m3_h)
            )
            left_lower = (
                left_uncertain.lower
                if left_uncertain is not None
                else left.pressure_pa
            )
            right_upper = (
                right_uncertain.upper
                if right_uncertain is not None
                else right.pressure_pa
            )
            if right_upper > left_lower:
                raise ValueError(
                    "fan-curve pressure uncertainty can create a pressure "
                    "increase with airflow between supplied points "
                    f"{left.airflow_m3_h:g} and {right.airflow_m3_h:g} m3/h"
                )

        edges_by_name = {edge.name: edge for edge in self.loop_network.edges}
        normalized: dict[str, UncertainValue] = {}
        for edge_name, item in self.edge_local_loss_coefficient.items():
            edge = edges_by_name.get(edge_name)
            if edge is None:
                raise ValueError(
                    "edge local-loss uncertainty references unknown edge "
                    f"{edge_name!r}"
                )
            evidence = edge.resistance_evidence
            if (
                edge.resistance_basis != "duct_geometry"
                or evidence is None
                or evidence.get("absolute_roughness_m") is None
                or evidence.get("kinematic_viscosity_m2_s") is None
            ):
                raise ValueError(
                    f"edge local-loss uncertainty for {edge_name!r} requires "
                    "an automatic-friction duct_geometry edge"
                )
            if item.unit != "1":
                raise ValueError(
                    f"edge local-loss uncertainty for {edge_name!r} "
                    "must use unit '1'"
                )
            if item.lower < 0:
                raise ValueError(
                    f"edge local-loss lower uncertainty bound for "
                    f"{edge_name!r} must remain >= 0"
                )
            nominal = float(evidence["local_loss_coefficient"])
            if not math.isclose(
                item.value,
                nominal,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                raise ValueError(
                    f"edge local-loss uncertainty nominal for {edge_name!r} "
                    "must match the loop-network geometry evidence"
                )
            normalized[edge_name] = item
        object.__setattr__(self, "edge_local_loss_coefficient", normalized)

        physical_uncertainty_specs = (
            (
                "edge_absolute_roughness_m",
                self.edge_absolute_roughness_m,
                "absolute_roughness_m",
                "m",
                "absolute-roughness",
                True,
            ),
            (
                "edge_kinematic_viscosity_m2_s",
                self.edge_kinematic_viscosity_m2_s,
                "kinematic_viscosity_m2_s",
                "m2/s",
                "kinematic-viscosity",
                False,
            ),
            (
                "edge_air_density_kg_m3",
                self.edge_air_density_kg_m3,
                "air_density_kg_m3",
                "kg/m3",
                "air-density",
                False,
            ),
        )
        for (
            attribute_name,
            items,
            evidence_key,
            expected_unit,
            label,
            allow_zero_lower,
        ) in physical_uncertainty_specs:
            normalized_physical: dict[str, UncertainValue] = {}
            for edge_name, item in items.items():
                edge = edges_by_name.get(edge_name)
                if edge is None:
                    raise ValueError(
                        f"edge {label} uncertainty references unknown edge "
                        f"{edge_name!r}"
                    )
                evidence = edge.resistance_evidence
                if (
                    edge.resistance_basis != "duct_geometry"
                    or evidence is None
                    or evidence.get("absolute_roughness_m") is None
                    or evidence.get("kinematic_viscosity_m2_s") is None
                ):
                    raise ValueError(
                        f"edge {label} uncertainty for {edge_name!r} requires "
                        "an automatic-friction duct_geometry edge"
                    )
                if item.unit != expected_unit:
                    raise ValueError(
                        f"edge {label} uncertainty for {edge_name!r} must use "
                        f"unit {expected_unit!r}"
                    )
                if allow_zero_lower:
                    if item.lower < 0:
                        raise ValueError(
                            f"edge {label} lower uncertainty bound for "
                            f"{edge_name!r} must remain >= 0"
                        )
                elif item.lower <= 0:
                    raise ValueError(
                        f"edge {label} lower uncertainty bound for "
                        f"{edge_name!r} must remain > 0"
                    )
                nominal = float(evidence[evidence_key])
                if not math.isclose(
                    item.value,
                    nominal,
                    rel_tol=1e-12,
                    abs_tol=1e-15,
                ):
                    raise ValueError(
                        f"edge {label} uncertainty nominal for {edge_name!r} "
                        "must match the loop-network geometry evidence"
                    )
                if evidence_key == "absolute_roughness_m":
                    hydraulic_diameter = float(evidence["hydraulic_diameter_m"])
                    if item.upper >= hydraulic_diameter:
                        raise ValueError(
                            f"edge {label} upper uncertainty bound for "
                            f"{edge_name!r} must remain smaller than the "
                            "hydraulic diameter"
                        )
                normalized_physical[edge_name] = item
            object.__setattr__(self, attribute_name, normalized_physical)

        normalized_length: dict[str, UncertainValue] = {}
        for edge_name, item in self.edge_length_m.items():
            edge = edges_by_name.get(edge_name)
            if edge is None:
                raise ValueError(
                    "edge length uncertainty references unknown edge "
                    f"{edge_name!r}"
                )
            evidence = edge.resistance_evidence
            if (
                edge.resistance_basis != "duct_geometry"
                or evidence is None
                or evidence.get("absolute_roughness_m") is None
                or evidence.get("kinematic_viscosity_m2_s") is None
            ):
                raise ValueError(
                    f"edge length uncertainty for {edge_name!r} requires "
                    "an automatic-friction duct_geometry edge"
                )
            if item.unit != "m":
                raise ValueError(
                    f"edge length uncertainty for {edge_name!r} must use "
                    "unit 'm'"
                )
            if item.lower <= 0:
                raise ValueError(
                    f"edge length lower uncertainty bound for {edge_name!r} "
                    "must remain > 0"
                )
            nominal = float(evidence["length_m"])
            if not math.isclose(
                item.value,
                nominal,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                raise ValueError(
                    f"edge length uncertainty nominal for {edge_name!r} "
                    "must match the loop-network geometry evidence"
                )
            normalized_length[edge_name] = item
        object.__setattr__(self, "edge_length_m", normalized_length)

        normalized_diameter: dict[str, UncertainValue] = {}
        for edge_name, item in self.edge_circular_diameter_m.items():
            edge = edges_by_name.get(edge_name)
            if edge is None:
                raise ValueError(
                    "edge circular-diameter uncertainty references unknown "
                    f"edge {edge_name!r}"
                )
            evidence = edge.resistance_evidence
            if (
                edge.resistance_basis != "duct_geometry"
                or evidence is None
                or evidence.get("absolute_roughness_m") is None
                or evidence.get("kinematic_viscosity_m2_s") is None
            ):
                raise ValueError(
                    f"edge circular-diameter uncertainty for {edge_name!r} "
                    "requires an automatic-friction duct_geometry edge"
                )
            if evidence.get("shape") != "circular":
                raise ValueError(
                    f"edge circular-diameter uncertainty for {edge_name!r} "
                    "requires circular duct geometry"
                )
            if item.unit != "m":
                raise ValueError(
                    f"edge circular-diameter uncertainty for {edge_name!r} "
                    "must use unit 'm'"
                )
            if item.lower <= 0:
                raise ValueError(
                    f"edge circular-diameter lower uncertainty bound for "
                    f"{edge_name!r} must remain > 0"
                )
            nominal = float(evidence["hydraulic_diameter_m"])
            if not math.isclose(
                item.value,
                nominal,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                raise ValueError(
                    f"edge circular-diameter uncertainty nominal for "
                    f"{edge_name!r} must match the loop-network geometry "
                    "evidence"
                )
            roughness_item = self.edge_absolute_roughness_m.get(edge_name)
            roughness_upper = (
                roughness_item.upper
                if roughness_item is not None
                else float(evidence["absolute_roughness_m"])
            )
            if roughness_upper >= item.lower:
                raise ValueError(
                    f"edge circular-diameter lower uncertainty bound for "
                    f"{edge_name!r} must remain larger than the maximum "
                    "bounded absolute roughness"
                )
            normalized_diameter[edge_name] = item
        object.__setattr__(
            self,
            "edge_circular_diameter_m",
            normalized_diameter,
        )

        rectangular_specs = (
            (
                "edge_rectangular_width_m",
                self.edge_rectangular_width_m,
                "width_m",
                "width",
            ),
            (
                "edge_rectangular_height_m",
                self.edge_rectangular_height_m,
                "height_m",
                "height",
            ),
        )
        for attribute_name, items, evidence_key, label in rectangular_specs:
            normalized_dimension: dict[str, UncertainValue] = {}
            for edge_name, item in items.items():
                edge = edges_by_name.get(edge_name)
                if edge is None:
                    raise ValueError(
                        f"edge rectangular-{label} uncertainty references "
                        f"unknown edge {edge_name!r}"
                    )
                evidence = edge.resistance_evidence
                if (
                    edge.resistance_basis != "duct_geometry"
                    or evidence is None
                    or evidence.get("absolute_roughness_m") is None
                    or evidence.get("kinematic_viscosity_m2_s") is None
                ):
                    raise ValueError(
                        f"edge rectangular-{label} uncertainty for "
                        f"{edge_name!r} requires an automatic-friction "
                        "duct_geometry edge"
                    )
                if evidence.get("shape") != "rectangular":
                    raise ValueError(
                        f"edge rectangular-{label} uncertainty for "
                        f"{edge_name!r} requires rectangular duct geometry"
                    )
                nominal_value = evidence.get(evidence_key)
                if nominal_value is None:
                    raise ValueError(
                        f"edge rectangular-{label} uncertainty for "
                        f"{edge_name!r} requires explicit stored "
                        f"{evidence_key} evidence"
                    )
                if item.unit != "m":
                    raise ValueError(
                        f"edge rectangular-{label} uncertainty for "
                        f"{edge_name!r} must use unit 'm'"
                    )
                if item.lower <= 0:
                    raise ValueError(
                        f"edge rectangular-{label} lower uncertainty bound "
                        f"for {edge_name!r} must remain > 0"
                    )
                if not math.isclose(
                    item.value,
                    float(nominal_value),
                    rel_tol=1e-12,
                    abs_tol=1e-12,
                ):
                    raise ValueError(
                        f"edge rectangular-{label} uncertainty nominal for "
                        f"{edge_name!r} must match the loop-network geometry "
                        "evidence"
                    )
                normalized_dimension[edge_name] = item
            object.__setattr__(
                self,
                attribute_name,
                normalized_dimension,
            )

        rectangular_edges = (
            set(self.edge_rectangular_width_m)
            | set(self.edge_rectangular_height_m)
        )
        for edge_name in rectangular_edges:
            evidence = edges_by_name[edge_name].resistance_evidence
            assert evidence is not None
            width_item = self.edge_rectangular_width_m.get(edge_name)
            height_item = self.edge_rectangular_height_m.get(edge_name)
            min_width = (
                width_item.lower
                if width_item is not None
                else float(evidence["width_m"])
            )
            min_height = (
                height_item.lower
                if height_item is not None
                else float(evidence["height_m"])
            )
            min_hydraulic_diameter = (
                2.0 * min_width * min_height / (min_width + min_height)
            )
            roughness_item = self.edge_absolute_roughness_m.get(edge_name)
            roughness_upper = (
                roughness_item.upper
                if roughness_item is not None
                else float(evidence["absolute_roughness_m"])
            )
            if roughness_upper >= min_hydraulic_diameter:
                raise ValueError(
                    f"edge rectangular geometry lower bounds for "
                    f"{edge_name!r} must keep hydraulic diameter larger "
                    "than the maximum bounded absolute roughness"
                )

        FanVariableFrictionLoopStudy(
            name=self.name,
            fan_curve=self.fan_curve,
            loop_network=self.loop_network,
            fan_discharge_node=self.fan_discharge_node,
            fan_suction_node=self.fan_suction_node,
            fixed_pressure_pa=self.fixed_pressure_pa.value,
            power_efficiencies=self.power_efficiencies,
            resistance_relative_tolerance=self.resistance_relative_tolerance,
            relaxation=self.relaxation,
            near_zero_airflow_m3_h=self.near_zero_airflow_m3_h,
            max_outer_iterations=self.max_outer_iterations,
            mass_balance_tolerance_m3_h=self.mass_balance_tolerance_m3_h,
            max_newton_iterations=self.max_newton_iterations,
            operating_pressure_tolerance_pa=self.operating_pressure_tolerance_pa,
            max_operating_iterations=self.max_operating_iterations,
        )


def _input_record(name: str, item: UncertainValue) -> dict:
    return {
        "name": name,
        "value": item.value,
        "unit": item.unit,
        "uncertainty_abs": item.uncertainty_abs,
        "lower": item.lower,
        "upper": item.upper,
        "provenance": (
            asdict(item.provenance) if item.provenance is not None else None
        ),
    }


def _rectangular_dimensions(
    area_m2: float,
    hydraulic_diameter_m: float,
) -> tuple[float, float]:
    area = float(area_m2)
    hydraulic_diameter = float(hydraulic_diameter_m)
    side_sum = 2.0 * area / hydraulic_diameter
    discriminant = side_sum**2 - 4.0 * area
    tolerance = 1e-12 * max(side_sum**2, 4.0 * area, 1.0)
    if discriminant < -tolerance:
        raise ValueError(
            "stored rectangular duct evidence is geometrically inconsistent"
        )
    root = math.sqrt(max(discriminant, 0.0))
    width = 0.5 * (side_sum + root)
    height = 0.5 * (side_sum - root)
    if width <= 0 or height <= 0:
        raise ValueError(
            "stored rectangular duct evidence has invalid dimensions"
        )
    return width, height


def _edge_at_parameters(
    edge: QuadraticFlowEdge,
    parameter_overrides: dict[str, float],
) -> QuadraticFlowEdge:
    evidence = edge.resistance_evidence
    if evidence is None:
        raise ValueError(
            f"edge {edge.name!r} has no duct-geometry resistance evidence"
        )
    common = {
        "length_m": parameter_overrides.get(
            "length_m", evidence["length_m"]
        ),
        "air_density_kg_m3": parameter_overrides.get(
            "air_density_kg_m3", evidence["air_density_kg_m3"]
        ),
        "local_loss_coefficient": parameter_overrides.get(
            "local_loss_coefficient", evidence["local_loss_coefficient"]
        ),
        "absolute_roughness_m": parameter_overrides.get(
            "absolute_roughness_m", evidence["absolute_roughness_m"]
        ),
        "kinematic_viscosity_m2_s": parameter_overrides.get(
            "kinematic_viscosity_m2_s", evidence["kinematic_viscosity_m2_s"]
        ),
        "reference_airflow_m3_h": evidence["reference_airflow_m3_h"],
    }
    shape = evidence["shape"]
    if shape == "circular":
        common["diameter_m"] = parameter_overrides.get(
            "diameter_m", evidence["hydraulic_diameter_m"]
        )
    elif shape == "rectangular":
        width = evidence.get("width_m")
        height = evidence.get("height_m")
        if width is None or height is None:
            width, height = _rectangular_dimensions(
                evidence["area_m2"],
                evidence["hydraulic_diameter_m"],
            )
        common["width_m"] = parameter_overrides.get(
            "width_m", width
        )
        common["height_m"] = parameter_overrides.get(
            "height_m", height
        )
    else:
        raise ValueError(f"unsupported stored duct shape {shape!r}")

    rebuilt = derive_loop_edge_resistance(
        LoopedDuctResistanceInput(**common)
    )
    for parameter_name, value in parameter_overrides.items():
        evidence_key = (
            "hydraulic_diameter_m"
            if parameter_name == "diameter_m"
            else parameter_name
        )
        rebuilt[f"uncertainty_base_{parameter_name}"] = evidence[evidence_key]
        rebuilt[f"uncertainty_adjusted_{parameter_name}"] = value
    return QuadraticFlowEdge(
        name=edge.name,
        start_node=edge.start_node,
        end_node=edge.end_node,
        resistance_pa_per_m3_s_squared=rebuilt[
            "resistance_pa_per_m3_s_squared"
        ],
        resistance_basis="duct_geometry",
        resistance_evidence=rebuilt,
    )


def _network_at_corner(
    study: FanVariableFrictionLoopUncertaintyStudy,
    edge_parameter_overrides: dict[str, dict[str, float]],
) -> LoopedFlowNetwork:
    return LoopedFlowNetwork(
        name=study.loop_network.name,
        node_injections_m3_h=study.loop_network.node_injections_m3_h,
        edges=tuple(
            _edge_at_parameters(
                edge,
                edge_parameter_overrides[edge.name],
            )
            if edge.name in edge_parameter_overrides
            else edge
            for edge in study.loop_network.edges
        ),
        reference_node=study.loop_network.reference_node,
    )


def _fan_curve_at_corner(
    study: FanVariableFrictionLoopUncertaintyStudy,
    pressure_overrides: dict[float, float],
    airflow_overrides: dict[int, float],
    speed_ratio: float | None,
    reference_curve: FanCurve | None = None,
) -> FanCurve:
    source_curve = reference_curve or study.fan_curve
    bounded_reference_curve = FanCurve(
        name=source_curve.name,
        points=tuple(
            type(point)(
                airflow_m3_h=airflow_overrides.get(
                    point_index,
                    point.airflow_m3_h,
                ),
                pressure_pa=pressure_overrides.get(
                    float(point.airflow_m3_h),
                    point.pressure_pa,
                ),
            )
            for point_index, point in enumerate(source_curve.points)
        ),
    )
    if speed_ratio is None:
        return bounded_reference_curve
    return scale_fan_curve_for_speed(
        bounded_reference_curve,
        speed_ratio,
    )


def _solve_case(
    study: FanVariableFrictionLoopUncertaintyStudy,
    fixed_pressure_pa: float,
    edge_parameter_overrides: dict[str, dict[str, float]],
    fan_pressure_overrides: dict[float, float] | None = None,
    fan_airflow_overrides: dict[int, float] | None = None,
    fan_speed_ratio: float | None = None,
    fan_curve_override: FanCurve | None = None,
) -> dict:
    return solve_fan_variable_friction_loop(
        FanVariableFrictionLoopStudy(
            name=study.name,
            fan_curve=_fan_curve_at_corner(
                study,
                fan_pressure_overrides or {},
                fan_airflow_overrides or {},
                fan_speed_ratio,
                fan_curve_override,
            ),
            loop_network=_network_at_corner(study, edge_parameter_overrides),
            fan_discharge_node=study.fan_discharge_node,
            fan_suction_node=study.fan_suction_node,
            fixed_pressure_pa=fixed_pressure_pa,
            power_efficiencies=study.power_efficiencies,
            resistance_relative_tolerance=study.resistance_relative_tolerance,
            relaxation=study.relaxation,
            near_zero_airflow_m3_h=study.near_zero_airflow_m3_h,
            max_outer_iterations=study.max_outer_iterations,
            mass_balance_tolerance_m3_h=study.mass_balance_tolerance_m3_h,
            max_newton_iterations=study.max_newton_iterations,
            operating_pressure_tolerance_pa=(
                study.operating_pressure_tolerance_pa
            ),
            max_operating_iterations=study.max_operating_iterations,
        )
    )

def _metric_envelope(points: list[dict], key: str, unit: str) -> dict:
    values = [float(point[key]) for point in points]
    return {
        "lower": round(min(values), 6),
        "upper": round(max(values), 6),
        "unit": unit,
    }


def _nominal_relative_excursion(
    envelope: dict,
    nominal_value: float,
) -> dict:
    nominal = float(nominal_value)
    lower_delta = float(envelope["lower"]) - nominal
    upper_delta = float(envelope["upper"]) - nominal

    def _percent(delta: float) -> float | None:
        if math.isclose(nominal, 0.0, rel_tol=0.0, abs_tol=1e-15):
            return None
        return round(delta / abs(nominal) * 100.0, 6)

    return {
        "nominal": round(nominal, 6),
        "lower_delta": round(lower_delta, 6),
        "upper_delta": round(upper_delta, 6),
        "lower_percent": _percent(lower_delta),
        "upper_percent": _percent(upper_delta),
        "unit": envelope["unit"],
    }


def _metric_extreme_case_witnesses(points: list[dict], key: str) -> dict:
    values = [float(point[key]) for point in points]
    lower_index = min(range(len(values)), key=values.__getitem__)
    upper_index = max(range(len(values)), key=values.__getitem__)
    return {
        "lower": {
            "corner_index": lower_index,
            "value": round(values[lower_index], 6),
        },
        "upper": {
            "corner_index": upper_index,
            "value": round(values[upper_index], 6),
        },
    }


def _critical_case_summary(corner_index: int, corner: dict) -> dict:
    summary = {
        "corner_index": corner_index,
        "fixed_pressure_pa": corner["fixed_pressure_pa"],
    }
    if "fan_speed_ratio" in corner:
        summary["fan_speed_ratio"] = corner["fan_speed_ratio"]
    if "fan_curve_scenario" in corner:
        summary["fan_curve_scenario"] = corner["fan_curve_scenario"]

    for key in (
        "fan_curve_pressure_pa",
        "fan_curve_airflow_m3_h",
        "edge_local_loss_coefficient",
        "edge_absolute_roughness_m",
        "edge_kinematic_viscosity_m2_s",
        "edge_air_density_kg_m3",
        "edge_length_m",
        "edge_circular_diameter_m",
        "edge_rectangular_width_m",
        "edge_rectangular_height_m",
    ):
        values = corner.get(key)
        if values:
            summary[key] = values
    return summary


def _metric_extrema_sources(
    corners: list[dict],
    key: str,
    unit: str,
) -> dict:
    values = [
        (index, float(corner["operating_point"][key]))
        for index, corner in enumerate(corners)
        if corner["operating_point"] is not None
    ]
    lower = min(value for _index, value in values)
    upper = max(value for _index, value in values)

    def _sources(target: float) -> list[dict]:
        return [
            _critical_case_summary(index, corners[index])
            for index, value in values
            if math.isclose(value, target, rel_tol=1e-12, abs_tol=1e-9)
        ]

    return {
        "lower": {
            "value": round(lower, 6),
            "unit": unit,
            "sources": _sources(lower),
        },
        "upper": {
            "value": round(upper, 6),
            "unit": unit,
            "sources": _sources(upper),
        },
    }


def _edge_airflow_corner_ranges(
    study: FanVariableFrictionLoopUncertaintyStudy,
    solved_networks: list[dict],
) -> list[dict]:
    rows = []
    for edge in study.loop_network.edges:
        values = []
        for network in solved_networks:
            match = next(
                item for item in network["edges"] if item["name"] == edge.name
            )
            values.append(float(match["airflow_m3_h"]))
        lower_index = min(range(len(values)), key=values.__getitem__)
        upper_index = max(range(len(values)), key=values.__getitem__)
        lower = values[lower_index]
        upper = values[upper_index]
        rows.append(
            {
                "edge": edge.name,
                "lower_airflow_m3_h": round(lower, 6),
                "upper_airflow_m3_h": round(upper, 6),
                "lower_corner_index": lower_index,
                "upper_corner_index": upper_index,
                "direction_reversal_across_corners": lower < 0.0 < upper,
            }
        )
    return rows


def _corner_outcome_diagnostics(corners: list[dict]) -> dict:
    status_counts: dict[str, int] = {}
    termination_reason_counts: dict[str, int] = {}
    unresolved_cases = []

    for corner_index, corner in enumerate(corners):
        status = str(corner["status"])
        status_counts[status] = status_counts.get(status, 0) + 1

        solver_diagnostics = corner.get("solver_diagnostics") or {}
        termination_reason = str(
            solver_diagnostics.get("termination_reason", "unspecified")
        )
        termination_reason_counts[termination_reason] = (
            termination_reason_counts.get(termination_reason, 0) + 1
        )

        if status != "solved":
            unresolved_cases.append(
                {
                    **_critical_case_summary(corner_index, corner),
                    "status": status,
                    "termination_reason": termination_reason,
                }
            )

    return {
        "status_counts": dict(sorted(status_counts.items())),
        "termination_reason_counts": dict(
            sorted(termination_reason_counts.items())
        ),
        "unresolved_corner_indices": [
            case["corner_index"] for case in unresolved_cases
        ],
        "unresolved_cases": unresolved_cases,
    }


def _maximum_corner_metric_sources(
    corners: list[dict],
    extractor,
    unit: str,
    *,
    absolute: bool = False,
) -> dict | None:
    values = []
    for corner_index, corner in enumerate(corners):
        raw_value = extractor(corner)
        if raw_value is None:
            continue
        observed_value = float(raw_value)
        score = abs(observed_value) if absolute else observed_value
        values.append((corner_index, observed_value, score))

    if not values:
        return None

    maximum = max(score for _index, _observed, score in values)
    sources = []
    for corner_index, observed_value, score in values:
        if not math.isclose(score, maximum, rel_tol=1e-12, abs_tol=1e-12):
            continue
        source = _critical_case_summary(corner_index, corners[corner_index])
        source["observed_value"] = round(observed_value, 9)
        sources.append(source)

    return {
        "value": round(maximum, 9),
        "unit": unit,
        "sources": sources,
    }


def _solver_quality_summary(
    study: FanVariableFrictionLoopUncertaintyStudy,
    corners: list[dict],
    nominal_status: str,
) -> dict:
    solved_corner_count = sum(corner["status"] == "solved" for corner in corners)
    complete_study_coverage = (
        nominal_status == "solved" and solved_corner_count == len(corners)
    )

    def _diagnostic(key: str):
        return lambda corner: (
            (corner.get("solver_diagnostics") or {}).get(key)
            if corner["status"] == "solved"
            else None
        )

    configured_tolerances = {
        "operating_pressure_tolerance_pa": study.operating_pressure_tolerance_pa,
        "resistance_relative_tolerance": study.resistance_relative_tolerance,
        "mass_balance_tolerance_m3_h": study.mass_balance_tolerance_m3_h,
    }
    configured_iteration_limits = {
        "max_outer_iterations": study.max_outer_iterations,
        "max_newton_iterations": study.max_newton_iterations,
        "max_operating_iterations": study.max_operating_iterations,
    }
    worst_metrics = {
        "absolute_operating_pressure_residual_pa": _maximum_corner_metric_sources(
            corners,
            lambda corner: (
                corner["operating_point"].get("pressure_residual_pa")
                if corner.get("operating_point") is not None
                else None
            ),
            "Pa",
            absolute=True,
        ),
        "network_max_relative_resistance_closure_error": _maximum_corner_metric_sources(
            corners,
            _diagnostic("network_max_relative_resistance_closure_error"),
            "1",
        ),
        "max_abs_mass_balance_residual_m3_h": _maximum_corner_metric_sources(
            corners,
            _diagnostic("max_abs_mass_balance_residual_m3_h"),
            "m3/h",
        ),
        "max_abs_pressure_law_residual_pa": _maximum_corner_metric_sources(
            corners,
            _diagnostic("max_abs_pressure_law_residual_pa"),
            "Pa",
        ),
        "network_outer_iterations": _maximum_corner_metric_sources(
            corners,
            _diagnostic("network_outer_iterations"),
            "iterations",
        ),
        "network_newton_iterations": _maximum_corner_metric_sources(
            corners,
            _diagnostic("network_newton_iterations"),
            "iterations",
        ),
        "operating_iterations": _maximum_corner_metric_sources(
            corners,
            _diagnostic("operating_iterations"),
            "iterations",
        ),
    }

    tolerance_specs = (
        (
            "absolute_operating_pressure_residual_pa",
            "operating_pressure_tolerance_pa",
        ),
        (
            "network_max_relative_resistance_closure_error",
            "resistance_relative_tolerance",
        ),
        (
            "max_abs_mass_balance_residual_m3_h",
            "mass_balance_tolerance_m3_h",
        ),
    )
    configured_tolerance_checks = {}
    for metric_key, tolerance_key in tolerance_specs:
        evidence = worst_metrics[metric_key]
        tolerance = float(configured_tolerances[tolerance_key])
        if evidence is None:
            configured_tolerance_checks[metric_key] = {
                "status": "not_evaluable",
                "observed_value": None,
                "unit": None,
                "configured_tolerance": tolerance,
                "utilization_ratio": None,
                "remaining_margin": None,
            }
            continue

        observed = float(evidence["value"])
        configured_tolerance_checks[metric_key] = {
            "status": (
                "within_tolerance"
                if observed <= tolerance
                else "exceeds_tolerance"
            ),
            "observed_value": round(observed, 9),
            "unit": evidence["unit"],
            "configured_tolerance": tolerance,
            "utilization_ratio": (
                None if tolerance == 0.0 else round(observed / tolerance, 9)
            ),
            "remaining_margin": round(tolerance - observed, 9),
        }

    within_tolerance_count = sum(
        check["status"] == "within_tolerance"
        for check in configured_tolerance_checks.values()
    )
    exceeded_tolerance_count = sum(
        check["status"] == "exceeds_tolerance"
        for check in configured_tolerance_checks.values()
    )
    not_evaluable_count = sum(
        check["status"] == "not_evaluable"
        for check in configured_tolerance_checks.values()
    )
    evaluable_check_count = (
        len(configured_tolerance_checks) - not_evaluable_count
    )
    if exceeded_tolerance_count:
        tolerance_assessment_status = "configured_tolerance_exceeded"
    elif not complete_study_coverage:
        tolerance_assessment_status = "incomplete_coverage"
    elif not_evaluable_count:
        tolerance_assessment_status = "not_evaluable"
    else:
        tolerance_assessment_status = "within_configured_tolerances"

    iteration_specs = (
        ("network_outer_iterations", "max_outer_iterations"),
        ("network_newton_iterations", "max_newton_iterations"),
        ("operating_iterations", "max_operating_iterations"),
    )
    configured_iteration_checks = {}
    for metric_key, limit_key in iteration_specs:
        evidence = worst_metrics[metric_key]
        limit = int(configured_iteration_limits[limit_key])
        if evidence is None:
            configured_iteration_checks[metric_key] = {
                "status": "not_evaluable",
                "observed_iterations": None,
                "configured_limit": limit,
                "utilization_ratio": None,
                "remaining_iterations": None,
            }
            continue

        observed = int(round(float(evidence["value"])))
        configured_iteration_checks[metric_key] = {
            "status": (
                "within_iteration_limit"
                if observed <= limit
                else "exceeds_iteration_limit"
            ),
            "observed_iterations": observed,
            "configured_limit": limit,
            "utilization_ratio": round(observed / limit, 9),
            "remaining_iterations": limit - observed,
        }

    within_iteration_limit_count = sum(
        check["status"] == "within_iteration_limit"
        for check in configured_iteration_checks.values()
    )
    exceeded_iteration_limit_count = sum(
        check["status"] == "exceeds_iteration_limit"
        for check in configured_iteration_checks.values()
    )
    iteration_not_evaluable_count = sum(
        check["status"] == "not_evaluable"
        for check in configured_iteration_checks.values()
    )
    iteration_evaluable_check_count = (
        len(configured_iteration_checks) - iteration_not_evaluable_count
    )
    if exceeded_iteration_limit_count:
        iteration_assessment_status = "configured_iteration_limit_exceeded"
    elif not complete_study_coverage:
        iteration_assessment_status = "incomplete_coverage"
    elif iteration_not_evaluable_count:
        iteration_assessment_status = "not_evaluable"
    else:
        iteration_assessment_status = "within_configured_iteration_limits"

    return {
        "corner_count": len(corners),
        "solved_corner_count": solved_corner_count,
        "complete_evaluated_corner_coverage": solved_corner_count == len(corners),
        "nominal_status": nominal_status,
        "complete_study_coverage": complete_study_coverage,
        "configured_tolerances": configured_tolerances,
        "configured_iteration_limits": configured_iteration_limits,
        "worst_metrics": worst_metrics,
        "configured_tolerance_checks": configured_tolerance_checks,
        "configured_tolerance_assessment": {
            "status": tolerance_assessment_status,
            "configured_check_count": len(configured_tolerance_checks),
            "evaluable_check_count": evaluable_check_count,
            "within_tolerance_count": within_tolerance_count,
            "exceeded_tolerance_count": exceeded_tolerance_count,
            "not_evaluable_count": not_evaluable_count,
            "complete_study_coverage": complete_study_coverage,
        },
        "configured_iteration_checks": configured_iteration_checks,
        "configured_iteration_assessment": {
            "status": iteration_assessment_status,
            "configured_check_count": len(configured_iteration_checks),
            "evaluable_check_count": iteration_evaluable_check_count,
            "within_limit_count": within_iteration_limit_count,
            "exceeded_limit_count": exceeded_iteration_limit_count,
            "not_evaluable_count": iteration_not_evaluable_count,
            "complete_study_coverage": complete_study_coverage,
        },
        "scope_note": (
            "Worst metrics aggregate solved evaluated corners only. "
            "complete_study_coverage is false if the nominal case or any "
            "evaluated corner is unresolved. Configured-tolerance utilization "
            "and configured-iteration-budget utilization are numerical "
            "solver-audit evidence only, using limits already supplied to "
            "this study; they are not equipment, commissioning, certification, "
            "or cleanroom acceptance margins. Pressure-law residual remains "
            "a raw diagnostic because this workflow defines no separate "
            "configured threshold for it."
        ),
    }


def _edge_airflow_extrema_sources(
    study: FanVariableFrictionLoopUncertaintyStudy,
    corners: list[dict],
) -> list[dict]:
    rows = []
    for edge in study.loop_network.edges:
        values = [
            (corner_index, float(corner["edge_airflows_m3_h"][edge.name]))
            for corner_index, corner in enumerate(corners)
            if corner["edge_airflows_m3_h"] is not None
        ]
        lower = min(value for _corner_index, value in values)
        upper = max(value for _corner_index, value in values)

        def _sources(target: float) -> list[dict]:
            return [
                _critical_case_summary(corner_index, corners[corner_index])
                for corner_index, value in values
                if math.isclose(
                    value,
                    target,
                    rel_tol=1e-12,
                    abs_tol=1e-9,
                )
            ]

        rows.append(
            {
                "edge": edge.name,
                "lower": {
                    "value": round(lower, 6),
                    "unit": "m3/h",
                    "sources": _sources(lower),
                },
                "upper": {
                    "value": round(upper, 6),
                    "unit": "m3/h",
                    "sources": _sources(upper),
                },
            }
        )
    return rows


def _power_metric_availability(
    corners: list[dict],
    key: str,
) -> dict:
    available_corner_indices = [
        corner_index
        for corner_index, corner in enumerate(corners)
        if corner.get("power_evidence") is not None
        and corner["power_evidence"].get(key) is not None
    ]
    available_corner_set = set(available_corner_indices)
    available = len(available_corner_indices)
    total = len(corners)
    missing_corner_indices = [
        corner_index
        for corner_index in range(total)
        if corner_index not in available_corner_set
    ]
    if total > 0 and available == total:
        status = "complete"
    elif available == 0:
        status = "unavailable"
    else:
        status = "partial"
    return {
        "status": status,
        "available_corner_count": available,
        "total_corner_count": total,
        "missing_corner_indices": missing_corner_indices,
    }


def _power_metric_corner_range(
    corners: list[dict],
    key: str,
    unit: str,
) -> dict | None:
    availability = _power_metric_availability(corners, key)
    if availability["status"] != "complete":
        return None
    values = [
        float(corner["power_evidence"][key])
        for corner in corners
    ]
    return {
        "lower": round(min(values), 6),
        "upper": round(max(values), 6),
        "unit": unit,
    }


def _power_metric_extrema_sources(
    corners: list[dict],
    key: str,
    unit: str,
) -> dict | None:
    availability = _power_metric_availability(corners, key)
    if availability["status"] != "complete":
        return None
    values = [
        (corner_index, float(corner["power_evidence"][key]))
        for corner_index, corner in enumerate(corners)
    ]

    lower = min(value for _corner_index, value in values)
    upper = max(value for _corner_index, value in values)

    def _sources(target: float) -> list[dict]:
        return [
            _critical_case_summary(corner_index, corners[corner_index])
            for corner_index, value in values
            if math.isclose(value, target, rel_tol=1e-12, abs_tol=1e-9)
        ]

    return {
        "lower": {
            "value": round(lower, 6),
            "unit": unit,
            "sources": _sources(lower),
        },
        "upper": {
            "value": round(upper, 6),
            "unit": unit,
            "sources": _sources(upper),
        },
    }




def _fan_curve_no_intersection_diagnostic(result: dict) -> dict | None:
    if result.get("status") != "no_intersection_in_supplied_range":
        return None

    checks = result.get("fan_curve_point_checks") or []
    if not checks:
        return None

    lower_check = checks[0]
    upper_check = checks[-1]
    lower_margin = float(lower_check["pressure_margin_pa"])

    if lower_margin < 0.0:
        selected = lower_check
        boundary = "lower"
        mismatch_kind = "fan_pressure_deficit"
    else:
        selected = upper_check
        boundary = "upper"
        mismatch_kind = "fan_pressure_surplus"

    signed_margin = float(selected["pressure_margin_pa"])
    return {
        "boundary": boundary,
        "mismatch_kind": mismatch_kind,
        "airflow_m3_h": round(float(selected["airflow_m3_h"]), 6),
        "fan_pressure_pa": round(float(selected["fan_pressure_pa"]), 9),
        "system_pressure_pa": round(
            float(selected["system_pressure_pa"]),
            9,
        ),
        "fan_minus_system_pressure_pa": round(signed_margin, 9),
        "absolute_boundary_pressure_gap_pa": round(
            abs(signed_margin),
            9,
        ),
    }


def _fan_curve_no_intersection_summary(corners: list[dict]) -> dict:
    cases = [
        (
            corner_index,
            corner,
            corner["fan_curve_no_intersection_diagnostic"],
        )
        for corner_index, corner in enumerate(corners)
        if corner.get("fan_curve_no_intersection_diagnostic") is not None
    ]

    lower_count = sum(
        diagnostic["boundary"] == "lower"
        for _index, _corner, diagnostic in cases
    )
    upper_count = sum(
        diagnostic["boundary"] == "upper"
        for _index, _corner, diagnostic in cases
    )

    largest_gap = None
    if cases:
        maximum_gap = max(
            float(diagnostic["absolute_boundary_pressure_gap_pa"])
            for _index, _corner, diagnostic in cases
        )
        sources = []
        for corner_index, corner, diagnostic in cases:
            gap = float(diagnostic["absolute_boundary_pressure_gap_pa"])
            if not math.isclose(
                gap,
                maximum_gap,
                rel_tol=1e-12,
                abs_tol=1e-9,
            ):
                continue
            source = _critical_case_summary(corner_index, corner)
            source.update(diagnostic)
            sources.append(source)
        largest_gap = {
            "value": round(maximum_gap, 9),
            "unit": "Pa",
            "sources": sources,
        }

    return {
        "no_intersection_corner_count": len(cases),
        "lower_boundary_corner_count": lower_count,
        "upper_boundary_corner_count": upper_count,
        "largest_absolute_boundary_pressure_gap_pa": largest_gap,
        "scope_note": (
            "This diagnostic reports the fan-minus-system pressure mismatch "
            "at the supplied fan-curve endpoint that bounds each "
            "no-intersection case. It does not extrapolate the fan curve, "
            "estimate the missing operating point, or infer fan capacity, "
            "stall/surge margin, manufacturer acceptance, or an acceptable "
            "pressure-gap threshold."
        ),
    }


def _fan_curve_intersection_bracket_diagnostic(result: dict) -> dict | None:
    if result.get("status") != "solved":
        return None

    point = result.get("fan_operating_point") or {}
    segment = point.get("interpolation_segment")
    checks = result.get("fan_curve_point_checks") or []
    if segment is None or len(checks) < 2:
        return None

    low_airflow = float(segment["low_airflow_m3_h"])
    high_airflow = float(segment["high_airflow_m3_h"])

    def _matching_check(target_airflow: float) -> dict | None:
        for check in checks:
            if math.isclose(
                float(check["airflow_m3_h"]),
                target_airflow,
                rel_tol=1e-12,
                abs_tol=1e-6,
            ):
                return check
        return None

    low_check = _matching_check(low_airflow)
    high_check = _matching_check(high_airflow)
    if low_check is None or high_check is None:
        return None

    tolerance = float(
        (result.get("solver_diagnostics") or {}).get(
            "operating_pressure_tolerance_pa",
            0.0,
        )
    )
    low_margin = float(low_check["pressure_margin_pa"])
    high_margin = float(high_check["pressure_margin_pa"])

    def _endpoint(check: dict) -> dict:
        return {
            "airflow_m3_h": round(float(check["airflow_m3_h"]), 6),
            "fan_pressure_pa": round(float(check["fan_pressure_pa"]), 9),
            "system_pressure_pa": round(float(check["system_pressure_pa"]), 9),
            "fan_minus_system_pressure_pa": round(
                float(check["pressure_margin_pa"]),
                9,
            ),
        }

    return {
        "low_endpoint": _endpoint(low_check),
        "high_endpoint": _endpoint(high_check),
        "operating_pressure_tolerance_pa": tolerance,
        "strict_sign_change": low_margin > 0.0 and high_margin < 0.0,
        "endpoint_within_tolerance": (
            abs(low_margin) <= tolerance or abs(high_margin) <= tolerance
        ),
        "bounded_intersection_supported": (
            low_margin >= -tolerance and high_margin <= tolerance
        ),
        "nearest_endpoint_absolute_pressure_gap_pa": round(
            min(abs(low_margin), abs(high_margin)),
            9,
        ),
        "endpoint_pressure_residual_span_pa": round(
            abs(low_margin - high_margin),
            9,
        ),
        "termination_reason": (
            (result.get("solver_diagnostics") or {}).get(
                "termination_reason",
                "unspecified",
            )
        ),
    }


def _fan_curve_intersection_bracket_summary(
    corners: list[dict],
    nominal_status: str,
) -> dict:
    cases = [
        (corner_index, corner, corner["fan_curve_intersection_bracket"])
        for corner_index, corner in enumerate(corners)
        if corner.get("fan_curve_intersection_bracket") is not None
    ]
    complete_study_coverage = (
        nominal_status == "solved" and len(cases) == len(corners)
    )

    def _minimum_evidence(key: str) -> dict | None:
        if not cases:
            return None
        minimum = min(
            float(diagnostic[key])
            for _corner_index, _corner, diagnostic in cases
        )
        sources = []
        for corner_index, corner, diagnostic in cases:
            if not math.isclose(
                float(diagnostic[key]),
                minimum,
                rel_tol=1e-12,
                abs_tol=1e-9,
            ):
                continue
            source = _critical_case_summary(corner_index, corner)
            source.update(
                {
                    "low_endpoint": diagnostic["low_endpoint"],
                    "high_endpoint": diagnostic["high_endpoint"],
                    "termination_reason": diagnostic["termination_reason"],
                    "strict_sign_change": diagnostic["strict_sign_change"],
                    "endpoint_within_tolerance": diagnostic[
                        "endpoint_within_tolerance"
                    ],
                    "bounded_intersection_supported": diagnostic[
                        "bounded_intersection_supported"
                    ],
                }
            )
            sources.append(source)
        return {
            "value": round(minimum, 9),
            "unit": "Pa",
            "sources": sources,
        }

    return {
        "corner_count": len(corners),
        "bracket_evidence_corner_count": len(cases),
        "bounded_intersection_supported_count": sum(
            diagnostic["bounded_intersection_supported"]
            for _index, _corner, diagnostic in cases
        ),
        "strict_sign_change_count": sum(
            diagnostic["strict_sign_change"]
            for _index, _corner, diagnostic in cases
        ),
        "endpoint_within_tolerance_count": sum(
            diagnostic["endpoint_within_tolerance"]
            for _index, _corner, diagnostic in cases
        ),
        "complete_study_coverage": complete_study_coverage,
        "minimum_nearest_endpoint_absolute_pressure_gap_pa": (
            _minimum_evidence("nearest_endpoint_absolute_pressure_gap_pa")
        ),
        "minimum_endpoint_pressure_residual_span_pa": (
            _minimum_evidence("endpoint_pressure_residual_span_pa")
        ),
        "scope_note": (
            "This evidence reuses the already evaluated supplied fan-curve "
            "points that bound each solved operating point. Signed fan-minus-"
            "system pressure at the interpolation endpoints documents how the "
            "bounded root was enclosed without fan-curve extrapolation. It is "
            "numerical root-bracketing provenance only; no acceptable pressure "
            "margin, stall/surge boundary, manufacturer operating region, or "
            "equipment acceptance threshold is inferred."
        ),
    }


def _fan_curve_supplied_point_residual_summary(
    corners: list[dict],
    nominal_audit: dict | None,
) -> dict:
    cases = [
        (
            corner_index,
            corner,
            corner["fan_curve_supplied_point_residual_audit"],
        )
        for corner_index, corner in enumerate(corners)
        if corner.get("fan_curve_supplied_point_residual_audit") is not None
    ]
    complete_corner_coverage = sum(
        audit["complete_supplied_point_coverage"]
        for _corner_index, _corner, audit in cases
    )
    solved_cases = [
        (corner_index, corner, audit)
        for corner_index, corner, audit in cases
        if corner.get("status") == "solved"
    ]
    selected_feature_count = sum(
        audit.get("selected_candidate_feature") is not None
        for _corner_index, _corner, audit in solved_cases
    )
    selected_first_priority_count = sum(
        audit.get("selected_candidate_feature_rank") == 0
        for _corner_index, _corner, audit in solved_cases
    )
    solved_with_additional_candidate_indices = [
        corner_index
        for corner_index, _corner, audit in solved_cases
        if (audit.get("additional_candidate_feature_count") or 0) > 0
    ]
    alternative_separation_cases = [
        (corner_index, corner, audit)
        for corner_index, corner, audit in solved_cases
        if audit.get(
            "nearest_alternative_candidate_airflow_interval_gap_m3_h"
        ) is not None
    ]
    selected_overlap_alternative_interval_indices = [
        corner_index
        for corner_index, _corner, audit in alternative_separation_cases
        if audit.get(
            "selected_airflow_overlaps_alternative_candidate_interval"
        ) is True
    ]
    alternative_index_separation_cases = [
        (corner_index, corner, audit)
        for corner_index, corner, audit in solved_cases
        if audit.get(
            "nearest_alternative_candidate_feature_index_interval_gap"
        ) is not None
    ]
    monotonic_count = sum(
        audit["residual_monotonic_non_increasing_with_tolerance"]
        for _corner_index, _corner, audit in cases
    )
    residual_increase_indices = [
        corner_index
        for corner_index, _corner, audit in cases
        if audit["residual_increase_transition_count"] > 0
    ]
    multiple_candidate_indices = [
        corner_index
        for corner_index, _corner, audit in cases
        if audit["candidate_crossing_feature_count"] > 1
    ]
    reverse_sign_change_indices = [
        corner_index
        for corner_index, _corner, audit in cases
        if audit.get("reverse_strict_sign_change_segment_count", 0) > 0
    ]
    reverse_sign_change_segment_count_total = sum(
        int(audit.get("reverse_strict_sign_change_segment_count", 0))
        for _corner_index, _corner, audit in cases
    )
    complete_study_coverage = (
        nominal_audit is not None
        and nominal_audit["complete_supplied_point_coverage"]
        and len(cases) == len(corners)
        and complete_corner_coverage == len(corners)
    )

    positive_cases = [
        (corner_index, corner, audit)
        for corner_index, corner, audit in cases
        if float(audit["largest_positive_residual_increase_pa"]) > 0.0
    ]
    maximum_positive_increase = None
    if positive_cases:
        maximum = max(
            float(audit["largest_positive_residual_increase_pa"])
            for _corner_index, _corner, audit in positive_cases
        )
        sources = []
        for corner_index, corner, audit in positive_cases:
            if not math.isclose(
                float(audit["largest_positive_residual_increase_pa"]),
                maximum,
                rel_tol=1e-12,
                abs_tol=1e-9,
            ):
                continue
            source = _critical_case_summary(corner_index, corner)
            source.update(
                {
                    "candidate_crossing_feature_count": audit[
                        "candidate_crossing_feature_count"
                    ],
                    "residual_increase_transition_count": audit[
                        "residual_increase_transition_count"
                    ],
                    "residual_monotonic_non_increasing_with_tolerance": audit[
                        "residual_monotonic_non_increasing_with_tolerance"
                    ],
                }
            )
            sources.append(source)
        maximum_positive_increase = {
            "value": round(maximum, 9),
            "unit": "Pa",
            "sources": sources,
        }

    minimum_alternative_candidate_gap = None
    minimum_alternative_candidate_gap_fraction = None
    minimum_alternative_candidate_gap_fraction_of_minimum_spacing = None
    minimum_alternative_candidate_index_gap = None
    if alternative_separation_cases:
        minimum_gap = min(
            float(
                audit[
                    "nearest_alternative_candidate_airflow_interval_gap_m3_h"
                ]
            )
            for _corner_index, _corner, audit in alternative_separation_cases
        )
        sources = []
        for corner_index, corner, audit in alternative_separation_cases:
            observed_gap = float(
                audit[
                    "nearest_alternative_candidate_airflow_interval_gap_m3_h"
                ]
            )
            if not math.isclose(
                observed_gap,
                minimum_gap,
                rel_tol=1e-12,
                abs_tol=1e-9,
            ):
                continue
            source = _critical_case_summary(corner_index, corner)
            source.update(
                {
                    "candidate_crossing_feature_count": audit[
                        "candidate_crossing_feature_count"
                    ],
                    "selected_candidate_feature": audit.get(
                        "selected_candidate_feature"
                    ),
                    "nearest_alternative_candidate_features": audit.get(
                        "nearest_alternative_candidate_features"
                    )
                    or [],
                }
            )
            sources.append(source)
        minimum_alternative_candidate_gap = {
            "value": round(minimum_gap, 9),
            "unit": "m3/h",
            "sources": sources,
        }

        minimum_gap_fraction = min(
            float(
                audit[
                    "nearest_alternative_candidate_airflow_interval_gap_fraction_of_supplied_curve_span"
                ]
            )
            for _corner_index, _corner, audit in alternative_separation_cases
        )
        normalized_sources = []
        for corner_index, corner, audit in alternative_separation_cases:
            observed_fraction = float(
                audit[
                    "nearest_alternative_candidate_airflow_interval_gap_fraction_of_supplied_curve_span"
                ]
            )
            if not math.isclose(
                observed_fraction,
                minimum_gap_fraction,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                continue
            source = _critical_case_summary(corner_index, corner)
            source.update(
                {
                    "candidate_crossing_feature_count": audit[
                        "candidate_crossing_feature_count"
                    ],
                    "supplied_fan_curve_airflow_span_m3_h": audit[
                        "supplied_fan_curve_airflow_span_m3_h"
                    ],
                    "selected_candidate_feature": audit.get(
                        "selected_candidate_feature"
                    ),
                    "nearest_alternative_candidate_features": audit.get(
                        "nearest_alternative_candidate_features"
                    )
                    or [],
                }
            )
            normalized_sources.append(source)
        minimum_alternative_candidate_gap_fraction = {
            "value": round(minimum_gap_fraction, 12),
            "unit": "1",
            "sources": normalized_sources,
        }

        minimum_gap_fraction_of_minimum_spacing = min(
            float(
                audit[
                    "nearest_alternative_candidate_airflow_interval_gap_fraction_of_minimum_supplied_point_spacing"
                ]
            )
            for _corner_index, _corner, audit in alternative_separation_cases
        )
        spacing_normalized_sources = []
        for corner_index, corner, audit in alternative_separation_cases:
            observed_fraction = float(
                audit[
                    "nearest_alternative_candidate_airflow_interval_gap_fraction_of_minimum_supplied_point_spacing"
                ]
            )
            if not math.isclose(
                observed_fraction,
                minimum_gap_fraction_of_minimum_spacing,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                continue
            source = _critical_case_summary(corner_index, corner)
            source.update(
                {
                    "candidate_crossing_feature_count": audit[
                        "candidate_crossing_feature_count"
                    ],
                    "minimum_supplied_point_airflow_spacing_m3_h": audit[
                        "minimum_supplied_point_airflow_spacing_m3_h"
                    ],
                    "maximum_supplied_point_airflow_spacing_m3_h": audit[
                        "maximum_supplied_point_airflow_spacing_m3_h"
                    ],
                    "selected_candidate_feature": audit.get(
                        "selected_candidate_feature"
                    ),
                    "nearest_alternative_candidate_features": audit.get(
                        "nearest_alternative_candidate_features"
                    )
                    or [],
                }
            )
            spacing_normalized_sources.append(source)
        minimum_alternative_candidate_gap_fraction_of_minimum_spacing = {
            "value": round(minimum_gap_fraction_of_minimum_spacing, 12),
            "unit": "1",
            "sources": spacing_normalized_sources,
        }

    if alternative_index_separation_cases:
        minimum_index_gap = min(
            int(
                audit[
                    "nearest_alternative_candidate_feature_index_interval_gap"
                ]
            )
            for _corner_index, _corner, audit in alternative_index_separation_cases
        )
        index_sources = []
        for corner_index, corner, audit in alternative_index_separation_cases:
            observed_index_gap = int(
                audit[
                    "nearest_alternative_candidate_feature_index_interval_gap"
                ]
            )
            if observed_index_gap != minimum_index_gap:
                continue
            source = _critical_case_summary(corner_index, corner)
            source.update(
                {
                    "candidate_crossing_feature_count": audit[
                        "candidate_crossing_feature_count"
                    ],
                    "expected_supplied_point_count": audit[
                        "expected_supplied_point_count"
                    ],
                    "selected_candidate_feature": audit.get(
                        "selected_candidate_feature"
                    ),
                    "nearest_alternative_candidate_features_by_index_interval_gap": (
                        audit.get(
                            "nearest_alternative_candidate_features_by_index_interval_gap"
                        )
                        or []
                    ),
                }
            )
            index_sources.append(source)
        minimum_alternative_candidate_index_gap = {
            "value": minimum_index_gap,
            "unit": "supplied_point_index_steps",
            "sources": index_sources,
        }

    return {
        "corner_count": len(corners),
        "audit_evidence_corner_count": len(cases),
        "complete_supplied_point_coverage_corner_count": (
            complete_corner_coverage
        ),
        "solved_corner_count": len(solved_cases),
        "selected_candidate_feature_corner_count": selected_feature_count,
        "selected_first_priority_candidate_corner_count": (
            selected_first_priority_count
        ),
        "solved_with_additional_candidate_feature_corner_count": len(
            solved_with_additional_candidate_indices
        ),
        "solved_with_additional_candidate_feature_corner_indices": (
            solved_with_additional_candidate_indices
        ),
        "alternative_candidate_separation_evidence_corner_count": len(
            alternative_separation_cases
        ),
        "alternative_candidate_index_separation_evidence_corner_count": len(
            alternative_index_separation_cases
        ),
        "selected_airflow_overlap_alternative_interval_corner_count": len(
            selected_overlap_alternative_interval_indices
        ),
        "selected_airflow_overlap_alternative_interval_corner_indices": (
            selected_overlap_alternative_interval_indices
        ),
        "minimum_selected_to_alternative_candidate_interval_gap_m3_h": (
            minimum_alternative_candidate_gap
        ),
        "minimum_selected_to_alternative_candidate_interval_gap_fraction_of_supplied_curve_span": (
            minimum_alternative_candidate_gap_fraction
        ),
        "minimum_selected_to_alternative_candidate_interval_gap_fraction_of_minimum_supplied_point_spacing": (
            minimum_alternative_candidate_gap_fraction_of_minimum_spacing
        ),
        "minimum_selected_to_alternative_candidate_feature_index_interval_gap": (
            minimum_alternative_candidate_index_gap
        ),
        "monotonic_non_increasing_corner_count": monotonic_count,
        "residual_increase_corner_count": len(residual_increase_indices),
        "residual_increase_corner_indices": residual_increase_indices,
        "multiple_candidate_feature_corner_count": len(
            multiple_candidate_indices
        ),
        "multiple_candidate_feature_corner_indices": (
            multiple_candidate_indices
        ),
        "reverse_strict_sign_change_corner_count": len(
            reverse_sign_change_indices
        ),
        "reverse_strict_sign_change_corner_indices": reverse_sign_change_indices,
        "reverse_strict_sign_change_segment_count_total": (
            reverse_sign_change_segment_count_total
        ),
        "complete_study_coverage": complete_study_coverage,
        "maximum_positive_residual_increase_pa": maximum_positive_increase,
        "scope_note": (
            "This aggregate preserves the base solver's discrete supplied-point "
            "fan-minus-system residual topology audit across uncertainty "
            "corners. Complete coverage means every supplied point was "
            "evaluated for the nominal case and every corner. Solved-corner "
            "selection evidence identifies the discrete feature chosen using "
            "the solver's documented priority and preserves whether additional "
            "discrete candidates were present. When alternatives exist, the "
            "aggregate can retain the smallest airflow gap from the selected "
            "solution to an alternative discrete point or sign-change interval "
            "in absolute airflow, as a fraction of that corner's supplied "
            "fan-curve airflow span, in units of that corner's minimum "
            "adjacent supplied-point airflow spacing, and as the minimum "
            "separation between exact supplied-point index intervals. The "
            "index-space value is discrete sample-grid topology only and does "
            "not infer a second continuous root. Reverse negative-to-positive "
            "strict sign-change segments are "
            "retained separately as audit-only sampled topology and are never "
            "promoted into solver candidates. Sampled monotonicity and candidate "
            "crossing features do not prove continuous uniqueness or dynamic "
            "stability and do not define "
            "stall/surge, manufacturer-region, commissioning, certification, "
            "or equipment-acceptance criteria."
        ),
    }


def _fan_curve_crossing_conditioning_diagnostic(result: dict) -> dict | None:
    bracket = _fan_curve_intersection_bracket_diagnostic(result)
    if bracket is None:
        return None

    point = result.get("fan_operating_point") or {}
    operating_airflow = point.get("airflow_m3_h")
    if operating_airflow is None:
        return None

    low = bracket["low_endpoint"]
    high = bracket["high_endpoint"]
    low_airflow = float(low["airflow_m3_h"])
    high_airflow = float(high["airflow_m3_h"])
    airflow_span = high_airflow - low_airflow
    if airflow_span <= 0.0:
        return None

    fan_slope = (
        float(high["fan_pressure_pa"]) - float(low["fan_pressure_pa"])
    ) / airflow_span
    system_slope = (
        float(high["system_pressure_pa"]) - float(low["system_pressure_pa"])
    ) / airflow_span
    residual_slope = (
        float(high["fan_minus_system_pressure_pa"])
        - float(low["fan_minus_system_pressure_pa"])
    ) / airflow_span
    absolute_residual_slope = abs(residual_slope)

    secant_root_airflow = None
    secant_root_error = None
    normalized_secant_root_error = None
    airflow_per_pa = None
    if not math.isclose(
        residual_slope,
        0.0,
        rel_tol=1e-12,
        abs_tol=1e-15,
    ):
        secant_root_airflow = low_airflow - (
            float(low["fan_minus_system_pressure_pa"]) / residual_slope
        )
        secant_root_error = abs(float(operating_airflow) - secant_root_airflow)
        normalized_secant_root_error = secant_root_error / airflow_span
        airflow_per_pa = 1.0 / absolute_residual_slope

    return {
        "bracket_airflow_span_m3_h": round(airflow_span, 9),
        "fan_pressure_slope_pa_per_m3_h": round(fan_slope, 12),
        "system_pressure_secant_slope_pa_per_m3_h": round(
            system_slope,
            12,
        ),
        "fan_minus_system_slope_pa_per_m3_h": round(
            residual_slope,
            12,
        ),
        "absolute_fan_minus_system_slope_pa_per_m3_h": round(
            absolute_residual_slope,
            12,
        ),
        "airflow_change_per_pa_m3_h_per_pa": (
            None if airflow_per_pa is None else round(airflow_per_pa, 12)
        ),
        "secant_root_airflow_m3_h": (
            None
            if secant_root_airflow is None
            else round(secant_root_airflow, 9)
        ),
        "solved_operating_airflow_m3_h": round(float(operating_airflow), 9),
        "secant_root_absolute_error_m3_h": (
            None if secant_root_error is None else round(secant_root_error, 9)
        ),
        "normalized_secant_root_error_fraction": (
            None
            if normalized_secant_root_error is None
            else round(normalized_secant_root_error, 12)
        ),
    }


def _fan_curve_crossing_conditioning_summary(
    corners: list[dict],
    nominal_status: str,
) -> dict:
    cases = [
        (corner_index, corner, corner["fan_curve_crossing_conditioning"])
        for corner_index, corner in enumerate(corners)
        if corner.get("fan_curve_crossing_conditioning") is not None
    ]
    complete_study_coverage = (
        nominal_status == "solved" and len(cases) == len(corners)
    )

    def _extreme_evidence(
        key: str,
        *,
        mode: str,
        unit: str,
    ) -> dict | None:
        available = [
            (corner_index, corner, diagnostic)
            for corner_index, corner, diagnostic in cases
            if diagnostic.get(key) is not None
        ]
        if not available:
            return None
        chooser = min if mode == "min" else max
        extreme = chooser(
            float(diagnostic[key]) for _, _, diagnostic in available
        )
        sources = []
        for corner_index, corner, diagnostic in available:
            if not math.isclose(
                float(diagnostic[key]),
                extreme,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                continue
            source = _critical_case_summary(corner_index, corner)
            source.update(
                {
                    "fan_pressure_slope_pa_per_m3_h": diagnostic[
                        "fan_pressure_slope_pa_per_m3_h"
                    ],
                    "system_pressure_secant_slope_pa_per_m3_h": diagnostic[
                        "system_pressure_secant_slope_pa_per_m3_h"
                    ],
                    "fan_minus_system_slope_pa_per_m3_h": diagnostic[
                        "fan_minus_system_slope_pa_per_m3_h"
                    ],
                    "secant_root_absolute_error_m3_h": diagnostic[
                        "secant_root_absolute_error_m3_h"
                    ],
                    "normalized_secant_root_error_fraction": diagnostic[
                        "normalized_secant_root_error_fraction"
                    ],
                }
            )
            sources.append(source)
        return {
            "value": round(extreme, 12),
            "unit": unit,
            "sources": sources,
        }

    return {
        "corner_count": len(corners),
        "conditioning_evidence_corner_count": len(cases),
        "secant_root_evidence_corner_count": sum(
            diagnostic["secant_root_airflow_m3_h"] is not None
            for _index, _corner, diagnostic in cases
        ),
        "complete_study_coverage": complete_study_coverage,
        "minimum_absolute_fan_minus_system_slope_pa_per_m3_h": (
            _extreme_evidence(
                "absolute_fan_minus_system_slope_pa_per_m3_h",
                mode="min",
                unit="Pa/(m3/h)",
            )
        ),
        "maximum_airflow_change_per_pa_m3_h_per_pa": (
            _extreme_evidence(
                "airflow_change_per_pa_m3_h_per_pa",
                mode="max",
                unit="(m3/h)/Pa",
            )
        ),
        "maximum_secant_root_absolute_error_m3_h": (
            _extreme_evidence(
                "secant_root_absolute_error_m3_h",
                mode="max",
                unit="m3/h",
            )
        ),
        "maximum_normalized_secant_root_error_fraction": (
            _extreme_evidence(
                "normalized_secant_root_error_fraction",
                mode="max",
                unit="1",
            )
        ),
        "scope_note": (
            "This diagnostic derives local secant gradients only from the "
            "already evaluated supplied fan-curve interpolation endpoints. "
            "The fan-minus-system gradient and its reciprocal describe local "
            "numerical root conditioning, while the secant-root difference "
            "compares a straight-line endpoint estimate with the solved "
            "nonlinear operating airflow. No stability criterion, stall/surge "
            "boundary, acceptable conditioning threshold, manufacturer "
            "operating region, or equipment acceptance limit is inferred."
        ),
    }


def _pressure_residual_airflow_equivalence_diagnostic(
    result: dict,
    operating_pressure_tolerance_pa: float,
) -> dict | None:
    conditioning = _fan_curve_crossing_conditioning_diagnostic(result)
    if conditioning is None:
        return None

    point = result.get("fan_operating_point") or {}
    pressure_residual = point.get("pressure_residual_pa")
    if pressure_residual is None:
        return None

    residual_slope = float(
        conditioning["fan_minus_system_slope_pa_per_m3_h"]
    )
    airflow_per_pa = conditioning["airflow_change_per_pa_m3_h_per_pa"]
    bracket_span = float(conditioning["bracket_airflow_span_m3_h"])
    tolerance = float(operating_pressure_tolerance_pa)
    residual = float(pressure_residual)

    base = {
        "configured_operating_pressure_tolerance_pa": round(tolerance, 12),
        "solved_pressure_residual_pa": round(residual, 12),
        "absolute_solved_pressure_residual_pa": round(abs(residual), 12),
        "fan_minus_system_slope_pa_per_m3_h": round(residual_slope, 12),
        "airflow_change_per_pa_m3_h_per_pa": airflow_per_pa,
        "bracket_airflow_span_m3_h": round(bracket_span, 9),
    }
    if airflow_per_pa is None:
        return {
            **base,
            "status": "not_evaluable_zero_local_residual_slope",
            "configured_tolerance_equivalent_airflow_m3_h": None,
            "solved_residual_equivalent_airflow_m3_h": None,
            "signed_linearized_airflow_correction_m3_h": None,
            "configured_tolerance_equivalent_fraction_of_bracket_span": None,
            "solved_residual_equivalent_fraction_of_bracket_span": None,
        }

    airflow_per_pressure = float(airflow_per_pa)
    configured_equivalent = tolerance * airflow_per_pressure
    residual_equivalent = abs(residual) * airflow_per_pressure
    signed_correction = -residual / residual_slope
    return {
        **base,
        "status": "evaluated",
        "configured_tolerance_equivalent_airflow_m3_h": round(
            configured_equivalent,
            12,
        ),
        "solved_residual_equivalent_airflow_m3_h": round(
            residual_equivalent,
            12,
        ),
        "signed_linearized_airflow_correction_m3_h": round(
            signed_correction,
            12,
        ),
        "configured_tolerance_equivalent_fraction_of_bracket_span": round(
            configured_equivalent / bracket_span,
            12,
        ),
        "solved_residual_equivalent_fraction_of_bracket_span": round(
            residual_equivalent / bracket_span,
            12,
        ),
    }


def _pressure_residual_airflow_equivalence_summary(
    corners: list[dict],
    nominal_status: str,
) -> dict:
    cases = [
        (
            corner_index,
            corner,
            corner["pressure_residual_airflow_equivalence"],
        )
        for corner_index, corner in enumerate(corners)
        if corner.get("pressure_residual_airflow_equivalence") is not None
    ]
    evaluable = [
        (corner_index, corner, diagnostic)
        for corner_index, corner, diagnostic in cases
        if diagnostic["status"] == "evaluated"
    ]
    complete_study_coverage = (
        nominal_status == "solved" and len(evaluable) == len(corners)
    )

    def _maximum_evidence(key: str, unit: str) -> dict | None:
        available = [
            (corner_index, corner, diagnostic)
            for corner_index, corner, diagnostic in evaluable
            if diagnostic.get(key) is not None
        ]
        if not available:
            return None
        maximum = max(
            float(diagnostic[key])
            for _corner_index, _corner, diagnostic in available
        )
        sources = []
        for corner_index, corner, diagnostic in available:
            if not math.isclose(
                float(diagnostic[key]),
                maximum,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                continue
            source = _critical_case_summary(corner_index, corner)
            source.update(
                {
                    "configured_operating_pressure_tolerance_pa": diagnostic[
                        "configured_operating_pressure_tolerance_pa"
                    ],
                    "solved_pressure_residual_pa": diagnostic[
                        "solved_pressure_residual_pa"
                    ],
                    "fan_minus_system_slope_pa_per_m3_h": diagnostic[
                        "fan_minus_system_slope_pa_per_m3_h"
                    ],
                    "airflow_change_per_pa_m3_h_per_pa": diagnostic[
                        "airflow_change_per_pa_m3_h_per_pa"
                    ],
                    "signed_linearized_airflow_correction_m3_h": diagnostic[
                        "signed_linearized_airflow_correction_m3_h"
                    ],
                    "bracket_airflow_span_m3_h": diagnostic[
                        "bracket_airflow_span_m3_h"
                    ],
                }
            )
            sources.append(source)
        return {
            "value": round(maximum, 12),
            "unit": unit,
            "sources": sources,
        }

    return {
        "corner_count": len(corners),
        "diagnostic_evidence_corner_count": len(cases),
        "evaluable_corner_count": len(evaluable),
        "complete_study_coverage": complete_study_coverage,
        "maximum_configured_tolerance_equivalent_airflow_m3_h": (
            _maximum_evidence(
                "configured_tolerance_equivalent_airflow_m3_h",
                "m3/h",
            )
        ),
        "maximum_solved_residual_equivalent_airflow_m3_h": (
            _maximum_evidence(
                "solved_residual_equivalent_airflow_m3_h",
                "m3/h",
            )
        ),
        "maximum_configured_tolerance_equivalent_fraction_of_bracket_span": (
            _maximum_evidence(
                "configured_tolerance_equivalent_fraction_of_bracket_span",
                "1",
            )
        ),
        "maximum_solved_residual_equivalent_fraction_of_bracket_span": (
            _maximum_evidence(
                "solved_residual_equivalent_fraction_of_bracket_span",
                "1",
            )
        ),
        "scope_note": (
            "This diagnostic maps the already configured operating-pressure "
            "solver tolerance and the solved pressure residual through the "
            "local supplied-point fan-minus-system secant gradient. The "
            "resulting airflow quantities are first-order numerical "
            "equivalents/corrections only; they are not measurement "
            "uncertainty, fan-performance uncertainty, interpolation-error "
            "bounds, continuous worst-case guarantees, stability criteria, "
            "or equipment-acceptance limits."
        ),
    }


def _operating_point_search_resolution_summary(
    corners: list[dict],
    nominal_status: str,
) -> dict:
    solved_corner_count = sum(corner["status"] == "solved" for corner in corners)
    cases = [
        (
            corner_index,
            corner,
            corner["operating_point_search_evidence"],
        )
        for corner_index, corner in enumerate(corners)
        if corner.get("operating_point_search_evidence") is not None
    ]
    solved_cases = [
        (corner_index, corner, evidence)
        for corner_index, corner, evidence in cases
        if corner["status"] == "solved"
    ]
    bisection_cases = [
        (corner_index, corner, evidence)
        for corner_index, corner, evidence in solved_cases
        if evidence["method"] == "bounded_bisection"
        and evidence.get("final_bisection_bracket") is not None
    ]
    supplied_point_cases = [
        (corner_index, corner, evidence)
        for corner_index, corner, evidence in solved_cases
        if evidence["method"] == "supplied_point_tolerance_contact"
    ]
    iteration_limit_cases = [
        (corner_index, corner, evidence)
        for corner_index, corner, evidence in cases
        if evidence["method"] == "bounded_bisection"
        and evidence.get("iteration_limit_evidence") is not None
    ]

    invariant_cases = [
        (
            corner_index,
            corner,
            evidence,
            evidence["final_bisection_bracket"].get("invariant_audit"),
        )
        for corner_index, corner, evidence in bisection_cases
        if evidence["final_bisection_bracket"].get("invariant_audit")
        is not None
    ]
    sign_change_violation_corner_indices = [
        corner_index
        for corner_index, _corner, _evidence, invariant in invariant_cases
        if not invariant["strict_sign_change_preserved"]
    ]
    midpoint_violation_corner_indices = [
        corner_index
        for corner_index, _corner, _evidence, invariant in invariant_cases
        if not invariant["selected_airflow_is_bracket_midpoint"]
    ]

    trace_cases = [
        (
            corner_index,
            corner,
            evidence,
            evidence.get("bisection_trace_audit"),
        )
        for corner_index, corner, evidence in cases
        if evidence.get("bisection_trace_audit") is not None
    ]
    solved_trace_cases = [
        case
        for case in trace_cases
        if case[1]["status"] == "solved"
        and case[2].get("final_bisection_bracket") is not None
    ]
    iteration_limit_trace_cases = [
        case
        for case in trace_cases
        if case[2].get("iteration_limit_evidence") is not None
    ]
    trace_length_violation_corner_indices = [
        corner_index
        for corner_index, _corner, _evidence, audit in trace_cases
        if not audit["trace_matches_operating_iterations"]
    ]
    trace_sign_violation_corner_indices = [
        corner_index
        for corner_index, _corner, _evidence, audit in trace_cases
        if not audit[
            "all_steps_preserve_strict_sign_change_before_evaluation"
        ]
    ]
    trace_midpoint_violation_corner_indices = [
        corner_index
        for corner_index, _corner, _evidence, audit in trace_cases
        if not audit["all_midpoints_are_arithmetic_bracket_midpoints"]
    ]
    trace_numeric_sign_violation_corner_indices = [
        corner_index
        for corner_index, _corner, _evidence, audit in trace_cases
        if not audit["all_numeric_brackets_preserve_strict_sign_change"]
    ]
    trace_sign_flag_mismatch_corner_indices = [
        corner_index
        for corner_index, _corner, _evidence, audit in trace_cases
        if not audit["all_recorded_sign_flags_match_numeric_residuals"]
    ]
    trace_numeric_midpoint_violation_corner_indices = [
        corner_index
        for corner_index, _corner, _evidence, audit in trace_cases
        if not audit[
            "all_numeric_midpoints_are_arithmetic_bracket_midpoints"
        ]
    ]
    trace_midpoint_flag_mismatch_corner_indices = [
        corner_index
        for corner_index, _corner, _evidence, audit in trace_cases
        if not audit["all_recorded_midpoint_flags_match_numeric_geometry"]
    ]
    trace_raw_state_violation_corner_indices = sorted(
        set(trace_numeric_sign_violation_corner_indices)
        | set(trace_sign_flag_mismatch_corner_indices)
        | set(trace_numeric_midpoint_violation_corner_indices)
        | set(trace_midpoint_flag_mismatch_corner_indices)
    )
    trace_pressure_state_violation_corner_indices = [
        corner_index
        for corner_index, _corner, _evidence, audit in trace_cases
        if not audit.get("all_trace_pressure_state_consistent", False)
    ]
    trace_residual_replay_violation_corner_indices = [
        corner_index
        for corner_index, _corner, _evidence, audit in trace_cases
        if audit.get(
            "all_trace_residuals_match_independent_replay",
            False,
        )
        is not True
    ]
    trace_pressure_component_replay_violation_corner_indices = [
        corner_index
        for corner_index, _corner, _evidence, audit in trace_cases
        if audit.get(
            "all_trace_pressure_components_match_independent_replay",
            False,
        )
        is not True
    ]
    trace_network_state_replay_violation_corner_indices = [
        corner_index
        for corner_index, _corner, _evidence, audit in trace_cases
        if audit.get(
            "all_trace_network_states_match_independent_replay",
            False,
        )
        is not True
    ]
    trace_pressure_component_replay_violation_details = []
    for corner_index, corner, evidence, audit in trace_cases:
        violations = audit.get("pressure_component_replay_violations", [])
        if not violations:
            continue
        detail = _critical_case_summary(corner_index, corner)
        detail.update(
            {
                "search_method": evidence["method"],
                "supplied_segment_index": evidence["supplied_segment_index"],
                "operating_iterations": evidence["operating_iterations"],
                "violation_count": len(violations),
                "violations": violations,
            }
        )
        trace_pressure_component_replay_violation_details.append(detail)
    trace_width_violation_corner_indices = [
        corner_index
        for corner_index, _corner, _evidence, audit in trace_cases
        if not audit["all_recorded_widths_match_airflow_brackets"]
    ]
    trace_width_fraction_violation_corner_indices = [
        corner_index
        for corner_index, _corner, _evidence, audit in trace_cases
        if not audit[
            "all_recorded_width_fractions_match_iteration_sequence"
        ]
    ]
    trace_geometry_violation_corner_indices = sorted(
        set(trace_width_violation_corner_indices)
        | set(trace_width_fraction_violation_corner_indices)
    )
    trace_termination_violation_corner_indices = [
        corner_index
        for corner_index, _corner, _evidence, audit in solved_trace_cases
        if not audit["termination_record_is_last"]
    ]
    trace_iteration_sequence_violation_corner_indices = [
        corner_index
        for corner_index, _corner, _evidence, audit in trace_cases
        if not audit["iterations_are_contiguous_from_one"]
    ]
    trace_state_transition_violation_corner_indices = [
        corner_index
        for corner_index, _corner, _evidence, audit in trace_cases
        if not audit["all_state_transitions_replay_recorded_decisions"]
    ]
    trace_terminal_outcome_violation_corner_indices = [
        corner_index
        for corner_index, _corner, _evidence, audit in trace_cases
        if not audit["terminal_outcome_consistent"]
    ]
    trace_decision_semantic_violation_corner_indices = [
        corner_index
        for corner_index, _corner, _evidence, audit in trace_cases
        if not audit.get(
            "all_decisions_match_midpoint_residual_semantics",
            False,
        )
    ]
    trace_origin_replay_violation_corner_indices = [
        corner_index
        for corner_index, _corner, _evidence, audit in trace_cases
        if not audit.get(
            "trace_origin_to_terminal_replay_consistent",
            False,
        )
    ]
    iteration_limit_terminal_replay_violation_corner_indices = [
        corner_index
        for corner_index, _corner, _evidence, audit
        in iteration_limit_trace_cases
        if audit.get("iteration_limit_terminal_replay") is None
        or not audit["iteration_limit_terminal_replay"][
            "terminal_bracket_replays_recorded_decision"
        ]
    ]

    iteration_limit_invariant_cases = [
        (
            corner_index,
            corner,
            evidence,
            evidence["iteration_limit_evidence"][
                "remaining_bisection_bracket"
            ].get("invariant_audit"),
        )
        for corner_index, corner, evidence in iteration_limit_cases
        if evidence["iteration_limit_evidence"][
            "remaining_bisection_bracket"
        ].get("invariant_audit")
        is not None
    ]
    iteration_limit_sign_change_violation_corner_indices = [
        corner_index
        for corner_index, _corner, _evidence, invariant
        in iteration_limit_invariant_cases
        if not invariant["strict_sign_change_preserved"]
    ]

    def _maximum_bracket_evidence(
        key: str,
        unit: str,
    ) -> dict | None:
        if not bisection_cases:
            return None
        maximum = max(
            float(evidence["final_bisection_bracket"][key])
            for _corner_index, _corner, evidence in bisection_cases
        )
        sources = []
        for corner_index, corner, evidence in bisection_cases:
            bracket = evidence["final_bisection_bracket"]
            if not math.isclose(
                float(bracket[key]),
                maximum,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                continue
            source = _critical_case_summary(corner_index, corner)
            source.update(
                {
                    "search_method": evidence["method"],
                    "supplied_segment_index": evidence[
                        "supplied_segment_index"
                    ],
                    "supplied_segment_low_airflow_m3_h": evidence[
                        "supplied_segment_low_airflow_m3_h"
                    ],
                    "supplied_segment_high_airflow_m3_h": evidence[
                        "supplied_segment_high_airflow_m3_h"
                    ],
                    "operating_iterations": evidence["operating_iterations"],
                    "final_bisection_bracket": bracket,
                }
            )
            sources.append(source)
        return {
            "value": round(maximum, 12),
            "unit": unit,
            "sources": sources,
        }

    def _maximum_invariant_error_evidence() -> dict | None:
        if not invariant_cases:
            return None
        maximum = max(
            float(invariant["absolute_width_fraction_consistency_error"])
            for _corner_index, _corner, _evidence, invariant
            in invariant_cases
        )
        sources = []
        for corner_index, corner, evidence, invariant in invariant_cases:
            error = float(
                invariant["absolute_width_fraction_consistency_error"]
            )
            if not math.isclose(
                error,
                maximum,
                rel_tol=1e-12,
                abs_tol=1e-18,
            ):
                continue
            source = _critical_case_summary(corner_index, corner)
            source.update(
                {
                    "search_method": evidence["method"],
                    "supplied_segment_index": evidence[
                        "supplied_segment_index"
                    ],
                    "operating_iterations": evidence["operating_iterations"],
                    "invariant_audit": invariant,
                }
            )
            sources.append(source)
        return {
            "value": round(maximum, 18),
            "unit": "1",
            "sources": sources,
        }

    def _maximum_trace_step_count_evidence() -> dict | None:
        if not trace_cases:
            return None
        maximum = max(
            int(audit["step_count"])
            for _corner_index, _corner, _evidence, audit in trace_cases
        )
        sources = []
        for corner_index, corner, evidence, audit in trace_cases:
            if int(audit["step_count"]) != maximum:
                continue
            source = _critical_case_summary(corner_index, corner)
            source.update(
                {
                    "search_method": evidence["method"],
                    "supplied_segment_index": evidence[
                        "supplied_segment_index"
                    ],
                    "operating_iterations": evidence["operating_iterations"],
                    "bisection_trace_audit": audit,
                }
            )
            sources.append(source)
        return {
            "value": maximum,
            "unit": "iterations",
            "sources": sources,
        }

    def _maximum_trace_geometry_metric_evidence(
        key: str,
        unit: str,
    ) -> dict | None:
        if not trace_cases:
            return None
        maximum = max(
            float(audit[key])
            for _corner_index, _corner, _evidence, audit in trace_cases
        )
        sources = []
        for corner_index, corner, evidence, audit in trace_cases:
            value = float(audit[key])
            if not math.isclose(
                value,
                maximum,
                rel_tol=1e-12,
                abs_tol=1e-18,
            ):
                continue
            source = _critical_case_summary(corner_index, corner)
            source.update(
                {
                    "search_method": evidence["method"],
                    "supplied_segment_index": evidence[
                        "supplied_segment_index"
                    ],
                    "operating_iterations": evidence["operating_iterations"],
                    "trace_geometry_metric": key,
                    "trace_geometry_metric_value": value,
                }
            )
            sources.append(source)
        return {
            "value": round(maximum, 18),
            "unit": unit,
            "sources": sources,
        }

    def _maximum_trace_pressure_component_replay_witnesses() -> list[dict]:
        if not trace_cases:
            return []
        maximum = max(
            float(
                audit[
                    "maximum_absolute_trace_pressure_component_replay_error_pa"
                ]
            )
            for _corner_index, _corner, _evidence, audit in trace_cases
        )
        witnesses = []
        for corner_index, corner, evidence, audit in trace_cases:
            audit_maximum = float(
                audit[
                    "maximum_absolute_trace_pressure_component_replay_error_pa"
                ]
            )
            if not math.isclose(
                audit_maximum,
                maximum,
                rel_tol=1e-12,
                abs_tol=1e-18,
            ):
                continue
            for witness in audit.get(
                "maximum_trace_pressure_component_replay_error_witnesses",
                [],
            ):
                if not math.isclose(
                    float(witness["absolute_error_pa"]),
                    maximum,
                    rel_tol=1e-12,
                    abs_tol=1e-18,
                ):
                    continue
                source = _critical_case_summary(corner_index, corner)
                source.update(
                    {
                        "search_method": evidence["method"],
                        "supplied_segment_index": evidence[
                            "supplied_segment_index"
                        ],
                        "operating_iterations": evidence[
                            "operating_iterations"
                        ],
                        "witness": witness,
                    }
                )
                witnesses.append(source)
        return witnesses

    def _maximum_iteration_limit_invariant_error_evidence() -> dict | None:
        if not iteration_limit_invariant_cases:
            return None
        maximum = max(
            float(invariant["absolute_width_fraction_consistency_error"])
            for _corner_index, _corner, _evidence, invariant
            in iteration_limit_invariant_cases
        )
        sources = []
        for (
            corner_index,
            corner,
            evidence,
            invariant,
        ) in iteration_limit_invariant_cases:
            error = float(
                invariant["absolute_width_fraction_consistency_error"]
            )
            if not math.isclose(
                error,
                maximum,
                rel_tol=1e-12,
                abs_tol=1e-18,
            ):
                continue
            remaining = evidence["iteration_limit_evidence"][
                "remaining_bisection_bracket"
            ]
            source = _critical_case_summary(corner_index, corner)
            source.update(
                {
                    "search_method": evidence["method"],
                    "supplied_segment_index": evidence[
                        "supplied_segment_index"
                    ],
                    "operating_iterations": evidence["operating_iterations"],
                    "remaining_bisection_bracket": remaining,
                    "invariant_audit": invariant,
                }
            )
            sources.append(source)
        return {
            "value": round(maximum, 18),
            "unit": "1",
            "sources": sources,
        }

    return {
        "corner_count": len(corners),
        "solved_corner_count": solved_corner_count,
        "search_evidence_corner_count": len(cases),
        "solved_search_evidence_corner_count": len(solved_cases),
        "bisection_corner_count": len(bisection_cases),
        "bisection_corner_indices": [
            corner_index
            for corner_index, _corner, _evidence in bisection_cases
        ],
        "supplied_point_contact_corner_count": len(supplied_point_cases),
        "supplied_point_contact_corner_indices": [
            corner_index
            for corner_index, _corner, _evidence in supplied_point_cases
        ],
        "bisection_invariant_evidence_corner_count": len(invariant_cases),
        "strict_sign_change_preserved_corner_count": (
            len(invariant_cases)
            - len(sign_change_violation_corner_indices)
        ),
        "strict_sign_change_violation_corner_indices": (
            sign_change_violation_corner_indices
        ),
        "selected_midpoint_centered_corner_count": (
            len(invariant_cases)
            - len(midpoint_violation_corner_indices)
        ),
        "selected_midpoint_violation_corner_indices": (
            midpoint_violation_corner_indices
        ),
        "bisection_trace_evidence_corner_count": len(trace_cases),
        "solved_bisection_trace_evidence_corner_count": (
            len(solved_trace_cases)
        ),
        "iteration_limit_bisection_trace_evidence_corner_count": (
            len(iteration_limit_trace_cases)
        ),
        "bisection_trace_complete_coverage": (
            len(trace_cases)
            == len(bisection_cases) + len(iteration_limit_cases)
        ),
        "bisection_trace_length_match_corner_count": (
            len(trace_cases) - len(trace_length_violation_corner_indices)
        ),
        "bisection_trace_length_violation_corner_indices": (
            trace_length_violation_corner_indices
        ),
        "bisection_trace_sign_preserved_corner_count": (
            len(trace_cases) - len(trace_sign_violation_corner_indices)
        ),
        "bisection_trace_sign_violation_corner_indices": (
            trace_sign_violation_corner_indices
        ),
        "bisection_trace_midpoint_centered_corner_count": (
            len(trace_cases) - len(trace_midpoint_violation_corner_indices)
        ),
        "bisection_trace_midpoint_violation_corner_indices": (
            trace_midpoint_violation_corner_indices
        ),
        "bisection_trace_numeric_sign_preserved_corner_count": (
            len(trace_cases) - len(trace_numeric_sign_violation_corner_indices)
        ),
        "bisection_trace_numeric_sign_violation_corner_indices": (
            trace_numeric_sign_violation_corner_indices
        ),
        "bisection_trace_sign_flag_match_corner_count": (
            len(trace_cases) - len(trace_sign_flag_mismatch_corner_indices)
        ),
        "bisection_trace_sign_flag_mismatch_corner_indices": (
            trace_sign_flag_mismatch_corner_indices
        ),
        "bisection_trace_numeric_midpoint_centered_corner_count": (
            len(trace_cases)
            - len(trace_numeric_midpoint_violation_corner_indices)
        ),
        "bisection_trace_numeric_midpoint_violation_corner_indices": (
            trace_numeric_midpoint_violation_corner_indices
        ),
        "bisection_trace_midpoint_flag_match_corner_count": (
            len(trace_cases)
            - len(trace_midpoint_flag_mismatch_corner_indices)
        ),
        "bisection_trace_midpoint_flag_mismatch_corner_indices": (
            trace_midpoint_flag_mismatch_corner_indices
        ),
        "bisection_trace_raw_state_consistent_corner_count": (
            len(trace_cases) - len(trace_raw_state_violation_corner_indices)
        ),
        "bisection_trace_raw_state_violation_corner_indices": (
            trace_raw_state_violation_corner_indices
        ),
        "maximum_bisection_trace_midpoint_error_m3_h": (
            _maximum_trace_geometry_metric_evidence(
                "maximum_absolute_trace_midpoint_error_m3_h",
                "m3/h",
            )
        ),
        "bisection_trace_pressure_state_consistent_corner_count": (
            len(trace_cases) - len(trace_pressure_state_violation_corner_indices)
        ),
        "bisection_trace_pressure_state_violation_corner_indices": (
            trace_pressure_state_violation_corner_indices
        ),
        "maximum_bisection_trace_system_pressure_balance_error_pa": (
            _maximum_trace_geometry_metric_evidence(
                "maximum_absolute_trace_system_pressure_balance_error_pa",
                "Pa",
            )
        ),
        "maximum_bisection_trace_residual_balance_error_pa": (
            _maximum_trace_geometry_metric_evidence(
                "maximum_absolute_trace_residual_balance_error_pa",
                "Pa",
            )
        ),
        "bisection_trace_residual_replay_consistent_corner_count": (
            len(trace_cases)
            - len(trace_residual_replay_violation_corner_indices)
        ),
        "bisection_trace_residual_replay_violation_corner_indices": (
            trace_residual_replay_violation_corner_indices
        ),
        "maximum_bisection_trace_residual_replay_error_pa": (
            _maximum_trace_geometry_metric_evidence(
                "maximum_absolute_trace_residual_replay_error_pa",
                "Pa",
            )
        ),
        "bisection_trace_pressure_component_replay_consistent_corner_count": (
            len(trace_cases)
            - len(trace_pressure_component_replay_violation_corner_indices)
        ),
        "bisection_trace_pressure_component_replay_violation_corner_indices": (
            trace_pressure_component_replay_violation_corner_indices
        ),
        "bisection_trace_pressure_component_replay_violation_count": sum(
            int(audit.get("pressure_component_replay_violation_count", 0))
            for _corner_index, _corner, _evidence, audit in trace_cases
        ),
        "bisection_trace_pressure_component_replay_violation_details": (
            trace_pressure_component_replay_violation_details
        ),
        "maximum_bisection_trace_pressure_component_replay_error_pa": (
            _maximum_trace_geometry_metric_evidence(
                "maximum_absolute_trace_pressure_component_replay_error_pa",
                "Pa",
            )
        ),
        "maximum_bisection_trace_pressure_component_replay_error_witnesses": (
            _maximum_trace_pressure_component_replay_witnesses()
        ),
        "bisection_trace_network_state_replay_consistent_corner_count": (
            len(trace_cases)
            - len(trace_network_state_replay_violation_corner_indices)
        ),
        "bisection_trace_network_state_replay_violation_corner_indices": (
            trace_network_state_replay_violation_corner_indices
        ),
        "bisection_trace_width_match_corner_count": (
            len(trace_cases) - len(trace_width_violation_corner_indices)
        ),
        "bisection_trace_width_violation_corner_indices": (
            trace_width_violation_corner_indices
        ),
        "bisection_trace_width_fraction_match_corner_count": (
            len(trace_cases)
            - len(trace_width_fraction_violation_corner_indices)
        ),
        "bisection_trace_width_fraction_violation_corner_indices": (
            trace_width_fraction_violation_corner_indices
        ),
        "bisection_trace_geometry_consistent_corner_count": (
            len(trace_cases) - len(trace_geometry_violation_corner_indices)
        ),
        "bisection_trace_geometry_violation_corner_indices": (
            trace_geometry_violation_corner_indices
        ),
        "maximum_bisection_trace_width_error_m3_h": (
            _maximum_trace_geometry_metric_evidence(
                "maximum_absolute_trace_width_error_m3_h",
                "m3/h",
            )
        ),
        "maximum_bisection_trace_width_fraction_error": (
            _maximum_trace_geometry_metric_evidence(
                "maximum_absolute_trace_width_fraction_error",
                "1",
            )
        ),
        "bisection_trace_terminal_last_corner_count": (
            len(solved_trace_cases)
            - len(trace_termination_violation_corner_indices)
        ),
        "bisection_trace_terminal_violation_corner_indices": (
            trace_termination_violation_corner_indices
        ),
        "bisection_trace_iteration_sequence_match_corner_count": (
            len(trace_cases)
            - len(trace_iteration_sequence_violation_corner_indices)
        ),
        "bisection_trace_iteration_sequence_violation_corner_indices": (
            trace_iteration_sequence_violation_corner_indices
        ),
        "bisection_trace_state_transition_replay_corner_count": (
            len(trace_cases)
            - len(trace_state_transition_violation_corner_indices)
        ),
        "bisection_trace_state_transition_violation_corner_indices": (
            trace_state_transition_violation_corner_indices
        ),
        "bisection_trace_terminal_outcome_consistent_corner_count": (
            len(trace_cases)
            - len(trace_terminal_outcome_violation_corner_indices)
        ),
        "bisection_trace_terminal_outcome_violation_corner_indices": (
            trace_terminal_outcome_violation_corner_indices
        ),
        "bisection_trace_decision_semantic_consistent_corner_count": (
            len(trace_cases)
            - len(trace_decision_semantic_violation_corner_indices)
        ),
        "bisection_trace_decision_semantic_violation_corner_indices": (
            trace_decision_semantic_violation_corner_indices
        ),
        "bisection_trace_origin_replay_corner_count": (
            len(trace_cases) - len(trace_origin_replay_violation_corner_indices)
        ),
        "bisection_trace_origin_replay_violation_corner_indices": (
            trace_origin_replay_violation_corner_indices
        ),
        "iteration_limit_trace_terminal_replay_corner_count": (
            len(iteration_limit_trace_cases)
            - len(
                iteration_limit_terminal_replay_violation_corner_indices
            )
        ),
        "iteration_limit_trace_terminal_replay_violation_corner_indices": (
            iteration_limit_terminal_replay_violation_corner_indices
        ),
        "maximum_bisection_trace_step_count": (
            _maximum_trace_step_count_evidence()
        ),
        "maximum_absolute_width_fraction_consistency_error": (
            _maximum_invariant_error_evidence()
        ),
        "iteration_limit_search_evidence_corner_count": (
            len(iteration_limit_cases)
        ),
        "iteration_limit_corner_indices": [
            corner_index
            for corner_index, _corner, _evidence in iteration_limit_cases
        ],
        "iteration_limit_invariant_evidence_corner_count": (
            len(iteration_limit_invariant_cases)
        ),
        "iteration_limit_strict_sign_change_preserved_corner_count": (
            len(iteration_limit_invariant_cases)
            - len(iteration_limit_sign_change_violation_corner_indices)
        ),
        "iteration_limit_strict_sign_change_violation_corner_indices": (
            iteration_limit_sign_change_violation_corner_indices
        ),
        "maximum_iteration_limit_absolute_width_fraction_consistency_error": (
            _maximum_iteration_limit_invariant_error_evidence()
        ),
        "complete_solved_corner_evidence": (
            len(solved_cases) == solved_corner_count
        ),
        "complete_study_coverage": (
            nominal_status == "solved"
            and solved_corner_count == len(corners)
            and len(cases) == len(corners)
        ),
        "maximum_final_bisection_bracket_width_m3_h": (
            _maximum_bracket_evidence("width_m3_h", "m3/h")
        ),
        "maximum_final_bisection_half_width_m3_h": (
            _maximum_bracket_evidence("half_width_m3_h", "m3/h")
        ),
        "maximum_final_bisection_width_fraction_of_supplied_segment": (
            _maximum_bracket_evidence(
                "width_fraction_of_supplied_segment",
                "1",
            )
        ),
        "scope_note": (
            "Search evidence distinguishes direct supplied-point tolerance "
            "contacts from bounded bisection. For bisection cases, the final "
            "active signed-residual bracket is the interval immediately "
            "before the selected midpoint satisfies the configured pressure "
            "tolerance. Bracket width and half-width are numerical search-"
            "geometry evidence only; they are not physical airflow "
            "uncertainty, interpolation-error bounds, continuous worst-case "
            "guarantees, or equipment-acceptance limits. v0.67 additionally "
            "audits implementation invariants using the unrounded live "
            "bisection state: strict residual-sign bracketing, selected "
            "midpoint centering, and the absolute discrepancy between actual "
            "and iteration-implied binary width contraction. v0.70 preserves "
            "the remaining signed bracket after a bisection iteration limit, "
            "including its completed-step contraction audit, without "
            "accepting or fabricating an operating point. v0.72 retains the "
            "complete bounded-bisection decision trace for solved bisection "
            "corners and audits trace length, per-step sign bracketing, "
            "midpoint geometry, and terminal decision placement without "
            "adding any physical acceptance limit. v0.73 replays each solved "
            "nonterminal L/H decision into the next recorded bracket. v0.75 "
            "extends trace retention to iteration-limit outcomes and verifies "
            "that the final L/H decision reproduces the retained remaining "
            "signed-residual bracket without accepting an operating point. "
            "v0.76 audits every retained trace step's recorded bracket width "
            "against its airflow endpoints and its normalized width against "
            "the binary contraction implied by the iteration number. v0.84 "
            "propagates exact pressure-component replay violation records and "
            "tied maximum-error witnesses across evaluated uncertainty corners."
        ),
    }


def _fan_curve_segment_position_diagnostic(result: dict) -> dict | None:
    bracket = _fan_curve_intersection_bracket_diagnostic(result)
    if bracket is None:
        return None

    point = result.get("fan_operating_point") or {}
    operating_airflow = point.get("airflow_m3_h")
    if operating_airflow is None:
        return None

    low_airflow = float(bracket["low_endpoint"]["airflow_m3_h"])
    high_airflow = float(bracket["high_endpoint"]["airflow_m3_h"])
    airflow = float(operating_airflow)
    span = high_airflow - low_airflow
    if span <= 0.0:
        return None

    lower_clearance = max(0.0, airflow - low_airflow)
    upper_clearance = max(0.0, high_airflow - airflow)
    nearest_clearance = min(lower_clearance, upper_clearance)
    normalized_position = lower_clearance / span
    normalized_nearest_clearance = nearest_clearance / span

    if math.isclose(
        lower_clearance,
        upper_clearance,
        rel_tol=1e-12,
        abs_tol=1e-9,
    ):
        nearest_endpoint = "tied"
    elif lower_clearance < upper_clearance:
        nearest_endpoint = "lower"
    else:
        nearest_endpoint = "upper"

    return {
        "segment_low_airflow_m3_h": round(low_airflow, 6),
        "segment_high_airflow_m3_h": round(high_airflow, 6),
        "segment_airflow_span_m3_h": round(span, 9),
        "solved_operating_airflow_m3_h": round(airflow, 9),
        "lower_segment_endpoint_clearance_m3_h": round(
            lower_clearance,
            9,
        ),
        "upper_segment_endpoint_clearance_m3_h": round(
            upper_clearance,
            9,
        ),
        "nearest_segment_endpoint": nearest_endpoint,
        "nearest_segment_endpoint_clearance_m3_h": round(
            nearest_clearance,
            9,
        ),
        "normalized_segment_position_fraction": round(
            normalized_position,
            12,
        ),
        "normalized_nearest_segment_endpoint_clearance_fraction": round(
            normalized_nearest_clearance,
            12,
        ),
    }


def _fan_curve_segment_position_summary(
    corners: list[dict],
    nominal_status: str,
) -> dict:
    cases = [
        (corner_index, corner, corner["fan_curve_segment_position"])
        for corner_index, corner in enumerate(corners)
        if corner.get("fan_curve_segment_position") is not None
    ]
    complete_study_coverage = (
        nominal_status == "solved" and len(cases) == len(corners)
    )

    def _extreme_evidence(
        key: str,
        *,
        mode: str,
        unit: str,
    ) -> dict | None:
        if not cases:
            return None
        chooser = min if mode == "min" else max
        extreme = chooser(
            float(diagnostic[key])
            for _corner_index, _corner, diagnostic in cases
        )
        sources = []
        for corner_index, corner, diagnostic in cases:
            if not math.isclose(
                float(diagnostic[key]),
                extreme,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                continue
            source = _critical_case_summary(corner_index, corner)
            source.update(
                {
                    "segment_low_airflow_m3_h": diagnostic[
                        "segment_low_airflow_m3_h"
                    ],
                    "segment_high_airflow_m3_h": diagnostic[
                        "segment_high_airflow_m3_h"
                    ],
                    "segment_airflow_span_m3_h": diagnostic[
                        "segment_airflow_span_m3_h"
                    ],
                    "nearest_segment_endpoint": diagnostic[
                        "nearest_segment_endpoint"
                    ],
                    "nearest_segment_endpoint_clearance_m3_h": diagnostic[
                        "nearest_segment_endpoint_clearance_m3_h"
                    ],
                    "normalized_segment_position_fraction": diagnostic[
                        "normalized_segment_position_fraction"
                    ],
                    "normalized_nearest_segment_endpoint_clearance_fraction": (
                        diagnostic[
                            "normalized_nearest_segment_endpoint_clearance_fraction"
                        ]
                    ),
                }
            )
            sources.append(source)
        return {
            "value": round(extreme, 12),
            "unit": unit,
            "sources": sources,
        }

    return {
        "corner_count": len(corners),
        "segment_position_evidence_corner_count": len(cases),
        "complete_study_coverage": complete_study_coverage,
        "minimum_nearest_segment_endpoint_clearance_m3_h": (
            _extreme_evidence(
                "nearest_segment_endpoint_clearance_m3_h",
                mode="min",
                unit="m3/h",
            )
        ),
        "minimum_normalized_nearest_segment_endpoint_clearance_fraction": (
            _extreme_evidence(
                "normalized_nearest_segment_endpoint_clearance_fraction",
                mode="min",
                unit="1",
            )
        ),
        "maximum_segment_airflow_span_m3_h": (
            _extreme_evidence(
                "segment_airflow_span_m3_h",
                mode="max",
                unit="m3/h",
            )
        ),
        "scope_note": (
            "This diagnostic reports where each solved operating airflow lies "
            "inside the exact supplied fan-curve interpolation segment that "
            "bounded the root. Clearance to the segment endpoints is proximity "
            "to supplied data points only; it is not an interpolation-error "
            "estimate, fan-performance uncertainty, stall/surge margin, "
            "manufacturer operating-region limit, or equipment-acceptance "
            "threshold."
        ),
    }


def _fan_curve_boundary_clearance(result: dict) -> dict | None:
    if result.get("status") != "solved":
        return None
    point = result.get("fan_operating_point")
    bounds = result.get("fan_curve_airflow_range_m3_h")
    if point is None or bounds is None or len(bounds) != 2:
        return None

    lower = float(bounds[0])
    upper = float(bounds[1])
    airflow = float(point["airflow_m3_h"])
    span = upper - lower
    lower_headroom = airflow - lower
    upper_headroom = upper - airflow
    nearest_headroom = min(lower_headroom, upper_headroom)

    if math.isclose(
        lower_headroom,
        upper_headroom,
        rel_tol=1e-12,
        abs_tol=1e-9,
    ):
        nearest_boundary = "both"
    elif lower_headroom < upper_headroom:
        nearest_boundary = "lower"
    else:
        nearest_boundary = "upper"

    return {
        "operating_airflow_m3_h": round(airflow, 6),
        "fan_curve_airflow_range_m3_h": [
            round(lower, 6),
            round(upper, 6),
        ],
        "lower_boundary_headroom_m3_h": round(lower_headroom, 6),
        "upper_boundary_headroom_m3_h": round(upper_headroom, 6),
        "nearest_boundary_headroom_m3_h": round(nearest_headroom, 6),
        "normalized_airflow_position": (
            None if span <= 0.0 else round((airflow - lower) / span, 9)
        ),
        "nearest_boundary_headroom_fraction": (
            None if span <= 0.0 else round(nearest_headroom / span, 9)
        ),
        "nearest_boundary": nearest_boundary,
    }


def _fan_curve_boundary_clearance_summary(
    corners: list[dict],
    nominal_status: str,
) -> dict:
    solved = [
        (corner_index, corner, corner["fan_curve_boundary_clearance"])
        for corner_index, corner in enumerate(corners)
        if corner.get("fan_curve_boundary_clearance") is not None
    ]
    complete_study_coverage = (
        nominal_status == "solved" and len(solved) == len(corners)
    )

    absolute_evidence = None
    normalized_evidence = None
    if solved:
        minimum_absolute = min(
            float(clearance["nearest_boundary_headroom_m3_h"])
            for _index, _corner, clearance in solved
        )
        normalized_values = [
            (
                corner_index,
                corner,
                clearance,
                clearance["nearest_boundary_headroom_fraction"],
            )
            for corner_index, corner, clearance in solved
            if clearance["nearest_boundary_headroom_fraction"] is not None
        ]

        def _source(
            corner_index: int,
            corner: dict,
            clearance: dict,
        ) -> dict:
            source = _critical_case_summary(corner_index, corner)
            source.update(
                {
                    "operating_airflow_m3_h": clearance[
                        "operating_airflow_m3_h"
                    ],
                    "fan_curve_airflow_range_m3_h": clearance[
                        "fan_curve_airflow_range_m3_h"
                    ],
                    "nearest_boundary": clearance["nearest_boundary"],
                    "nearest_boundary_headroom_m3_h": clearance[
                        "nearest_boundary_headroom_m3_h"
                    ],
                    "nearest_boundary_headroom_fraction": clearance[
                        "nearest_boundary_headroom_fraction"
                    ],
                }
            )
            return source

        absolute_evidence = {
            "value": round(minimum_absolute, 6),
            "unit": "m3/h",
            "sources": [
                _source(corner_index, corner, clearance)
                for corner_index, corner, clearance in solved
                if math.isclose(
                    float(clearance["nearest_boundary_headroom_m3_h"]),
                    minimum_absolute,
                    rel_tol=1e-12,
                    abs_tol=1e-9,
                )
            ],
        }

        if normalized_values:
            minimum_normalized = min(
                float(value)
                for _index, _corner, _clearance, value in normalized_values
            )
            normalized_evidence = {
                "value": round(minimum_normalized, 9),
                "unit": "fraction_of_supplied_airflow_span",
                "sources": [
                    _source(corner_index, corner, clearance)
                    for corner_index, corner, clearance, value
                    in normalized_values
                    if math.isclose(
                        float(value),
                        minimum_normalized,
                        rel_tol=1e-12,
                        abs_tol=1e-12,
                    )
                ],
            }

    return {
        "corner_count": len(corners),
        "solved_corner_count": len(solved),
        "complete_study_coverage": complete_study_coverage,
        "minimum_nearest_boundary_headroom_m3_h": absolute_evidence,
        "minimum_nearest_boundary_headroom_fraction": normalized_evidence,
        "scope_note": (
            "Boundary clearance is geometric distance in airflow from each "
            "solved operating point to the nearest endpoint of that corner's "
            "actual supplied/transformed fan-curve range. It is a "
            "no-extrapolation audit diagnostic only; no minimum acceptable "
            "headroom, stall/surge margin, manufacturer operating region, or "
            "equipment acceptance criterion is inferred."
        ),
    }


def analyze_fan_variable_friction_loop_uncertainty(
    study: FanVariableFrictionLoopUncertaintyStudy,
) -> dict:
    parameter_maps = (
        (
            "local_loss_coefficient",
            "edge_local_loss_coefficient",
            study.edge_local_loss_coefficient,
        ),
        (
            "absolute_roughness_m",
            "edge_absolute_roughness_m",
            study.edge_absolute_roughness_m,
        ),
        (
            "kinematic_viscosity_m2_s",
            "edge_kinematic_viscosity_m2_s",
            study.edge_kinematic_viscosity_m2_s,
        ),
        (
            "air_density_kg_m3",
            "edge_air_density_kg_m3",
            study.edge_air_density_kg_m3,
        ),
        (
            "length_m",
            "edge_length_m",
            study.edge_length_m,
        ),
        (
            "diameter_m",
            "edge_circular_diameter_m",
            study.edge_circular_diameter_m,
        ),
        (
            "width_m",
            "edge_rectangular_width_m",
            study.edge_rectangular_width_m,
        ),
        (
            "height_m",
            "edge_rectangular_height_m",
            study.edge_rectangular_height_m,
        ),
    )

    nominal_overrides: dict[str, dict[str, float]] = {}
    for parameter_name, _output_key, items in parameter_maps:
        for edge_name, item in items.items():
            nominal_overrides.setdefault(edge_name, {})[
                parameter_name
            ] = item.value

    nominal_fan_pressure_overrides = {
        airflow_m3_h: item.value
        for airflow_m3_h, item in study.fan_curve_pressure_pa.items()
    }
    nominal_fan_airflow_overrides = {
        point_index: item.value
        for point_index, item in study.fan_curve_airflow_m3_h.items()
    }
    nominal = _solve_case(
        study,
        study.fixed_pressure_pa.value,
        nominal_overrides,
        nominal_fan_pressure_overrides,
        nominal_fan_airflow_overrides,
        (
            study.fan_speed_ratio.value
            if study.fan_speed_ratio is not None
            else None
        ),
    )

    fixed_values = sorted(
        {study.fixed_pressure_pa.lower, study.fixed_pressure_pa.upper}
    )
    dimensions = [
        (parameter_name, output_key, edge_name, item)
        for parameter_name, output_key, items in parameter_maps
        for edge_name, item in sorted(items.items())
    ]
    value_sets = [
        sorted({item.lower, item.upper})
        for _parameter_name, _output_key, _edge_name, item in dimensions
    ]
    fan_pressure_dimensions = sorted(study.fan_curve_pressure_pa.items())
    fan_pressure_value_sets = [
        sorted({item.lower, item.upper})
        for _airflow_m3_h, item in fan_pressure_dimensions
    ]
    fan_airflow_dimensions = sorted(study.fan_curve_airflow_m3_h.items())
    fan_airflow_value_sets = [
        sorted({item.lower, item.upper})
        for _point_index, item in fan_airflow_dimensions
    ]
    fan_speed_values = (
        sorted({study.fan_speed_ratio.lower, study.fan_speed_ratio.upper})
        if study.fan_speed_ratio is not None
        else [None]
    )

    # Explicit whole-curve scenarios preserve point-to-point dependence.
    # They are mutually exclusive with independent point bounds, so scenario
    # count replaces the pressure/airflow Cartesian factor when configured.
    fan_curve_case_count = (
        1 + len(study.fan_curve_scenarios)
        if study.fan_curve_scenarios
        else (
            prod(len(values) for values in fan_pressure_value_sets)
            * prod(len(values) for values in fan_airflow_value_sets)
        )
    )

    # Enforce the configured combinatorial limit before materializing any
    # Cartesian product. This keeps an invalid high-dimensional uncertainty
    # request from allocating a potentially enormous intermediate list.
    corner_count = (
        len(fixed_values)
        * prod(len(values) for values in value_sets)
        * fan_curve_case_count
        * len(fan_speed_values)
    )
    if corner_count > study.max_corner_cases:
        raise ValueError(
            "fan/variable-friction uncertainty corner count "
            f"{corner_count} is exceeding "
            f"max_corner_cases={study.max_corner_cases}"
        )

    parameter_combinations = (
        list(product(*value_sets)) if value_sets else [()]
    )
    if study.fan_curve_scenarios:
        fan_curve_cases = [
            {
                "scenario": "nominal",
                "fan_curve": study.fan_curve,
                "pressure_overrides": {},
                "airflow_overrides": {},
            },
            *[
                {
                    "scenario": scenario.name,
                    "fan_curve": scenario.fan_curve,
                    "pressure_overrides": {},
                    "airflow_overrides": {},
                }
                for scenario in study.fan_curve_scenarios
            ],
        ]
    else:
        fan_pressure_combinations = (
            list(product(*fan_pressure_value_sets))
            if fan_pressure_value_sets
            else [()]
        )
        fan_airflow_combinations = (
            list(product(*fan_airflow_value_sets))
            if fan_airflow_value_sets
            else [()]
        )
        fan_curve_cases = [
            {
                "scenario": None,
                "fan_curve": None,
                "pressure_overrides": {
                    airflow_m3_h: value
                    for (airflow_m3_h, _item), value in zip(
                        fan_pressure_dimensions,
                        fan_pressure_values,
                    )
                },
                "airflow_overrides": {
                    point_index: value
                    for (point_index, _item), value in zip(
                        fan_airflow_dimensions,
                        fan_airflow_values,
                    )
                },
            }
            for fan_pressure_values in fan_pressure_combinations
            for fan_airflow_values in fan_airflow_combinations
        ]

    corners = []
    solved_points = []
    solved_networks = []
    for fixed_pressure in fixed_values:
        for values in parameter_combinations:
            edge_parameter_overrides: dict[str, dict[str, float]] = {}
            corner_parameter_values = {
                output_key: {}
                for _parameter_name, output_key, _items in parameter_maps
            }
            for dimension, value in zip(dimensions, values):
                parameter_name, output_key, edge_name, _item = dimension
                edge_parameter_overrides.setdefault(edge_name, {})[
                    parameter_name
                ] = value
                corner_parameter_values[output_key][edge_name] = round(
                    value, 15
                )
            for fan_curve_case in fan_curve_cases:
                for fan_speed_ratio in fan_speed_values:
                    fan_pressure_overrides = fan_curve_case[
                        "pressure_overrides"
                    ]
                    fan_airflow_overrides = fan_curve_case[
                        "airflow_overrides"
                    ]
                    result = _solve_case(
                        study,
                        fixed_pressure,
                        edge_parameter_overrides,
                        fan_pressure_overrides,
                        fan_airflow_overrides,
                        fan_speed_ratio,
                        fan_curve_case["fan_curve"],
                    )
                    point = result["fan_operating_point"]
                    network = result["operating_network_solution"]
                    edge_airflows = None
                    if (
                        result["status"] == "solved"
                        and point is not None
                        and network is not None
                    ):
                        solved_points.append(point)
                        solved_networks.append(network)
                        edge_airflows = {
                            edge["name"]: edge["airflow_m3_h"]
                            for edge in network["edges"]
                        }

                    corners.append(
                        {
                            "fixed_pressure_pa": round(fixed_pressure, 6),
                            **(
                                {
                                    "fan_speed_ratio": round(
                                        fan_speed_ratio,
                                        6,
                                    )
                                }
                                if fan_speed_ratio is not None
                                else {}
                            ),
                            **(
                                {
                                    "fan_curve_scenario": fan_curve_case[
                                        "scenario"
                                    ]
                                }
                                if fan_curve_case["scenario"] is not None
                                else {}
                            ),
                            "fan_curve_pressure_pa": {
                                str(round(airflow_m3_h, 6)): round(value, 6)
                                for airflow_m3_h, value in fan_pressure_overrides.items()
                            },
                            "fan_curve_airflow_m3_h": {
                                str(point_index): round(value, 6)
                                for point_index, value in fan_airflow_overrides.items()
                            },
                            "edge_local_loss_coefficient": corner_parameter_values[
                                "edge_local_loss_coefficient"
                            ],
                            "edge_absolute_roughness_m": corner_parameter_values[
                                "edge_absolute_roughness_m"
                            ],
                            "edge_kinematic_viscosity_m2_s": corner_parameter_values[
                                "edge_kinematic_viscosity_m2_s"
                            ],
                            "edge_air_density_kg_m3": corner_parameter_values[
                                "edge_air_density_kg_m3"
                            ],
                            "edge_length_m": corner_parameter_values[
                                "edge_length_m"
                            ],
                            "edge_circular_diameter_m": corner_parameter_values[
                                "edge_circular_diameter_m"
                            ],
                            "edge_rectangular_width_m": corner_parameter_values[
                                "edge_rectangular_width_m"
                            ],
                            "edge_rectangular_height_m": corner_parameter_values[
                                "edge_rectangular_height_m"
                            ],
                            "status": result["status"],
                            "operating_point_search_evidence": result.get(
                                "operating_point_search_evidence"
                            ),
                            "fan_curve_no_intersection_diagnostic": (
                                _fan_curve_no_intersection_diagnostic(result)
                            ),
                            "fan_curve_intersection_bracket": (
                                _fan_curve_intersection_bracket_diagnostic(
                                    result
                                )
                            ),
                            "fan_curve_crossing_conditioning": (
                                _fan_curve_crossing_conditioning_diagnostic(
                                    result
                                )
                            ),
                            "pressure_residual_airflow_equivalence": (
                                _pressure_residual_airflow_equivalence_diagnostic(
                                    result,
                                    study.operating_pressure_tolerance_pa,
                                )
                            ),
                            "fan_curve_segment_position": (
                                _fan_curve_segment_position_diagnostic(result)
                            ),
                            "fan_curve_supplied_point_residual_audit": result.get(
                                "fan_curve_supplied_point_residual_audit"
                            ),
                            "fan_curve_airflow_range_m3_h": result[
                                "fan_curve_airflow_range_m3_h"
                            ],
                            "fan_curve_boundary_clearance": (
                                _fan_curve_boundary_clearance(result)
                            ),
                            "operating_point": point,
                            "edge_airflows_m3_h": edge_airflows,
                            "power_evidence": result["power_evidence"],
                            "solver_diagnostics": result["solver_diagnostics"],
                        }
                    )

    unresolved_corner_count = sum(
        corner["status"] != "solved" for corner in corners
    )
    all_corners_solved = (
        nominal["status"] == "solved"
        and unresolved_corner_count == 0
    )
    corner_outcome_diagnostics = _corner_outcome_diagnostics(corners)
    fan_curve_no_intersection_summary = (
        _fan_curve_no_intersection_summary(corners)
    )
    nominal_fan_curve_intersection_bracket = (
        _fan_curve_intersection_bracket_diagnostic(nominal)
    )
    fan_curve_intersection_bracket_summary = (
        _fan_curve_intersection_bracket_summary(
            corners,
            nominal["status"],
        )
    )
    nominal_fan_curve_crossing_conditioning = (
        _fan_curve_crossing_conditioning_diagnostic(nominal)
    )
    fan_curve_crossing_conditioning_summary = (
        _fan_curve_crossing_conditioning_summary(
            corners,
            nominal["status"],
        )
    )
    nominal_pressure_residual_airflow_equivalence = (
        _pressure_residual_airflow_equivalence_diagnostic(
            nominal,
            study.operating_pressure_tolerance_pa,
        )
    )
    pressure_residual_airflow_equivalence_summary = (
        _pressure_residual_airflow_equivalence_summary(
            corners,
            nominal["status"],
        )
    )
    nominal_operating_point_search_evidence = nominal.get(
        "operating_point_search_evidence"
    )
    operating_point_search_resolution_summary = (
        _operating_point_search_resolution_summary(
            corners,
            nominal["status"],
        )
    )
    nominal_fan_curve_segment_position = (
        _fan_curve_segment_position_diagnostic(nominal)
    )
    fan_curve_segment_position_summary = (
        _fan_curve_segment_position_summary(
            corners,
            nominal["status"],
        )
    )
    nominal_fan_curve_supplied_point_residual_audit = nominal.get(
        "fan_curve_supplied_point_residual_audit"
    )
    fan_curve_supplied_point_residual_summary = (
        _fan_curve_supplied_point_residual_summary(
            corners,
            nominal_fan_curve_supplied_point_residual_audit,
        )
    )
    solver_quality_summary = _solver_quality_summary(
        study,
        corners,
        nominal["status"],
    )

    nominal_fan_curve_boundary_clearance = _fan_curve_boundary_clearance(
        nominal
    )
    fan_curve_boundary_clearance_summary = (
        _fan_curve_boundary_clearance_summary(
            corners,
            nominal["status"],
        )
    )

    operating_point_envelope = None
    operating_point_extreme_cases = None
    operating_point_extrema_sources = None
    edge_airflow_corner_ranges = None
    edge_airflow_extrema_sources = None
    power_evidence_corner_ranges = None
    power_evidence_extrema_sources = None
    power_evidence_availability = None
    operating_point_excursions_from_nominal = None
    power_evidence_excursions_from_nominal = None
    if all_corners_solved:
        operating_point_envelope = {
            "airflow_m3_h": _metric_envelope(
                solved_points,
                "airflow_m3_h",
                "m3/h",
            ),
            "fan_pressure_pa": _metric_envelope(
                solved_points,
                "fan_pressure_pa",
                "Pa",
            ),
            "system_pressure_pa": _metric_envelope(
                solved_points,
                "system_pressure_pa",
                "Pa",
            ),
            "air_power_kw": _metric_envelope(
                solved_points,
                "air_power_kw",
                "kW",
            ),
        }
        operating_point_extreme_cases = {
            key: _metric_extreme_case_witnesses(solved_points, key)
            for key in (
                "airflow_m3_h",
                "fan_pressure_pa",
                "system_pressure_pa",
                "air_power_kw",
            )
        }
        operating_point_excursions_from_nominal = {
            key: _nominal_relative_excursion(
                operating_point_envelope[key],
                nominal["fan_operating_point"][key],
            )
            for key in (
                "airflow_m3_h",
                "fan_pressure_pa",
                "system_pressure_pa",
                "air_power_kw",
            )
        }
        operating_point_extrema_sources = {
            "airflow_m3_h": _metric_extrema_sources(
                corners,
                "airflow_m3_h",
                "m3/h",
            ),
            "fan_pressure_pa": _metric_extrema_sources(
                corners,
                "fan_pressure_pa",
                "Pa",
            ),
            "system_pressure_pa": _metric_extrema_sources(
                corners,
                "system_pressure_pa",
                "Pa",
            ),
            "air_power_kw": _metric_extrema_sources(
                corners,
                "air_power_kw",
                "kW",
            ),
        }
        edge_airflow_corner_ranges = _edge_airflow_corner_ranges(
            study,
            solved_networks,
        )
        edge_airflow_extrema_sources = _edge_airflow_extrema_sources(
            study,
            corners,
        )
        power_metric_specs = (
            ("fluid_air_power_kw", "kW"),
            ("shaft_power_kw", "kW"),
            ("electrical_input_kw", "kW"),
            ("specific_fan_power_w_per_m3_s", "W/(m3/s)"),
        )
        power_evidence_availability = {
            key: _power_metric_availability(corners, key)
            for key, _unit in power_metric_specs
        }
        power_evidence_corner_ranges = {
            key: _power_metric_corner_range(corners, key, unit)
            for key, unit in power_metric_specs
        }
        power_evidence_extrema_sources = {
            key: _power_metric_extrema_sources(corners, key, unit)
            for key, unit in power_metric_specs
        }

        nominal_power_evidence = nominal.get("power_evidence") or {}
        power_evidence_excursions_from_nominal = {
            key: (
                None
                if power_evidence_corner_ranges[key] is None
                or nominal_power_evidence.get(key) is None
                else _nominal_relative_excursion(
                    power_evidence_corner_ranges[key],
                    nominal_power_evidence[key],
                )
            )
            for key, _unit in power_metric_specs
        }

    fixed_record = _input_record(
        "fixed_pressure_pa",
        study.fixed_pressure_pa,
    )
    fan_pressure_records = [
        _input_record(
            f"fan_curve_pressure:{airflow_m3_h:g}_m3_h",
            item,
        )
        for airflow_m3_h, item in sorted(study.fan_curve_pressure_pa.items())
    ]
    fan_airflow_records = [
        _input_record(
            f"fan_curve_airflow:point_{point_index}",
            item,
        )
        for point_index, item in sorted(study.fan_curve_airflow_m3_h.items())
    ]
    fan_speed_record = (
        _input_record("fan_speed_ratio", study.fan_speed_ratio)
        if study.fan_speed_ratio is not None
        else None
    )
    scenario_records = [
        {
            "name": f"fan_curve_scenario:{scenario.name}",
            "value": scenario.name,
            "unit": "curve",
            "uncertainty_abs": None,
            "lower": None,
            "upper": None,
            "provenance": (
                asdict(scenario.provenance)
                if scenario.provenance is not None
                else None
            ),
        }
        for scenario in study.fan_curve_scenarios
    ]
    edge_records = [
        *[
            _input_record(f"edge_local_loss:{name}", item)
            for name, item in study.edge_local_loss_coefficient.items()
        ],
        *[
            _input_record(f"edge_roughness:{name}", item)
            for name, item in study.edge_absolute_roughness_m.items()
        ],
        *[
            _input_record(f"edge_viscosity:{name}", item)
            for name, item in study.edge_kinematic_viscosity_m2_s.items()
        ],
        *[
            _input_record(f"edge_air_density:{name}", item)
            for name, item in study.edge_air_density_kg_m3.items()
        ],
        *[
            _input_record(f"edge_length:{name}", item)
            for name, item in study.edge_length_m.items()
        ],
        *[
            _input_record(f"edge_circular_diameter:{name}", item)
            for name, item in study.edge_circular_diameter_m.items()
        ],
        *[
            _input_record(f"edge_rectangular_width:{name}", item)
            for name, item in study.edge_rectangular_width_m.items()
        ],
        *[
            _input_record(f"edge_rectangular_height:{name}", item)
            for name, item in study.edge_rectangular_height_m.items()
        ],
    ]
    missing = [
        record["name"]
        for record in [
            fixed_record,
            *([fan_speed_record] if fan_speed_record is not None else []),
            *fan_pressure_records,
            *fan_airflow_records,
            *scenario_records,
            *edge_records,
        ]
        if record["provenance"] is None
    ]
    if study.fan_curve_provenance is None:
        missing.insert(0, "fan_curve")

    result = {
        "analysis": study.name,
        "status": "complete" if all_corners_solved else "indeterminate",
        "fan_curve": study.fan_curve.name,
        "loop_network": study.loop_network.name,
        "fan_discharge_node": study.fan_discharge_node,
        "fan_suction_node": study.fan_suction_node,
        "fan_curve_scenarios": [
            {
                "name": scenario.name,
                "fan_curve": scenario.fan_curve.name,
                "points": [
                    {
                        "airflow_m3_h": point.airflow_m3_h,
                        "pressure_pa": point.pressure_pa,
                    }
                    for point in scenario.fan_curve.points
                ],
                "provenance": (
                    asdict(scenario.provenance)
                    if scenario.provenance is not None
                    else None
                ),
            }
            for scenario in study.fan_curve_scenarios
        ],
        "input_intervals": {
            "fixed_pressure_pa": {
                "nominal": study.fixed_pressure_pa.value,
                "lower": study.fixed_pressure_pa.lower,
                "upper": study.fixed_pressure_pa.upper,
                "unit": "Pa",
            },
            "fan_speed_ratio": (
                {
                    "nominal": study.fan_speed_ratio.value,
                    "lower": study.fan_speed_ratio.lower,
                    "upper": study.fan_speed_ratio.upper,
                    "unit": "1",
                }
                if study.fan_speed_ratio is not None
                else None
            ),
            "fan_curve_pressure_pa": {
                str(round(airflow_m3_h, 6)): {
                    "nominal": item.value,
                    "lower": item.lower,
                    "upper": item.upper,
                    "unit": "Pa",
                }
                for airflow_m3_h, item in sorted(
                    study.fan_curve_pressure_pa.items()
                )
            },
            "fan_curve_airflow_m3_h": {
                str(point_index): {
                    "nominal": item.value,
                    "lower": item.lower,
                    "upper": item.upper,
                    "unit": "m3/h",
                }
                for point_index, item in sorted(
                    study.fan_curve_airflow_m3_h.items()
                )
            },
            "edge_local_loss_coefficient": {
                name: {
                    "nominal": item.value,
                    "lower": item.lower,
                    "upper": item.upper,
                    "unit": "1",
                }
                for name, item in study.edge_local_loss_coefficient.items()
            },
            "edge_absolute_roughness_m": {
                name: {
                    "nominal": item.value,
                    "lower": item.lower,
                    "upper": item.upper,
                    "unit": "m",
                }
                for name, item in study.edge_absolute_roughness_m.items()
            },
            "edge_kinematic_viscosity_m2_s": {
                name: {
                    "nominal": item.value,
                    "lower": item.lower,
                    "upper": item.upper,
                    "unit": "m2/s",
                }
                for name, item in study.edge_kinematic_viscosity_m2_s.items()
            },
            "edge_air_density_kg_m3": {
                name: {
                    "nominal": item.value,
                    "lower": item.lower,
                    "upper": item.upper,
                    "unit": "kg/m3",
                }
                for name, item in study.edge_air_density_kg_m3.items()
            },
            "edge_length_m": {
                name: {
                    "nominal": item.value,
                    "lower": item.lower,
                    "upper": item.upper,
                    "unit": "m",
                }
                for name, item in study.edge_length_m.items()
            },
            "edge_circular_diameter_m": {
                name: {
                    "nominal": item.value,
                    "lower": item.lower,
                    "upper": item.upper,
                    "unit": "m",
                }
                for name, item in study.edge_circular_diameter_m.items()
            },
            "edge_rectangular_width_m": {
                name: {
                    "nominal": item.value,
                    "lower": item.lower,
                    "upper": item.upper,
                    "unit": "m",
                }
                for name, item in study.edge_rectangular_width_m.items()
            },
            "edge_rectangular_height_m": {
                name: {
                    "nominal": item.value,
                    "lower": item.lower,
                    "upper": item.upper,
                    "unit": "m",
                }
                for name, item in study.edge_rectangular_height_m.items()
            },
        },
        "nominal_status": nominal["status"],
        "nominal_operating_point": nominal["fan_operating_point"],
        "nominal_power_evidence": nominal["power_evidence"],
        "nominal_result": nominal,
        "corner_count": len(corners),
        "solved_corner_count": len(solved_points),
        "unresolved_corner_count": unresolved_corner_count,
        "corner_outcome_diagnostics": corner_outcome_diagnostics,
        "fan_curve_no_intersection_summary": (
            fan_curve_no_intersection_summary
        ),
        "nominal_fan_curve_intersection_bracket": (
            nominal_fan_curve_intersection_bracket
        ),
        "fan_curve_intersection_bracket_summary": (
            fan_curve_intersection_bracket_summary
        ),
        "nominal_fan_curve_crossing_conditioning": (
            nominal_fan_curve_crossing_conditioning
        ),
        "fan_curve_crossing_conditioning_summary": (
            fan_curve_crossing_conditioning_summary
        ),
        "nominal_pressure_residual_airflow_equivalence": (
            nominal_pressure_residual_airflow_equivalence
        ),
        "pressure_residual_airflow_equivalence_summary": (
            pressure_residual_airflow_equivalence_summary
        ),
        "nominal_operating_point_search_evidence": (
            nominal_operating_point_search_evidence
        ),
        "operating_point_search_resolution_summary": (
            operating_point_search_resolution_summary
        ),
        "nominal_fan_curve_segment_position": (
            nominal_fan_curve_segment_position
        ),
        "fan_curve_segment_position_summary": (
            fan_curve_segment_position_summary
        ),
        "nominal_fan_curve_supplied_point_residual_audit": (
            nominal_fan_curve_supplied_point_residual_audit
        ),
        "fan_curve_supplied_point_residual_summary": (
            fan_curve_supplied_point_residual_summary
        ),
        "solver_quality_summary": solver_quality_summary,
        "nominal_fan_curve_boundary_clearance": (
            nominal_fan_curve_boundary_clearance
        ),
        "fan_curve_boundary_clearance_summary": (
            fan_curve_boundary_clearance_summary
        ),
        "corners": corners,
        "operating_point_envelope": operating_point_envelope,
        "operating_point_extreme_cases": operating_point_extreme_cases,
        "operating_point_extrema_sources": operating_point_extrema_sources,
        "operating_point_excursions_from_nominal": (
            operating_point_excursions_from_nominal
        ),
        "edge_airflow_corner_ranges": edge_airflow_corner_ranges,
        "edge_airflow_extrema_sources": edge_airflow_extrema_sources,
        "power_efficiencies": (
            None
            if study.power_efficiencies is None
            else study.power_efficiencies.to_dict()
        ),
        "power_evidence_availability": power_evidence_availability,
        "power_evidence_corner_ranges": power_evidence_corner_ranges,
        "power_evidence_extrema_sources": power_evidence_extrema_sources,
        "power_evidence_excursions_from_nominal": (
            power_evidence_excursions_from_nominal
        ),
        "traceability": {
            "complete": not missing,
            "missing_provenance": missing,
            "fan_curve_provenance": (
                asdict(study.fan_curve_provenance)
                if study.fan_curve_provenance is not None
                else None
            ),
            "inputs": [
                fixed_record,
                *([fan_speed_record] if fan_speed_record is not None else []),
                *fan_pressure_records,
                *fan_airflow_records,
                *scenario_records,
                *edge_records,
            ],
        },
        "message": (
            "All evaluated uncertainty corners converged and intersect the "
            "supplied fan curve; reported operating-point values are min/max "
            "across those solved corners."
            if all_corners_solved
            else "At least one evaluated uncertainty corner is unresolved "
            "because the fan curve has no bounded intersection or the "
            "variable-friction/network solver did not converge. No complete "
            "operating-point or edge-flow corner range is reported."
        ),
        "engineering_note": (
            "This is deterministic corner analysis for user-supplied "
            "absolute bounds on fixed pressure, fan speed ratio, selected "
            "supplied fan-curve point pressures and airflow coordinates, and selected "
            "automatic-friction duct local-loss "
            "coefficients, absolute roughness, kinematic viscosity, air density, "
            "duct length, circular diameter, and rectangular width/height. "
            "Every corner rebuilds the affected "
            "geometry-edge evidence and re-solves the complete Darcy-friction "
            "network at every fan/system airflow evaluated by the bounded "
            "operating-point search. Reported airflow, pressure, and air-power "
            "min/max values are ranges across evaluated corners only; when complete, "
            "nominal-centered absolute and percentage excursions are also reported "
            "for operating-point and available power-chain metrics. Those excursions "
            "describe only the evaluated corner set and are not sensitivity "
            "coefficients. Their source corner indices "
            "and fan scenario/speed/fixed-pressure context are retained for "
            "auditability. Corner outcome diagnostics separately retain "
            "status and solver termination-reason counts plus the exact input "
            "context of every unresolved evaluated corner without converting "
            "partial solved cases into a complete envelope. No-intersection "
            "corners additionally retain the exact supplied endpoint pressure "
            "mismatch that bounds the case, without fan-curve extrapolation "
            "or estimating a missing operating point. When explicit "
            "fan/motor/VFD efficiencies are supplied, solved-corner power "
            "evidence also retains fluid, shaft, electrical-input, and "
            "specific-fan-power ranges plus their source corners. Each power "
            "metric range is emitted only when that metric is available at "
            "every evaluated solved corner; partial metric coverage is "
            "reported explicitly and withheld from min/max summarization. The "
            "fan-curve boundary-clearance audit also retains each solved "
            "corner's actual supplied/transformed airflow range and reports "
            "the closest evaluated operating point to a no-extrapolation "
            "endpoint without inventing a minimum acceptable margin. The "
            "local crossing-conditioning audit reuses each supplied-point "
            "intersection bracket to report fan, system, and residual secant "
            "slopes plus secant-root agreement without inferring a stability "
            "or acceptance threshold. The pressure-residual-to-airflow audit "
            "maps only the configured operating-pressure solver tolerance and "
            "actual solved residual through that local secant gradient; its "
            "airflow equivalents are numerical diagnostics, not physical "
            "uncertainty or acceptance limits. The supplied-point residual-topology "
            "audit also propagates discrete monotonicity and candidate-crossing "
            "features from every nonlinear solver case without presenting "
            "sampled behavior as proof of continuous uniqueness. Those "
            "efficiencies remain fixed user inputs in this workflow; no "
            "efficiency value or efficiency uncertainty is inferred. These "
            "are not claimed as guaranteed extrema for all interior "
            "combinations. "
            "No probability distribution, "
            "covariance beyond explicitly supplied whole-curve scenarios, "
            "unconfigured geometry tolerance inference, "
            "damper/control inference, leakage, system effect, acoustics, "
            "stall/surge assessment, motor/VFD limits, compressibility, "
            "transients, or manufacturer acceptance is inferred."
        ),
    }
    result["result_integrity"] = {
        "algorithm": "sha256",
        "canonicalization": "json-sort-keys-compact-utf8-v1",
        "scope": (
            "cleanroomx.fan_variable_friction_loop_uncertainty."
            "result_without_result_integrity.v1"
        ),
        "sha256": _canonical_result_sha256(result),
    }
    return result
