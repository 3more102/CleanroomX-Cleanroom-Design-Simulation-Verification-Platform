# Fan / variable-friction loop uncertainty

CleanroomX v0.37 introduced deterministic bounded uncertainty for the nonlinear fan/variable-friction loop workflow, v0.39 extended the same corner engine to selected physical Darcy inputs, v0.40 added duct length/circular diameter, v0.41 preserved explicit rectangular dimensions, v0.42 added selected fan-point pressure bounds, v0.43 added bounded airflow coordinates at selected supplied fan-curve points, v0.44 added bounded fan-speed ratio uncertainty, v0.45 added explicit correlated whole fan-curve scenarios, v0.46 added exact operating-point extrema witnesses, v0.47 added deterministic corner-outcome diagnostics, v0.48 added tie-aware internal edge-airflow extrema provenance, v0.49 added evaluated-corner fan air-power extrema, and v0.50 adds efficiency-aware evaluated power evidence with exact source-corner traceability without extrapolation or freezing the airflow-dependent resistance model.

The analysis deliberately avoids assigning one fixed equivalent resistance to a network whose Darcy friction changes with branch airflow. Each uncertainty corner rebuilds the affected geometry evidence and then reuses the complete nonlinear fan/loop solver.

## Bounded inputs

The workflow supports explicit absolute uncertainty for:

- the fixed-pressure term added to the loop pressure;
- an optional fan speed ratio relative to the supplied reference curve;
- pressure at selected supplied fan-curve airflow points;
- airflow coordinates at selected supplied fan-curve point indices;
- or named whole fan-curve scenarios that preserve supplied point-to-point dependence;
- selected automatic-friction geometry-edge local-loss coefficients `K`;
- selected edge absolute roughness values;
- selected edge kinematic-viscosity values;
- selected edge air-density values;
- selected automatic-friction edge duct lengths;
- selected automatic-friction circular-duct diameters; and
- selected automatic-friction rectangular-duct widths and heights.

`fan_speed_ratio` may be supplied as a number or as an uncertainty object with `value`, `uncertainty_abs`, and optional provenance. Its complete interval must remain strictly positive. Each configured speed-ratio corner first builds the bounded reference fan curve and then reuses CleanroomX's existing affinity-law transform, so airflow scales with speed ratio and pressure with speed ratio squared. No allowed VFD range or manufacturer speed limit is inferred.

Fan-point pressure bounds are supplied in `fan_curve_pressure_uncertainty`; each entry identifies an existing `airflow_m3_h` point and supplies only `uncertainty_abs` plus optional provenance. Fan-point airflow-coordinate bounds are supplied in `fan_curve_airflow_uncertainty`; each entry uses a zero-based `point_index` so nominal airflow remains defined only in `fan_curve.points[].airflow_m3_h`. Every possible pressure corner must remain nonnegative and non-increasing with airflow, and every possible airflow-coordinate corner must remain nonnegative and strictly increasing.

`fan_curve_scenarios` is an array of named complete fan curves with optional provenance. When configured, CleanroomX evaluates the nominal supplied curve plus every named scenario as whole curves; it does not independently permute their points. Whole-curve scenarios are therefore mutually exclusive with `fan_curve_pressure_uncertainty` and `fan_curve_airflow_uncertainty`, while they may still be crossed with fan-speed, fixed-pressure, and duct uncertainty. Scenario names must be unique and `nominal` is reserved for the baseline curve.

Each nominal edge value remains defined once in `loop_network.edges[].duct_geometry`. The uncertainty blocks supply only absolute bounds and optional provenance; repeating a second nominal value is rejected. The JSON keys are `edge_local_loss_uncertainty`, `edge_absolute_roughness_uncertainty`, `edge_kinematic_viscosity_uncertainty`, `edge_air_density_uncertainty`, `edge_length_uncertainty`, `edge_circular_diameter_uncertainty`, `edge_rectangular_width_uncertainty`, and `edge_rectangular_height_uncertainty`.

These edge-level uncertainty dimensions apply only to automatic-friction `duct_geometry` edges. Explicit-resistance edges and geometry edges with user-supplied friction factors are rejected because they do not participate in the same airflow-dependent Darcy closure model. Lower bounds must remain physically valid: local K and roughness cannot become negative; viscosity, density, bounded duct length, circular diameter, rectangular width, and rectangular height must remain positive; and the maximum bounded roughness must remain below the minimum hydraulic diameter implied by the configured dimensional bounds. Circular-diameter bounds apply only to circular ducts, while width/height bounds apply only to rectangular ducts.

## Corner solution

For every evaluated scenario/corner combination, CleanroomX:

