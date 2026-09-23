from __future__ import annotations

import math
from dataclasses import dataclass

from .fan_curve import FanCurve, FanCurvePoint
from .fan_loop_network import FanLoopNetworkStudy
from .loop_network import LoopedFlowNetwork
from .pressure_power import FanPowerEfficiencies, analyze_fan_pressure_power
from .variable_friction_loop import solve_variable_friction_looped_network


def _positive(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field_name} must be finite and > 0")
    return value


def _unit_interval(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0 or value > 1:
        raise ValueError(f"{field_name} must be finite and in (0, 1]")
    return value


def _nonnegative(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{field_name} must be finite and >= 0")
    return value


def _positive_integer(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be an integer > 0")
    return value


@dataclass(frozen=True)
class FanVariableFrictionLoopStudy:
    name: str
    fan_curve: FanCurve
    loop_network: LoopedFlowNetwork
    fan_discharge_node: str
    fan_suction_node: str
    fixed_pressure_pa: float = 0.0
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
                "fan/variable-friction loop study name cannot be empty"
            )
        object.__setattr__(
            self,
            "fixed_pressure_pa",
            _nonnegative(self.fixed_pressure_pa, "fixed_pressure_pa"),
        )
        if (
            self.power_efficiencies is not None
            and not isinstance(self.power_efficiencies, FanPowerEfficiencies)
        ):
            raise ValueError(
                "power_efficiencies must be FanPowerEfficiencies or None"
            )
        object.__setattr__(
            self,
            "resistance_relative_tolerance",
            _positive(
                self.resistance_relative_tolerance,
                "resistance_relative_tolerance",
            ),
        )
        object.__setattr__(
            self,
            "relaxation",
            _unit_interval(self.relaxation, "relaxation"),
        )
        object.__setattr__(
            self,
            "near_zero_airflow_m3_h",
            _nonnegative(
                self.near_zero_airflow_m3_h,
                "near_zero_airflow_m3_h",
            ),
        )
        object.__setattr__(
            self,
            "max_outer_iterations",
            _positive_integer(
                self.max_outer_iterations, "max_outer_iterations"
            ),
        )
        object.__setattr__(
            self,
            "mass_balance_tolerance_m3_h",
            _positive(
                self.mass_balance_tolerance_m3_h,
                "mass_balance_tolerance_m3_h",
            ),
        )
        object.__setattr__(
            self,
            "max_newton_iterations",
            _positive_integer(
                self.max_newton_iterations, "max_newton_iterations"
            ),
        )
        object.__setattr__(
            self,
            "operating_pressure_tolerance_pa",
            _positive(
                self.operating_pressure_tolerance_pa,
                "operating_pressure_tolerance_pa",
            ),
        )
        object.__setattr__(
            self,
            "max_operating_iterations",
            _positive_integer(
                self.max_operating_iterations, "max_operating_iterations"
            ),
        )

        # Reuse the established two-terminal fan/loop topology checks without
        # using the fixed-resistance equivalent-law solver.
        FanLoopNetworkStudy(
            name=self.name,
            fan_curve=self.fan_curve,
            loop_network=self.loop_network,
            fan_discharge_node=self.fan_discharge_node,
            fan_suction_node=self.fan_suction_node,
            fixed_pressure_pa=self.fixed_pressure_pa,
        )


def _network_at_airflow(
    study: FanVariableFrictionLoopStudy,
    airflow_m3_h: float,
) -> LoopedFlowNetwork:
    airflow = _nonnegative(airflow_m3_h, "airflow_m3_h")
    reference_airflow = study.loop_network.node_injections_m3_h[
        study.fan_discharge_node
    ]
    scale = airflow / reference_airflow
    return LoopedFlowNetwork(
        name=study.loop_network.name,
        node_injections_m3_h={
            node: injection * scale
            for node, injection in study.loop_network.node_injections_m3_h.items()
        },
        edges=study.loop_network.edges,
        reference_node=study.loop_network.reference_node,
    )


def _node_pressure(result: dict, node_name: str) -> float:
    for node in result["nodes"]:
        if node["name"] == node_name:
            return float(node["relative_pressure_pa"])
    raise RuntimeError(f"node {node_name!r} missing from loop-network result")


def _fan_pressure(
    left: FanCurvePoint,
    right: FanCurvePoint,
    airflow_m3_h: float,
) -> float:
    fraction = (
        (airflow_m3_h - left.airflow_m3_h)
        / (right.airflow_m3_h - left.airflow_m3_h)
    )
    return left.pressure_pa + fraction * (
        right.pressure_pa - left.pressure_pa
    )


def _solve_network_at_airflow(
    study: FanVariableFrictionLoopStudy,
    airflow_m3_h: float,
) -> tuple[dict, float]:
    network = _network_at_airflow(study, airflow_m3_h)
    solved = solve_variable_friction_looped_network(
        network,
        resistance_relative_tolerance=study.resistance_relative_tolerance,
        relaxation=study.relaxation,
        near_zero_airflow_m3_h=study.near_zero_airflow_m3_h,
        max_outer_iterations=study.max_outer_iterations,
        mass_balance_tolerance_m3_h=study.mass_balance_tolerance_m3_h,
        max_newton_iterations=study.max_newton_iterations,
    )
    discharge_pressure = _node_pressure(solved, study.fan_discharge_node)
    suction_pressure = _node_pressure(solved, study.fan_suction_node)
    network_pressure = discharge_pressure - suction_pressure
    if not math.isfinite(network_pressure) or network_pressure < -1e-9:
        raise RuntimeError(
            "variable-friction loop solution produced invalid fan-terminal "
            "pressure requirement"
        )
    return solved, max(network_pressure, 0.0)


def _point_check(
    study: FanVariableFrictionLoopStudy,
    point: FanCurvePoint,
) -> tuple[dict, dict]:
    network, network_pressure = _solve_network_at_airflow(
        study, point.airflow_m3_h
    )
    total_pressure = study.fixed_pressure_pa + network_pressure
    residual = point.pressure_pa - total_pressure
    vf = network["variable_friction"]
    return (
        {
            "airflow_m3_h": round(point.airflow_m3_h, 6),
            "fan_pressure_pa": round(point.pressure_pa, 9),
            "loop_network_pressure_pa": round(network_pressure, 9),
            "system_pressure_pa": round(total_pressure, 9),
            "pressure_margin_pa": round(residual, 9),
            "network_outer_iterations": vf["outer_iterations"],
            "max_relative_resistance_closure_error": vf[
                "max_relative_resistance_closure_error"
            ],
        },
        network,
    )


def _nonconverged_result(
    study: FanVariableFrictionLoopStudy,
    *,
    curve_checks: list[dict],
    message: str,
) -> dict:
    return {
        "study": study.name,
        "status": "non_converged",
        "fan_curve": study.fan_curve.name,
        "fan_discharge_node": study.fan_discharge_node,
        "fan_suction_node": study.fan_suction_node,
        "fixed_pressure_pa": round(study.fixed_pressure_pa, 6),
        "fan_curve_airflow_range_m3_h": [
            round(study.fan_curve.points[0].airflow_m3_h, 6),
            round(study.fan_curve.points[-1].airflow_m3_h, 6),
        ],
        "fan_curve_point_checks": curve_checks,
        "fan_operating_point": None,
        "operating_network_solution": None,
        "system_pressure_check": None,
        "power_evidence": None,
        "solver_diagnostics": {
            "converged": False,
            "termination_reason": "network_solver_non_convergence",
            "operating_iterations": 0,
            "operating_pressure_tolerance_pa": (
                study.operating_pressure_tolerance_pa
            ),
        },
        "message": message,
        "scope_note": _scope_note(),
    }


def _scope_note() -> str:
    return (
        "This workflow couples the supplied fan curve directly to the "
        "two-terminal loop network while re-solving flow-dependent Darcy "
        "friction at every evaluated airflow. Fan pressure is interpolated "
        "only between supplied fan points and is never extrapolated. "
        "Automatic Darcy updates reuse the existing explicit roughness, "
        "kinematic-viscosity, density, geometry, and local-K model; edges "
        "with explicit resistance or user-supplied friction remain fixed. "
        "This is a steady incompressible engineering screening model, not "
        "CFD. It does not infer dampers, leakage, controls, system effect, "
        "acoustics, stall/surge limits, motor/VFD limits, transients, or "
        "manufacturer acceptance. Fluid pressure power is reported directly; "
        "shaft/electrical power is reported only from explicit efficiencies."
    )


def solve_fan_variable_friction_loop(
    study: FanVariableFrictionLoopStudy,
) -> dict:
    points = study.fan_curve.points
    curve_checks: list[dict] = []
    point_networks: list[dict] = []

    try:
        for point in points:
            check, network = _point_check(study, point)
            curve_checks.append(check)
            point_networks.append(network)
    except RuntimeError as exc:
        return _nonconverged_result(
            study,
            curve_checks=curve_checks,
            message=(
                "The variable-friction loop solver did not converge while "
                f"evaluating the bounded fan curve: {exc}"
            ),
        )

    tolerance = study.operating_pressure_tolerance_pa
    selected_airflow: float | None = None
    selected_fan_pressure: float | None = None
    selected_network: dict | None = None
    selected_network_pressure: float | None = None
    selected_segment = 0
    operating_iterations = 0
    termination_reason = "no_intersection_in_supplied_range"

    for index, (point, check, network) in enumerate(
        zip(points, curve_checks, point_networks)
    ):
        if abs(float(check["pressure_margin_pa"])) <= tolerance:
            selected_airflow = point.airflow_m3_h
            selected_fan_pressure = point.pressure_pa
            selected_network = network
            selected_network_pressure = float(
                check["loop_network_pressure_pa"]
            )
            selected_segment = min(index, len(points) - 2)
            termination_reason = "fan_curve_point_residual"
            break

    if selected_airflow is None:
        for index, (left, right) in enumerate(zip(points, points[1:])):
            left_residual = float(curve_checks[index]["pressure_margin_pa"])
            right_residual = float(
                curve_checks[index + 1]["pressure_margin_pa"]
            )
            if not (left_residual > 0.0 and right_residual < 0.0):
                continue

            low = left.airflow_m3_h
            high = right.airflow_m3_h
            low_residual = left_residual
            final: tuple[float, float, dict, float, float] | None = None

            try:
                for iteration in range(1, study.max_operating_iterations + 1):
                    airflow = 0.5 * (low + high)
                    fan_pressure = _fan_pressure(left, right, airflow)
                    network, network_pressure = _solve_network_at_airflow(
                        study, airflow
                    )
                    system_pressure = (
                        study.fixed_pressure_pa + network_pressure
                    )
                    residual = fan_pressure - system_pressure
                    final = (
                        airflow,
                        fan_pressure,
                        network,
                        network_pressure,
                        residual,
                    )
                    operating_iterations = iteration
                    if abs(residual) <= tolerance:
                        termination_reason = "pressure_residual"
                        break
                    if residual > 0.0:
                        low = airflow
                        low_residual = residual
                    else:
                        high = airflow
                else:
                    termination_reason = "bisection_iteration_limit"
            except RuntimeError as exc:
                return _nonconverged_result(
                    study,
                    curve_checks=curve_checks,
                    message=(
                        "The variable-friction loop solver did not converge "
                        "during bounded fan/system root search: "
                        f"{exc}"
                    ),
                )

            if final is None:
                continue
            (
                selected_airflow,
                selected_fan_pressure,
                selected_network,
                selected_network_pressure,
                residual,
            ) = final
            selected_segment = index
            if abs(residual) > tolerance:
                return {
                    **_nonconverged_result(
                        study,
                        curve_checks=curve_checks,
                        message=(
                            "Bounded fan/system bisection reached "
                            "max_operating_iterations before satisfying the "
                            "configured pressure residual tolerance."
                        ),
                    ),
                    "solver_diagnostics": {
                        "converged": False,
                        "termination_reason": termination_reason,
                        "operating_iterations": operating_iterations,
                        "operating_pressure_tolerance_pa": tolerance,
                        "final_pressure_residual_pa": round(residual, 9),
                        "bracket_low_airflow_m3_h": round(low, 9),
                        "bracket_high_airflow_m3_h": round(high, 9),
                    },
                }
            break

    base = {
        "study": study.name,
        "fan_curve": study.fan_curve.name,
        "fan_discharge_node": study.fan_discharge_node,
        "fan_suction_node": study.fan_suction_node,
        "fixed_pressure_pa": round(study.fixed_pressure_pa, 6),
        "fan_curve_airflow_range_m3_h": [
            round(points[0].airflow_m3_h, 6),
            round(points[-1].airflow_m3_h, 6),
        ],
        "fan_curve_point_checks": curve_checks,
    }

    if selected_airflow is None:
        if float(curve_checks[0]["pressure_margin_pa"]) < 0.0:
            message = (
                "System pressure exceeds fan pressure at the lowest supplied "
                "airflow point. No lower-flow fan extrapolation is performed."
            )
        else:
            message = (
                "Fan pressure remains above system pressure at the highest "
                "supplied airflow point. No higher-flow fan extrapolation is "
                "performed."
            )
        return {
            **base,
            "status": "no_intersection_in_supplied_range",
            "fan_operating_point": None,
            "operating_network_solution": None,
            "system_pressure_check": None,
            "power_evidence": None,
            "solver_diagnostics": {
                "converged": True,
                "termination_reason": termination_reason,
                "operating_iterations": 0,
                "operating_pressure_tolerance_pa": tolerance,
            },
            "message": message,
            "scope_note": _scope_note(),
        }

    assert selected_fan_pressure is not None
    assert selected_network is not None
    assert selected_network_pressure is not None
    system_pressure = study.fixed_pressure_pa + selected_network_pressure
    residual = selected_fan_pressure - system_pressure
    airflow_m3_s = selected_airflow / 3600.0
    left = points[selected_segment]
    right = points[selected_segment + 1]
    vf = selected_network["variable_friction"]
    power_evidence = analyze_fan_pressure_power(
        selected_airflow,
        selected_fan_pressure,
        study.power_efficiencies,
    )
    network_pressure_power_w = (
        airflow_m3_s * selected_network_pressure
    )
    fixed_pressure_power_w = airflow_m3_s * study.fixed_pressure_pa
    edge_dissipation_w = selected_network["pressure_power"][
        "total_edge_dissipation_w"
    ]
    fan_to_system_power_residual_w = (
        power_evidence["fluid_air_power_w"]
        - fixed_pressure_power_w
        - edge_dissipation_w
    )
    power_evidence["system_components"] = {
        "fixed_pressure_power_w": round(fixed_pressure_power_w, 9),
        "loop_network_terminal_pressure_power_w": round(
            network_pressure_power_w, 9
        ),
        "loop_network_edge_dissipation_w": edge_dissipation_w,
        "loop_network_energy_balance_residual_w": selected_network[
            "pressure_power"
        ]["balance_residual_w"],
        "fan_to_fixed_plus_edge_loss_residual_w": round(
            fan_to_system_power_residual_w, 9
        ),
    }

    return {
        **base,
        "status": "solved",
        "fan_operating_point": {
            "airflow_m3_h": round(selected_airflow, 6),
            "airflow_m3_s": round(airflow_m3_s, 9),
            "fan_pressure_pa": round(selected_fan_pressure, 9),
            "system_pressure_pa": round(system_pressure, 9),
            "pressure_residual_pa": round(residual, 9),
            "air_power_kw": round(
                airflow_m3_s * system_pressure / 1000.0, 9
            ),
            "interpolation_segment": {
                "low_airflow_m3_h": round(left.airflow_m3_h, 6),
                "high_airflow_m3_h": round(right.airflow_m3_h, 6),
            },
        },
        "operating_network_solution": selected_network,
        "power_evidence": power_evidence,
        "system_pressure_check": {
            "fixed_pressure_pa": round(study.fixed_pressure_pa, 6),
            "loop_network_pressure_pa": round(
                selected_network_pressure, 9
            ),
            "total_system_pressure_pa": round(system_pressure, 9),
            "fan_pressure_pa": round(selected_fan_pressure, 9),
            "fan_minus_system_pressure_pa": round(residual, 9),
        },
        "solver_diagnostics": {
            "converged": True,
            "termination_reason": termination_reason,
            "operating_iterations": operating_iterations,
            "operating_pressure_tolerance_pa": tolerance,
            "network_outer_iterations": vf["outer_iterations"],
            "network_resistance_relative_tolerance": vf[
                "resistance_relative_tolerance"
            ],
            "network_max_relative_resistance_closure_error": vf[
                "max_relative_resistance_closure_error"
            ],
            "max_abs_mass_balance_residual_m3_h": selected_network[
                "max_abs_mass_balance_residual_m3_h"
            ],
            "max_abs_pressure_law_residual_pa": selected_network[
                "max_abs_pressure_law_residual_pa"
            ],
        },
        "message": (
            "Operating point found inside the supplied fan-curve range by "
            "bounded interpolation with a complete variable-friction loop "
            "re-solve at every evaluated airflow."
        ),
        "scope_note": _scope_note(),
    }
