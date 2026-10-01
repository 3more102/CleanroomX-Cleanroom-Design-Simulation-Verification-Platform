from __future__ import annotations

import math


# KSC-STD-Z-0017 Rev A section 7.4.1 identifies circular-pipe laminar
# flow at Re < 2000 and the Colebrook turbulent region at Re > 4000.
# Automatic resolution therefore fails closed between those regimes.
LAMINAR_REYNOLDS_LIMIT = 2000.0
TURBULENT_REYNOLDS_LIMIT = 4000.0


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


def reynolds_number(
    velocity_m_s: float,
    hydraulic_diameter_m: float,
    kinematic_viscosity_m2_s: float,
) -> float:
    velocity = _positive(velocity_m_s, "velocity_m_s")
    hydraulic_diameter = _positive(
        hydraulic_diameter_m, "hydraulic_diameter_m"
    )
    kinematic_viscosity = _positive(
        kinematic_viscosity_m2_s, "kinematic_viscosity_m2_s"
    )
    return velocity * hydraulic_diameter / kinematic_viscosity


def colebrook_darcy_friction_factor(
    reynolds: float,
    relative_roughness: float,
) -> float:
    reynolds = _positive(reynolds, "reynolds_number")
    relative_roughness = _nonnegative(
        relative_roughness, "relative_roughness"
    )
    if reynolds <= TURBULENT_REYNOLDS_LIMIT:
        raise ValueError(
            "Colebrook friction factor is applied only for turbulent "
            "Reynolds number > 4000"
        )
    if relative_roughness >= 1:
        raise ValueError("relative_roughness must be < 1")

    # Solve in x = 1/sqrt(f):
    # x = -2 log10(epsilon/(3.7 D) + 2.51 x / Re)
    def residual(x: float) -> float:
        return x + 2.0 * math.log10(
            relative_roughness / 3.7 + 2.51 * x / reynolds
        )

    low = 1.0
    high = 100.0
    low_residual = residual(low)
    high_residual = residual(high)
    if low_residual > 0 or high_residual < 0:
        raise ValueError("could not bracket Colebrook friction-factor solution")

    for _ in range(100):
        midpoint = 0.5 * (low + high)
        value = residual(midpoint)
        if abs(value) <= 1e-12:
            low = high = midpoint
            break
        if value > 0:
            high = midpoint
        else:
            low = midpoint

    inverse_sqrt_f = 0.5 * (low + high)
    return 1.0 / inverse_sqrt_f**2


def resolve_darcy_friction_factor(
    *,
    velocity_m_s: float,
    hydraulic_diameter_m: float,
    kinematic_viscosity_m2_s: float,
    absolute_roughness_m: float,
    circular_geometry: bool,
) -> dict:
    reynolds = reynolds_number(
        velocity_m_s,
        hydraulic_diameter_m,
        kinematic_viscosity_m2_s,
    )
    roughness = _nonnegative(absolute_roughness_m, "absolute_roughness_m")
    hydraulic_diameter = _positive(
        hydraulic_diameter_m, "hydraulic_diameter_m"
    )
    if roughness >= hydraulic_diameter:
        raise ValueError("absolute_roughness_m must be smaller than hydraulic diameter")

    relative_roughness = roughness / hydraulic_diameter
    if reynolds < LAMINAR_REYNOLDS_LIMIT:
        if not circular_geometry:
            raise ValueError(
                "automatic laminar friction is supported only for circular ducts; "
                "provide an explicit friction_factor for noncircular laminar flow"
            )
        friction_factor = 64.0 / reynolds
        method = "laminar_64_over_re"
    elif reynolds <= TURBULENT_REYNOLDS_LIMIT:
        raise ValueError(
            "automatic Darcy friction is indeterminate in the transition region "
            "2000 <= Re <= 4000; provide an explicit friction_factor or a "
            "project-qualified transition correlation"
        )
    else:
        friction_factor = colebrook_darcy_friction_factor(
            reynolds, relative_roughness
        )
        method = "colebrook"

    return {
        "friction_factor": friction_factor,
        "method": method,
        "reynolds_number": reynolds,
        "absolute_roughness_m": roughness,
        "relative_roughness": relative_roughness,
        "kinematic_viscosity_m2_s": float(kinematic_viscosity_m2_s),
    }
