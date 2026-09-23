# Fan-Driven Passive Parallel-Network Integration

CleanroomX v0.12 couples the bounded fan-curve operating-point solver from v0.11 to the passive common-pressure-node parallel-path model from v0.9.

## Model

Each passive path has a fixed quadratic resistance:

    ΔP_i = R_i × Q_i²

Because all paths share the same upstream and downstream pressure nodes, each path has the same variable pressure drop:

    Q_i = sqrt(ΔP / R_i)

The total flow is:

    Q = sqrt(ΔP) × sum(1 / sqrt(R_i))

so the parallel network has an equivalent resistance:

    R_eq = 1 / [sum(1 / sqrt(R_i))]²

and the complete explicit system model is:

    ΔP_system = ΔP_fixed + R_eq × Q²

CleanroomX intersects this system curve with the user-supplied fan curve using the existing piecewise-linear, no-extrapolation solver. When an operating point exists inside the supplied fan data, the resulting total airflow is redistributed across the original parallel paths and checked for mass balance and equal pressure drop.

## Input

Use cleanroomx-fan-network with JSON containing:

- name
- optional fixed_pressure_pa, default 0
- fan_curve with ordered airflow_m3_h / pressure_pa points
- at least two passive paths
- one or more sections per path, using the same section fields as the v0.9 parallel-flow solver

Example:

~~~bash
cleanroomx-fan-network examples/fan_parallel_network_demo.json
cleanroomx-fan-network examples/fan_parallel_network_demo.json --format json
cleanroomx-fan-network examples/fan_parallel_network_demo.json --output fan-network-report.md
~~~

## Reported checks

The result reports:

- equivalent parallel-network resistance
- each original path resistance
- solved fan/system operating airflow and pressure
- fixed and variable pressure contributions
- fan-minus-system pressure residual
- solved airflow and flow fraction for each path
- per-section velocity and pressure-loss breakdown
- mass-balance residual
- equal-pressure residual
- fan/system margin at every supplied fan-curve point

## Engineering boundary

This is a bounded steady-state screening model. It is valid only for passive paths that share common pressure nodes and can be represented with constant R×Q² resistance over the solved operating region.

The workflow does not infer or solve:

- arbitrary looped duct networks
- variable Darcy friction factor or Reynolds-number iteration
- damper positions, control loops, VAV behavior, or balancing devices
- leakage or pressure-dependent terminal devices
- fan-law scaling or fan-curve extrapolation
- system-effect corrections
- stall/surge or stable-operating-region acceptance
- acoustics
- motor/electrical efficiency or manufacturer selection

Use applicable project design criteria, manufacturer data, detailed HVAC calculations, commissioning measurements, and qualified engineering review for real designs.
