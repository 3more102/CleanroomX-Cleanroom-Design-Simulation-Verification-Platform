# Fan / variable-friction loop coupling

CleanroomX v0.33 couples a supplied fan pressure/airflow curve directly to the existing two-terminal loop-network solver while re-evaluating automatic Darcy friction at every airflow used during the operating-point search.

This workflow is intentionally separate from the v0.26 fixed-resistance fan/loop solver. v0.26 is exact for a network whose edge laws remain fixed quadratic laws. v0.33 is for loop edges whose resistance was derived from explicit duct geometry, absolute roughness, and kinematic viscosity and therefore needs the v0.30 Darcy-friction closure iteration as airflow changes.

## Model

For each candidate total airflow, CleanroomX:

1. scales the declared equal/opposite fan discharge and suction injections to the candidate airflow;
2. solves the complete loop network;
3. re-evaluates Darcy friction for every automatic-friction geometry edge at its solved absolute branch airflow;
4. iterates resistance until the configured relative closure tolerance is reached;
5. calculates the fan-terminal loop pressure difference;
6. adds the explicit fixed-pressure term;
7. compares that system pressure with the piecewise-linear fan pressure inside the supplied curve.

The fan operating point is found only inside a supplied fan-curve segment. No fan-curve extrapolation is performed.

For bounded-bisection traces, v0.81 independently replays the supplied-segment low/high/midpoint states, freshly re-solves the nonlinear loop, re-interpolates fan pressure, and verifies the retained fan-minus-system residuals against those fresh model evaluations. This is deterministic numerical provenance only, not a physical uncertainty, stability, or equipment-acceptance margin.

v0.82 independently replays the retained midpoint pressure components themselves. For each bounded-bisection step, CleanroomX reconstructs the midpoint from the selected supplied fan segment and decision chain, freshly interpolates fan pressure, re-solves the variable-friction loop, and compares the resulting fan, loop-network, and total system pressures with the retained values. This closes the common-mode corruption gap where fan and system pressure can shift together while the residual and retained-state arithmetic identities still agree. The 1e-9 Pa comparison is numerical implementation tolerance only, not an engineering acceptance band.

v0.83 extends that replay to the complete active bracket at every retained bisection step. Low and high endpoint fan, loop-network, and total system pressures are retained alongside the midpoint state, then independently reconstructed and compared against fresh fan interpolation and nonlinear network solves. This detects endpoint pressure-state corruption even when low/high residuals, all midpoint pressure evidence, decision semantics, and the recorded bracket geometry remain unchanged.

v0.84 makes any pressure-component replay failure directly traceable. Each mismatch records its exact bisection iteration, low/midpoint/high bracket position, fan/loop-network/system component, recorded pressure, independently recomputed pressure, and absolute error. Tied maximum-error witnesses are preserved without changing the existing 1e-9 Pa implementation-replay tolerance or any engineering acceptance criterion.

v0.85 closes the remaining solved-result provenance gap by independently re-solving the selected operating airflow itself after search completion. The replay verifies that the selected airflow is anchored to the retained search origin and that the final fan, loop-network, total-system, and residual pressures match a fresh model evaluation. This is implementation-provenance hardening only; it does not add physical uncertainty or equipment-acceptance criteria.

v0.86 extends independent replay to the terminal bisection bracket itself. Solved final brackets retain low/high fan, nonlinear loop-network, and total system pressures; iteration-limit evidence retains the post-decision remaining bracket after the last budgeted L/H update. Each terminal endpoint is freshly re-solved from the selected supplied fan segment and retained decision chain, with exact mismatch records and tied maximum-error witnesses. This remains numerical implementation provenance, not physical uncertainty, stability evidence, or equipment acceptance.

v0.87 independently replays the internal nonlinear network state behind every retained low, midpoint, and high bisection position. CleanroomX stores a SHA-256 fingerprint over a canonical projection of solved node pressures/balances, edge flows/resistances and pressure-law residuals, pressure-power balance, and variable-friction closure evidence, then freshly re-solves the reconstructed airflow and recomputes the fingerprint. This closes the provenance gap where scalar fan/loop/system pressure evidence can remain unchanged while the internal solved network state changes. The fingerprint is deterministic implementation evidence, not physical uncertainty, stability, commissioning, certification, or equipment-acceptance evidence.

