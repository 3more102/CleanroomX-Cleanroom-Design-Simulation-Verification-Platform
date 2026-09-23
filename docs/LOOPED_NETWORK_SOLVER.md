# Looped airflow-network solver

CleanroomX v0.23 adds a steady-state pressure-node solver for connected networks that may contain arbitrary loops.

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

## Example

    cleanroomx-loop-flow examples/looped_network_demo.json

JSON output:

    cleanroomx-loop-flow examples/looped_network_demo.json --format json

Write a Markdown report:

    cleanroomx-loop-flow examples/looped_network_demo.json --output looped-network-report.md

Optional numerical controls:

    cleanroomx-loop-flow examples/looped_network_demo.json --mass-balance-tolerance-m3-h 1e-6 --max-iterations 100

## Scope boundary

This is a fixed-resistance steady-state network solver. It does not infer duct geometry, Darcy friction factors, fitting coefficients, leakage, dampers, controls, fan curves, fan/system operating points, density changes, compressibility, or transient behavior.

The solver therefore does not replace detailed HVAC network design or commissioning. A later integration can derive edge resistances from explicit duct geometry and couple the network to bounded fan models while preserving the same residual reporting.
