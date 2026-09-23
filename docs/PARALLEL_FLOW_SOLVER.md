# Parallel duct branch-flow solver

CleanroomX v0.9 adds a bounded branch-flow solver for parallel duct paths.

## Model

The solver applies to paths connected between the same upstream and downstream pressure nodes. Every duct section in one path carries the same path airflow.

With fixed Darcy friction factor, air density, geometry, and local-loss coefficients, each path follows:

    delta_p = R * Q^2

For paths in parallel, the pressure loss is equal and the path flows sum to the specified total airflow. CleanroomX therefore solves the common pressure loss and distributes flow according to each path resistance. The report includes mass-continuity and equal-pressure residuals as numerical verification outputs.

This extends the duct-analysis family: v0.6 evaluates pressure loss for explicitly assigned section flows, v0.8 propagates fixed terminal demands through a directed supply tree, and v0.9 solves the passive flow split for simple paths connected between the same pressure nodes.

## Inputs

Each section requires:

- length;
- Darcy friction factor;
- air density;
- summed local loss coefficient;
- either circular diameter or rectangular width and height.

The network requires a specified total airflow and at least two parallel paths.

No friction factors, fitting coefficients, air density, or flow targets are inferred from an ISO cleanroom class.

## CLI

    cleanroomx-duct-flow examples/parallel_flow_demo.json

JSON output:

    cleanroomx-duct-flow examples/parallel_flow_demo.json --format json

Write Markdown:

    cleanroomx-duct-flow examples/parallel_flow_demo.json --output parallel-flow-report.md

## Engineering boundary

This solver is for simple passive parallel paths only. It does not solve arbitrary looped graphs, shared trunk sections, fan operating points, dampers/controllers, variable friction factor with Reynolds number, leakage, pressure-dependent terminal devices, or transient behavior.

ASHRAE Handbook—Fundamentals documents duct friction and dynamic-loss methods used by the underlying resistance model. Final duct sizing, balancing, fan selection, and commissioning remain qualified engineering tasks.


## v0.10 fan operating-point extension

The v0.9 parallel-path solver still requires a specified total airflow. For a separate bounded calculation that intersects explicit fan static-pressure data with an explicit quadratic system curve, see docs/FAN_OPERATING_POINT.md. CleanroomX v0.10 does not yet couple arbitrary parallel/looped networks directly to a fan curve.
