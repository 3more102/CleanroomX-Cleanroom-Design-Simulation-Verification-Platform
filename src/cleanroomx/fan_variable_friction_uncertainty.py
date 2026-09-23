from __future__ import annotations

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
        if not math.isclose(
            score,
            maximum,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
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
    solved_corner_count = sum(
        corner["status"] == "solved" for corner in corners
    )

    def _diagnostic(key: str):
        return lambda corner: (
            (corner.get("solver_diagnostics") or {}).get(key)
            if corner["status"] == "solved"
            else None
        )

    return {
        "corner_count": len(corners),
        "solved_corner_count": solved_corner_count,
        "complete_evaluated_corner_coverage": (
            solved_corner_count == len(corners)
        ),
        "nominal_status": nominal_status,
        "complete_study_coverage": (
            nominal_status == "solved"
            and solved_corner_count == len(corners)
        ),
        "configured_tolerances": {
            "operating_pressure_tolerance_pa": (
                study.operating_pressure_tolerance_pa
            ),
            "resistance_relative_tolerance": (
                study.resistance_relative_tolerance
            ),
            "mass_balance_tolerance_m3_h": (
                study.mass_balance_tolerance_m3_h
            ),
        },
        "worst_metrics": {
            "absolute_operating_pressure_residual_pa": (
                _maximum_corner_metric_sources(
                    corners,
                    lambda corner: (
                        corner["operating_point"].get("pressure_residual_pa")
                        if corner.get("operating_point") is not None
                        else None
                    ),
                    "Pa",
                    absolute=True,
                )
            ),
            "network_max_relative_resistance_closure_error": (
                _maximum_corner_metric_sources(
                    corners,
                    _diagnostic(
                        "network_max_relative_resistance_closure_error"
                    ),
                    "1",
                )
            ),
            "max_abs_mass_balance_residual_m3_h": (
                _maximum_corner_metric_sources(
                    corners,
                    _diagnostic("max_abs_mass_balance_residual_m3_h"),
                    "m3/h",
                )
            ),
            "max_abs_pressure_law_residual_pa": (
                _maximum_corner_metric_sources(
                    corners,
                    _diagnostic("max_abs_pressure_law_residual_pa"),
                    "Pa",
                )
            ),
            "network_outer_iterations": _maximum_corner_metric_sources(
                corners,
                _diagnostic("network_outer_iterations"),
                "iterations",
            ),
            "operating_iterations": _maximum_corner_metric_sources(
                corners,
                _diagnostic("operating_iterations"),
                "iterations",
            ),
        },
        "scope_note": (
            "Worst metrics aggregate solved evaluated corners only. "
            "complete_study_coverage is false if the nominal case or any "
            "evaluated corner is unresolved. Pressure-law residual and "
            "iteration maxima are reported as diagnostics without inventing "
            "an acceptance threshold."
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
                            "operating_point": point,
                            "edge_airflows_m3_h": edge_airflows,
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
    solver_quality_summary = _solver_quality_summary(
        study,
        corners,
        nominal["status"],
    )

    operating_point_envelope = None
    operating_point_extreme_cases = None
    operating_point_extrema_sources = None
    edge_airflow_corner_ranges = None
    edge_airflow_extrema_sources = None
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

    return {
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
        "nominal_result": nominal,
        "corner_count": len(corners),
        "solved_corner_count": len(solved_points),
        "unresolved_corner_count": unresolved_corner_count,
        "corner_outcome_diagnostics": corner_outcome_diagnostics,
        "solver_quality_summary": solver_quality_summary,
        "corners": corners,
        "operating_point_envelope": operating_point_envelope,
        "operating_point_extreme_cases": operating_point_extreme_cases,
        "operating_point_extrema_sources": operating_point_extrema_sources,
        "edge_airflow_corner_ranges": edge_airflow_corner_ranges,
        "edge_airflow_extrema_sources": edge_airflow_extrema_sources,
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
            "their source corner indices "
            "and fan scenario/speed/fixed-pressure context are retained for "
            "auditability. Corner outcome diagnostics separately retain "
            "status and solver termination-reason counts plus the exact input "
            "context of every unresolved evaluated corner without converting "
            "partial solved cases into a complete envelope. These are not "
            "claimed as guaranteed extrema for all interior combinations. "
            "No probability distribution, "
            "covariance beyond explicitly supplied whole-curve scenarios, "
            "unconfigured geometry tolerance inference, "
            "damper/control inference, leakage, system effect, acoustics, "
            "stall/surge assessment, motor/VFD limits, compressibility, "
            "transients, or manufacturer acceptance is inferred."
        ),
    }
