# Looped airflow-network solver

CleanroomX v0.25 retains the steady-state pressure-node solver for connected networks with arbitrary loops and adds auditable derivation of fixed edge resistance from explicit duct geometry.

## Model

Every edge uses an explicit fixed quadratic resistance:

    deltaP = R * Q * abs(Q)

where:

- deltaP is the pressure difference from the declared start node to the declared end node in Pa;
- Q is signed airflow in m3/s;
- R is a user-supplied fixed resistance in Pa/(m3/s)^2.

Positive node injection means airflow enters the network at that node. Negative injection means airflow leaves the network. The complete set of node injections must balance to zero.

One node is selected as the pressure reference and reported as 0 Pa. All other node pressures are relative to that reference; changing the reference changes only the pressure offset, not solved edge flows.

## Numerical method

CleanroomX:

1. validates a connected graph, unique edge names, positive finite resistances, and balanced node injections;
2. constructs a spanning-tree pressure estimate that satisfies the specified injections on that tree;
3. solves the nonlinear node-continuity equations with a damped Newton method;
4. reports node mass-balance residuals and edge pressure-law residuals.

The edge direction in the input is only the positive sign convention. A solved negative airflow is valid and is reported with its actual physical direction.

## Resistance input

Each edge must use exactly one resistance source:

- `resistance_pa_per_m3_s_squared` for an explicitly supplied fixed resistance; or
- `duct_geometry` to derive a fixed resistance from Darcy-Weisbach straight-duct friction plus an explicit local-loss coefficient.

With an explicit Darcy factor, no reference airflow is needed because the factor is already fixed. For automatic friction, `absolute_roughness_m`, `kinematic_viscosity_m2_s`, and `reference_airflow_m3_h` are all required. CleanroomX resolves the Darcy factor once at that reference airflow and then holds the derived resistance fixed during loop solving.

The derived fixed quadratic coefficient is

    R = 0.5 * rho * (f * L / Dh + K) / A^2

so that `deltaP = R * Q * abs(Q)`.

## Example

Explicit-resistance network:

    cleanroomx-loop-flow examples/looped_network_demo.json

Geometry-derived fixed-resistance network:

    cleanroomx-loop-flow examples/looped_network_geometry_demo.json

JSON output:

    cleanroomx-loop-flow examples/looped_network_demo.json --format json

Write a Markdown report:

    cleanroomx-loop-flow examples/looped_network_demo.json --output looped-network-report.md

Optional numerical controls:

    cleanroomx-loop-flow examples/looped_network_demo.json --mass-balance-tolerance-m3-h 1e-6 --max-iterations 100

## Scope boundary

This remains a fixed-resistance steady-state network solver. v0.25 can derive that fixed resistance from explicit geometry, density, Darcy factor, and local-loss coefficient. Automatic friction is resolved only at an explicit reference airflow and is not iterated as solved loop flow changes.

The workflow does not infer fitting coefficients, damper positions, controls, leakage, fan curves, fan/system operating points, density changes, compressibility, or transient behavior. It does not replace detailed HVAC network design or commissioning.
