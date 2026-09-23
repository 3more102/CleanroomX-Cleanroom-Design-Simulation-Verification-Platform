# Geometry-derived looped duct networks

CleanroomX v0.24 extends the fixed-resistance looped airflow solver by deriving each edge resistance from explicit duct geometry and fixed engineering inputs.

## Fixed-resistance derivation

For every section:

    R_section = rho / (2 A^2) * (f L / Dh + K)

and:

    deltaP = R_section * Q * abs(Q)

where:

- rho is the explicit air density;
- A is duct cross-sectional area;
- f is an explicit fixed Darcy friction factor;
- L is section length;
- Dh is hydraulic diameter;
- K is the explicit summed local-loss coefficient;
- Q is signed airflow.

Sections in series are summed to obtain the loop edge resistance. Circular and rectangular geometry are supported.

## Why friction factor is explicit

The loop solver determines airflow. Therefore a friction factor calculated from Reynolds number would itself depend on the unknown airflow and would require a coupled nonlinear friction iteration. v0.24 deliberately does not hide that extra model inside a fixed-resistance solve.

Use an explicit fixed Darcy friction factor for every section. Inputs such as absolute roughness and kinematic viscosity are rejected by this workflow rather than being silently interpreted.

## Run

    cleanroomx-loop-duct examples/looped_duct_geometry_demo.json

JSON output:

    cleanroomx-loop-duct examples/looped_duct_geometry_demo.json --format json

Markdown report:

    cleanroomx-loop-duct examples/looped_duct_geometry_demo.json --output looped-duct-report.md

The report preserves node-continuity and edge pressure-law residuals from the v0.23 solver and adds section geometry, derived resistance, solved velocity, Darcy friction loss, local loss, and a geometry pressure residual.

## Scope boundary

This workflow is a steady-state fixed-resistance screening model. It does not iterate Darcy friction with Reynolds number, infer roughness or fittings, size ducts, solve fan operating points, model dampers or controls, leakage, compressibility, or transient behavior.
