# Fan-speed / loop-network study

CleanroomX v0.29 combines the existing bounded fan affinity-law transformation with the v0.26 passive two-terminal fixed-resistance fan/loop-network solver.

## Model

For each explicit user-supplied speed ratio `r = N/N_ref`, only the supplied reference fan-curve points are transformed:

    Q_r = r * Q_ref
    deltaP_r = r^2 * deltaP_ref

The study also reports `r^3` as the classical homologous fan-power scaling factor. It is not reported as motor electrical input power.

Each transformed curve is then passed unchanged to the v0.26 fan/loop-network workflow. The loop is reduced to its exact fixed quadratic two-terminal equivalent:

    deltaP_loop = R_eq * Q^2

and combined with the configured fixed pressure:

    deltaP_system = deltaP_fixed + R_eq * Q^2

The fan/system intersection is searched only inside the transformed supplied fan-curve range. If an intersection exists, the original loop network is re-solved at that operating airflow so the report retains node pressures, signed edge flows, mass-continuity residuals, edge pressure-law residuals, and fan/system residuals.

## Input

The JSON input contains:

- a reference fan curve;
- explicit unique positive speed ratios;
- optional reference fan speed in rpm;
- the same passive two-terminal loop-network input accepted by `cleanroomx-fan-loop`;
- explicit fan discharge and suction nodes;
- optional nonnegative fixed pressure.

All existing loop-network resistance rules remain unchanged. Geometry-derived resistance may be used, but any automatic Darcy friction remains frozen at its declared reference basis.

## Run

    cleanroomx-fan-loop-speed examples/fan_loop_speed_demo.json

JSON output:

    cleanroomx-fan-loop-speed examples/fan_loop_speed_demo.json --format json

Markdown report:

    cleanroomx-fan-loop-speed examples/fan_loop_speed_demo.json --output fan-loop-speed-report.md

## Engineering boundary

This is a bounded steady-state screening workflow. It does not infer an acceptable fan/VFD speed range, motor or VFD limits, efficiency, manufacturer performance outside supplied data, stall/surge acceptance, variable-friction iteration, damper/control action, leakage, system effect, compressibility, acoustics, or transient response. It does not replace manufacturer selection, detailed HVAC design, commissioning, or qualified engineering review.
