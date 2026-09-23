# Fan / variable-friction loop uncertainty

CleanroomX v0.37 introduced deterministic bounded uncertainty for the nonlinear fan/variable-friction loop workflow, v0.39 extended the same corner engine to selected physical Darcy inputs, v0.40 added duct length/circular diameter, v0.41 preserved explicit rectangular dimensions, v0.42 added selected fan-point pressure bounds, v0.43 added bounded airflow coordinates at selected supplied fan-curve points, v0.44 added bounded fan-speed ratio uncertainty, v0.45 added explicit correlated whole fan-curve scenarios, v0.46 added exact operating-point extrema witnesses, v0.47 added deterministic corner-outcome diagnostics, v0.48 added tie-aware internal edge-airflow extrema provenance, v0.49 added evaluated-corner fan air-power extrema with the same witness model, v0.50 retained the solver's explicit efficiency-chain power evidence across the same evaluated corners, v0.51 added aggregate solver-quality evidence with exact worst-case corner witnesses, v0.52 added explicit utilization and remaining-margin evidence against the solver tolerances already configured for operating-pressure residual, resistance closure, and mass balance, v0.53 added nominal-centered absolute and percentage excursions for complete evaluated-corner envelopes without extrapolation or freezing the airflow-dependent resistance model, and v0.54 adds supplied/transformed fan-curve boundary-clearance evidence for every solved evaluated corner, while v0.55 adds exact supplied-endpoint pressure-mismatch diagnostics for evaluated no-intersection corners, v0.56 adds configured outer/Newton/operating iteration-budget utilization and remaining-budget evidence, v0.57 adds canonical SHA-256 identity for the exact nonlinear uncertainty result, v0.58 adds complete per-metric power-coverage auditing so subset-only power evidence cannot be presented as a complete corner range, v0.59 adds supplied-curve fan/system intersection-bracket provenance for solved corners, v0.60 adds local fan/system crossing-conditioning and secant-root agreement evidence derived from those exact brackets, v0.61 propagates the nonlinear solver's supplied-point residual-topology audit across every evaluated uncertainty corner, v0.62 adds local supplied-point interpolation-segment position evidence for every solved corner, and v0.63 adds exact selected-candidate provenance plus alternative-candidate accounting for solved corners.


v0.55 adds explicit supplied-endpoint diagnostics for evaluated uncertainty corners that return `no_intersection_in_supplied_range`. When the lower supplied airflow endpoint already has a negative fan-minus-system pressure margin, the case is recorded as a lower-boundary fan-pressure deficit; otherwise the unresolved bounded case is recorded at the upper supplied airflow endpoint as a fan-pressure surplus. Each diagnostic preserves the boundary airflow, fan pressure, system pressure, signed pressure margin, absolute pressure gap, and active corner context. The aggregate result counts lower/upper cases and retains every tied source corner for the largest evaluated endpoint gap. This is bounded diagnostic evidence only: CleanroomX does not extrapolate the fan curve or infer the missing operating point, manufacturer operating region, stall/surge margin, or equipment acceptance.


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

## Local crossing-conditioning evidence

v0.60 derives local numerical conditioning evidence only from the already retained supplied-point intersection bracket. For every solved corner it reports the fan-pressure secant slope, system-pressure secant slope, their fan-minus-system residual slope, the absolute residual-gradient magnitude, and the reciprocal airflow-per-pressure gradient when that residual slope is nonzero. It also computes the airflow where the endpoint residual secant would cross zero and compares that straight-line estimate with the fully solved nonlinear operating airflow.

The aggregate result retains complete-versus-partial coverage plus tied source-corner provenance for the minimum absolute fan-minus-system gradient, maximum reciprocal airflow-per-pressure gradient, and maximum absolute/normalized secant-root disagreement. These diagnostics quantify local numerical root conditioning and endpoint-secancy only. They do not establish a dynamic fan/system stability condition, acceptable robustness margin, stall/surge boundary, manufacturer operating region, commissioning criterion, certification result, or equipment-acceptance limit.

## Supplied-point residual-topology evidence

