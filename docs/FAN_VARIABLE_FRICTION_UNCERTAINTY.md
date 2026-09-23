# Fan / variable-friction loop uncertainty

CleanroomX v0.37 introduced deterministic bounded uncertainty for the nonlinear fan/variable-friction loop workflow, and v0.39 extends the same corner engine to selected physical Darcy inputs without freezing the airflow-dependent resistance model.

The analysis deliberately avoids assigning one fixed equivalent resistance to a network whose Darcy friction changes with branch airflow. Each uncertainty corner rebuilds the affected geometry evidence and then reuses the complete nonlinear fan/loop solver.

## Bounded inputs

The workflow supports explicit absolute uncertainty for:

- the fixed-pressure term added to the loop pressure;
- selected automatic-friction geometry-edge local-loss coefficients `K`;
- selected edge absolute roughness values;
- selected edge kinematic-viscosity values; and
- selected edge air-density values.

Each nominal edge value remains defined once in `loop_network.edges[].duct_geometry`. The uncertainty blocks supply only absolute bounds and optional provenance; repeating a second nominal value is rejected. The JSON keys are `edge_local_loss_uncertainty`, `edge_absolute_roughness_uncertainty`, `edge_kinematic_viscosity_uncertainty`, and `edge_air_density_uncertainty`.

These edge-level uncertainty dimensions apply only to automatic-friction `duct_geometry` edges. Explicit-resistance edges and geometry edges with user-supplied friction factors are rejected because they do not participate in the same airflow-dependent Darcy closure model. Lower bounds must remain physically valid: local K and roughness cannot become negative, viscosity and density must remain positive, and the roughness upper bound must remain below the stored hydraulic diameter.

## Corner solution

For every unique lower/upper combination, CleanroomX:

1. applies the bounded fixed-pressure value;
2. rebuilds each selected geometry edge using the corner values for any configured local-loss, roughness, viscosity, and density bounds while preserving the stored geometry and reference airflow;
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

See `examples/fan_variable_friction_uncertainty_demo.json` for the original fixed-pressure/K workflow and `examples/fan_variable_friction_physical_uncertainty_demo.json` for v0.39 roughness/viscosity/density bounds.

```text
cleanroomx-fan-loop-friction-uncertainty examples/fan_variable_friction_uncertainty_demo.json
cleanroomx-fan-loop-friction-uncertainty examples/fan_variable_friction_uncertainty_demo.json --format json
```

The CLI exits with code 0 only for a `complete` result. Indeterminate analyses return code 2.

`max_corner_cases` defaults to 256. Every non-zero bounded dimension doubles the two-endpoint corner space, while zero-width dimensions are deduplicated. CleanroomX rejects an analysis that exceeds the configured limit; it never silently truncates the corner set.

## Engineering boundary

This is deterministic corner analysis over user-supplied engineering bounds. It does not infer statistical distributions, covariance, fan-curve uncertainty, unconfigured geometry manufacturing tolerances, temperature-dependent fluid properties, coupled property covariance, damper position, controls, leakage, system effect, acoustics, stall/surge limits, motor/VFD acceptance, compressibility, transients, or manufacturer acceptance.
