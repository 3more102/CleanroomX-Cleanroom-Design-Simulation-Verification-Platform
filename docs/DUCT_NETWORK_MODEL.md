# Duct critical-path pressure-loss model

CleanroomX v0.6 adds a transparent, path-based duct pressure-loss calculation for preliminary cleanroom HVAC design. v0.6.1 hardens numeric validation so non-finite inputs are rejected before analysis. v0.19 adds an optional Reynolds/roughness-based Darcy friction-factor calculation while preserving the original explicit-factor workflow.

## Section calculation

Each duct section requires explicit project inputs for:

- airflow;
- air density;
- length;
- geometry: circular diameter, or rectangular width and height;
- sum of local fitting/equipment loss coefficients referenced to that section velocity;
- either an explicit Darcy friction factor, or both absolute roughness and kinematic viscosity for automatic friction-factor resolution.

The section velocity is calculated from volumetric flow and area. Velocity pressure is:

    q = 0.5 * rho * V^2

Straight-duct friction is calculated with Darcy-Weisbach:

    delta_p_f = f * (L / D_h) * q

Local losses are:

    delta_p_local = sum(K) * q

The section total is the sum of friction and local pressure losses.

For rectangular ducts, CleanroomX uses hydraulic diameter:

    D_h = 4A / P = 2ab / (a + b)

For circular ducts, hydraulic diameter equals the inside diameter.

## Path and network calculation

A duct path is a user-defined series of sections. CleanroomX sums section losses in each path and identifies the path with the largest calculated loss as the critical path.

When a duct network is present in an HVAC project, its critical-path pressure drop replaces the manually entered duct-pressure-drop component for preliminary supply-fan power sizing. Other fan components such as coil, terminal-filter, and explicitly entered miscellaneous pressure drops remain separate.

This is intentionally a **critical-path comparison**, not a full nonlinear airflow-network solver. Branch flow distribution is not inferred.

## Input validation

All numeric duct inputs must be finite. Positive quantities such as airflow, air density, and duct dimensions must also be greater than zero. Length, Darcy friction factor, and local loss coefficient may be zero where physically intentional, subject to the section requiring a nonzero friction length or local loss.

Rejecting `NaN` and positive/negative infinity prevents invalid pressure-loss values from silently propagating into the fan-duty calculation.

## v0.19 automatic friction-factor option

The original explicit `friction_factor` field remains supported. As an alternative, JSON inputs may omit it and provide:

    "absolute_roughness_m": 0.00009,
    "kinematic_viscosity_m2_s": 0.000015

CleanroomX then evaluates:

    Re = V * D_h / nu

For circular laminar flow with `Re < 2300`, it uses the Darcy relation:

    f = 64 / Re

For `Re >= 2300`, it solves the Colebrook equation iteratively using Reynolds number and relative roughness `epsilon / D_h`. Rectangular ducts use hydraulic diameter in the turbulent calculation.

Automatic laminar friction for noncircular ducts is deliberately rejected. The circular `64/Re` relation is not blindly applied to rectangular geometry because laminar noncircular friction depends on cross-sectional shape. Supply an explicit Darcy factor for that case.

Manual and automatic friction inputs are mutually exclusive so the calculation basis is auditable.

## Engineering boundaries

- Automatic friction uses only the supplied roughness, kinematic viscosity, section geometry, and section airflow; CleanroomX does not invent material roughness or fluid properties.
- The path and fixed-demand-tree models evaluate friction at their known section flow. The reference-flow fan/duct integration evaluates it at the declared reference flow and then holds the resolved factor constant while scaling its quadratic system curve.
- The passive parallel-flow solvers remain fixed-resistance models and continue to require explicit friction factors; v0.19 does not implement nonlinear variable-friction pressure balancing.
- Fitting loss coefficients are explicit inputs. Use project/manufacturer data or an applicable licensed fitting database.
- The model does not determine fan operating point, system effect, duct leakage, noise, balancing-damper position, control behavior, redundancy, or commissioning acceptance.
- The calculation is preliminary engineering screening and does not replace detailed duct design or qualified engineering review.

## References

- ASHRAE Handbook—Fundamentals, Chapter 21, Duct Design: Darcy friction, hydraulic diameter, dynamic losses, and combined sectional losses.
- ASHRAE Duct Fitting Database / Standard 120 resources for fitting resistance and loss-coefficient testing.

Use the current applicable licensed standard, project specification, local regulations, and manufacturer data for real projects.


## v0.8 branch-flow extension

For automatic flow propagation through a fixed-demand directed supply tree, see `docs/BRANCH_FLOW_NETWORK.md`. The original `duct_network` path-comparison model remains available for backward compatibility and for cases where each path airflow is already known.
