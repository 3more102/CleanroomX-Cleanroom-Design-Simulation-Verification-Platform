# Fan / variable-friction loop uncertainty

CleanroomX v0.81 adds independent fan/system residual replay provenance on top of the v0.80 pressure-state audit. Each retained bisection low/high/midpoint state is reconstructed from the selected supplied fan segment and L/H/T chain, the nonlinear loop is freshly re-solved, and the retained fan-minus-system residual is checked against that independent model evaluation. Exact violating corner indices and tied maximum replay-error witnesses are preserved. This is numerical implementation provenance only, not physical uncertainty or equipment acceptance.

v0.82 independently replays retained midpoint fan, loop-network, and total system pressure components. v0.83 extends that evidence to every retained low/midpoint/high bisection state, so uncertainty summaries now classify a corner as pressure-component-replay consistent only when the complete active bracket pressure state matches a fresh nonlinear model replay. Exact violation-corner indices and tied maximum replay errors remain numerical provenance, not engineering acceptance criteria.

v0.84 propagates exact pressure-component replay mismatch records through the uncertainty summary. In addition to violating corner indices, the summary retains the precise iteration, bracket position, pressure component, recorded/recomputed values, absolute error, aggregate violation count, and tied maximum-error witnesses for the evaluated corners. This remains deterministic numerical provenance only.

v0.85 independently replays the selected operating state for every solved uncertainty corner. Coverage now records whether the retained selected airflow matches its search origin, whether final fan/loop/system/residual pressures match a fresh nonlinear solve, exact violation corners/details, and maximum replay-error provenance.

v0.86 adds terminal-bracket pressure-component replay for both solved bounded-bisection corners and iteration-limit corners. The uncertainty summary retains exact terminal replay violation corners, aggregate violation counts/details, maximum terminal replay error, and tied worst-error witnesses, including an endpoint created by the final budgeted L/H update before an iteration-limit exit.

v0.87 propagates independent internal network-state fingerprint replay across evaluated nonlinear uncertainty corners. The summary records consistent and violating corner indices while each retained bisection trace preserves low/midpoint/high canonical network-state fingerprints verified against fresh nonlinear re-solves.

v0.88 propagates the corresponding terminal-bracket network-state replay across solved and iteration-limit uncertainty corners. Aggregate evidence records terminal replay consistent/violating corner indices and exact violating low/high endpoint positions while preserving the existing terminal pressure-component replay evidence.

v0.89 extends the selected operating-state replay at every solved uncertainty corner with the canonical internal network-state SHA-256. Aggregate evidence records selected operating network-state replay consistent and violating corner indices, while violation details preserve the recorded and independently recomputed selected-state hashes.

v0.90 switches all network-state replay hashes used by those uncertainty-corner audits to the order-invariant v2 canonicalization for named nodes, edges, and variable-friction closure rows. Aggregate semantics do not change; equivalent solved states with different enumeration order no longer create false replay violations.

v0.91 advances those same trace, terminal, and selected-state hashes to the v3 network-result projection. In addition to final solved state, the fingerprint now covers network/reference identity, inner Newton iteration metadata, mass-balance tolerance, variable-friction convergence/configuration, and the ordered outer-iteration history, so uncertainty-corner replay also detects deterministic solver-provenance corruption without changing any uncertainty or acceptance semantics.

