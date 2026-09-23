from __future__ import annotations

import math
from dataclasses import dataclass

from .friction import resolve_darcy_friction_factor


def _positive(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field_name} must be finite and > 0")
    return value


def _nonnegative(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{field_name} must be finite and >= 0")
    return value


@dataclass(frozen=True)
class LoopedDuctResistanceInput:
    """Geometry used to derive one fixed quadratic loop-edge resistance."""

    length_m: float
    air_density_kg_m3: float
    friction_factor: float | None = None
    local_loss_coefficient: float = 0.0
    diameter_m: float | None = None
    width_m: float | None = None
    height_m: float | None = None
    absolute_roughness_m: float | None = None
    kinematic_viscosity_m2_s: float | None = None
    reference_airflow_m3_h: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "length_m", _nonnegative(self.length_m, "length_m"))
        object.__setattr__(
            self,
            "air_density_kg_m3",
            _positive(self.air_density_kg_m3, "air_density_kg_m3"),
        )
        object.__setattr__(
            self,
            "local_loss_coefficient",
            _nonnegative(self.local_loss_coefficient, "local_loss_coefficient"),
        )

        circular = self.diameter_m is not None
        rectangular = self.width_m is not None or self.height_m is not None
        if circular == rectangular:
            raise ValueError(
                "provide either diameter_m or both width_m and height_m, but not both"
            )
        if circular:
            object.__setattr__(
                self, "diameter_m", _positive(self.diameter_m, "diameter_m")
            )
        else:
            if self.width_m is None or self.height_m is None:
                raise ValueError("rectangular duct requires both width_m and height_m")
            object.__setattr__(self, "width_m", _positive(self.width_m, "width_m"))
            object.__setattr__(
                self, "height_m", _positive(self.height_m, "height_m")
            )

        if self.length_m == 0.0 and self.local_loss_coefficient == 0.0:
            raise ValueError(
                "duct geometry must have positive length_m or local_loss_coefficient"
            )

        auto_fields = (
            self.absolute_roughness_m,
            self.kinematic_viscosity_m2_s,
            self.reference_airflow_m3_h,
        )
        if self.friction_factor is not None:
            object.__setattr__(
                self,
                "friction_factor",
                _nonnegative(self.friction_factor, "friction_factor"),
            )
            if any(value is not None for value in auto_fields):
                raise ValueError(
                    "provide either friction_factor or automatic-friction inputs "
                    "(absolute_roughness_m, kinematic_viscosity_m2_s, "
                    "reference_airflow_m3_h), not both"
                )
        else:
            if any(value is None for value in auto_fields):
                raise ValueError(
                    "automatic friction requires absolute_roughness_m, "
                    "kinematic_viscosity_m2_s, and reference_airflow_m3_h"
                )
            object.__setattr__(
                self,
                "absolute_roughness_m",
                _nonnegative(self.absolute_roughness_m, "absolute_roughness_m"),
            )
            object.__setattr__(
                self,
                "kinematic_viscosity_m2_s",
                _positive(
                    self.kinematic_viscosity_m2_s,
                    "kinematic_viscosity_m2_s",
                ),
            )
            object.__setattr__(
                self,
                "reference_airflow_m3_h",
                _positive(self.reference_airflow_m3_h, "reference_airflow_m3_h"),
            )
            if self.absolute_roughness_m >= self.hydraulic_diameter_m:
                raise ValueError(
                    "absolute_roughness_m must be smaller than hydraulic diameter"
                )

    @property
    def shape(self) -> str:
        return "circular" if self.diameter_m is not None else "rectangular"

    @property
    def area_m2(self) -> float:
        if self.diameter_m is not None:
            return math.pi * self.diameter_m**2 / 4.0
        assert self.width_m is not None and self.height_m is not None
        return self.width_m * self.height_m

    @property
    def hydraulic_diameter_m(self) -> float:
        if self.diameter_m is not None:
            return self.diameter_m
        assert self.width_m is not None and self.height_m is not None
        return 2.0 * self.width_m * self.height_m / (
            self.width_m + self.height_m
        )


def derive_loop_edge_resistance(spec: LoopedDuctResistanceInput) -> dict:
    """Derive fixed R in deltaP = R*Q*abs(Q) from explicit duct geometry."""

    if spec.friction_factor is not None:
        friction_factor = spec.friction_factor
        friction_method = "user_input"
        reynolds = None
        relative_roughness = None
    else:
        assert spec.reference_airflow_m3_h is not None
        assert spec.kinematic_viscosity_m2_s is not None
        assert spec.absolute_roughness_m is not None
        reference_airflow_m3_s = spec.reference_airflow_m3_h / 3600.0
        velocity_m_s = reference_airflow_m3_s / spec.area_m2
        friction = resolve_darcy_friction_factor(
            velocity_m_s=velocity_m_s,
            hydraulic_diameter_m=spec.hydraulic_diameter_m,
            kinematic_viscosity_m2_s=spec.kinematic_viscosity_m2_s,
            absolute_roughness_m=spec.absolute_roughness_m,
            circular_geometry=spec.shape == "circular",
        )
        friction_factor = friction["friction_factor"]
        friction_method = friction["method"]
        reynolds = friction["reynolds_number"]
        relative_roughness = friction["relative_roughness"]

    loss_coefficient = (
        friction_factor * spec.length_m / spec.hydraulic_diameter_m
        + spec.local_loss_coefficient
    )
    if loss_coefficient <= 0.0:
        raise ValueError(
            "derived loop-edge resistance must be > 0; "
            "increase friction/local loss inputs"
        )

    resistance = (
        0.5
        * spec.air_density_kg_m3
        * loss_coefficient
        / spec.area_m2**2
    )
    return {
        "resistance_pa_per_m3_s_squared": resistance,
        "basis": "duct_geometry",
        "shape": spec.shape,
        "length_m": spec.length_m,
        "diameter_m": spec.diameter_m,
        "width_m": spec.width_m,
        "height_m": spec.height_m,
        "area_m2": spec.area_m2,
        "hydraulic_diameter_m": spec.hydraulic_diameter_m,
        "air_density_kg_m3": spec.air_density_kg_m3,
        "friction_factor": friction_factor,
        "friction_factor_method": friction_method,
        "local_loss_coefficient": spec.local_loss_coefficient,
        "combined_loss_coefficient": loss_coefficient,
        "reference_airflow_m3_h": spec.reference_airflow_m3_h,
        "reynolds_number": reynolds,
        "absolute_roughness_m": spec.absolute_roughness_m,
        "relative_roughness": relative_roughness,
        "kinematic_viscosity_m2_s": spec.kinematic_viscosity_m2_s,
    }