v0.61 propagates the base nonlinear solver's discrete fan-minus-system residual audit into the nominal case and every evaluated uncertainty corner. Each audit records expected and evaluated supplied-point counts, complete or partial point coverage, supplied points that fall within the configured operating-pressure tolerance, strict positive-to-negative sign-change segments, every adjacent supplied-point residual transition, sampled non-increasing behavior within tolerance, and any positive residual increase.

The aggregate uncertainty result reports how many corners have complete supplied-point coverage and sampled non-increasing residuals, exact corner indices with residual increases, exact corner indices with more than one discrete candidate crossing feature, and tied source-corner provenance for the largest positive residual increase when one exists. A candidate feature is either a supplied point within the configured root tolerance or a strict sign-change segment. v0.63 also retains the solver-priority-ordered candidate list and selected discrete feature for every solved corner, then aggregates selected-candidate coverage, first-priority selection coverage, and exact solved-corner indices where additional discrete candidates were present. This is deliberately a discrete sampled-data audit: it does not count or prove continuous physical intersections, guarantee uniqueness between supplied points, establish dynamic stability, identify stall/surge boundaries, or create a manufacturer or equipment-acceptance criterion.

## Interpolation-segment position evidence

v0.62 reuses each solved corner's exact supplied-point intersection bracket and reports where the solved operating airflow lies inside that local piecewise-linear fan-curve segment. The diagnostic includes segment airflow span, lower and upper supplied-point clearance, nearest segment endpoint, normalized segment position, and normalized nearest-endpoint clearance.

The aggregate result preserves complete-versus-partial coverage and tied source-corner provenance for the minimum absolute supplied-point clearance, minimum normalized clearance, and maximum active segment span. This is interpolation-geometry provenance only. Point spacing is not treated as an interpolation-error bound, fan-performance uncertainty, stall/surge margin, manufacturer operating-region limit, or equipment-acceptance criterion.

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
- evaluated-corner fluid-air-power, shaft-power, electrical-input, and specific-fan-power ranges when the required explicit efficiencies are available;
- tie-aware source-corner provenance for every available power-chain lower/upper extreme;
- a compact exact zero-based first-witness corner index for each operating-point lower/upper bound;
- tie-aware operating-point extrema-source evidence listing every matching witness corner together with its active fixed-pressure, fan-speed/scenario, fan-point, and duct uncertainty inputs;
- internal edge-airflow ranges plus the exact lower/upper first-witness corner indices for each edge;
- tie-aware internal edge-airflow extrema-source evidence listing every matching witness corner and its active uncertainty inputs;
- solver diagnostics for every corner;
- deterministic corner status and solver termination-reason counts, plus exact unresolved-corner indices and active input context;
- aggregate worst solved-corner operating-pressure residual, resistance-closure error, mass-balance residual, pressure-law residual, and iteration counts with tied source-corner context;
- configured solver-tolerance checks for operating-pressure residual, resistance closure, and mass balance, including utilization ratio, remaining numerical margin, and complete-vs-partial coverage state;
- nominal-centered absolute and percentage excursions for complete operating-point envelopes and available power-chain ranges;
- per-solved-corner lower/upper and nearest airflow headroom to the exact supplied/transformed fan-curve endpoints, plus normalized airflow position and normalized nearest-boundary headroom;
- aggregate minimum nearest-boundary headroom with tie-aware source-corner provenance;
- the limiting supplied endpoint for each no-intersection corner, including endpoint airflow, fan pressure, system pressure, signed fan-minus-system pressure mismatch, mismatch type, and absolute boundary pressure gap;
- aggregate lower/upper no-intersection boundary counts and the largest evaluated endpoint pressure gap with tied source provenance;
- exact low/high supplied-point fan pressure, system pressure, and signed fan-minus-system residual for the interpolation segment bounding every solved operating point;
- aggregate intersection-bracket coverage, strict sign-change/tolerance-contact counts, and tied source provenance for minimum endpoint residual-gap/span evidence;
- per-solved-corner fan-pressure, system-pressure, and fan-minus-system secant slopes across the exact supplied-point bracket, plus reciprocal airflow-per-pressure gradient when defined;
- secant-root airflow and absolute/normalized difference from the solved nonlinear operating airflow, with aggregate minimum residual-gradient and maximum secant-root-disagreement provenance;
- supplied-point residual-topology evidence for every corner, including point-coverage state, tolerance contacts, strict sign-change segments, adjacent residual transitions, sampled non-increasing behavior, positive residual increases, and discrete candidate-crossing features;
- aggregate residual-topology coverage plus exact corner indices for residual increases or multiple discrete candidate features, with tied source provenance for the largest positive residual increase when present;
- selected discrete crossing-candidate provenance for every solved corner, including selection policy, selected feature/rank, additional-candidate count, and aggregate selected/first-priority coverage;
- per-solved-corner active fan-curve interpolation-segment span, lower/upper supplied-point clearance, nearest segment endpoint, normalized position, and normalized nearest-endpoint clearance;
- aggregate minimum supplied-point clearance and maximum active segment span with tied source-corner provenance;
- explicit complete/partial/unavailable coverage state for each power metric, including available/total corner counts and exact missing corner indices;
- provenance completeness for the fan curve and every bounded input; and
- a canonical SHA-256 result digest with explicit algorithm, canonicalization, and versioned scope metadata.

