from __future__ import annotations

import math
from dataclasses import dataclass


_PATH_KINDS = frozenset(
    {
        "door",
        "window",
        "undercut",
        "transfer_grille",
        "pass_box",
        "wall_penetration",
        "crack",
        "intentional_leakage",
        "generic_opening",
        "generic",
    }
)
_FLOW_MODELS = frozenset({"power_law", "orifice"})


class _PressureNetworkNumericalError(RuntimeError):
    """Raised when finite inputs produce a non-finite solver state."""


def _finite_result(value: float, context: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise _PressureNetworkNumericalError(
            "pressure-network numerical result became non-finite: "
            + context
        )
    return value


def _finite_sum(values, context: str) -> float:
    try:
        total = math.fsum(values)
    except OverflowError as exc:
        raise _PressureNetworkNumericalError(
            "pressure-network numerical result became non-finite: "
            + context
        ) from exc
    return _finite_result(total, context)


def _finite(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite")
    return value


def _nonnegative(value: float, field_name: str) -> float:
    value = _finite(value, field_name)
    if value < 0.0:
        raise ValueError(f"{field_name} must be >= 0")
    return value


def _positive(value: float, field_name: str) -> float:
    value = _finite(value, field_name)
    if value <= 0.0:
        raise ValueError(f"{field_name} must be > 0")
    return value


@dataclass(frozen=True)
class PressureNode:
    name: str
    supply_m3_h: float = 0.0
    return_m3_h: float = 0.0
    exhaust_m3_h: float = 0.0
    fixed_pressure_pa: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("pressure-network node name must be a non-empty string")
        object.__setattr__(
            self,
            "supply_m3_h",
            _nonnegative(self.supply_m3_h, f"{self.name} supply_m3_h"),
        )
        object.__setattr__(
            self,
            "return_m3_h",
            _nonnegative(self.return_m3_h, f"{self.name} return_m3_h"),
        )
        object.__setattr__(
            self,
            "exhaust_m3_h",
            _nonnegative(self.exhaust_m3_h, f"{self.name} exhaust_m3_h"),
        )
        if self.fixed_pressure_pa is not None:
            object.__setattr__(
                self,
                "fixed_pressure_pa",
                _finite(
                    self.fixed_pressure_pa,
                    f"{self.name} fixed_pressure_pa",
                ),
            )
        mechanical_injection = (
            self.supply_m3_h
            - self.return_m3_h
            - self.exhaust_m3_h
        )
        if not math.isfinite(mechanical_injection):
            raise ValueError(
                f"{self.name} mechanical_injection_m3_h must remain finite"
            )

    @property
    def mechanical_injection_m3_h(self) -> float:
        return self.supply_m3_h - self.return_m3_h - self.exhaust_m3_h


@dataclass(frozen=True)
class PressurePath:
    name: str
    start_node: str
    end_node: str
    kind: str
    model: str
    coefficient_m3_s_pa_n: float | None = None
    exponent: float | None = None
    discharge_coefficient: float | None = None
    area_m2: float | None = None
    air_density_kg_m3: float | None = None
    pressure_offset_pa: float = 0.0
    linearization_pressure_pa: float = 0.01

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("pressure-network path name must be a non-empty string")
        if not isinstance(self.start_node, str) or not self.start_node.strip():
            raise ValueError(
                "pressure-network path start_node must be a non-empty string"
            )
        if not isinstance(self.end_node, str) or not self.end_node.strip():
            raise ValueError(
                "pressure-network path end_node must be a non-empty string"
            )
        if self.start_node == self.end_node:
            raise ValueError("pressure-network path cannot connect a node to itself")
        if self.kind not in _PATH_KINDS:
            raise ValueError(
                "pressure-network path kind must be one of: "
                + ", ".join(sorted(_PATH_KINDS))
            )
        if self.model not in _FLOW_MODELS:
            raise ValueError(
                "pressure-network path model must be 'power_law' or 'orifice'"
            )
        object.__setattr__(
            self,
            "pressure_offset_pa",
            _finite(
                self.pressure_offset_pa,
                f"{self.name} pressure_offset_pa",
            ),
        )
        object.__setattr__(
            self,
            "linearization_pressure_pa",
            _positive(
                self.linearization_pressure_pa,
                f"{self.name} linearization_pressure_pa",
            ),
        )

        if self.model == "power_law":
            if self.coefficient_m3_s_pa_n is None or self.exponent is None:
                raise ValueError(
                    "power_law path requires coefficient_m3_s_pa_n and exponent"
                )
            coefficient = _positive(
                self.coefficient_m3_s_pa_n,
                f"{self.name} coefficient_m3_s_pa_n",
            )
            exponent = _finite(self.exponent, f"{self.name} exponent")
            if not 0.5 <= exponent <= 1.0:
                raise ValueError(
                    f"{self.name} exponent must be in [0.5, 1.0]"
                )
            if (
                self.discharge_coefficient is not None
                or self.area_m2 is not None
                or self.air_density_kg_m3 is not None
            ):
                raise ValueError(
                    "power_law path cannot also define discharge_coefficient, "
                    "area_m2, or air_density_kg_m3"
                )
            object.__setattr__(
                self,
                "coefficient_m3_s_pa_n",
                coefficient,
            )
            object.__setattr__(self, "exponent", exponent)
        else:
            if (
                self.discharge_coefficient is None
                or self.area_m2 is None
                or self.air_density_kg_m3 is None
            ):
                raise ValueError(
                    "orifice path requires discharge_coefficient, area_m2, "
                    "and air_density_kg_m3"
                )
            if self.coefficient_m3_s_pa_n is not None or self.exponent is not None:
                raise ValueError(
                    "orifice path cannot also define "
                    "coefficient_m3_s_pa_n or exponent"
                )
            object.__setattr__(
                self,
                "discharge_coefficient",
                _positive(
                    self.discharge_coefficient,
                    f"{self.name} discharge_coefficient",
                ),
            )
            object.__setattr__(
                self,
                "area_m2",
                _positive(self.area_m2, f"{self.name} area_m2"),
            )
            object.__setattr__(
                self,
                "air_density_kg_m3",
                _positive(
                    self.air_density_kg_m3,
                    f"{self.name} air_density_kg_m3",
                ),
            )


@dataclass(frozen=True)
class PressureTarget:
    name: str
    high_node: str
    low_node: str
    minimum_delta_pa: float
    maximum_delta_pa: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("pressure target name must be a non-empty string")
        if not isinstance(self.high_node, str) or not self.high_node.strip():
            raise ValueError(
                "pressure target high_node must be a non-empty string"
            )
        if not isinstance(self.low_node, str) or not self.low_node.strip():
            raise ValueError(
                "pressure target low_node must be a non-empty string"
            )
        if self.high_node == self.low_node:
            raise ValueError(
                "pressure target must reference two different nodes"
            )
        minimum = _finite(
            self.minimum_delta_pa,
            f"{self.name} minimum_delta_pa",
        )
        if minimum < 0.0:
            raise ValueError(
                f"{self.name} minimum_delta_pa must be >= 0"
            )
        object.__setattr__(self, "minimum_delta_pa", minimum)
        if self.maximum_delta_pa is not None:
            maximum = _finite(
                self.maximum_delta_pa,
                f"{self.name} maximum_delta_pa",
            )
            if maximum < minimum:
                raise ValueError(
                    f"{self.name} maximum_delta_pa must be "
                    ">= minimum_delta_pa"
                )
            object.__setattr__(self, "maximum_delta_pa", maximum)


@dataclass(frozen=True)
class RoomPressureNetwork:
    name: str
    nodes: tuple[PressureNode, ...]
    paths: tuple[PressurePath, ...]
    targets: tuple[PressureTarget, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError(
                "pressure-network name must be a non-empty string"
            )
        if len(self.nodes) < 2:
            raise ValueError(
                "pressure-network requires at least two nodes"
            )
        node_names = [node.name for node in self.nodes]
        if len(node_names) != len(set(node_names)):
            raise ValueError(
                "pressure-network node names must be unique"
            )
        node_set = set(node_names)
        fixed_nodes = {
            node.name
            for node in self.nodes
            if node.fixed_pressure_pa is not None
        }
        if not fixed_nodes:
            raise ValueError(
                "pressure-network requires at least one fixed-pressure node"
            )
        if not self.paths:
            raise ValueError(
                "pressure-network requires at least one pressure path"
            )
        path_names = [path.name for path in self.paths]
        if len(path_names) != len(set(path_names)):
            raise ValueError(
                "pressure-network path names must be unique"
            )
        for path in self.paths:
            if (
                path.start_node not in node_set
                or path.end_node not in node_set
            ):
                raise ValueError(
                    f"path {path.name!r} references a node "
                    "that is not configured"
                )

        target_names = [target.name for target in self.targets]
        if len(target_names) != len(set(target_names)):
            raise ValueError(
                "pressure target names must be unique"
            )
        for target in self.targets:
            if (
                target.high_node not in node_set
                or target.low_node not in node_set
            ):
                raise ValueError(
                    f"pressure target {target.name!r} references "
                    "an unknown node"
                )

        adjacency = {name: set() for name in node_names}
        for path in self.paths:
            adjacency[path.start_node].add(path.end_node)
            adjacency[path.end_node].add(path.start_node)
        visited = set(fixed_nodes)
        pending = list(fixed_nodes)
        while pending:
            node = pending.pop()
            for neighbor in adjacency[node]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    pending.append(neighbor)
        if visited != node_set:
            missing = ", ".join(sorted(node_set - visited))
            raise ValueError(
                "every pressure-network node must connect by pressure paths "
                "to a fixed-pressure boundary; unreachable: "
                + missing
            )


def _path_flow_and_derivative(
    path: PressurePath,
    start_pressure_pa: float,
    end_pressure_pa: float,
) -> tuple[float, float, float]:
    effective_delta_pa = _finite_result(
        start_pressure_pa
        - end_pressure_pa
        + path.pressure_offset_pa,
        f"{path.name} effective_pressure_difference_pa",
    )
    magnitude = abs(effective_delta_pa)
    transition = path.linearization_pressure_pa

    if path.model == "power_law":
        assert path.coefficient_m3_s_pa_n is not None
        assert path.exponent is not None
        coefficient = path.coefficient_m3_s_pa_n
        exponent = path.exponent
        if magnitude < transition:
            slope = _finite_result(
                coefficient * transition ** (exponent - 1.0),
                f"{path.name} local_flow_sensitivity_m3_s_pa",
            )
            flow = _finite_result(
                slope * effective_delta_pa,
                f"{path.name} airflow_m3_s",
            )
            return (
                flow,
                slope,
                effective_delta_pa,
            )
        flow = _finite_result(
            coefficient
            * math.copysign(
                magnitude**exponent,
                effective_delta_pa,
            ),
            f"{path.name} airflow_m3_s",
        )
        derivative = _finite_result(
            coefficient
            * exponent
            * magnitude ** (exponent - 1.0),
            f"{path.name} local_flow_sensitivity_m3_s_pa",
        )
        return flow, derivative, effective_delta_pa

    assert path.discharge_coefficient is not None
    assert path.area_m2 is not None
    density_factor = _finite_result(
        2.0 / path.air_density_kg_m3,
        f"{path.name} inverse_density_factor",
    )
    k = _finite_result(
        path.discharge_coefficient
        * path.area_m2
        * math.sqrt(density_factor),
        f"{path.name} orifice_flow_coefficient",
    )
    if magnitude < transition:
        slope = _finite_result(
            k / math.sqrt(transition),
            f"{path.name} local_flow_sensitivity_m3_s_pa",
        )
        flow = _finite_result(
            slope * effective_delta_pa,
            f"{path.name} airflow_m3_s",
        )
        return (
            flow,
            slope,
            effective_delta_pa,
        )
    flow = _finite_result(
        k
        * math.copysign(
            math.sqrt(magnitude),
            effective_delta_pa,
        ),
        f"{path.name} airflow_m3_s",
    )
    derivative = _finite_result(
        0.5 * k / math.sqrt(magnitude),
        f"{path.name} local_flow_sensitivity_m3_s_pa",
    )
    return flow, derivative, effective_delta_pa


def _solve_linear_system(
    matrix: list[list[float]],
    rhs: list[float],
) -> list[float]:
    size = len(rhs)
    if len(matrix) != size or any(len(row) != size for row in matrix):
        raise RuntimeError(
            "pressure-network Newton system dimensions are inconsistent"
        )
    augmented = [
        [
            _finite_result(
                value,
                f"Newton matrix row {row_index} column {column_index}",
            )
            for column_index, value in enumerate(row)
        ]
        + [
            _finite_result(
                rhs[row_index],
                f"Newton right-hand side row {row_index}",
            )
        ]
        for row_index, row in enumerate(matrix)
    ]

    for column in range(size):
        pivot = max(
            range(column, size),
            key=lambda row: abs(augmented[row][column]),
        )
        if abs(augmented[pivot][column]) < 1e-18:
            raise RuntimeError(
                "pressure-network Newton system became singular"
            )
        augmented[column], augmented[pivot] = (
            augmented[pivot],
            augmented[column],
        )

        for row in range(column + 1, size):
            factor = _finite_result(
                augmented[row][column]
                / augmented[column][column],
                f"Newton elimination factor row {row} column {column}",
            )
            if factor == 0.0:
                continue
            for item in range(column, size + 1):
                product = _finite_result(
                    factor * augmented[column][item],
                    (
                        "Newton elimination product "
                        f"row {row} column {item}"
                    ),
                )
                augmented[row][item] = _finite_result(
                    augmented[row][item] - product,
                    (
                        "Newton elimination state "
                        f"row {row} column {item}"
                    ),
                )

    solution = [0.0] * size
    for row in range(size - 1, -1, -1):
        products = [
            _finite_result(
                augmented[row][column] * solution[column],
                (
                    "Newton back-substitution product "
                    f"row {row} column {column}"
                ),
            )
            for column in range(row + 1, size)
        ]
        correction = _finite_sum(
            products,
            f"Newton back-substitution sum row {row}",
        )
        numerator = _finite_result(
            augmented[row][size] - correction,
            f"Newton back-substitution numerator row {row}",
        )
        solution[row] = _finite_result(
            numerator / augmented[row][row],
            f"Newton solution row {row}",
        )
    return solution


def solve_room_pressure_network(
    network: RoomPressureNetwork,
    *,
    mass_balance_tolerance_m3_h: float = 1e-6,
    max_iterations: int = 100,
) -> dict:
    tolerance_m3_h = _positive(
        mass_balance_tolerance_m3_h,
        "mass_balance_tolerance_m3_h",
    )
    if (
        isinstance(max_iterations, bool)
        or not isinstance(max_iterations, int)
        or max_iterations <= 0
    ):
        raise ValueError(
            "max_iterations must be an integer > 0"
        )

    unknown_nodes = tuple(
        node.name
        for node in network.nodes
        if node.fixed_pressure_pa is None
    )
    unknown_index = {
        name: index
        for index, name in enumerate(unknown_nodes)
    }
    fixed_pressures = [
        node.fixed_pressure_pa
        for node in network.nodes
        if node.fixed_pressure_pa is not None
    ]
    initial_pressure = _finite_sum(
        (
            pressure / len(fixed_pressures)
            for pressure in fixed_pressures
        ),
        "initial fixed-pressure average",
    )
    pressures = {
        node.name: (
            node.fixed_pressure_pa
            if node.fixed_pressure_pa is not None
            else initial_pressure
        )
        for node in network.nodes
    }
    mechanical_m3_s = {
        node.name: node.mechanical_injection_m3_h / 3600.0
        for node in network.nodes
    }
    tolerance_m3_s = tolerance_m3_h / 3600.0

    def evaluate(
        node_pressures: dict[str, float],
    ) -> tuple[
        dict[str, float],
        list[float],
        list[float],
        list[float],
    ]:
        residuals = dict(mechanical_m3_s)
        flows: list[float] = []
        derivatives: list[float] = []
        effective_deltas: list[float] = []
        for path in network.paths:
            flow, derivative, effective_delta = (
                _path_flow_and_derivative(
                    path,
                    node_pressures[path.start_node],
                    node_pressures[path.end_node],
                )
            )
            flows.append(flow)
            derivatives.append(derivative)
            effective_deltas.append(effective_delta)
            residuals[path.start_node] = _finite_result(
                residuals[path.start_node] - flow,
                f"{path.start_node} mass-balance residual",
            )
            residuals[path.end_node] = _finite_result(
                residuals[path.end_node] + flow,
                f"{path.end_node} mass-balance residual",
            )
        return (
            residuals,
            flows,
            derivatives,
            effective_deltas,
        )

    iterations = 0
    while True:
        (
            residuals,
            flows,
            derivatives,
            effective_deltas,
        ) = evaluate(pressures)
        max_unknown_residual = max(
            (
                abs(residuals[name])
                for name in unknown_nodes
            ),
            default=0.0,
        )
        if max_unknown_residual <= tolerance_m3_s:
            break
        if iterations >= max_iterations:
            raise RuntimeError(
                "pressure-network solver did not converge "
                "within max_iterations"
            )

        size = len(unknown_nodes)
        jacobian = [
            [0.0 for _ in range(size)]
            for _ in range(size)
        ]
        for path, derivative in zip(
            network.paths,
            derivatives,
        ):
            start_index = unknown_index.get(path.start_node)
            end_index = unknown_index.get(path.end_node)
            if start_index is not None:
                jacobian[start_index][start_index] = _finite_result(
                    jacobian[start_index][start_index] - derivative,
                    (
                        "Newton Jacobian diagonal for "
                        f"{path.start_node}"
                    ),
                )
                if end_index is not None:
                    jacobian[start_index][end_index] = _finite_result(
                        jacobian[start_index][end_index] + derivative,
                        (
                            "Newton Jacobian coupling "
                            f"{path.start_node}->{path.end_node}"
                        ),
                    )
            if end_index is not None:
                if start_index is not None:
                    jacobian[end_index][start_index] = _finite_result(
                        jacobian[end_index][start_index] + derivative,
                        (
                            "Newton Jacobian coupling "
                            f"{path.end_node}->{path.start_node}"
                        ),
                    )
                jacobian[end_index][end_index] = _finite_result(
                    jacobian[end_index][end_index] - derivative,
                    (
                        "Newton Jacobian diagonal for "
                        f"{path.end_node}"
                    ),
                )

        step = _solve_linear_system(
            jacobian,
            [
                -residuals[name]
                for name in unknown_nodes
            ],
        )
        baseline = max_unknown_residual
        scale = 1.0
        accepted = False
        while scale >= 2.0**-20:
            candidate = dict(pressures)
            candidate_is_finite = True
            for name, delta in zip(
                unknown_nodes,
                step,
            ):
                candidate_pressure = (
                    pressures[name] + scale * delta
                )
                if not math.isfinite(candidate_pressure):
                    candidate_is_finite = False
                    break
                candidate[name] = candidate_pressure
            if not candidate_is_finite:
                scale *= 0.5
                continue
            try:
                candidate_residuals, *_ = evaluate(candidate)
            except _PressureNetworkNumericalError:
                scale *= 0.5
                continue
            candidate_norm = max(
                (
                    abs(candidate_residuals[name])
                    for name in unknown_nodes
                ),
                default=0.0,
            )
            if candidate_norm < baseline:
                pressures = candidate
                accepted = True
                break
            scale *= 0.5

        if not accepted:
            raise RuntimeError(
                "pressure-network Newton line search failed "
                "to reduce mass-balance residual"
            )
        iterations += 1

    (
        residuals,
        flows,
        derivatives,
        effective_deltas,
    ) = evaluate(pressures)

    incident: dict[
        str,
        list[tuple[PressurePath, float]],
    ] = {
        node.name: []
        for node in network.nodes
    }
    for path, flow in zip(network.paths, flows):
        incident[path.start_node].append((path, flow))
        incident[path.end_node].append((path, -flow))

    node_results = []
    for node in network.nodes:
        residual_m3_h = _finite_result(
            residuals[node.name] * 3600.0,
            f"{node.name} mass_balance_residual_m3_h",
        )
        dominant = None
        if incident[node.name]:
            dominant_path, room_outward_flow = max(
                incident[node.name],
                key=lambda item: abs(item[1]),
            )
            dominant_airflow_m3_h = _finite_result(
                abs(room_outward_flow) * 3600.0,
                (
                    f"{node.name} dominant pressure-path "
                    "airflow_m3_h"
                ),
            )
            dominant = {
                "path": dominant_path.name,
                "airflow_m3_h": round(
                    dominant_airflow_m3_h,
                    6,
                ),
                "direction": (
                    "zero flow"
                    if room_outward_flow == 0.0
                    else (
                        "outflow"
                        if room_outward_flow > 0.0
                        else "inflow"
                    )
                ),
            }

        item = {
            "name": node.name,
            "pressure_pa": round(
                pressures[node.name],
                9,
            ),
            "fixed_pressure": (
                node.fixed_pressure_pa is not None
            ),
            "supply_m3_h": round(
                node.supply_m3_h,
                6,
            ),
            "return_m3_h": round(
                node.return_m3_h,
                6,
            ),
            "exhaust_m3_h": round(
                node.exhaust_m3_h,
                6,
            ),
            "mechanical_injection_m3_h": round(
                node.mechanical_injection_m3_h,
                6,
            ),
            "dominant_pressure_path": dominant,
        }
        if node.fixed_pressure_pa is None:
            item["mass_balance_residual_m3_h"] = round(
                residual_m3_h,
                12,
            )
        else:
            item["required_external_balance_m3_h"] = round(
                -residual_m3_h,
                6,
            )
        node_results.append(item)

    path_results = []
    for (
        path,
        flow,
        derivative,
        effective_delta,
    ) in zip(
        network.paths,
        flows,
        derivatives,
        effective_deltas,
    ):
        if flow > 0.0:
            direction = (
                f"{path.start_node} -> {path.end_node}"
            )
        elif flow < 0.0:
            direction = (
                f"{path.end_node} -> {path.start_node}"
            )
        else:
            direction = "zero flow"

        airflow_m3_h = _finite_result(
            flow * 3600.0,
            f"{path.name} airflow_m3_h",
        )
        pressure_difference_pa = _finite_result(
            pressures[path.start_node] - pressures[path.end_node],
            f"{path.name} pressure_difference_pa",
        )

        path_results.append(
            {
                "name": path.name,
                "kind": path.kind,
                "model": path.model,
                "start_node": path.start_node,
                "end_node": path.end_node,
                "pressure_difference_pa": round(
                    pressure_difference_pa,
                    9,
                ),
                "pressure_offset_pa": round(
                    path.pressure_offset_pa,
                    9,
                ),
                "effective_pressure_difference_pa": round(
                    effective_delta,
                    9,
                ),
                "airflow_m3_s": round(flow, 12),
                "airflow_m3_h": round(
                    airflow_m3_h,
                    6,
                ),
                "flow_direction": direction,
                "local_flow_sensitivity_m3_s_pa": round(
                    derivative,
                    12,
                ),
                "linearization_pressure_pa": round(
                    path.linearization_pressure_pa,
                    9,
                ),
                "parameters": (
                    {
                        "coefficient_m3_s_pa_n": (
                            path.coefficient_m3_s_pa_n
                        ),
                        "exponent": path.exponent,
                    }
                    if path.model == "power_law"
                    else {
                        "discharge_coefficient": (
                            path.discharge_coefficient
                        ),
                        "area_m2": path.area_m2,
                        "air_density_kg_m3": (
                            path.air_density_kg_m3
                        ),
                    }
                ),
            }
        )

    target_results = []
    for target in network.targets:
        delta = _finite_result(
            pressures[target.high_node]
            - pressures[target.low_node],
            f"{target.name} observed_delta_pa",
        )
        minimum_ok = (
            delta >= target.minimum_delta_pa
        )
        maximum_ok = (
            target.maximum_delta_pa is None
            or delta <= target.maximum_delta_pa
        )
        passed = minimum_ok and maximum_ok
        minimum_margin_pa = _finite_result(
            delta - target.minimum_delta_pa,
            f"{target.name} minimum_margin_pa",
        )
        maximum_margin_pa = (
            None
            if target.maximum_delta_pa is None
            else _finite_result(
                target.maximum_delta_pa - delta,
                f"{target.name} maximum_margin_pa",
            )
        )
        target_results.append(
            {
                "name": target.name,
                "high_node": target.high_node,
                "low_node": target.low_node,
                "observed_delta_pa": round(delta, 9),
                "minimum_delta_pa": (
                    target.minimum_delta_pa
                ),
                "maximum_delta_pa": (
                    target.maximum_delta_pa
                ),
                "status": (
                    "pass" if passed else "fail"
                ),
                "minimum_margin_pa": round(
                    minimum_margin_pa,
                    9,
                ),
                "maximum_margin_pa": (
                    None
                    if maximum_margin_pa is None
                    else round(
                        maximum_margin_pa,
                        9,
                    )
                ),
            }
        )

    failed_targets = [
        item["name"]
        for item in target_results
        if item["status"] != "pass"
    ]
    max_residual_m3_h = max(
        (
            _finite_result(
                abs(residuals[name] * 3600.0),
                f"{name} absolute mass_balance_residual_m3_h",
            )
            for name in unknown_nodes
        ),
        default=0.0,
    )
    total_supply = _finite_sum(
        (node.supply_m3_h for node in network.nodes),
        "total supply_m3_h",
    )
    total_return = _finite_sum(
        (node.return_m3_h for node in network.nodes),
        "total return_m3_h",
    )
    total_exhaust = _finite_sum(
        (node.exhaust_m3_h for node in network.nodes),
        "total exhaust_m3_h",
    )
    net_injection = _finite_result(
        total_supply - total_return - total_exhaust,
        "total mechanical net_injection_m3_h",
    )

    return {
        "network": network.name,
        "status": (
            "solved"
            if not failed_targets
            else "solved_with_target_violations"
        ),
        "solver": {
            "method": "damped_newton",
            "iterations": iterations,
            "max_iterations": max_iterations,
            "mass_balance_tolerance_m3_h": (
                tolerance_m3_h
            ),
            (
                "max_abs_unknown_node_"
                "mass_balance_residual_m3_h"
            ): round(
                max_residual_m3_h,
                12,
            ),
        },
        "mechanical_airflow_totals_m3_h": {
            "supply": round(total_supply, 6),
            "return": round(total_return, 6),
            "exhaust": round(total_exhaust, 6),
            "net_injection": round(
                net_injection,
                6,
            ),
        },
        "nodes": node_results,
        "paths": path_results,
        "targets": target_results,
        "target_summary": {
            "configured": len(target_results),
            "passed": (
                len(target_results)
                - len(failed_targets)
            ),
            "failed": len(failed_targets),
            "failed_targets": failed_targets,
        },
        "scope_note": (
            "Steady-state multizone pressure screening "
            "using explicit pressure-flow paths and "
            "mechanical supply/return/exhaust inputs. "
            "Power-law paths use "
            "Q=C*sign(dP)*abs(dP)^n and orifice paths "
            "use Q=Cd*A*sign(dP)*sqrt(2*abs(dP)/rho), "
            "with a reported linear near-zero "
            "regularization below each path's configured "
            "transition pressure. Path pressure offsets "
            "are explicit inputs. This model does not "
            "infer leakage coefficients, opening areas, "
            "wind, stack effect, door-event transients, "
            "or certification compliance."
        ),
    }