v0.88 extends the same canonical network-state identity to the terminal bisection bracket. Both solved final brackets and post-decision iteration-limit remaining brackets retain low/high SHA-256 fingerprints, and the audit independently re-solves those endpoint airflows before comparing the internal network state. This specifically covers an endpoint created by the final budgeted L/H update, which can exist after the last retained trace row. The evidence remains deterministic implementation provenance only.

v0.89 applies the same canonical network-state identity to the accepted selected operating solution itself. The selected-state replay now retains the selected network SHA-256 and independently re-solves the selected airflow before comparing the canonical node/edge/pressure-power/variable-friction state. This closes the remaining selected-state provenance gap where final scalar fan, loop-network, total-system, and residual pressures could still agree while the internal selected network state differs. The fingerprint remains deterministic implementation provenance only.

v0.90 hardens that fingerprint canonicalization against harmless collection-order changes. Solved node rows, solved edge rows, and variable-friction edge-closure rows are sorted by their unique names before compact JSON serialization and SHA-256 hashing. Trace, terminal-bracket, and selected operating-state replay therefore compare semantic solved-state content rather than incidental enumeration order while retaining sensitivity to the same numeric state.

v0.91 retains that same order-invariant canonical projection for the terminal bracket itself, not only its digest. Solved final and post-decision iteration-limit low/high endpoint projections are independently reconstructed and compared field-by-field, with exact deterministic JSON-style mismatch paths for node, edge, pressure-power, or variable-friction closure differences. This makes terminal-state corruption directly localizable while preserving v0.90's immunity to harmless named-collection reordering. The projection remains implementation provenance only.

v0.92 makes the shared canonical projection both signed-zero-stable and solver-provenance-complete. Floating `-0.0` is normalized to `0.0`, while the projection now includes network/status/reference-node identity, inner Newton iteration count, mass-balance tolerance, variable-friction convergence/configuration, and ordered outer-iteration history. Named node/edge/closure collections remain sorted by name, while chronological solver history remains order-sensitive by design. The same v3 projection drives SHA-256 replay and v0.91 terminal mismatch-path diagnostics.

v0.93 extends the same v3 hash and field-by-field canonical projection replay to every successfully evaluated supplied fan-curve point before root selection. Each supplied-point check retains both representations; a fresh nonlinear solve at that exact airflow verifies the SHA-256 and projection independently and reports deterministic mismatch paths when the projection differs. This covers solved cases, complete `no_intersection_in_supplied_range` cases, and the successfully evaluated prefix before a network-solver failure. The audit is deterministic implementation provenance only.

For automatic geometry edges, the existing CleanroomX Darcy-Weisbach resistance model is reused:

`R = 0.5 rho (f L / Dh + K) / A^2`

with pressure loss represented as `deltaP = R Q |Q|`. The Darcy factor is recomputed from the existing Reynolds/roughness model at each non-negligible solved edge flow. Explicit-resistance edges and geometry edges with a user-supplied friction factor remain fixed.

## Input

See `examples/fan_variable_friction_loop_demo.json`.

Required study fields are:

- `name`;
- `fan_curve` with at least two strictly increasing airflow points and non-increasing pressure;
- `loop_network`;
- `fan_discharge_node`;
- `fan_suction_node`.

The fan nodes must use equal/opposite nonzero reference injections and every other node must have zero external injection. The reference injection sets topology and scaling; it is not assumed to be the final fan operating airflow.

Optional `fixed_pressure_pa` is nonnegative and is added to the solved loop pressure.

Optional `solver` fields are:

- `resistance_relative_tolerance` (default `1e-6`);
- `relaxation` in `(0, 1]` (default `0.5`);
- `near_zero_airflow_m3_h` (default `1e-6`);
- `max_outer_iterations` (default `50`);
- `mass_balance_tolerance_m3_h` (default `1e-6`);
- `max_newton_iterations` (default `100`);
- `operating_pressure_tolerance_pa` (default `1e-6`);
- `max_operating_iterations` (default `80`).

