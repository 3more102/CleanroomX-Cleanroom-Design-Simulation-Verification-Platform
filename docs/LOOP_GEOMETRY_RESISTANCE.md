# Reference-geometry loop resistance

CleanroomX v0.24 adds a bounded bridge between the duct-geometry model and the fixed-resistance loop solver.

## Model

Each loop edge declares a positive reference airflow plus explicit duct geometry, air density, local-loss coefficient, and either:

- an explicit Darcy friction factor; or
- absolute roughness and kinematic viscosity for the existing automatic Darcy-friction calculation.

At the declared reference airflow, CleanroomX calculates the edge pressure drop from Darcy-Weisbach friction plus local losses and derives:

    R = deltaP_reference / Q_reference^2

The existing loop solver then holds this derived resistance fixed and applies:

    deltaP = R * Q * abs(Q)

to the solved signed edge flow.

## Why the reference airflow is explicit

Darcy friction can vary with Reynolds number. Deriving the factor at a declared reference airflow makes the approximation auditable. CleanroomX does not silently update the friction factor while balancing the mesh.

The report preserves the reference airflow, geometry, velocity, Darcy factor and method, Reynolds number when available, reference pressure drop, and derived fixed resistance for every edge.

## Example

    cleanroomx-loop-geometry examples/loop_geometry_demo.json

JSON output:

    cleanroomx-loop-geometry examples/loop_geometry_demo.json --format json

Write a Markdown report:

    cleanroomx-loop-geometry examples/loop_geometry_demo.json --output loop-geometry-report.md

Optional loop-solver controls:

    cleanroomx-loop-geometry examples/loop_geometry_demo.json --mass-balance-tolerance-m3-h 1e-6 --max-iterations 100

## Engineering boundary

This workflow derives resistance once at the user-supplied reference airflow. It is not a variable-friction nonlinear duct-network solver and does not iterate Reynolds number or Darcy factor at the solved edge airflow.

It also does not infer duct material roughness, fitting coefficients, leakage, damper position, controls, fan curves, compressibility, or transient behavior. Use applicable project data, manufacturer information, licensed standards, and qualified HVAC/cleanroom engineering review for real designs.
