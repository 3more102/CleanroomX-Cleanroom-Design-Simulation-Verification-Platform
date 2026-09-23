# Duct-network pressure-loss model

CleanroomX v0.5 adds a transparent preliminary supply-duct pressure-loss model that can feed the existing supply-fan sizing calculation.

## Section model

Each duct section is described by explicit project inputs: airflow, cross-sectional area, hydraulic diameter, length, air density, Darcy friction factor, summed minor-loss coefficient (K), and optional fixed pressure drop.

Velocity:

    v = Q / A

Velocity pressure:

    q = rho * v^2 / 2

Darcy-Weisbach friction loss:

    delta_p_f = f * (L / D_h) * q

Minor loss:

    delta_p_m = K * q

Section total:

    delta_p_section = delta_p_f + delta_p_m + delta_p_fixed

CleanroomX deliberately requires the Darcy friction factor and K values as project inputs. It does not infer duct roughness, Reynolds number, fitting coefficients, or proprietary manufacturer losses.

## Paths and critical path

A duct path is an ordered list of sections from the fan toward a terminal branch. Shared upstream sections may appear in more than one path when the user describes multiple terminal routes.

For each path:

    delta_p_path = sum(delta_p_section)

The path with the largest calculated loss is reported as the critical path. When a supply fan is configured, this critical-path loss is added to the existing entered duct-pressure allowance, coil pressure drop, terminal-filter pressure drop, and other entered losses.

The legacy `fan_system.duct_pressure_drop_pa` field remains supported. With a duct network present, it is treated as an additional entered duct allowance so the calculation stays explicit and backward compatible.

## Limits

This model is a preliminary steady-state pressure-loss budget, not a final duct design or fan-selection tool. It does not currently solve a flow-distribution network, calculate Reynolds-dependent friction factor, model leakage, acoustic criteria, fire/smoke requirements, system effect, balancing-device authority, velocity-pressure recovery, dirty-filter allowance, fan curves, VFD operating points, or redundancy.

Use project specifications, applicable codes and standards, manufacturer data, and qualified HVAC/cleanroom engineering review for real designs.