Unknown solver options are rejected.

## Result states

- `solved`: a fan/system intersection was found inside the supplied fan-curve range and the variable-friction network converged.
- `no_intersection_in_supplied_range`: all required network evaluations converged, but no bounded fan/system crossing exists.
- `non_converged`: the variable-friction network or the bounded operating-point iteration did not satisfy its configured convergence limit.

An unresolved state never produces a fabricated operating point.

## Diagnostics

A solved result includes:

- fan operating airflow and pressure;
- loop pressure and total system pressure;
- fan/system residual;
- interpolation segment;
- fluid air power `Q * deltaP` only;
- complete operating network solution;
- node continuity and edge pressure-law residuals;
- variable-friction outer-iteration count;
- resistance-closure error;
- edge Reynolds/friction evidence;
- supplied fan-point system checks;
- a supplied-point network-state replay audit retaining the v3 canonical SHA-256 and projection for each successfully evaluated fan point, independently re-solving those exact airflows, localizing projection differences to deterministic field paths, and distinguishing complete from partial point coverage;
- operating-point termination reason;
- a supplied-point fan-minus-system residual-topology audit with expected/evaluated point counts, complete/partial point coverage, tolerance contacts, solver-eligible strict positive-to-negative sign-change segments, audit-only strict negative-to-positive reverse sign-change segments, adjacent residual transitions, sampled monotonic non-increasing behavior within the configured pressure tolerance, and discrete candidate-crossing features;
- for solved cases, selected-candidate provenance containing the documented selection policy, selected feature, zero-based priority rank, number of additional sampled candidates, and whether the selected feature is the only discrete candidate.
- operating-point search provenance that distinguishes direct supplied-point tolerance contacts from bounded bisection; bisection solutions retain the final active signed-residual bracket, width, half-width, selected midpoint/residual, iteration, and width relative to the original supplied interpolation segment.

The reported air power is fluid power, not shaft or electrical input.

The residual-topology audit uses only supplied fan-curve points already evaluated by the bounded nonlinear solver. A candidate feature is a supplied point within the configured root tolerance or a strict positive-to-negative sign-change segment. v0.69 additionally retains strict negative-to-positive sampled sign changes as audit-only reverse segments; they are not candidate features and cannot alter the selected operating point. Candidate-feature counts, reverse-segment counts, and sampled monotonicity are diagnostic evidence only: they do not count or prove continuous fan/system intersections, guarantee uniqueness between supplied points, establish dynamic stability, identify stall/surge boundaries, or define manufacturer/equipment acceptance. v0.63 additionally preserves the exact deterministic selection policy and selected discrete feature for solved results so the chosen bounded root is auditable when more than one sampled candidate feature exists.

v0.65 preserves the actual bounded root-search geometry. When a bisection midpoint terminates on the configured pressure tolerance, the result records the active positive/negative-residual airflow interval immediately before termination and its width/half-width. A supplied-point tolerance contact records its exact supplied-point index and leaves bisection evidence unset. These are numerical search diagnostics only, not physical airflow uncertainty, interpolation-error bounds, continuous worst-case guarantees, or equipment-acceptance criteria.

v0.67 audits the retained bisection geometry against implementation invariants using the unrounded live search state. It records whether the active interval still has a strict positive/negative residual sign change, whether the accepted airflow is the active interval midpoint, the number of completed binary contraction steps, the expected width fraction from that iteration count, the actual width fraction, and their absolute floating-point discrepancy. This is solver self-verification evidence only and does not add an engineering acceptance threshold.

v0.68 extends v0.66 alternative-candidate separation with a dimensionless scale-aware value. Each selected-to-alternative discrete point/interval airflow gap is divided by the exact supplied fan-curve airflow span for that solve, and the nearest alternative retains both absolute and normalized separation. This remains sampled-data numerical topology evidence only; it is not a continuous root-separation guarantee, physical robustness margin, stability/stall/surge criterion, manufacturer operating region, commissioning/certification result, or equipment-acceptance limit.

