# Fan / variable-friction loop uncertainty

CleanroomX v0.37 adds deterministic bounded uncertainty to the nonlinear fan/variable-friction loop workflow introduced in v0.33.

The analysis deliberately avoids assigning one fixed equivalent resistance to a network whose Darcy friction changes with branch airflow. Each uncertainty corner rebuilds the affected geometry evidence and then reuses the complete nonlinear fan/loop solver.

## Bounded inputs

The v0.37 workflow supports explicit absolute uncertainty for:

- the fixed-pressure term added to the loop pressure; and
- selected automatic-friction geometry-edge local-loss coefficients `K`.

The edge nominal local-loss coefficient remains defined once in `loop_network.edges[].duct_geometry.local_loss_coefficient`. The uncertainty block supplies only an absolute bound and optional provenance; repeating a second nominal value is rejected.

Only automatic-friction `duct_geometry` edges can receive local-loss uncertainty in this workflow. Explicit-resistance edges and geometry edges with user-supplied friction factors are rejected for this uncertainty dimension because they do not participate in the same airflow-dependent Darcy closure model.

## Corner solution

For every unique lower/upper combination, CleanroomX:

1. applies the bounded fixed-pressure value;
2. rebuilds each selected geometry edge at the bounded local-loss coefficient using its stored geometry, roughness, viscosity, density, and reference airflow;
3. re-solves the variable-friction loop at every fan-curve point used for bracketing;
4. re-solves the complete variable-friction loop at every bisection airflow;
5. keeps the fan/system operating-point search inside the supplied fan-curve range;
6. records `solved`, `no_intersection_in_supplied_range`, or `non_converged` independently for each corner.

The result is `complete` only when the nominal case and every evaluated corner are solved. Otherwise it is `indeterminate`, and no complete operating-point or internal edge-flow range is emitted.

## Result evidence

A complete result reports:

- nominal nonlinear operating-point evidence;
- the explicit bounded input intervals;
- evaluated corner count and per-corner state;
- airflow, fan-pressure, and system-pressure min/max across solved corners;
- internal edge-airflow ranges across evaluated corners;
- solver diagnostics for every corner; and
- provenance completeness for the fan curve and every bounded input.

These min/max values are evaluated-corner ranges only. They are not claimed to be mathematically guaranteed continuous-interval extrema for every interior combination.

## Input and CLI

See `examples/fan_variable_friction_uncertainty_demo.json`.

```text
cleanroomx-fan-loop-friction-uncertainty examples/fan_variable_friction_uncertainty_demo.json
cleanroomx-fan-loop-friction-uncertainty examples/fan_variable_friction_uncertainty_demo.json --format json
```

The CLI exits with code 0 only for a `complete` result. Indeterminate analyses return code 2.

`max_corner_cases` defaults to 256. CleanroomX rejects an analysis that exceeds the configured limit; it never silently truncates the corner set.

## Engineering boundary

This is deterministic corner analysis over user-supplied engineering bounds. It does not infer statistical distributions, covariance, fan-curve uncertainty, geometry manufacturing tolerances, damper position, controls, leakage, system effect, acoustics, stall/surge limits, motor/VFD acceptance, compressibility, transients, or manufacturer acceptance.