CleanroomX v0.37 introduced deterministic bounded uncertainty for the nonlinear fan/variable-friction loop workflow, v0.39 extended the same corner engine to selected physical Darcy inputs, v0.40 added duct length/circular diameter, v0.41 preserved explicit rectangular dimensions, v0.42 added selected fan-point pressure bounds, v0.43 added bounded airflow coordinates at selected supplied fan-curve points, v0.44 added bounded fan-speed ratio uncertainty, v0.45 added explicit correlated whole fan-curve scenarios, v0.46 added exact operating-point extrema witnesses, v0.47 added deterministic corner-outcome diagnostics, v0.48 added tie-aware internal edge-airflow extrema provenance, v0.49 added evaluated-corner fan air-power extrema with the same witness model, v0.50 retained the solver's explicit efficiency-chain power evidence across the same evaluated corners, v0.51 added aggregate solver-quality evidence with exact worst-case corner witnesses, v0.52 added explicit utilization and remaining-margin evidence against the solver tolerances already configured for operating-pressure residual, resistance closure, and mass balance, v0.53 added nominal-centered absolute and percentage excursions for complete evaluated-corner envelopes without extrapolation or freezing the airflow-dependent resistance model, and v0.54 adds supplied/transformed fan-curve boundary-clearance evidence for every solved evaluated corner, while v0.55 adds exact supplied-endpoint pressure-mismatch diagnostics for evaluated no-intersection corners, v0.56 adds configured outer/Newton/operating iteration-budget utilization and remaining-budget evidence, v0.57 adds canonical SHA-256 identity for the exact nonlinear uncertainty result, v0.58 adds complete per-metric power-coverage auditing so subset-only power evidence cannot be presented as a complete corner range, v0.59 adds supplied-curve fan/system intersection-bracket provenance for solved corners, v0.60 adds local fan/system crossing-conditioning and secant-root agreement evidence derived from those exact brackets, v0.61 propagates the nonlinear solver's supplied-point residual-topology audit across every evaluated uncertainty corner, v0.62 adds local supplied-point interpolation-segment position evidence for every solved corner, and v0.63 adds exact selected-candidate provenance plus alternative-candidate accounting for solved corners, while v0.64 maps pressure-residual tolerances and solved residuals through the local crossing gradient into first-order airflow-equivalent numerical diagnostics, and v0.65 preserves final bounded root-search geometry and method-aware coverage across uncertainty corners, v0.66 adds airflow-separation evidence for alternative discrete crossing candidates, v0.67 adds implementation-invariant auditing for retained bisection search geometry, v0.68 adds supplied-curve-span-normalized alternative-candidate separation with tied source-corner provenance, v0.69 retains reverse negative-to-positive sampled residual sign changes as audit-only topology without changing the solver candidate policy, v0.70 preserves remaining signed-bisection geometry when an operating-point search reaches its configured iteration limit without accepting a root, v0.71 adds supplied-grid-resolution-normalized alternative-candidate separation, v0.72 propagates complete successful bounded-bisection decision-trace audits across evaluated uncertainty corners, v0.73 adds deterministic trace iteration-sequence and L/H state-transition replay auditing, v0.74 adds supplied-point candidate index-separation with tied source-corner provenance, v0.75 extends replay-audited decision traces to iteration-limit non-converged corners with exact final L/H-to-terminal-bracket replay verification, v0.76 audits each retained trace step's recorded bracket width and binary normalized-width contraction with exact violation-corner and worst-error provenance, v0.77 anchors every retained trace to its original selected supplied-point bracket and audits complete origin-to-terminal reconstruction across evaluated uncertainty corners, v0.78 independently audits each retained L/H/T decision against its midpoint residual and configured pressure tolerance, and v0.79 independently recomputes numeric sign-bracket and arithmetic-midpoint facts from each retained trace record and propagates exact raw-state violation corner provenance, while v0.80 retains and audits each bisection midpoint's fan, loop, fixed, system, and residual pressure state and aggregates exact pressure-state violation corners plus worst identity-error witnesses. v0.81 independently re-solves the nonlinear fan/variable-friction model at every replayed low/high/midpoint bisection state, checks retained residuals against that fresh evaluation, and aggregates exact replay-violation corners plus tied worst replay-error witnesses.


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

## Pressure residual → airflow numerical equivalence

v0.64 reuses each solved corner's local fan-minus-system secant gradient from the crossing-conditioning audit to express pressure-domain numerical quantities on an equivalent airflow scale. The configured operating-pressure tolerance is multiplied by the local reciprocal residual-gradient magnitude, while the actual solved pressure residual is converted to both an absolute airflow-equivalent residual and a signed linearized airflow correction. Both equivalent magnitudes are also normalized by the active supplied-point interpolation-bracket airflow span.

The uncertainty aggregate preserves complete-versus-partial diagnostic coverage and tied source-corner provenance for the largest configured-tolerance airflow equivalent, largest solved-residual airflow equivalent, and their largest bracket-normalized fractions. No additional fan-curve point, extrapolation, or physical acceptance threshold is introduced.

These quantities are first-order numerical equivalents/corrections only. They are not measurement uncertainty, fan-performance uncertainty, interpolation-error bounds, continuous worst-case guarantees, stability criteria, stall/surge limits, manufacturer operating-region limits, commissioning criteria, or equipment-acceptance limits.

## Bounded operating-point search geometry

v0.65 propagates each solved nonlinear case's operating-point search provenance into the uncertainty study. A direct supplied-point tolerance contact retains its exact supplied-point index and no fabricated bisection interval. A bounded-bisection solve retains the active positive/negative-residual airflow interval immediately before the selected midpoint satisfies the configured operating-pressure tolerance, including low/high airflow, signed endpoint residuals, width, half-width, selected midpoint/residual, iteration number, and width normalized by the original supplied interpolation-segment span.