v0.71 adds supplied-grid resolution context to the same discrete topology evidence. The audit records the minimum and maximum adjacent supplied-point airflow spacing plus their max/min ratio, then expresses every selected-to-alternative interval gap in units of the minimum adjacent supplied-point spacing. This is deterministic sampling-resolution context only; it does not create an interpolation-error estimate, continuous root-separation guarantee, physical robustness/stability margin, stall/surge criterion, manufacturer operating region, commissioning/certification result, or equipment-acceptance threshold.

v0.74 also records exact supplied-point index intervals for every solver-eligible discrete candidate and measures the selected candidate's minimum index-step separation from every alternative interval. This index-space evidence is independent of nonuniform airflow spacing and retains tied nearest alternatives. It is sample-grid topology only; it does not infer another continuous root, interpolation error, physical uncertainty, robustness/stability, stall/surge behavior, manufacturer operating limits, commissioning/certification status, or equipment acceptance.

v0.69 completes the sampled sign-topology record by retaining strict negative-to-positive supplied-point residual crossings separately from the solver-eligible positive-to-negative crossing segments. The report exposes each reverse segment and the total bidirectional strict sign-change count, while the solver candidate list and selection policy remain unchanged. Reverse segments are audit-only sampled-data evidence and do not establish an additional continuous root or any physical acceptance/stability conclusion.

v0.70 retains bounded-bisection evidence when the operating-point search reaches `max_operating_iterations` without satisfying the configured pressure residual tolerance. The result remains `non_converged` and carries no accepted operating point, but records the last evaluated midpoint and the remaining active positive/negative-residual bracket, including width, half-width, normalized width, completed binary contraction steps, strict-sign preservation, and contraction-consistency error. This is numerical search/implementation provenance only, not physical airflow uncertainty, interpolation error, a continuous root interval guarantee, stability/stall/surge evidence, or equipment acceptance.

v0.72 retains the complete midpoint decision trace for every successful bounded-bisection operating-point solve. Each record preserves the active positive/negative-residual bracket before evaluation, arithmetic midpoint, midpoint residual, normalized width, and the deterministic decision: `L` replaces the positive-residual low endpoint, `H` replaces the negative-residual high endpoint, and `T` accepts the midpoint within the configured pressure tolerance. The audit checks trace length against operating iterations, strict sign bracketing, midpoint centering, and terminal decision placement. This is implementation provenance only and does not add a physical uncertainty, interpolation-error, stability, manufacturer-limit, commissioning, certification, or equipment-acceptance criterion.

v0.73 makes that trace replayable as a state-transition record. For each nonterminal L/H step, the audit reconstructs the expected next airflow bracket and signed-residual bracket and checks them against the next retained trace record; it also verifies that iteration numbers are contiguous from one. This detects trace corruption or solver/trace divergence without changing the accepted operating point. Replay evidence is numerical implementation provenance only, not physical uncertainty, interpolation error, continuous-root uniqueness/stability evidence, or an equipment-acceptance criterion.

v0.75 extends the same replay-audited trace to bounded-bisection searches that stop only because the configured operating-iteration budget is exhausted. No operating point is accepted and no terminal `T` record is fabricated. Instead, the final recorded `L` or `H` decision is replayed into the retained remaining signed-residual bracket, and both airflow and residual endpoints must match the retained terminal search state. This is numerical implementation/search-state provenance only; it is not physical airflow uncertainty, an interpolation-error bound, a continuous-root guarantee, stability/stall/surge evidence, a manufacturer operating region, commissioning/certification evidence, or an equipment-acceptance criterion.

v0.76 additionally audits the geometry fields stored in every solved or iteration-limit trace record. The recorded `width_m3_h` must equal the retained high-minus-low airflow endpoints, and `width_fraction_of_supplied_segment` must equal the binary contraction `0.5 ** (iteration - 1)`. Per-step absolute errors are retained so report and uncertainty layers can expose exact violation provenance. These checks validate recorded numerical search state only; they do not create a physical uncertainty or acceptance margin.

