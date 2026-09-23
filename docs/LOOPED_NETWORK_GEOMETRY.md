# Geometry-derived loop-edge resistance

CleanroomX v0.24 adds an optional geometry-to-resistance layer for the v0.23 fixed-resistance looped airflow solver.

## Model boundary

The underlying loop solver still uses the fixed quadratic edge law:

    deltaP = R * Q * abs(Q)

v0.24 can derive each edge resistance `R` from one or more series duct sections using explicit:

- circular or rectangular geometry;
- section length;
- air density;
- local loss coefficient;
- either a supplied Darcy friction factor or explicit absolute roughness plus kinematic viscosity;
- one positive reference airflow shared by all series sections in the same graph edge.

For each section:

    R_section = 0.5 * rho * (f * L / Dh + K) / A^2

Series-section resistances are summed to form the graph-edge resistance.

## Automatic Darcy friction

When `friction_factor` is omitted, the existing automatic-friction workflow resolves it from the section's explicit reference airflow, geometry, roughness, and kinematic viscosity. The resolved factor is then **frozen** while the loop solver balances the network.

This is deliberate. v0.24 does not iterate Reynolds number or Darcy friction factor as solved loop airflow changes.

## Reference airflow

Every section belonging to one graph edge must use the same `airflow_m3_h`. That value is the explicit reference airflow for the resistance derivation. It is not a constraint on the solved airflow.

The report preserves:

- reference airflow;
- section geometry;
- resolved friction factor and method;
- Reynolds number when calculated;
- section quadratic resistance;
- section reference pressure drop;
- summed edge resistance and reference pressure drop;
- solved loop airflow, pressure difference, and residuals.

## CLI

    cleanroomx-loop-duct examples/looped_network_geometry_demo.json

JSON output:

    cleanroomx-loop-duct examples/looped_network_geometry_demo.json --format json

Markdown output to a file:

    cleanroomx-loop-duct examples/looped_network_geometry_demo.json --output loop-duct-report.md

## Scope limits

This workflow does not infer material roughness, air viscosity, fitting coefficients, edge reference airflow, dampers, leakage, controls, fan curves, compressibility, or transient behavior. It does not iterate friction factor with the solved loop flow and does not replace detailed HVAC network design, CFD, commissioning, or qualified engineering review.
