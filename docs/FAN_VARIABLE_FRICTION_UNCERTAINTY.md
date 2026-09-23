# Fan / variable-friction loop uncertainty

CleanroomX v0.37 introduced deterministic bounded uncertainty for the nonlinear fan/variable-friction loop workflow, v0.39 extended the same corner engine to selected physical Darcy inputs, v0.40 added duct length/circular diameter, v0.41 preserved explicit rectangular dimensions, v0.42 added selected fan-point pressure bounds, v0.43 added bounded airflow coordinates at selected supplied fan-curve points, and v0.44 adds explicit bounded fan-speed ratio uncertainty using the existing affinity-law curve transform without extrapolation or freezing the airflow-dependent resistance model.

The analysis deliberately avoids assigning one fixed equivalent resistance to a network whose Darcy friction changes with branch airflow. Each uncertainty corner rebuilds the affected geometry evidence and then reuses the complete nonlinear fan/loop solver.

## Bounded inputs

The workflow supports explicit absolute uncertainty for:

- the fixed-pressure term added to the loop pressure;
- an optional fan speed ratio relative to the supplied reference curve;
- pressure at selected supplied fan-curve airflow points;
- airflow coordinates at selected supplied fan-curve point indices;
- selected automatic-friction geometry-edge local-loss coefficients `K`;
- selected edge absolute roughness values;
- selected edge kinematic-viscosity values;
- selected edge air-density values;
- selected automatic-friction edge duct lengths;
- selected automatic-friction circular-duct diameters; and
- selected automatic-friction rectangular-duct widths and heights.

`fan_speed_ratio` may be supplied as a number or as an uncertainty object with `value`, `uncertainty_abs`, and optional provenance. Its complete interval must remain strictly positive. Each configured speed-ratio corner first builds the bounded reference fan curve and then reuses CleanroomX's existing affinity-law transform, so airflow scales with speed ratio and pressure with speed ratio squared. No allowed VFD range or manufacturer speed limit is inferred.

Fan-point pressure bounds are supplied in `fan_curve_pressure_uncertainty`; each entry identifies an existing `airflow_m3_h` point and supplies only `uncertainty_abs` plus optional provenance. Fan-point airflow-coordinate bounds are supplied in `fan_curve_airflow_uncertainty`; each entry uses a zero-based `point_index` so nominal airflow remains defined only in `fan_curve.points[].airflow_m3_h`. Every possible pressure corner must remain nonnegative and non-increasing with airflow, and every possible airflow-coordinate corner must remain nonnegative and strictly increasing.

Each nominal edge value remains defined once in `loop_network.edges[].duct_geometry`. The uncertainty blocks supply only absolute bounds and optional provenance; repeating a second nominal value is rejected. The JSON keys are `edge_local_loss_uncertainty`, `edge_absolute_roughness_uncertainty`, `edge_kinematic_viscosity_uncertainty`, `edge_air_density_uncertainty`, `edge_length_uncertainty`, `edge_circular_diameter_uncertainty`, `edge_rectangular_width_uncertainty`, and `edge_rectangular_height_uncertainty`.

These edge-level uncertainty dimensions apply only to automatic-friction `duct_geometry` edges. Explicit-resistance edges and geometry edges with user-supplied friction factors are rejected because they do not participate in the same airflow-dependent Darcy closure model. Lower bounds must remain physically valid: local K and roughness cannot become negative; viscosity, density, bounded duct length, circular diameter, rectangular width, and rectangular height must remain positive; and the maximum bounded roughness must remain below the minimum hydraulic diameter implied by the configured dimensional bounds. Circular-diameter bounds apply only to circular ducts, while width/height bounds apply only to rectangular ducts.

## Corner solution

For every unique lower/upper combination, CleanroomX:

1. applies the bounded fixed-pressure value plus selected supplied fan-point pressures and airflow coordinates to form a bounded reference fan curve;
2. applies the configured fan-speed ratio to that bounded reference curve using the existing affinity-law transform;
3. rebuilds each selected geometry edge using the corner values for any configured local-loss, roughness, viscosity, density, length, circular-diameter, rectangular-width, and rectangular-height bounds while preserving unbounded geometry and the stored reference airflow;
4. re-solves the variable-friction loop at every fan-curve point used for bracketing;
5. re-solves the complete variable-friction loop at every bisection airflow;
6. keeps the fan/system operating-point search inside the transformed supplied fan-curve range;
7. records `solved`, `no_intersection_in_supplied_range`, or `non_converged` independently for each corner.

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

See `examples/fan_variable_friction_uncertainty_demo.json` for the original fixed-pressure/K workflow, `examples/fan_variable_friction_physical_uncertainty_demo.json` for v0.39 roughness/viscosity/density bounds, and `examples/fan_variable_friction_geometry_uncertainty_demo.json` for v0.40 duct-length/circular-diameter bounds. `examples/fan_variable_friction_rectangular_uncertainty_demo.json` demonstrates v0.41 rectangular width/height bounds. `examples/fan_variable_friction_fan_curve_uncertainty_demo.json` demonstrates v0.42 selected fan-point pressure bounds. `examples/fan_variable_friction_fan_airflow_uncertainty_demo.json` demonstrates v0.43 selected fan-point airflow-coordinate bounds. `examples/fan_variable_friction_speed_uncertainty_demo.json` demonstrates v0.44 bounded fan-speed ratio uncertainty.

```text
cleanroomx-fan-loop-friction-uncertainty examples/fan_variable_friction_uncertainty_demo.json
cleanroomx-fan-loop-friction-uncertainty examples/fan_variable_friction_uncertainty_demo.json --format json
```

The CLI exits with code 0 only for a `complete` result. Indeterminate analyses return code 2.

`max_corner_cases` defaults to 256. Every non-zero bounded dimension doubles the two-endpoint corner space, while zero-width dimensions are deduplicated. CleanroomX rejects an analysis that exceeds the configured limit; it never silently truncates the corner set.

## Engineering boundary

This is deterministic corner analysis over user-supplied engineering bounds. It does not infer statistical distributions, covariance, fan-curve point-to-point uncertainty dependence, allowed fan/VFD speed ranges, manufacturer speed limits, unconfigured geometry manufacturing tolerances, temperature-dependent fluid properties, coupled property covariance, damper position, controls, leakage, system effect, acoustics, stall/surge limits, motor/VFD acceptance, compressibility, transients, or manufacturer acceptance.