v0.77 anchors every retained bounded-bisection decision trace to the exact initial signed-residual bracket selected from adjacent supplied fan-curve points, then reconstructs the complete L/H/T chain from that origin through the solved final bracket or retained iteration-limit bracket. Every recorded airflow and residual bracket state must agree with the replayed chain, independently of the v0.76 stored-width geometry audit. This is end-to-end numerical implementation provenance only; it does not add physical uncertainty, interpolation-error, root-uniqueness, stability/stall/surge, manufacturer-region, commissioning/certification, or equipment-acceptance evidence.

v0.78 independently audits the meaning of every retained decision. A midpoint inside the configured operating-pressure tolerance must record `T`; a positive midpoint residual outside tolerance must record `L`; and a negative midpoint residual outside tolerance must record `H`. The audit retains per-step recorded/expected decisions and exact violating iterations, so a self-consistent replay cannot hide an incorrectly labeled endpoint replacement. This remains numerical implementation provenance only and does not create physical uncertainty, stability, manufacturer-region, commissioning, certification, or equipment-acceptance evidence.

v0.79 independently recomputes strict signed-residual bracketing and arithmetic midpoint geometry from each retained trace record's numeric fields, then checks the stored sign-change and midpoint flags against those recomputed facts. It also retains per-step raw-state evidence and the maximum absolute midpoint-centering error, so correct-looking stored booleans cannot hide corrupted numeric trace state. This remains numerical implementation provenance only; it does not add physical airflow uncertainty, interpolation-error, root-uniqueness/stability, stall/surge, manufacturer-region, commissioning/certification, or equipment-acceptance evidence.

v0.80 additionally retains the midpoint fan pressure, variable-friction loop pressure, fixed-pressure component, total system pressure, and fan-minus-system residual for every bounded-bisection evaluation. The audit independently verifies `system = fixed + loop`, `residual = fan - system`, and that the retained fixed-pressure component matches the study input. Maximum absolute pressure-identity errors are reported alongside exact per-step checks. This remains numerical implementation provenance only; it is not physical uncertainty, an interpolation-error bound, a root-stability proof, or an equipment-acceptance criterion.

v0.81 adds an independent fan/system residual replay above that retained-state audit. The replay reconstructs each active low/high/midpoint airflow from the selected supplied fan segment and the recorded L/H/T chain, re-runs the nonlinear variable-friction network solve at those airflows, recomputes interpolated fan pressure, and compares every retained low/high/midpoint residual against the fresh model evaluation. A self-consistent corruption of retained fan pressure and residual can therefore pass the v0.80 pressure identities yet still be detected by v0.81. The replay is numerical implementation provenance only and does not establish physical uncertainty, fan-model validity, root uniqueness/stability, stall/surge margin, or equipment acceptance.

## CLI

```text
cleanroomx-fan-loop-friction examples/fan_variable_friction_loop_demo.json
cleanroomx-fan-loop-friction examples/fan_variable_friction_loop_demo.json --format json
cleanroomx-fan-loop-friction examples/fan_variable_friction_loop_demo.json --output fan-variable-loop.md
```

The CLI exits with code 0 only for `solved`; unresolved/non-converged studies return code 2.

## Engineering boundary

This is a steady incompressible engineering network model, not CFD. It does not infer damper position, leakage, system effect, acoustic performance, fan stall/surge boundaries, motor/VFD limits, controls, transients, or manufacturer acceptance. The supplied fan data and all engineering inputs remain the user's responsibility.


## Automatic-friction evidence validation

Before solving, every geometry edge identified as automatic-friction is validated against its stored resistance evidence. The solver requires complete finite geometry, density/local-loss, roughness, kinematic-viscosity, positive reference-airflow, hydraulic-diameter/area, and positive stored friction-factor evidence. This validation occurs before near-zero-flow freezing, so a zero-flow branch cannot hide malformed automatic-friction provenance.
