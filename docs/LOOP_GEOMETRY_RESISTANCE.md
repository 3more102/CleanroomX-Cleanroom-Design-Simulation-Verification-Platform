# Reference-geometry loop resistance

CleanroomX v0.25 bridges the duct-geometry model and the fixed-resistance loop solver without silently introducing flow-dependent friction iteration.

## Reference-flow derivation

Every loop edge declares one positive reference airflow and one or more duct sections in series. Each section supplies circular or rectangular geometry, air density, explicit local-loss coefficient, and either:

- a fixed Darcy friction factor; or
- absolute roughness and kinematic viscosity, allowing the existing Darcy-friction model to resolve the factor at the declared reference airflow.

For each section CleanroomX evaluates Darcy-Weisbach plus local losses at the reference airflow and derives:

    R_section = deltaP_reference / Q_reference^2

Series-section resistances are summed:

    R_edge = sum(R_section)

The existing connected loop solver then holds that edge resistance fixed and solves:

    deltaP = R_edge * Q * abs(Q)

for signed edge airflow and relative node pressure.

## Audit evidence

The report preserves, per section:

- reference airflow and velocity;
- geometry and hydraulic diameter;
- air density and local-loss coefficient;
- Darcy factor and whether it was user-supplied or resolved automatically;
- Reynolds number and roughness evidence when automatic friction is used;
- reference pressure drop and derived fixed resistance;
- solved airflow, velocity, and fixed-resistance pressure drop.

The loop result continues to report node-continuity, edge pressure-law, and geometry reconstruction residuals.

## Run

    cleanroomx-loop-geometry examples/loop_geometry_demo.json

JSON output:

    cleanroomx-loop-geometry examples/loop_geometry_demo.json --format json

Markdown report:

    cleanroomx-loop-geometry examples/loop_geometry_demo.json --output loop-geometry-report.md

## Engineering boundary

Automatic Darcy friction, when requested, is resolved only at the declared reference airflow. The resulting friction factor and resistance are held fixed during loop balancing. CleanroomX does not iterate Reynolds number or Darcy factor at the solved edge airflow.

This workflow also does not infer material roughness, fitting coefficients, leakage, damper positions, controls, fan curves, compressibility, or transient behavior. It remains preliminary engineering screening and does not replace detailed HVAC/cleanroom design or commissioning.