The aggregate separates bisection corners from supplied-point contacts, verifies search evidence across solved corners, and preserves tied source-corner provenance for the maximum final bracket width, half-width, and normalized width. Partial studies retain evidence for solved corners without presenting it as complete-study coverage.

Final bracket width and half-width are numerical search-geometry evidence only. They are not physical airflow uncertainty, interpolation-error bounds, statistical confidence intervals, continuous worst-case guarantees, stability margins, stall/surge boundaries, manufacturer operating-region limits, commissioning/certification criteria, or equipment-acceptance limits.


## Bisection implementation-invariant evidence

v0.67 verifies retained bounded-bisection geometry against the solver mechanics
that generated it. For every bisection-solved corner, the audit records whether
the unrounded live bracket retains the required positive residual at its low
airflow endpoint and negative residual at its high endpoint, and whether the
accepted airflow is the active bracket midpoint. It also compares the retained
bracket-width fraction with the binary contraction fraction implied by the
recorded iteration count and reports the absolute floating-point discrepancy.

The aggregate uncertainty evidence reports invariant-evidence coverage, exact
corner indices for any sign-bracket or midpoint-centering violation, and tied
source-corner provenance for the largest raw width-fraction consistency error.
Direct supplied-point tolerance contacts remain outside this bisection-only
audit. These checks verify implementation consistency; they do not define an
engineering acceptance threshold, physical uncertainty, interpolation-error
bound, dynamic-stability criterion, stall/surge margin, manufacturer operating
region, or equipment-acceptance limit.

## Iteration-limit bisection provenance

v0.70 extends the bounded-search audit to non-converged cases that stop specifically at the configured operating-point iteration limit. The result keeps `fan_operating_point` unset but retains the last evaluated midpoint and pressure residual plus the remaining active positive/negative-residual bracket after the final budgeted contraction. That remaining bracket records absolute width, half-width, supplied-segment-normalized width, completed contraction steps, strict-sign preservation, expected versus actual binary width fraction, and the floating-point consistency error.

The uncertainty aggregate includes these unresolved search records in overall search-evidence coverage, reports exact iteration-limit corner indices, invariant-evidence coverage, any remaining-bracket sign violations, and tied source-corner provenance for the maximum remaining-bracket width-fraction consistency error. Solved final-bracket evidence remains separate. The remaining interval is numerical search/implementation provenance only; it is not an accepted operating point, physical airflow uncertainty, an interpolation-error bound, a continuous worst-case/root guarantee, a stability or stall/surge criterion, or an equipment-acceptance limit.

## Successful bisection decision-trace provenance

v0.72 extends solved bounded-bisection auditability from the terminal bracket to the complete deterministic midpoint path. Every successful bisection corner retains each pre-evaluation signed-residual bracket, arithmetic midpoint, midpoint residual, bracket-width fraction, and endpoint-replacement or tolerance-acceptance decision. The aggregate reports exact trace coverage, exact corner indices for trace-length, sign-bracket, midpoint-geometry, or terminal-position violations, and tied source-corner provenance for the maximum retained trace length.

The compact L/H/T sequence is numerical implementation provenance only: L replaces the positive-residual low endpoint, H replaces the negative-residual high endpoint, and T accepts the midpoint within the configured pressure tolerance. It does not quantify physical airflow uncertainty, interpolation error, continuous root separation, stability/stall/surge behavior, manufacturer operating limits, commissioning/certification compliance, or equipment acceptance.

v0.73 replays every nonterminal L/H decision into the next retained trace state. The audit checks contiguous iteration numbering plus the expected next low/high airflow and signed-residual endpoints, and the uncertainty aggregate reports exact corner indices for any sequence or replay violation. This is a deterministic implementation-consistency check only; it does not infer an additional root, an interpolation-error bound, physical robustness, stability, stall/surge behavior, or equipment acceptance.

v0.76 audits the trace geometry fields themselves for both solved and iteration-limit bisections. Each recorded absolute bracket width is checked against its retained endpoints, and each normalized width is checked against the binary contraction implied by its iteration number. The aggregate reports exact corner indices for absolute-width and normalized-width failures plus tied witnesses for the maximum raw consistency errors. This remains numerical implementation provenance only.

v0.77 anchors each retained trace to the selected supplied-point bracket and replays the complete chain to its solved or iteration-limit terminal state. v0.78 adds an orthogonal decision-semantics audit: every retained L/H/T action is checked against the sign and configured-tolerance classification of its midpoint residual. The uncertainty aggregate reports exact corner indices for any decision-semantic mismatch. These checks are deterministic numerical implementation provenance only; they do not infer physical uncertainty, interpolation error, root uniqueness/stability, stall/surge behavior, manufacturer limits, commissioning/certification status, or equipment acceptance.

