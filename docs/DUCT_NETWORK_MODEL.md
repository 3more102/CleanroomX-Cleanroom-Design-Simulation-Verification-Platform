# Duct critical-path pressure-loss model

CleanroomX v0.6 adds a transparent, path-based duct pressure-loss calculation for preliminary cleanroom HVAC design. v0.6.1 hardens numeric validation so non-finite inputs are rejected before analysis.

## Section calculation

Each duct section requires explicit project inputs for:

- airflow;
- air density;
- Darcy friction factor;
- length;
- geometry: circular diameter, or rectangular width and height;
- sum of local fitting/equipment loss coefficients referenced to that section velocity.

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

## Engineering boundaries

- Friction factor is an explicit input. CleanroomX does not infer roughness, Reynolds number, or a Colebrook solution in v0.6.
- Fitting loss coefficients are explicit inputs. Use project/manufacturer data or an applicable licensed fitting database.
- The model does not determine fan operating point, system effect, duct leakage, noise, balancing-damper position, control behavior, redundancy, or commissioning acceptance.
- The calculation is preliminary engineering screening and does not replace detailed duct design or qualified engineering review.

## References

- ASHRAE Handbook—Fundamentals, Chapter 21, Duct Design: Darcy friction, hydraulic diameter, dynamic losses, and combined sectional losses.
- ASHRAE Duct Fitting Database / Standard 120 resources for fitting resistance and loss-coefficient testing.

Use the current applicable licensed standard, project specification, local regulations, and manufacturer data for real projects.


## v0.8 branch-flow extension

For automatic flow propagation through a fixed-demand directed supply tree, see `docs/BRANCH_FLOW_NETWORK.md`. The original `duct_network` path-comparison model remains available for backward compatibility and for cases where each path airflow is already known.
