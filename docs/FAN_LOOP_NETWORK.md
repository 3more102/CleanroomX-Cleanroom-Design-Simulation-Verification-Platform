# Fan-driven looped airflow network

CleanroomX v0.26 couples a supplied fan curve to the fixed-resistance arbitrary-loop solver introduced in v0.23 and extended with geometry-derived edge resistance in v0.25.

## Bounded model

This workflow applies to a passive connected loop network with:

- one declared source node;
- one declared sink node;
- zero external injection at every other node;
- fixed positive quadratic edge resistances;
- an optional nonnegative fixed pressure term outside the passive mesh;
- a supplied fan pressure/airflow curve.

The loop-network edges may use either explicit resistance or the v0.25 geometry-derived resistance input. Geometry-derived and automatic-friction resistances remain fixed at their configured basis.

## Method

For a source-to-sink reference airflow, CleanroomX solves the full passive mesh and obtains the required source-to-sink pressure rise.

Because every edge follows the homogeneous fixed law

    deltaP = R * Q * abs(Q)

and the source/sink injection pattern is scaled uniformly, the complete passive mesh also follows a quadratic source-to-sink law:

    deltaP_loop = R_eq * Q^2

CleanroomX derives

    R_eq = deltaP_reference / Q_reference^2

and combines it with the optional fixed pressure term:

    deltaP_system = deltaP_fixed + R_eq * Q^2

The existing bounded fan/system solver then intersects that system curve with piecewise-linear interpolation of the supplied fan data. No fan-curve extrapolation is performed.

If an operating point is found, CleanroomX solves the **full loop network again** at the operating airflow and reports both:

- fan minus full-system pressure residual;
- full-loop pressure minus equivalent-quadratic pressure residual.

This second solve is an explicit closure check rather than relying only on the reduced equivalent curve.

## JSON input

Top-level fields:

- `name`
- `source_node`
- `sink_node`
- optional `network_reference_airflow_m3_h` (default 3600 m³/h)
- optional `fixed_pressure_pa` (default 0 Pa)
- `fan_curve`
- `loop_network`

The `loop_network` object contains `edges`, an optional `name`, and an optional `reference_node`. Do not provide `node_injections_m3_h`; this workflow owns the source/sink injection pattern.

Each edge uses the normal v0.25 loop format, for example an explicit edge:

    {
      "name": "Supply to A",
      "start_node": "Supply",
      "end_node": "Junction A",
      "resistance_pa_per_m3_s_squared": 80.0
    }

or a geometry-derived edge:

    {
      "name": "A to Return",
      "start_node": "Junction A",
      "end_node": "Return",
      "duct_geometry": {
        "length_m": 12.0,
        "air_density_kg_m3": 1.2,
        "friction_factor": 0.02,
        "local_loss_coefficient": 1.0,
        "diameter_m": 0.55
      }
    }

## CLI

Run the example:

    cleanroomx-fan-loop examples/fan_loop_network_demo.json

JSON output:

    cleanroomx-fan-loop examples/fan_loop_network_demo.json --format json

Write a Markdown report:

    cleanroomx-fan-loop examples/fan_loop_network_demo.json --output fan-loop-report.md

The CLI returns exit code 2 when no fan/system intersection exists inside the supplied fan-curve range.

## Scope boundary

This is a passive, fixed-resistance, source-to-sink fan/mesh operating-point workflow. It does not support distributed external injections/withdrawals, variable-friction iteration, balancing-damper optimization, control laws, leakage, fan stall/surge acceptance, system-effect corrections, compressibility, or transient behavior.

The reference airflow is a numerical/evidence basis for reducing the homogeneous fixed-resistance mesh; it is not a required operating airflow or an acceptance criterion. No manufacturer selection or commissioning acceptance is inferred.