1. selects either one independently bounded reference fan curve or one explicit whole-curve scenario, with the nominal supplied curve retained as a scenario baseline;
2. applies the configured fan-speed ratio to that selected reference curve using the existing affinity-law transform;
3. applies the bounded fixed-pressure value and rebuilds each selected geometry edge using the corner values for any configured local-loss, roughness, viscosity, density, length, circular-diameter, rectangular-width, and rectangular-height bounds while preserving unbounded geometry and the stored reference airflow;
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
- airflow, fan-pressure, system-pressure, and fan air-power min/max across solved corners;
- a compact exact zero-based first-witness corner index for each operating-point lower/upper bound;
- tie-aware operating-point extrema-source evidence listing every matching witness corner together with its active fixed-pressure, fan-speed/scenario, fan-point, and duct uncertainty inputs;
- internal edge-airflow ranges plus the exact lower/upper first-witness corner indices for each edge;
- tie-aware internal edge-airflow extrema-source evidence listing every matching witness corner and its active uncertainty inputs;
- per-corner nonlinear fan pressure/power evidence plus the nominal power record;
- evaluated-corner fluid-air-power ranges and, only when explicit efficiencies are supplied, shaft-power, electrical-input, and specific-fan-power ranges;
- tie-aware power extrema-source evidence resolving each available power-range bound to every matching evaluated corner;
- solver diagnostics for every corner;
- deterministic corner status and solver termination-reason counts, plus exact unresolved-corner indices and active input context; and
- provenance completeness for the fan curve and every bounded input.

For indeterminate studies, v0.47 retains unresolved-corner diagnostics but still emits no complete operating-point (including air power) or internal edge-flow envelope. These min/max values are evaluated-corner ranges only. The v0.46 compact witness index resolves deterministically to the first matching corner for backward-compatible single-witness access, while `operating_point_extrema_sources` preserves every numerically matching tie and the bounded inputs that define those cases. The Markdown report surfaces the same operating-point source evidence, edge-flow first-witness indices, v0.48 tie-aware internal edge-flow extrema-source records, and v0.50 evaluated power ranges with source-corner witnesses. The v0.49 air-power operating-point range remains available for backward-compatible operating-point reporting. v0.50 additionally preserves each corner's full power record and reports shaft, electrical, and specific-fan-power ranges only when the required explicit efficiencies exist. Power min/max values are evaluated-corner diagnostics only because Q×ΔP and derived power may attain an interior extremum. These records are not sensitivity coefficients and are not claimed to be mathematically guaranteed continuous-interval extrema for every interior combination.

## Input and CLI

See `examples/fan_variable_friction_uncertainty_demo.json` for the original fixed-pressure/K workflow, `examples/fan_variable_friction_physical_uncertainty_demo.json` for v0.39 roughness/viscosity/density bounds, and `examples/fan_variable_friction_geometry_uncertainty_demo.json` for v0.40 duct-length/circular-diameter bounds. `examples/fan_variable_friction_rectangular_uncertainty_demo.json` demonstrates v0.41 rectangular width/height bounds. `examples/fan_variable_friction_fan_curve_uncertainty_demo.json` demonstrates v0.42 selected fan-point pressure bounds. `examples/fan_variable_friction_fan_airflow_uncertainty_demo.json` demonstrates v0.43 selected fan-point airflow-coordinate bounds. `examples/fan_variable_friction_speed_uncertainty_demo.json` demonstrates v0.44 bounded fan-speed ratio uncertainty. `examples/fan_variable_friction_curve_scenarios_demo.json` demonstrates v0.45 correlated whole fan-curve scenarios.

```text
cleanroomx-fan-loop-friction-uncertainty examples/fan_variable_friction_uncertainty_demo.json
cleanroomx-fan-loop-friction-uncertainty examples/fan_variable_friction_uncertainty_demo.json --format json
```

The CLI exits with code 0 only for a `complete` result. Indeterminate analyses return code 2.

`max_corner_cases` defaults to 256. Every non-zero bounded dimension doubles the two-endpoint corner space, while zero-width dimensions are deduplicated. CleanroomX rejects an analysis that exceeds the configured limit; it never silently truncates the corner set.

## Engineering boundary

This is deterministic case/corner analysis over user-supplied engineering bounds and explicit whole-curve scenarios. It does not infer statistical distributions, covariance beyond the dependence explicitly encoded by a supplied whole-curve scenario, allowed fan/VFD speed ranges, manufacturer speed limits, unconfigured geometry manufacturing tolerances, temperature-dependent fluid properties, coupled property covariance, damper position, controls, leakage, system effect, acoustics, stall/surge limits, motor/VFD acceptance, compressibility, transients, or manufacturer acceptance.