v0.57 computes result integrity only after the full analysis payload is assembled. The digest covers the exact result content before the `result_integrity` block using compact UTF-8 JSON with sorted keys and no NaN encoding. Recomputing the same deterministic result therefore reproduces the same SHA-256 value, while any hashed result-content change changes the digest. This is content identity/integrity evidence only; it does not prove who authored the inputs, whether an external source is authoritative, or whether the analysis is suitable for commissioning, certification, or equipment acceptance.

For indeterminate studies, v0.47 retains unresolved-corner diagnostics but still emits no complete operating-point (including air power) or internal edge-flow envelope. v0.51 solver-quality aggregation may still summarize any solved evaluated corners, but it marks complete-study coverage false and never presents partial numerical evidence as complete verification. v0.52 evaluates the three solver metrics that already have configured tolerances and reports worst-value utilization plus remaining margin; if the nominal case or any corner is unresolved, the tolerance assessment is explicitly marked as incomplete coverage rather than promoted to a complete numerical verification result. Pressure-law residual and iteration maxima remain diagnostics without an invented acceptance threshold. v0.53 also reports lower/upper departures from the solved nominal case, including percentage excursion when the nominal denominator is non-zero. These values remain evaluated-corner summaries only: they are not sensitivity coefficients and do not prove continuous-interval extrema. v0.54 boundary-clearance evidence may still summarize solved corners in an indeterminate study, but `complete_study_coverage` remains false and the diagnostic is never promoted into a complete uncertainty envelope. No acceptable minimum endpoint headroom, stall/surge margin, manufacturer operating region, or equipment-acceptance threshold is inferred. v0.55 no-intersection endpoint evidence complements that solved-corner diagnostic by preserving the actual supplied boundary that prevented a bounded intersection and its pressure mismatch. It does not extrapolate the fan curve or estimate where an out-of-range operating point would occur. The v0.46 compact witness index resolves deterministically to the first matching corner for backward-compatible single-witness access, while `operating_point_extrema_sources` preserves every numerically matching tie and the bounded inputs that define those cases. The Markdown report surfaces the same operating-point source evidence, edge-flow first-witness indices, and v0.48 tie-aware internal edge-flow extrema-source records. The v0.49 air-power range is likewise the min/max of evaluated corners only. v0.50 extends that same evaluated-corner treatment to the solver's fan-side power chain. Shaft power requires an explicit fan efficiency; electrical input and specific fan power require explicit fan, motor, and VFD efficiencies. Missing efficiencies remain unavailable rather than being guessed, and configured efficiencies are fixed deterministic inputs rather than uncertainty dimensions in this workflow. v0.58 additionally requires complete per-metric corner coverage before emitting a power range, extrema provenance, or nominal-relative excursion. Partial coverage is reported with exact missing corner indices and withheld from min/max summarization. v0.59 complements the existing airflow-boundary and no-intersection diagnostics by retaining the exact supplied fan-curve interpolation endpoints that numerically enclose each solved fan/system root, including fan/system pressures and signed residuals. This is root-bracketing provenance only; it does not infer a stall/surge margin, manufacturer operating region, or equipment acceptance threshold. These records are not sensitivity coefficients and are not claimed to be mathematically guaranteed continuous-interval extrema for every interior combination.

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