v0.80 adds an orthogonal pressure-state identity audit to every retained bounded-bisection trace. Each midpoint retains fan pressure, loop-network pressure, the fixed-pressure component, total system pressure, and the resulting fan-minus-system residual. The audit checks the fixed-pressure component against the study input and independently verifies `system = fixed + loop` plus `residual = fan - system`. Across evaluated corners, the uncertainty summary reports exact pressure-state violation indices and tied witnesses for the maximum absolute system-pressure and residual identity errors. These are implementation-provenance checks only, not physical uncertainty or acceptance margins.

## Supplied-point residual-topology evidence

v0.61 propagates the base nonlinear solver's discrete fan-minus-system residual audit into the nominal case and every evaluated uncertainty corner. Each audit records expected and evaluated supplied-point counts, complete or partial point coverage, supplied points that fall within the configured operating-pressure tolerance, solver-eligible strict positive-to-negative sign-change segments, every adjacent supplied-point residual transition, sampled non-increasing behavior within tolerance, and any positive residual increase. v0.69 additionally retains strict negative-to-positive sign-change segments as audit-only reverse topology; these reverse segments never enter the solver candidate list.

The aggregate uncertainty result reports how many corners have complete supplied-point coverage and sampled non-increasing residuals, exact corner indices with residual increases, exact corner indices with more than one discrete candidate crossing feature, reverse-sign-change corner counts and exact indices, total reverse segment count, and tied source-corner provenance for the largest positive residual increase when one exists. A candidate feature is either a supplied point within the configured root tolerance or a strict positive-to-negative sign-change segment; reverse negative-to-positive segments remain audit-only. v0.63 also retains the solver-priority-ordered candidate list and selected discrete feature for every solved corner, then aggregates selected-candidate coverage, first-priority selection coverage, and exact solved-corner indices where additional discrete candidates were present. This is deliberately a discrete sampled-data audit: it does not count or prove continuous physical intersections, guarantee uniqueness between supplied points, establish dynamic stability, identify stall/surge boundaries, or create a manufacturer or equipment-acceptance criterion.

v0.68 adds a scale-aware form of the v0.66 alternative-candidate separation. For each solved case with an additional discrete candidate, CleanroomX divides the absolute selected-airflow-to-candidate-interval gap by the exact supplied fan-curve airflow span used for that case. The aggregate preserves the minimum normalized separation and every tied source corner, alongside the existing absolute m³/h gap. No additional root is solved or inferred. The normalized value is a sampled-data numerical topology diagnostic, not a continuous root-separation guarantee, physical uncertainty, robustness/stability margin, stall/surge criterion, manufacturer operating region, commissioning/certification criterion, or equipment-acceptance limit.

v0.71 additionally records each case's minimum and maximum adjacent supplied-point airflow spacing and the max/min spacing ratio, then normalizes the selected-to-alternative candidate interval gap by the minimum spacing. The uncertainty aggregate preserves the minimum sampling-resolution-normalized separation with exact tied source-corner provenance and the corresponding minimum supplied spacing. This is numerical sampling-topology evidence only; it is not an interpolation-error bound, continuous root-separation guarantee, physical uncertainty, robustness/stability margin, stall/surge criterion, manufacturer operating region, commissioning/certification result, or equipment-acceptance limit.

v0.74 adds exact supplied-point index intervals to solver-eligible discrete candidates and computes the minimum index-step separation between the selected candidate interval and each alternative candidate interval. The uncertainty aggregate preserves the minimum index-space separation and tied source-corner witnesses. This is discrete sample-grid topology only; it does not infer an additional continuous root, interpolation error, physical uncertainty, robustness/stability margin, stall/surge behavior, manufacturer operating region, commissioning/certification result, or equipment-acceptance limit.

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
- operating-point search provenance for solved supplied-point/bisection cases and v0.70 iteration-limit cases, including exact affected corner indices, remaining signed-bracket geometry/invariants, and tied worst consistency-error provenance without accepting a non-converged operating point;
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
- supplied-point residual-topology evidence for every corner, including point-coverage state, tolerance contacts, solver-eligible positive-to-negative strict sign-change segments, audit-only reverse negative-to-positive strict sign-change segments, adjacent residual transitions, sampled non-increasing behavior, positive residual increases, and discrete candidate-crossing features;
- aggregate residual-topology coverage plus exact corner indices for residual increases, multiple discrete candidate features, and reverse sign changes, together with the total reverse-segment count and tied source provenance for the largest positive residual increase when present;
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
