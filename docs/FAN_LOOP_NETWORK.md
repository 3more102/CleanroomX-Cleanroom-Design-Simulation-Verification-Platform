# Fan / loop-network coupling

CleanroomX v0.26 couples the bounded fan-curve operating-point solver to the connected fixed-resistance loop-network solver.

## Two-terminal reference network

The configured loop network must represent a passive two-terminal system:

- one fan-discharge node has a positive reference injection;
- one fan-suction node has the equal and opposite reference withdrawal;
- every other network node has zero external injection.

The reference flow is used to solve the fixed-resistance mesh once. The pressure difference from discharge to suction gives an equivalent quadratic resistance:

    R_eq = deltaP_reference / Q_reference^2

Because every loop edge follows the fixed homogeneous law deltaP = R*Q*abs(Q), this two-terminal equivalent resistance remains constant when the entire through-flow is scaled.

## Fan operating point

CleanroomX forms:

    deltaP_system = deltaP_fixed + R_eq * Q^2

and intersects it with the supplied fan curve using the existing bounded piecewise-linear solver. No fan-curve extrapolation is performed.

When an operating point exists, the original loop network is solved again at that total airflow. The result reports fan operating airflow and pressure, equivalent loop resistance, the reference and operating network solutions, node/edge residuals, the direct loop pressure versus the equivalent-network pressure, and the fan-minus-system pressure residual.

If no intersection exists inside the supplied fan data, no operating loop solution is fabricated.

## Geometry-derived edges

The nested loop-network input uses the v0.25 loader unchanged. Edges may therefore use explicit fixed resistance or v0.25 duct_geometry resistance derivation, including reference-flow automatic Darcy friction. Any geometry-derived friction/resistance remains frozen at its declared v0.25 basis during fan coupling.

## Run

    cleanroomx-fan-loop examples/fan_loop_network_demo.json

JSON output:

    cleanroomx-fan-loop examples/fan_loop_network_demo.json --format json

Markdown report:

    cleanroomx-fan-loop examples/fan_loop_network_demo.json --output fan-loop-report.md

## Engineering boundary

This is a passive steady-state two-terminal coupling model. It does not support additional external injections/withdrawals inside the loop, variable-friction iteration, dampers or controls, leakage, system-effect correction, acoustics, stall/surge acceptance, motor/VFD limits, compressibility, or transients. It does not replace manufacturer selection, detailed HVAC design, commissioning, or qualified engineering review.
