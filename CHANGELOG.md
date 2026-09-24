# Changelog

## v0.91 selected operating network-state projection replay diagnostics — 2026-09-24

- Retains the canonical selected operating network-state projection alongside the existing selected-state SHA-256 fingerprint.
- Independently re-solves the exact retained selected airflow and compares node, edge, pressure-power, and variable-friction closure projection fields with the fresh solved state.
- Localizes selected projection corruption to deterministic JSON-style field paths such as `$.nodes[0].relative_pressure_pa`, including cases where the retained selected-state SHA-256 itself remains unchanged.
- Propagates projection replay availability, consistency, mismatch counts, exact paths, violating uncertainty-corner indices, and report evidence while preserving the existing pressure and fingerprint replay diagnostics.
- Preserves v0.90 terminal projection replay, v0.89 selected fingerprint replay, root selection, no-extrapolation behavior, solver tolerances, iteration budgets, and engineering acceptance semantics.
- Bumped package/runtime metadata to v0.91.0.

## v0.90 terminal network-state projection replay diagnostics — 2026-09-24

- Retains canonical low/high terminal network-state projections alongside their SHA-256 fingerprints on solved final and post-decision iteration-limit brackets.
- Independently re-solves each terminal endpoint and compares the retained canonical node, edge, pressure-power, and variable-friction closure projection with the fresh projection.
- Localizes projection corruption to deterministic JSON-style field paths such as `$.nodes[0].relative_pressure_pa`, even when the retained SHA-256 fingerprint itself is not modified.
- Aggregates projection-replay consistency, exact violating endpoint positions, mismatch paths, and corner-level details through nonlinear uncertainty summaries, standalone reports, and engineering dossiers.
- Preserves v0.89 selected-operating-state fingerprint replay, v0.88 terminal fingerprint replay, v0.87 full-trace fingerprints, pressure-component replay, solver tolerances, root selection, no-extrapolation behavior, and engineering acceptance semantics.
- Bumped package/runtime metadata to v0.90.0.

## v0.89 selected operating network-state fingerprint replay — 2026-09-24

- Extends the v0.85 selected operating-state replay from scalar fan/loop/system/residual pressures to the canonical internal nonlinear network state.
- Retains a SHA-256 fingerprint of the selected solved node, edge, pressure-power, and variable-friction closure state and independently recomputes it from a fresh solve at the retained selected airflow.
- Detects selected operating-state internal corruption even when the retained selected airflow, search origin, and all scalar pressure/residual evidence remain unchanged.
- Propagates selected network-state replay consistency and exact recorded/recomputed hashes through nonlinear uncertainty summaries, standalone reports, engineering dossiers, and regression coverage.
- Preserves v0.88 terminal-bracket network-state replay, v0.87 full-trace network-state replay, root-selection/no-extrapolation behavior, numerical tolerances, iteration budgets, and engineering acceptance semantics.
- Bumped package/runtime metadata to v0.89.0.

## v0.88 terminal-bracket network-state fingerprint replay — 2026-09-24

- Retains canonical SHA-256 internal network-state fingerprints on solved final and post-decision iteration-limit terminal bracket low/high endpoints.
- Independently re-solves both terminal endpoints and compares canonical node, edge, pressure-power, and variable-friction closure state fingerprints.
- Detects terminal internal-state corruption even when terminal fan, loop-network, total-system pressures and retained trace replay evidence remain unchanged.
- Propagates terminal network-state replay consistency, exact violating endpoint positions plus recorded/recomputed hashes, uncertainty-corner provenance, standalone reports, and engineering dossiers.
- Preserves v0.87 full-trace network-state replay, v0.86 terminal pressure-component replay, root selection, iteration budgets, no-extrapolation behavior, and engineering acceptance semantics.
- Bumped package/runtime metadata to v0.88.0.

## v0.87 independent internal network-state fingerprint replay — 2026-09-24

- Retains a SHA-256 fingerprint for the canonical internal nonlinear network state at every low, midpoint, and high bounded-bisection position.
- Canonical state covers solved node pressures/balances, edge flows/resistances and pressure-law residuals, pressure-power balance, and variable-friction closure evidence.
- Freshly re-solves every reconstructed bisection state and compares the retained fingerprint with the independently recomputed fingerprint.
- Detects internal network-state provenance corruption even when scalar fan/loop/system pressure, residual, bracket-geometry, full-bracket replay, selected-state replay, and v0.86 terminal-bracket replay evidence remain unchanged.
- Propagates network-state replay coverage and exact violation-corner indices through standalone reports, nonlinear uncertainty summaries, engineering dossiers, and solved/iteration-limit regressions.
- Preserves root selection, bisection decisions, terminal-bracket replay, fan interpolation, nonlinear solver tolerances, no-extrapolation behavior, and all existing engineering acceptance semantics.
- Bumped package/runtime metadata to v0.87.0.

## v0.86 terminal-bracket pressure-component replay — 2026-09-24

- Retains low/high fan, nonlinear loop-network, and total system pressure on solved final bisection brackets and post-decision iteration-limit remaining brackets.
- Independently replays the terminal low/high pressure components from the selected supplied fan segment and the complete retained L/H/T decision chain.
- Closes the post-final-decision iteration-limit provenance gap where a newly replaced endpoint previously retained its residual but not a directly replay-auditable pressure-component state.
- Extends v0.84 exact mismatch provenance to terminal brackets with exact position/component, recorded/recomputed pressure, absolute error, violation records, and tied maximum-error witnesses.
- Propagates terminal replay consistency, violation corners/details, aggregate violation counts, maximum error, and tied worst witnesses through nonlinear uncertainty summaries and reports.
- Preserves v0.85 selected operating-state replay, v0.84 exact per-step mismatch provenance, v0.83 full-bracket replay, root-selection/no-extrapolation behavior, iteration budgets, and engineering acceptance semantics.
- Bumped package/runtime metadata to v0.86.0.


## v0.85 selected operating-state independent replay — 2026-09-24

- Adds a fresh nonlinear replay of every solved selected operating airflow after the bounded search completes, independently recomputing fan pressure, loop-network pressure, total system pressure, and fan-minus-system residual.
- Anchors the selected airflow to its retained search origin: the terminal bisection midpoint for bounded-bisection solutions or the exact supplied fan-curve point for direct tolerance contacts.
- Records per-component replay errors, exact violations, maximum error, and tied maximum-error witnesses without changing the existing 1e-9 Pa numerical replay tolerance or any engineering acceptance criterion.
- Propagates selected-state replay coverage, origin mismatches, violation corners/details, and worst replay-error evidence across nonlinear uncertainty studies and Markdown reports.
- Adds common-mode pressure-corruption regression coverage and supplied-point origin coverage.
- Bumped package/runtime metadata to v0.85.0.


## v0.84 exact pressure-component replay violation provenance — 2026-09-24

- Adds deterministic violation records for every independent pressure-component replay mismatch with exact bisection iteration, bracket position (low/midpoint/high), pressure component (fan/loop-network/system), recorded value, independently recomputed value, and absolute error.
- Preserves tied maximum-error witnesses so the worst replay discrepancy can be traced to the exact retained component state instead of only a scalar maximum.
- Propagates exact pressure-component replay violation details, aggregate violation counts, and tied maximum-error witnesses across evaluated nonlinear uncertainty corners.
- Extends standalone and uncertainty Markdown reports with the new violation/witness provenance while preserving all v0.83 compatibility aliases and solver behavior.
- No engineering acceptance criteria, root-selection policy, interpolation behavior, or numerical tolerance changed; this is audit/provenance hardening only.
- Bumped package/runtime metadata to v0.84.0.


## v0.83 full-bracket pressure-component replay — 2026-09-24

- Retains low and high endpoint fan pressure, nonlinear loop-network pressure, and total system pressure in every bounded-bisection trace step, complementing the v0.82 midpoint pressure state.
- Independently reconstructs and re-solves low, midpoint, and high pressure components from the selected supplied fan segment and active bisection decision chain.
- Adds explicit low-endpoint, high-endpoint, midpoint, and complete-bracket replay verdicts while preserving the existing v0.82 midpoint aliases for compatibility.
- Detects endpoint common-mode pressure corruption that leaves low/high residuals, midpoint pressure evidence, decision semantics, raw-state geometry, and v0.81 residual replay unchanged.
- Uses the existing strict 1e-9 Pa numerical replay tolerance and propagates complete-bracket violations through nonlinear uncertainty summaries and reports.
- Preserves bounded root selection, no-extrapolation behavior, iteration budgets, solver acceptance tolerances, and all engineering acceptance criteria; this remains deterministic implementation-provenance hardening.
- Bumped package/runtime metadata to v0.83.0.


## v0.82 independent pressure-component replay — 2026-09-24

- Independently replays each retained bisection midpoint's fan pressure, nonlinear loop-network pressure, and total system pressure from the selected supplied fan segment and a fresh variable-friction network solve.
- Compares the replayed pressure components directly with their retained trace values instead of relying only on the v0.80 algebraic identities or the v0.81 fan-minus-system residual.
- Detects common-mode pressure corruption where fan, loop, and total system pressures shift together while the residual and all retained-state pressure identities remain self-consistent.
- Retains complete per-step component-replay coverage, a strict 1e-9 Pa numerical tolerance, exact uncertainty-corner violation indices, and tied maximum component-replay error provenance.
- Propagates component-replay evidence through standalone loop reports, nonlinear uncertainty reports, engineering dossiers, and regression coverage for solved and iteration-limit traces.
- Preserves root selection, decision semantics, iteration budgets, fan-curve no-extrapolation behavior, and all existing engineering acceptance criteria; this remains numerical implementation provenance only.
- Bumped package/runtime metadata to v0.82.0.

## v0.81 independent fan/system residual replay — 2026-09-24

- Reconstructs every retained bounded-bisection low/high/midpoint airflow from the selected supplied fan segment and recorded L/H/T decision chain, then freshly re-solves the nonlinear variable-friction loop at each replayed state.
- Recomputes interpolated fan pressure and total system pressure independently of retained trace pressure/residual fields, and checks every retained low/high/midpoint fan-minus-system residual against that fresh model evaluation.
- Keeps the v0.80 pressure-state identity audit intact as a complementary retained-state check; v0.81 additionally detects self-consistent stored fan-pressure/residual corruption that can satisfy those identities.
- Retains per-step replay evidence, a strict 1e-9 Pa comparison tolerance, maximum replay error, exact nonlinear uncertainty-corner violation indices, and tied worst-error provenance.
- Propagates the replay evidence through standalone loop reports, nonlinear uncertainty reports, engineering dossiers, README/docs, solved cases, and iteration-limit cases.
- Adds regression coverage where terminal fan pressure and residual are corrupted together so raw-state, pressure-state, decision-semantic, and origin replay checks remain consistent while independent model replay correctly fails.
- Does not change candidate priority, bounded root selection, root-acceptance tolerance, iteration budgets, fan-curve no-extrapolation behavior, or any engineering acceptance criterion.
- Bumped package/runtime metadata to v0.81.0.


## v0.80 bisection trace pressure-state audit — 2026-09-24

- Retains midpoint fan pressure, variable-friction loop pressure, fixed pressure, total system pressure, and fan-minus-system residual for every bounded-bisection trace evaluation.
- Independently checks the retained pressure identities `system = fixed + loop` and `residual = fan - system`, and anchors each retained fixed-pressure component to the study input.
- Aggregates exact nonlinear uncertainty-corner indices for pressure-state audit failures plus tied maximum system-pressure and residual identity errors.
- Surfaces the new evidence in standalone fan/variable-friction loop reports, nonlinear uncertainty reports, and engineering dossiers.
- Adds direct corruption regressions that distinguish total-system pressure inconsistency from fixed-pressure provenance corruption, while preserving v0.79 raw-state, v0.78 decision-semantics, v0.77 origin replay, and iteration-limit behavior.
- Does not change candidate priority, root selection, root-acceptance tolerance, iteration budgets, fan-curve no-extrapolation behavior, or any engineering acceptance criterion.
- Treats pressure-state checks strictly as numerical implementation provenance; they are not physical airflow uncertainty, interpolation-error bounds, root uniqueness/stability evidence, stall/surge evidence, commissioning/certification evidence, or equipment acceptance.
- Bumped package/runtime metadata to v0.80.0.

## v0.79 independent bisection trace raw-state audit — 2026-09-24

- Independently recomputes strict sign-change from retained low/high fan-minus-system residuals for every bounded-bisection trace step.
- Independently recomputes each retained airflow midpoint from the numeric bracket endpoints and records the absolute midpoint-centering error.
- Checks the stored strict-sign-change and midpoint-validity flags against those recomputed numeric facts instead of trusting the flags as evidence.
- Aggregates exact nonlinear uncertainty-corner indices for numeric sign failures, sign-flag mismatches, numeric midpoint failures, midpoint-flag mismatches, and combined raw-state audit failures, plus tied maximum midpoint-error witnesses.
- Adds solved, iteration-limit, flag-corruption, and self-consistent corrupted-midpoint regression coverage while preserving the merged v0.78 decision-semantics audit and v0.77 origin replay.
- Does not change candidate priority, root selection, root-acceptance tolerance, iteration budgets, fan-curve no-extrapolation behavior, or any engineering acceptance criterion.
- Treats raw-state checks strictly as numerical implementation provenance; they are not physical airflow uncertainty, interpolation-error bounds, root uniqueness/stability evidence, stall/surge evidence, commissioning/certification evidence, or equipment acceptance.
- Bumped package/runtime metadata to v0.79.0.

## v0.78 bisection trace decision-semantics audit — 2026-09-24

- Independently verifies every retained bounded-bisection L/H/T decision against the recorded midpoint fan-minus-system residual and the configured operating-pressure tolerance.
- Retains per-step recorded/expected decision evidence plus exact violating iteration numbers, separate from state-transition replay and origin-to-terminal replay.
- Aggregates exact nonlinear uncertainty-corner indices for decision-semantic violations and surfaces the evidence in standalone loop, uncertainty, and engineering-dossier Markdown.
- Adds solved, iteration-limit, and deliberate decision-corruption regression coverage while preserving v0.76 geometry checks and v0.77 origin replay.
- Does not change candidate priority, root selection, root-acceptance rules, iteration budgets, fan-curve no-extrapolation behavior, or any engineering acceptance criterion.
- Treats decision semantics strictly as numerical implementation provenance; it is not physical airflow uncertainty, interpolation error, root uniqueness/stability evidence, a stall/surge criterion, a manufacturer operating region, commissioning/certification evidence, or an equipment-acceptance threshold.
- Bumped package/runtime metadata to v0.78.0.

## v0.77 bisection trace origin-to-terminal replay — 2026-09-24

- Anchors every retained bounded-bisection decision trace to the exact initial signed-residual bracket selected from adjacent supplied fan-curve points.
- Reconstructs the complete L/H/T decision chain from that origin and independently verifies every recorded airflow/residual bracket state.
- Verifies the reconstructed terminal bracket against the solved final bracket or, for iteration-limit outcomes, the retained remaining active bracket.
- Aggregates exact nonlinear uncertainty-corner indices for origin-to-terminal replay violations and surfaces the evidence in standalone loop, uncertainty, and engineering-dossier Markdown.
- Preserves v0.76 per-step width/normalized-width geometry audits and adds solved plus iteration-limit regression coverage without changing candidate priority, root-acceptance rules, iteration budgets, or no-extrapolation behavior.
- Treats the replay strictly as numerical implementation provenance; it is not physical airflow uncertainty, interpolation error, root uniqueness/stability evidence, a stall/surge criterion, a manufacturer operating region, commissioning/certification evidence, or an equipment-acceptance threshold.
- Bumped package/runtime metadata to v0.77.0.

## v0.76 bisection decision-trace geometry consistency — 2026-09-24

- Audits every retained bounded-bisection trace record's `width_m3_h` against its recorded low/high airflow endpoints.
- Audits every retained trace record's normalized supplied-segment width against the exact binary contraction implied by its one-based bisection iteration.
- Retains per-step expected/recorded width evidence and absolute consistency errors, with aggregate exact uncertainty-corner violation indices and worst-error witnesses.
- Applies the same trace-geometry audit to solved pressure-tolerance and non-converged iteration-limit traces without changing root selection, iteration budgets, or terminal replay semantics.
- Surfaces the evidence in standalone fan-loop, nonlinear uncertainty, and engineering-dossier Markdown.
- Adds a corruption-detection regression that deliberately alters retained width fields and verifies the audit fails those fields while preserving the independent replay checks.
- Treats trace geometry strictly as numerical implementation provenance; it is not physical airflow uncertainty, interpolation error, a continuous-root guarantee, stability/stall/surge evidence, commissioning/certification evidence, or an equipment-acceptance criterion.
- Bumped package/runtime metadata to v0.76.0.

## v0.75 iteration-limit decision-trace terminal replay — 2026-09-24

- Extends retained bounded-bisection decision traces to non-converged searches that exhaust `max_operating_iterations`.
- Keeps iteration-limit outcomes explicitly non-converged with no accepted operating point and no fabricated terminal `T` decision.
- Replays the final recorded `L`/`H` decision into the retained remaining signed-residual bracket and audits exact airflow/residual endpoint agreement.
- Aggregates solved and iteration-limit trace coverage, terminal-outcome consistency, final replay violations, and maximum trace length across nonlinear uncertainty corners.
- Surfaces the evidence in standalone loop, uncertainty, and engineering-dossier Markdown with direct solver, uncertainty, and dossier regression coverage.
- Treats the trace and terminal replay strictly as numerical implementation provenance; they are not physical airflow uncertainty, interpolation-error bounds, continuous-root guarantees, stability/stall/surge evidence, manufacturer operating limits, commissioning/certification evidence, or equipment-acceptance criteria.
- Bumped package/runtime metadata to v0.75.0.

## v0.74 supplied-point candidate index-separation audit — 2026-09-24

- Retains exact supplied-point index intervals for solver-eligible tolerance-contact points and positive-to-negative sign-change segments.
- Measures selected-to-alternative discrete candidate separation directly in supplied-point index steps, independently of nonuniform airflow spacing.
- Retains tied nearest alternatives in index space and aggregates the minimum index-interval separation across uncertainty corners with exact source-corner provenance.
- Surfaces the evidence in standalone nonlinear fan-loop, uncertainty, and engineering-dossier Markdown alongside absolute-airflow, full-curve-span, and minimum-supplied-spacing separation evidence.
- Adds direct solver, uncertainty, and dossier regression coverage without changing candidate priority, bounded root solving, bisection trace/replay semantics, or no-extrapolation behavior.
- Treats supplied-point index separation strictly as discrete sample-grid topology; it is not physical uncertainty, an interpolation-error estimate, a continuous root-separation guarantee, stability/stall/surge evidence, a manufacturer operating region, commissioning/certification evidence, or an equipment-acceptance threshold.
- Bumped package/runtime metadata to v0.74.0.

## v0.73 bisection decision-trace replay audit — 2026-09-24

- Replays every nonterminal successful bounded-bisection L/H decision into the next retained trace record and verifies both airflow-bracket and signed-residual-bracket state transitions.
- Verifies trace iteration numbering is contiguous from one in addition to the existing trace-length, strict-sign, midpoint-geometry, and terminal-position checks.
- Retains per-transition replay evidence with exact from/to iteration numbers and separate airflow/residual transition checks.
- Aggregates exact uncertainty-corner indices for iteration-sequence and state-transition replay violations.
- Surfaces the new replay audit in standalone fan-loop, uncertainty, and engineering-dossier Markdown and adds direct regression coverage.
- Preserves operating-point selection, supplied-curve no-extrapolation behavior, and all v0.72 decision-trace semantics.
- Treats replay evidence strictly as numerical implementation provenance; it is not physical airflow uncertainty, interpolation error, root uniqueness/stability evidence, a manufacturer operating region, commissioning/certification evidence, or an equipment-acceptance threshold.
- Bumped package/runtime metadata to v0.73.0.

## v0.72 bounded-bisection decision-trace provenance — 2026-09-24

- Retains every midpoint evaluation used by a successful bounded fan/system bisection solve, including the active signed-residual bracket, midpoint residual, normalized bracket width, and exact endpoint-replacement or tolerance-acceptance decision.
- Encodes the deterministic decision path as an auditable L/H/T sequence: replace the positive-residual low endpoint, replace the negative-residual high endpoint, or accept the midpoint on the configured pressure tolerance.
- Audits trace length against operating iterations, strict sign bracketing before every evaluation, arithmetic midpoint geometry, and terminal tolerance-decision placement.
- Propagates decision-trace evidence across nonlinear uncertainty corners with exact violation corner indices and tied source-corner provenance for the maximum retained trace length.
- Surfaces trace provenance in standalone fan-loop, nonlinear uncertainty, and engineering-dossier Markdown.
- Adds direct solver, uncertainty, and dossier regression coverage across Python 3.11, 3.12, and 3.13.
- Preserves v0.70 iteration-limit bisection provenance and v0.71 supplied-grid-resolution normalization without changing operating-point selection or no-extrapolation behavior.
- Treats the trace strictly as numerical implementation provenance; it is not physical airflow uncertainty, interpolation error, a continuous root guarantee, stability/stall/surge evidence, a manufacturer operating limit, commissioning/certification evidence, or an equipment-acceptance threshold.
- Bumped package/runtime metadata to v0.72.0.

## v0.71 supplied-grid resolution normalization — 2026-09-24

- Records minimum and maximum adjacent supplied fan-curve airflow spacing plus the max/min spacing ratio inside the nonlinear residual-topology audit.
- Normalizes each selected-to-alternative discrete candidate interval gap by the minimum adjacent supplied-point spacing, alongside the existing full-curve-span normalization.
- Aggregates the minimum sampling-resolution-normalized separation across uncertainty corners with exact tied source-corner provenance and the corresponding supplied-point spacing.
- Surfaces the new evidence in standalone nonlinear fan-loop and uncertainty Markdown.
- Adds direct solver and uncertainty regression coverage while preserving all existing no-extrapolation and unresolved-case withholding rules.
- Treats supplied-grid normalization strictly as sampled-data numerical topology evidence; it is not an interpolation-error estimate, continuous root-separation guarantee, physical robustness/stability margin, stall/surge criterion, manufacturer operating region, commissioning/certification result, or equipment-acceptance limit.
- Bumped package/runtime metadata to v0.71.0.

## v0.70 iteration-limit bisection provenance — 2026-09-24

- Preserves bounded-bisection search provenance when the configured operating-point iteration budget is exhausted before the pressure residual reaches tolerance.
- Retains the last evaluated midpoint/residual and the remaining active strict-sign bisection bracket, including width, half-width, supplied-segment-normalized width, completed contraction steps, and binary-width consistency evidence.
- Keeps iteration-limit outcomes explicitly non-converged with no accepted or fabricated operating point.
- Aggregates iteration-limit search evidence across nonlinear uncertainty corners, including exact affected corner indices, remaining-bracket invariant coverage, strict-sign violations, and maximum width-fraction consistency error with tied source provenance.
- Surfaces unresolved iteration-limit search geometry in standalone fan-loop, uncertainty, and engineering-dossier Markdown while keeping solved final-bracket evidence separate.
- Adds direct solver and uncertainty regression coverage across the supported Python matrix.
- Preserves v0.69 bidirectional sampled residual topology and all existing no-extrapolation, unresolved-case withholding, and solver-candidate rules.
- Treats remaining bracket geometry as numerical implementation/search evidence only; it is not physical airflow uncertainty, an interpolation-error bound, a continuous worst-case guarantee, a stability/stall/surge criterion, or an equipment-acceptance limit.
- Bumped package/runtime metadata to v0.70.0.

## v0.69 bidirectional sampled residual sign-change topology audit — 2026-09-24

- Retains strict negative-to-positive fan-minus-system residual sign-change segments across supplied fan-curve samples as explicit audit-only evidence.
- Keeps the operating-point solver unchanged: tolerance-contact points and strict positive-to-negative sign-change segments remain the only discrete solver candidates.
- Reports reverse sign-change segments per case, total bidirectional strict sign-change count, and uncertainty-corner reverse-crossing counts and exact corner indices.
- Surfaces the same audit-only evidence in standalone nonlinear fan-loop, uncertainty, and engineering-dossier Markdown.
- Adds regression coverage proving a reverse sampled crossing is visible in the audit while the solver candidate list remains empty for that feature.
- Preserves v0.68 scale-aware alternative-candidate separation, v0.67 bisection implementation-invariant auditing, and all no-extrapolation/unresolved-case withholding rules.
- Treats reverse sampled crossings as discrete numerical topology only; they do not establish an additional continuous root, dynamic stability, stall/surge behavior, manufacturer operating region, commissioning/certification result, or equipment-acceptance limit.
- Bumped package/runtime metadata to v0.69.0.

## v0.68 scale-aware alternative crossing-candidate separation — 2026-09-24

- Normalizes each v0.66 selected-to-alternative discrete candidate airflow gap by the exact supplied fan-curve airflow span used for that nonlinear solve.
- Retains the normalized fraction on every alternative candidate feature and on the nearest tied alternative evidence without evaluating or extrapolating any additional fan-curve point.
- Aggregates the minimum normalized separation across solved uncertainty corners with exact tied source-corner provenance and the corresponding supplied-curve airflow span.
- Surfaces absolute and normalized candidate separation in standalone fan-loop, nonlinear uncertainty, and engineering-dossier Markdown.
- Adds direct multi-candidate arithmetic tests plus uncertainty and dossier regression coverage.
- Preserves v0.67 bisection implementation-invariant auditing and all existing no-extrapolation and unresolved-case withholding rules.
- Treats normalized separation as sampled-data numerical topology evidence only; it is not a physical robustness margin, continuous root-separation guarantee, stability/stall/surge criterion, manufacturer operating region, commissioning/certification result, or equipment-acceptance limit.
- Bumped package/runtime metadata to v0.68.0.

## v0.67 bisection implementation-invariant audit — 2026-09-24

- Audits retained bounded-bisection search geometry directly from the unrounded live solver state without changing the operating-point solve.
- Records whether the active terminal bracket preserves the strict positive/negative residual sign change and whether the accepted airflow is the active bracket midpoint within a floating-point implementation comparison.
- Records completed binary contraction steps, the iteration-implied width fraction of the original supplied segment, the actual width fraction, and their absolute floating-point consistency error.
- Keeps the invariant audit inapplicable to direct supplied-point tolerance contacts rather than inventing bisection evidence.
- Aggregates invariant-evidence counts, exact sign/midpoint violation corner indices, and tied source-corner provenance for the maximum raw width-fraction consistency error.
- Surfaces invariant evidence in standalone fan-loop, nonlinear uncertainty, and engineering-dossier reports while preserving v0.66 alternative-candidate separation evidence.
- Adds solver, uncertainty, and dossier regression coverage.
- Treats these as implementation-verification diagnostics only; no engineering acceptance threshold, physical uncertainty, interpolation-error bound, stability criterion, or equipment limit is introduced.
- Bumped package/runtime metadata to v0.67.0.

## v0.66 alternative crossing-candidate separation audit — 2026-09-24

- Extends solved nonlinear fan/variable-friction crossing provenance with airflow separation to every additional discrete supplied-point candidate feature.
- Treats supplied-point tolerance contacts as point intervals and strict sign-change candidates as their exact supplied-point airflow intervals.
- Reports the selected airflow's gap to every alternative discrete candidate interval, including explicit zero-gap overlap, while retaining solver-priority rank and tied nearest alternatives.
- Aggregates alternative-separation coverage, overlap corner indices, and the minimum selected-to-alternative interval gap with exact tied source-corner provenance.
- Preserves v0.65 bounded root-search geometry and v0.64 pressure-residual airflow-equivalence evidence in standalone, uncertainty, and dossier reporting.
- Adds deterministic solver, uncertainty, and dossier regression coverage across Python 3.11, 3.12, and 3.13.
- Treats this as discrete sampled-data numerical topology evidence only; it does not estimate another continuous root, prove multiple physical intersections, or define stability, stall/surge, manufacturer-region, commissioning, certification, or equipment-acceptance criteria.
- Bumped package/runtime metadata to v0.66.0.

## v0.65 bounded operating-point root-search geometry — 2026-09-24

- Retains the final active signed-residual bisection interval immediately before a bounded nonlinear fan/system midpoint satisfies the configured operating-pressure tolerance.
- Records final bracket low/high airflow, signed endpoint residuals, width, half-width, selected midpoint/residual, iteration number, and width normalized by the original supplied interpolation-segment span.
- Distinguishes bounded-bisection solutions from direct supplied-point tolerance contacts; direct contacts preserve their selected supplied-point index and do not fabricate bisection evidence.
- Propagates operating-point search evidence through nonlinear uncertainty corners and aggregates method counts, complete solved-corner coverage, and worst final bracket width/half-width/normalized width with exact tied source-corner provenance.
- Surfaces final root-search geometry in standalone fan-loop, nonlinear uncertainty, and engineering-dossier Markdown.
- Adds direct solver, uncertainty, partial-coverage, and dossier regression coverage.
- Treats bracket width and half-width strictly as numerical search-geometry evidence, not physical airflow uncertainty, interpolation-error bounds, continuous worst-case guarantees, or equipment-acceptance limits.
- Bumped package/runtime metadata to v0.65.0.

## v0.64 pressure-residual airflow-equivalence audit — 2026-09-24

- Maps the already configured operating-pressure solver tolerance through each solved corner's local fan-minus-system secant gradient into an equivalent airflow magnitude.
- Maps each corner's actual signed solved pressure residual through the same local gradient into absolute airflow-equivalent residual and signed linearized airflow-correction evidence.
- Normalizes both equivalents by the active supplied-point interpolation-bracket airflow span for scale-aware diagnostics.
- Aggregates worst evaluated equivalents with exact tied source-corner provenance and explicit complete-versus-partial coverage.
- Reuses existing supplied-point bracket and crossing-conditioning evidence only; no extra fan-curve evaluation, extrapolation, or new acceptance threshold is introduced.
- Treats the values as first-order numerical solver diagnostics, not measurement uncertainty, fan-performance uncertainty, interpolation-error bounds, continuous worst-case guarantees, stability criteria, or equipment acceptance limits.
- Surfaces the new evidence in standalone Markdown and engineering dossiers and adds complete/zero-solved-corner regression coverage.
- Bumped package/runtime metadata to v0.64.0.

## v0.63 selected crossing-candidate provenance — 2026-09-24

- Orders discrete supplied-point crossing candidates using the nonlinear solver's actual selection policy: tolerance-contact fan points first in point order, followed by strict positive-to-negative sign-change segments in segment order.
- Records the exact selected candidate for every solved nonlinear fan/variable-friction case, including candidate kind, zero-based solver-priority rank, additional candidate count, and whether the selected sampled feature is the only discrete candidate.
- Leaves selected-candidate fields unset for no-intersection and non-converged cases rather than fabricating a choice.
- Propagates selected-candidate provenance through nonlinear uncertainty corners and aggregates selected-evidence coverage, first-priority-selection coverage, and exact solved-corner indices where additional discrete candidates remain.
- Surfaces the selection policy and selected-candidate evidence in standalone reports while extending engineering-dossier residual-topology summaries.
- Adds deterministic regression coverage for multiple synthetic discrete candidates and for repository example/uncertainty/dossier propagation.
- Preserves the independently added v0.62 interpolation-segment position audit.
- Treats this as deterministic sampled-data solver-choice provenance only; it does not prove continuous physical intersection count or uniqueness and does not define dynamic stability, stall/surge, manufacturer-region, commissioning, certification, or equipment-acceptance criteria.
- Bumped package/runtime metadata to v0.63.0.

## v0.62 fan-curve interpolation segment-position audit — 2026-09-24

- Adds per-solved-corner evidence for the exact supplied fan-curve interpolation segment containing the nonlinear operating point.
- Reports segment airflow span, lower/upper supplied-point clearance, nearest supplied segment endpoint, normalized segment position, and normalized nearest-endpoint clearance.
- Aggregates minimum absolute/normalized supplied-point clearance and maximum active segment span with exact tied source-corner provenance.
- Preserves complete-versus-partial coverage explicitly; unresolved corners do not receive fabricated segment-position evidence.
- Surfaces the same evidence in standalone nonlinear uncertainty Markdown and engineering-dossier tables.
- Adds regression coverage for arithmetic, extrema provenance, reporting, dossier propagation, and zero-solved-corner behavior.
- Treats supplied-point proximity as interpolation-geometry provenance only; it is not an interpolation-error estimate, uncertainty bound, stall/surge margin, manufacturer operating region, or equipment-acceptance threshold.
- Bumped package/runtime metadata to v0.62.0.

## v0.61 supplied-point residual-topology audit — 2026-09-24

- Adds a discrete fan-minus-system residual-topology audit to the nonlinear fan/variable-friction operating-point solver using the supplied fan-curve points already evaluated during bounded root search.
- Records expected/evaluated point counts, complete versus partial point coverage, tolerance-contact points, strict sign-change segments, residual transitions, sampled monotonic non-increasing behavior within the configured pressure tolerance, and the largest positive residual increase.
- Preserves partial audit evidence when network evaluation becomes non-converged instead of implying that all supplied fan points were checked.
- Propagates the audit into every nonlinear uncertainty corner and aggregates complete point coverage, sampled-monotonicity counts, residual-increase corner indices, multiple discrete candidate-feature corner indices, and tied source provenance for the largest positive residual increase when present.
- Surfaces the evidence in standalone nonlinear-loop reports, uncertainty reports, and engineering-dossier tables.
- Adds regression coverage for solved, no-intersection, non-converged, uncertainty-corner, and dossier paths.
- Explicitly states that candidate crossing features and sampled residual monotonicity are not a count or proof of continuous physical intersections, dynamic stability, stall/surge limits, manufacturer operating region, or equipment acceptance.
- Bumped package/runtime metadata to v0.61.0.

## v0.60 fan/system local crossing-conditioning audit — 2026-09-24

- Derives fan-pressure, system-pressure, and signed fan-minus-system secant slopes from each solved corner's existing supplied-point intersection bracket.
- Reports absolute residual-gradient magnitude plus the reciprocal local airflow-per-pressure gradient when the bracket residual slope is nonzero.
- Computes the straight-line secant-root airflow and its absolute/normalized difference from the solved nonlinear operating airflow without any extra fan-curve evaluation or extrapolation.
- Aggregates minimum absolute residual slope and maximum secant-root disagreement with exact tied source-corner provenance.
- Preserves partial diagnostic evidence for indeterminate studies while keeping complete-study coverage explicit.
- Surfaces the same evidence in standalone Markdown and engineering-dossier tables.
- Adds regression coverage for arithmetic, provenance, report output, dossier propagation, and zero-solved-corner behavior.
- Treats the new quantities as numerical root-conditioning diagnostics only; no dynamic stability, stall/surge, manufacturer-region, commissioning, certification, or equipment-acceptance threshold is inferred.
- Bumped package/runtime metadata to v0.60.0.

## v0.59 fan/system intersection-bracket provenance — 2026-09-24

- Retains the exact supplied fan-curve interpolation endpoints that bound every solved nonlinear uncertainty operating point.
- Preserves endpoint fan pressure, system pressure, and signed fan-minus-system residual without any new solver evaluation or fan-curve extrapolation.
- Distinguishes strict sign-change brackets from supplied-point/root contacts that are within the configured operating-pressure tolerance.
- Aggregates solved-corner bracket coverage plus minimum nearest-endpoint pressure-gap and endpoint-residual-span evidence with exact tied source-corner provenance.
- Includes the new bracket evidence inside the existing canonical SHA-256 nonlinear-result integrity scope.
- Preserves v0.58 complete per-metric power-coverage auditing and its withholding rules for partial metrics.
- Surfaces the new evidence in standalone Markdown, engineering dossiers, and nonlinear uncertainty documentation.
- Adds regression coverage for complete studies and zero-solved-corner/indeterminate studies.
- Treats bracket evidence as numerical root-enclosure provenance only; it is not a stall/surge, manufacturer operating-region, commissioning, certification, or equipment-acceptance margin.
- Bumped package/runtime metadata to v0.59.0.

## v0.58 complete per-metric power-coverage audit — 2026-09-24

- Requires every evaluated solved corner to provide a power metric before CleanroomX emits that metric's min/max range, extrema provenance, or nominal-relative excursion.
- Adds explicit `complete`, `partial`, and `unavailable` coverage states with available/total corner counts and exact missing corner indices for fluid air power, shaft power, electrical input, and specific fan power.
- Exposes the nominal solver power record directly as `nominal_power_evidence`.
- Prevents a partially populated power metric from being summarized as though it covered the complete deterministic corner study.
- Surfaces electrical-input and SFP coverage states in engineering-dossier Markdown and all power-metric coverage states in standalone uncertainty reports.
- Preserves v0.57 deterministic result-integrity evidence plus v0.56 solver-iteration budget evidence and earlier bounded-solver diagnostics.
- Adds regression coverage for partial metric coverage, missing explicit efficiencies, complete coverage, nominal power evidence, and report output.
- Bumped package/runtime metadata to v0.58.0.

## v0.57 deterministic nonlinear result integrity — 2026-09-24

- Adds a canonical SHA-256 digest to every fan/variable-friction nonlinear uncertainty result.
- Hashes the complete result before the integrity block using compact UTF-8 JSON with sorted keys, explicit canonicalization metadata, and a versioned scope identifier.
- Keeps result-integrity evidence separate from engineering acceptance: the digest identifies exact computed content but does not authenticate source authority, calibration, certification, or equipment suitability.
- Surfaces the full result digest in standalone uncertainty Markdown and engineering dossiers.
- Adds dossier summary counts for present/missing nonlinear result-integrity records without changing existing engineering status decisions.
- Adds regressions that independently recompute the digest, verify deterministic repeatability, verify input-sensitive changes, and confirm dossier propagation.
- Bumped package/runtime metadata to v0.57.0.

## v0.56 configured solver-iteration budget audit — 2026-09-24

- Exposes the selected operating network's inner Newton iteration count alongside the existing outer Darcy-friction and operating-point iteration diagnostics.
- Aggregates worst solved-corner outer, Newton, and operating-point iteration counts with exact tied source-corner provenance.
- Preserves the study's existing `max_outer_iterations`, `max_newton_iterations`, and `max_operating_iterations` settings as explicit configured iteration limits.
- Reports utilization ratio and remaining iterations for each configured solver iteration budget, with a separate complete/partial aggregate audit state.
- Keeps the v0.52 residual-tolerance audit unchanged while preserving v0.53 nominal-relative excursions, v0.54 fan-curve boundary clearance, and v0.55 no-intersection endpoint diagnostics.
- Treats iteration-budget utilization strictly as numerical convergence evidence, not an equipment, commissioning, certification, or cleanroom acceptance margin.
- Surfaces the new audit in standalone Markdown and engineering-dossier reporting and adds regression coverage for complete and zero-solved-corner studies.
- Bumped package/runtime metadata to v0.56.0.

## v0.55 no-intersection supplied-endpoint diagnostics — 2026-09-24

- Adds explicit supplied-endpoint diagnostics for nonlinear uncertainty corners whose fan/system operating point does not intersect inside the available fan-curve range.
- Identifies whether each unresolved case is bounded by the lower or upper supplied airflow endpoint and records the endpoint airflow, fan pressure, system pressure, signed fan-minus-system pressure margin, mismatch type, and absolute pressure gap.
- Aggregates lower-boundary and upper-boundary no-intersection counts and retains tie-aware source-corner provenance for the largest evaluated endpoint pressure gap.
- Preserves the strict no-extrapolation boundary: the diagnostic does not estimate a missing operating point, fan capacity beyond supplied data, stall/surge margin, manufacturer operating region, or equipment acceptance.
- Surfaces no-intersection boundary evidence in standalone Markdown reports, engineering-dossier tables, and dossier executive summaries.
- Adds regression coverage for both lower-boundary fan-pressure-deficit and upper-boundary fan-pressure-surplus cases plus dossier aggregation.
- Bumped package/runtime metadata to v0.55.0.

## v0.54 supplied fan-curve boundary-clearance audit — 2026-09-24

- Adds per-solved-corner airflow distance from the operating point to both endpoints of that corner's exact supplied or speed-transformed fan-curve airflow range.
- Reports lower, upper, and nearest endpoint headroom in m³/h together with normalized airflow position, normalized nearest-boundary headroom, and the nearest endpoint identity.
- Aggregates the minimum nearest-boundary headroom across solved evaluated corners with tie-aware source-corner provenance and preserves the exact active fan/system/duct uncertainty context.
- Keeps boundary-clearance evidence explicitly diagnostic: no minimum acceptable headroom, stall/surge margin, manufacturer operating region, or equipment-acceptance criterion is inferred.
- Marks complete versus partial study coverage independently, so indeterminate analyses may retain solved-corner diagnostic evidence without fabricating a complete uncertainty envelope.
- Surfaces the new evidence in standalone Markdown reports and engineering-dossier tables, with regression coverage for exact arithmetic, provenance, zero-solved-corner behavior, and dossier integration.
- Bumped package/runtime metadata to v0.54.0.

## v0.53 nominal-relative corner excursion evidence — 2026-09-24

- Adds nominal-centered absolute and percentage excursion evidence for complete nonlinear fan/variable-friction uncertainty operating-point envelopes.
- Covers operating airflow, fan pressure, system pressure, and fan air power, plus available fluid/shaft/electrical/SFP power-chain ranges.
- Percentage excursion is withheld when the solved nominal value is effectively zero rather than inventing an unstable denominator.
- Keeps excursions conditional on complete corner coverage; indeterminate studies emit no nominal-relative envelope evidence.
- Explicitly treats the new values as evaluated-corner summaries rather than sensitivity coefficients or guarantees about continuous interior extrema.
- Surfaces operating-point excursions in standalone Markdown reports and a compact airflow-excursion column in engineering dossiers.
- Adds regression coverage for excursion arithmetic, power-chain availability, reporting, dossier integration, and indeterminate withholding.
- Bumped package/runtime metadata to v0.53.0.

## v0.52 configured solver-tolerance utilization audit — 2026-09-24

- Extends nonlinear fan/variable-friction uncertainty solver-quality evidence with explicit checks against the operating-pressure, resistance-closure, and mass-balance tolerances already configured for the solver.
- Reports each worst solved-corner metric's configured tolerance, utilization ratio, and remaining numerical margin without introducing any new acceptance threshold.
- Adds an aggregate status that distinguishes complete within-tolerance coverage, incomplete study coverage, unavailable checks, and any detected configured-tolerance exceedance.
- Keeps pressure-law residual and iteration counts as diagnostics only because the workflow has no configured acceptance threshold for those quantities.
- Surfaces the configured solver-tolerance audit in standalone Markdown reports and integrated engineering-dossier tables.
- Adds regression coverage for complete studies, zero-solved-corner studies, utilization/margin arithmetic, report output, and dossier integration.
- Bumped package/runtime metadata to v0.52.0.

## v0.51 aggregate nonlinear solver-quality evidence — 2026-09-24

- Added a compact solver-quality summary across nonlinear fan/variable-friction uncertainty corners.
- Reports worst solved-corner absolute operating-pressure residual, Darcy resistance-closure error, mass-balance residual, pressure-law residual, network outer iterations, and operating-point iterations.
- Retains every tied source corner for each worst metric, including active fan/system/duct uncertainty context and the observed signed value where applicable.
- Preserves configured pressure, resistance-closure, and mass-balance tolerances without inventing thresholds for pressure-law residual or iteration counts.
- Distinguishes evaluated-corner coverage from complete-study coverage, including nominal-case status, so partial evidence is not presented as complete verification.
- Extended Markdown reporting and regression coverage for complete and zero-solved-corner studies.
- Bumped package/runtime metadata to v0.51.0.

## v0.50 efficiency-chain power corner evidence — 2026-09-24

- Preserves each solved nonlinear uncertainty corner's existing fan-side power evidence instead of discarding it after the operating-point solve.
- Adds complete-study evaluated-corner ranges for fluid air power, shaft power, electrical input, and specific fan power.
- Adds tie-aware source-corner attribution for every available power-chain lower/upper extreme using the same active fan/system/duct input context as other extrema witnesses.
- Reports shaft power only with an explicit fan efficiency, and electrical input / specific fan power only with explicit fan, motor, and VFD efficiencies; no efficiency is inferred.
- Keeps efficiency values fixed in this workflow rather than silently treating them as uncertain inputs.
- Withholds complete power-chain ranges and extrema witnesses whenever any nonlinear uncertainty corner is unresolved.
- Adds standalone Markdown and engineering-dossier reporting plus regression coverage for exact source resolution, missing-efficiency behavior, indeterminate withholding, and dossier columns.
- Bumped package/runtime metadata to v0.50.0.

## v0.49 evaluated-corner air-power envelope and provenance — 2026-09-24

- Added fan air-power min/max across every solved nonlinear uncertainty corner in complete studies.
- Extends compact first-witness operating-point extrema and tie-aware source attribution to `air_power_kw`.
- Markdown uncertainty reports now surface nominal air power, bounded evaluated-corner air-power range, critical cases, and witness provenance.
- Engineering dossier uncertainty tables now include the complete-study air-power corner range.
- Keeps the result explicitly bounded to evaluated corners: no continuous interior extremum, equipment efficiency, motor/VFD acceptance, or manufacturer guarantee is inferred from the corner range.
- Indeterminate studies continue to withhold the complete operating-point envelope, including air power.
- Added exact-corner regression coverage for air-power calculation, witnesses, reports, and dossier integration.
- Bumped package/runtime metadata to v0.49.0.

## v0.48 tie-aware internal edge-flow extrema provenance — 2026-09-24

- Added tie-aware source attribution for every internal edge-airflow lower/upper extremum in complete nonlinear uncertainty studies.
- Each edge extremum now preserves every evaluated corner sharing the same extreme value, including fixed pressure, fan speed/scenario, fan-point overrides, and duct physical/geometry overrides.
- Retains the existing compact first-witness edge corner indices for backward-compatible direct lookup.
- Keeps edge extrema-source evidence conditional on a complete study; indeterminate studies continue to emit neither complete edge-flow ranges nor fabricated edge witnesses.
- Markdown reports now include an internal edge-airflow witness-provenance table.
- Added regression coverage for exact source-corner resolution, tied whole-curve scenarios, report output, and indeterminate withholding.
- Bumped package/runtime metadata to v0.48.0.

## v0.47 uncertainty corner outcome diagnostics — 2026-09-24

- Added deterministic status accounting across every evaluated nonlinear fan/variable-friction uncertainty corner.
- Records solver termination-reason counts directly from each corner's existing solver diagnostics.
- Adds exact unresolved corner indices plus their fixed-pressure, fan-speed/scenario, fan-point, and duct uncertainty input context.
- Keeps unresolved-corner evidence diagnostic only: indeterminate studies still emit no complete operating-point or internal edge-flow envelope.
- Markdown reports now surface status/termination summaries and a compact unresolved-corner table.
- Added regression coverage for both all-solved accounting and indeterminate corner traceability.
- Bumped package/runtime metadata to v0.47.0.

## v0.46 uncertainty envelope witness provenance — 2026-09-23

- Added exact evaluated-corner witnesses for nonlinear uncertainty operating-point minima and maxima.
- Preserves the compact zero-based first-witness corner index/value for each airflow, fan-pressure, and system-pressure envelope bound.
- Adds tie-aware `operating_point_extrema_sources` evidence that records every evaluated corner sharing an extremum, including its fixed pressure, configured fan speed/scenario, and any active fan-point or duct physical/geometry overrides.
- Extended every internal edge-airflow range with the exact lower/upper corner indices that produced those extrema.
- Keeps all witness evidence conditional on a complete envelope; indeterminate analyses do not fabricate extreme-case attribution.
- Markdown uncertainty reports now include an envelope-witness provenance table and internal edge-airflow witness table, while JSON retains direct indices into the full corner evidence array.
- Added regression coverage that resolves every operating-point and edge-flow witness back to the exact reported corner value and verifies the richer source attribution.
- Bumped package/runtime metadata to v0.46.0.

## v0.45 correlated whole fan-curve scenarios — 2026-09-23

- Added explicit named whole fan-curve scenarios to nonlinear fan/variable-friction uncertainty analysis so point-to-point dependence can be preserved instead of forcing independent Cartesian point perturbations.
- Evaluates the nominal supplied curve plus each configured scenario as complete curves, crossed only with the configured fixed-pressure, fan-speed, and duct physical/geometry uncertainty dimensions.
- Allows whole-curve scenarios to combine with bounded fan-speed ratio using the existing affinity-law transform before each complete nonlinear loop solve.
- Makes whole-curve scenarios mutually exclusive with independent fan-point pressure/airflow-coordinate bounds, preventing accidental mixing of correlated and independent fan-performance models.
- Validates scenario fan curves through the existing nonnegative, strictly increasing airflow and non-increasing pressure requirements; rejects duplicate names and reserves `nominal` for the baseline curve.
- Includes scenario count in the pre-materialization `max_corner_cases` guard, preserves per-scenario provenance, reports scenario identity in Markdown/JSON corner evidence, and adds standalone plus dossier regression coverage.
- Added `examples/fan_variable_friction_curve_scenarios_demo.json` and bumped package/runtime metadata to v0.45.0.

## v0.44 bounded fan-speed ratio uncertainty — 2026-09-23

- Added an optional user-supplied fan speed-ratio interval to nonlinear fan/variable-friction corner analysis.
- Builds each bounded reference fan curve from configured point-pressure/airflow-coordinate bounds, then reuses the existing CleanroomX affinity-law transform before solving the complete nonlinear loop.
- Scales airflow with speed ratio and pressure with speed ratio squared while preserving the transformed supplied-data range and strict no-extrapolation behavior.
- Keeps the new input fully opt-in so legacy uncertainty studies retain their prior fan-curve naming, provenance completeness, corner counts, and solver behavior when no speed ratio is configured.
- Rejects speed-ratio intervals whose lower bound is not strictly positive and includes configured speed bounds in the pre-materialization corner-limit check.
- Added JSON loading, Markdown corner evidence, a reproducible speed-uncertainty example, and regression coverage.
- Bumped package/runtime metadata to v0.44.0.

## v0.43 bounded fan-curve airflow-coordinate uncertainty — 2026-09-23

- Extended nonlinear fan/variable-friction corner analysis to user-supplied absolute airflow-coordinate bounds at selected supplied fan-curve point indices.
- Keeps nominal airflow coordinates single-sourced in the supplied fan curve; uncertainty entries identify an existing zero-based point index and provide only an absolute airflow bound plus optional provenance.
- Combines fan-airflow corners with fan-pressure, fixed-pressure, and duct physical/geometry uncertainty dimensions, then re-solves the complete nonlinear Darcy-friction network at every corner.
- Rejects negative airflow intervals, unknown/duplicate point indices, repeated nominal airflow values, and any interval combination capable of producing non-increasing supplied airflow coordinates.
- Preserves strict supplied fan-curve range behavior: no extrapolation is introduced, and unresolved corners suppress a complete envelope.
- Added Markdown evidence, a reproducible airflow-coordinate uncertainty example, provenance tracking, regression coverage, and package metadata alignment.
- Enforces `max_corner_cases` before materializing any Cartesian products, preventing rejected high-dimensional studies from allocating oversized intermediate combination lists.
- Bumped package/runtime metadata to v0.43.0.

## v0.42 bounded fan-curve point pressure uncertainty — 2026-09-23

- Extended nonlinear fan/variable-friction corner analysis to user-supplied absolute pressure bounds at selected supplied fan-curve airflow points.
- Keeps nominal point pressure single-sourced in the fan curve; uncertainty entries identify an existing airflow coordinate and provide only an absolute pressure bound plus optional provenance.
- Combines fan-pressure corners with fixed-pressure and duct physical/geometry uncertainty dimensions, then re-solves the complete nonlinear Darcy-friction network at every corner.
- Rejects negative pressure intervals, unknown/duplicate airflow-point references, repeated nominal pressures, and any interval combination capable of making pressure increase with airflow.
- Preserves the supplied airflow coordinates and strict no-extrapolation fan boundary.
- Added Markdown evidence, a reproducible fan-curve uncertainty example, provenance tracking, and regression coverage.
- Bumped package/runtime metadata to v0.42.0.

## v0.41 bounded rectangular duct-geometry uncertainty — 2026-09-23

- Preserves explicit circular diameter and rectangular width/height in geometry-derived loop-resistance evidence.
- Extends nonlinear fan/variable-friction corner analysis to user-supplied absolute rectangular width and height bounds.
- Rebuilds rectangular area, hydraulic diameter, Reynolds/friction evidence, and resistance at every geometry corner before each complete nonlinear fan/network solve.
- Rejects shape-mismatched dimension bounds, nonpositive dimensional intervals, repeated nominal values, and geometry corners whose minimum hydraulic diameter would not exceed the maximum bounded roughness.
- Added per-corner rectangular dimension evidence, Markdown reporting, a reproducible rectangular example, and regression coverage.
- Bumped package/runtime metadata to v0.41.0.

## v0.40 bounded nonlinear duct-geometry uncertainty — 2026-09-23

- Extended nonlinear fan/variable-friction corner analysis to user-supplied absolute bounds on automatic-friction duct length and circular-duct diameter.
- Rebuilds affected duct geometry and Darcy evidence at every geometry corner before every complete nonlinear fan/network solve; no fixed-equivalent-resistance shortcut is introduced.
- Keeps nominal geometry single-sourced in loop-network evidence and rejects repeated nominal values in uncertainty blocks.
- Rejects nonpositive bounded lengths/diameters and diameter ranges that would make the maximum bounded roughness reach or exceed the minimum bounded diameter.
- Keeps rectangular width/height uncertainty outside scope because current stored rectangular evidence does not preserve an unambiguous dimension orientation.
- Added interval/provenance reporting, per-corner geometry evidence, Markdown output, a reproducible geometry example, and regression coverage.
- Bumped package/runtime metadata to v0.40.0.

## v0.39 bounded physical Darcy-input uncertainty — 2026-09-23

- Extended nonlinear fan/variable-friction corner analysis to user-supplied absolute bounds on automatic-friction edge roughness, kinematic viscosity, and air density while retaining fixed-pressure and local-loss K uncertainty.
- Rebuilds affected duct-geometry evidence at every physical-input corner before every complete nonlinear fan/network solve; no frozen equivalent-resistance shortcut is introduced.
- Keeps nominal physical values single-sourced in loop-network geometry and rejects repeated nominals in uncertainty blocks.
- Rejects nonphysical bounded intervals: negative roughness/local K, nonpositive viscosity/density, and roughness reaching the hydraulic diameter.
- Added per-corner physical-input evidence, interval/provenance reporting, Markdown output, a reproducible physical-input example, and regression coverage.
- Replaced the stale duplicate uncertainty-model definition with a compatibility re-export of the canonical study model.
- Bumped package/runtime metadata to v0.39.0.

## v0.38 dossier-integrated nonlinear fan / loop uncertainty — 2026-09-23

- Integrated v0.37 fan/variable-friction loop uncertainty analyses into engineering dossier manifests.
- Added SHA-256 source fingerprints, executive-summary analysis/corner counts, full JSON evidence retention, and Markdown corner-envelope reporting.\n- Extended HVAC-to-fan operating-airflow consistency to every evaluated nonlinear uncertainty corner; unresolved corners remain `not_comparable` and never receive fabricated airflow values.
- Propagates indeterminate nonlinear uncertainty analyses into dossier attention while tracking missing uncertainty provenance separately as unresolved traceability.
- Extends optional HVAC/fan operating-airflow consistency to every evaluated nonlinear uncertainty corner; unresolved or non-converged corners remain not comparable.
- Preserves the v0.37 numerical boundary: every corner still uses the complete nonlinear Darcy-friction fan/loop solver, and unresolved corners never produce a complete envelope.
- Added a reproducible dossier manifest plus end-to-end, adverse-state, missing-provenance, missing-source, and deterministic-output regression coverage.
- Bumped package/runtime metadata to v0.38.0.

## v0.37 nonlinear fan / variable-friction uncertainty — 2026-09-23

- Added deterministic bounded corner analysis around the v0.33 nonlinear fan/variable-friction loop solver.
- Supports explicit absolute uncertainty on fixed system pressure and selected automatic-friction duct local-loss coefficients without duplicating nominal K values outside the loop geometry.
- Rebuilds affected geometry-edge evidence and re-solves the complete Darcy-friction network at every bounded fan/system evaluation for every corner.
- Preserves strict supplied-range fan behavior; no-intersection and numerical non-convergence make the uncertainty result indeterminate and suppress complete operating-point/edge-flow envelopes.
- Tracks fan-curve, fixed-pressure, and local-loss uncertainty provenance separately from numerical solution status.
- Deduplicates zero-width uncertainty dimensions and enforces an explicit max_corner_cases limit instead of silently truncating combinations.
- Added JSON loading, Markdown/JSON reporting, the cleanroomx-fan-loop-friction-uncertainty CLI, reproducible example data, documentation, and regression coverage.
- Bumped package/runtime metadata to v0.37.0.

## v0.36 nonlinear-network validation hardening — 2026-09-23

- Added pre-solve validation for every loop edge identified as automatic Darcy-friction geometry.
- Requires complete stored geometry, density/local-loss, roughness, kinematic-viscosity, positive reference-airflow, hydraulic-diameter/area, and positive stored friction-factor evidence.
- Reconstructs the stored automatic-friction calculation at the declared reference airflow before iteration so malformed provenance cannot be hidden by a near-zero-flow freeze.
- Added regression coverage for incomplete, zero, NaN, and infinite stored automatic-friction evidence.
- Retains intentional parallel physical paths; existing connected-graph, self-loop, injection-balance, two-terminal fan-boundary, and finite solver-control validation remains unchanged.
- Bumped package/runtime metadata to v0.36.0.

## v0.35 dossier-integrated nonlinear fan / loop workflows — 2026-09-23

- Integrated v0.33 fan/variable-friction loop studies and v0.34 fan-speed/variable-friction loop studies into dossier manifests.
- Added SHA-256 source fingerprints, full JSON evidence retention, executive-summary counts, and Markdown solver diagnostics for both nonlinear workflow families.
- Propagates both bounded no-intersection and numerical `non_converged` cases into dossier attention; numerical non-convergence is never reported as PASS.
- Extended HVAC-to-fan operating-airflow consistency to solved nonlinear loop and nonlinear speed cases while preserving unresolved/non-converged cases as not comparable.
- Added a combined reproducible dossier example plus end-to-end, deterministic-fingerprint, missing-source, adverse-state, and cross-consistency regression coverage.
- Bumped package/runtime metadata to v0.35.0.

## v0.34 fan-speed / variable-friction loop coupling — 2026-09-23

- Added explicit affinity-law fan-speed studies over the v0.33 bounded fan/variable-friction loop solver.
- Reuses `scale_fan_curve_for_speed` for every configured speed ratio; no fan-scaling equations are duplicated.
- Re-solves the complete loop and Darcy-friction closure at every transformed fan-curve point and bounded operating-point airflow.
- Preserves transformed fan-curve bounds with no extrapolation and reports solved, `no_intersection_in_supplied_range`, and `non_converged` states independently per speed.
- Reports optional rpm, operating airflow/pressure, signed network edge flows, Reynolds/friction evidence, resistance closure, continuity, edge-law residuals, and fan/system residuals.
- Added JSON loading, Markdown/JSON reporting, the `cleanroomx-fan-loop-friction-speed` CLI, example data, documentation, and fixed-resistance compatibility/non-convergence regression coverage.
- Bumped package and runtime metadata to v0.34.0.

## v0.33 bounded fan / variable-friction loop coupling — 2026-09-23

- Added direct coupling between supplied fan pressure/airflow data and the v0.30 variable-friction two-terminal loop solver.
- Re-solves the complete loop and updates automatic Darcy friction at every supplied fan point and every bounded operating-point bisection airflow instead of reducing the system to one fixed equivalent quadratic resistance.
- Preserves strict no-extrapolation behavior for fan data and reports `no_intersection_in_supplied_range` when no bounded crossing exists.
- Adds explicit `non_converged` results when variable-friction network closure or bounded operating-point iteration cannot satisfy configured limits; no fabricated operating point is emitted.
- Reports fan/system residuals, network continuity and edge-law residuals, Darcy resistance-closure evidence, iteration diagnostics, and fluid air power.
- Keeps explicit-resistance and user-supplied-friction edges fixed while iterating only geometry edges configured with roughness and kinematic viscosity.
- Added validated JSON solver controls, Markdown/JSON reporting, the `cleanroomx-fan-loop-friction` CLI, a reproducible example, focused regression tests, and engineering-boundary documentation.
- Added a fixed-resistance compatibility regression against the existing v0.26 fan/loop solver.
- Bumped package and runtime metadata to v0.33.0 while retaining the v0.32 dossier integrations.


## v0.32 dossier-integrated fan/loop uncertainty and speed studies — 2026-09-23

- Integrated bounded fan/loop-network uncertainty analyses into engineering dossier manifests with SHA-256 source fingerprints, executive summaries, Markdown reporting, and full JSON evidence preservation.
- Propagates indeterminate fan/loop uncertainty corners into dossier attention state while tracking missing uncertainty provenance separately as unresolved traceability.
- Integrated fan-speed/fixed-resistance-loop studies into dossier manifests with per-speed operating points, internal-network continuity evidence, fan/system residuals, and source fingerprints.
- Extended HVAC-to-fan operating-airflow consistency to fan-speed/loop-network cases; unresolved transformed-curve intersections remain not comparable rather than becoming failures.
- Added an end-to-end combined dossier example, missing-source and deterministic-fingerprint regression coverage, and adverse-state summary tests.
- Bumped package/runtime metadata to v0.32.0 without changing the underlying v0.29 or v0.31 numerical solvers.


## v0.31 bounded fan / loop-network uncertainty — 2026-09-23

- Added deterministic lower/upper corner analysis around the v0.26 passive two-terminal fan/loop-network workflow while preserving v0.29 fan-speed loop studies and v0.30 variable-friction loop solving.
- Supports explicit absolute uncertainty on fixed system pressure and on any named fixed loop-edge quadratic resistance without duplicating nominal resistance values outside the loop-network input.
- Rebuilds and solves every unique configured corner, derives each corner's equivalent loop resistance, intersects it with supplied fan data without extrapolation, and re-solves the complete loop when bounded.
- Reports operating-airflow/system-pressure and internal edge-flow min/max across evaluated corners only when the nominal case and every corner are solved; unresolved corners make the analysis `indeterminate`.
- Preserves adjusted-edge provenance and per-corner solver residuals; internal edge-flow corner ranges are diagnostic evaluated-corner evidence rather than claimed continuous-interval extrema.
- Deduplicates zero-width uncertainty dimensions and rejects analyses exceeding the explicit `max_corner_cases` limit (default 256) instead of silently truncating the uncertainty space.
- Tracks fan-curve, fixed-pressure, and configured edge-resistance uncertainty provenance separately from numerical solution status.
- Added JSON loading, Markdown/JSON reporting, the `cleanroomx-fan-loop-uncertainty` CLI, example data, documentation, and regression tests.
- Bumped package/runtime metadata to v0.31.0.

## v0.30 variable-friction loop solving — 2026-09-23

- Added an optional outer iteration around the validated fixed-resistance loop solver for geometry-derived edges configured with automatic Darcy friction.
- Recomputes Reynolds number and Darcy friction from each automatic edge's absolute solved airflow, then rebuilds the Darcy-Weisbach plus local-K quadratic resistance.
- Supports configurable resistance-closure tolerance, friction-factor update relaxation, outer-iteration limits, and inner mass-balance/Newton tolerances.
- Preserves direct resistance inputs and geometry edges with user-supplied friction factors as fixed.
- Explicitly freezes automatic-friction edges at configured near-zero airflow instead of inventing Reynolds or friction values at zero velocity.
- Preserves the existing circular laminar 64/Re and turbulent Colebrook model; noncircular automatic laminar flow remains rejected explicitly.
- Added edge-level target/used resistance closure evidence, iteration history, Markdown/JSON reporting, the cleanroomx-loop-friction CLI, example data, documentation, and regression tests.
- Bumped package/runtime metadata to v0.30.0 while preserving v0.29 fan-speed/loop studies.

## v0.29 bounded fan-speed / loop-network study — 2026-09-23

- Added explicit fan-speed sweeps over passive two-terminal fixed-resistance loop networks.
- Reused the existing affinity-law fan-curve transform and v0.26 bounded fan/loop-network solver for every speed case rather than introducing a second operating-point implementation.
- Re-solves the original mesh at each bounded operating airflow and reports signed edge flows, node pressures, continuity/pressure-law residuals, equivalent-network residual, and fan/system residual.
- Preserves no-intersection cases without fan-curve extrapolation and reports the overall study as attention-required when any configured speed case is unresolved.
- Added optional reference-rpm reporting, JSON/Markdown reporting, the `cleanroomx-fan-loop-speed` CLI, example data, documentation, CLI regression coverage, and v0.29.0 metadata.
- Keeps variable-friction iteration, inferred VFD limits, motor/drive limits, controls, leakage, system effect, stall/surge acceptance, transients, and manufacturer selection outside scope.

## v0.28 loop-workflow dossier integration — 2026-09-23

- Integrated v0.26 fan/loop-network studies into engineering dossier manifests with SHA-256 source fingerprints, executive component summaries, Markdown reporting, and unresolved-intersection attention tracking.
- Integrated v0.27 explicit loop damper-resistance scenario studies into the same dossier workflow with case counts and baseline solver-residual evidence.
- Extended dossier HVAC-to-fan operating-airflow consistency so solved fan/loop-network operating points participate alongside standalone fan/system, reference-flow fan/duct, passive parallel-network, and fan-speed cases.
- Preserved unsolved fan/loop studies as unresolved/not-comparable in airflow consistency rather than converting them into failures.
- Added end-to-end dossier and consistency regression coverage plus an integrated loop-workflow dossier example.
- Bumped package/runtime metadata to v0.28.0 without changing the underlying fan, loop-network, or damper physical models.

## v0.27 explicit loop damper-resistance scenarios — 2026-09-23

- Added deterministic loop-network scenario studies for explicit user-supplied edge resistance multipliers.
- Solves the unchanged baseline plus each named throttling case with the existing fixed-resistance loop solver.
- Restricts configured multipliers to finite values greater than or equal to 1.0, representing added/throttled quadratic resistance rather than inferred damper position.
- Reports per-case adjusted resistance evidence, edge-flow redistribution versus baseline, and continuity/pressure-law residuals.
- Preserves the underlying explicit or geometry-derived resistance provenance inside each adjusted-edge evidence record.
- Added JSON loading, Markdown/JSON reporting, the `cleanroomx-damper-study` CLI, example data, documentation, regression tests, and v0.27.0 metadata.
- Keeps automatic balancing, actuator dynamics, damper K inference, control loops, leakage, and variable-friction iteration outside scope.

## v0.26 bounded fan / loop-network coupling — 2026-09-23

- Added two-terminal coupling between supplied fan curves and connected fixed-resistance loop networks.
- Derives an equivalent loop resistance from a reference through-flow solve, using the exact quadratic scaling of fixed `R·Q·|Q|` edges.
- Requires equal/opposite fan discharge and suction reference injections and zero external injection at every other node.
- Intersects `fixed_pressure + R_eq·Q²` with the supplied fan curve without extrapolation, then re-solves the original loop at the operating airflow.
- Reports reference and operating network evidence, signed edge flows, node pressures, continuity/pressure-law residuals, equivalent-network residual, and fan/system residual.
- Reuses v0.25 explicit or geometry-derived loop edges unchanged; geometry/reference-flow friction remains frozen at its declared basis.
- Added JSON loading, Markdown/JSON reporting, the `cleanroomx-fan-loop` CLI, example data, documentation, and focused regression tests.
- Bumped package/runtime metadata to v0.26.0.

## v0.25 geometry-derived fixed loop resistance — 2026-09-23

- Added optional derivation of loop-edge quadratic resistance from explicit circular or rectangular duct geometry.
- Uses Darcy-Weisbach straight-duct friction plus an explicit local-loss coefficient: `R = 0.5·ρ·(fL/Dh + K)/A²`.
- Supports either a user-supplied Darcy friction factor or automatic friction from explicit roughness, kinematic viscosity, and reference airflow.
- Automatic friction is resolved once at the declared reference airflow; the derived resistance remains fixed during nonlinear loop balancing.
- Preserves explicit `resistance_pa_per_m3_s_squared` inputs unchanged and rejects ambiguous edges that provide both resistance sources.
- Adds resistance-basis and derivation evidence to JSON/Markdown loop reports.
- Added a geometry-derived loop example and regression coverage for circular/rectangular geometry, automatic friction, loader validation, reporting, and backward compatibility.
- Bumped package/runtime metadata to v0.25.0.

## v0.24 fan/system operating-point uncertainty — 2026-09-23

- Added deterministic bounded uncertainty analysis for user-supplied fixed system pressure and quadratic system resistance.
- Evaluates every unique lower/upper system-curve corner with the existing no-extrapolation fan/system solver.
- Reports a complete airflow/pressure operating-point envelope only when the nominal case and every bounded corner intersect the supplied fan curve; otherwise the analysis remains `indeterminate`.
- Keeps air power as nominal/corner evidence rather than labeling corner extrema as a conservative power envelope, because `Q × ΔP` can have an interior extremum along a fan-curve segment.
- Added fan-curve and system-input provenance tracking, Markdown/JSON reporting, the `cleanroomx-fan-uncertainty` CLI, example data, documentation, and regression tests.
- Integrated fan/system uncertainty into engineering dossiers with SHA-256 source traceability, attention-state handling, and missing-provenance tracking.
- Bumped package/runtime metadata to v0.24.0 while preserving v0.23.1 loop-network hardening.

## v0.23.1 loop-network injection-balance hardening — 2026-09-23

- Tightened loop-network global node-injection validation to a fixed absolute tolerance of 1e-6 m³/h.
- Removed flow-magnitude-relative scaling that could admit a materially nonzero net source/sink mismatch in very large-flow inputs.
- Added regression coverage proving a 0.1 m³/h imbalance is rejected even when opposing node flows are near 1e9 m³/h.
- Bumped package/runtime metadata to v0.23.1.

## v0.23 fixed-resistance looped airflow networks — 2026-09-23

- Added a connected steady-state pressure-node solver for airflow networks with arbitrary loops.
- Uses explicit fixed quadratic edge laws `ΔP = R·Q·|Q|` and balanced user-supplied node injections.
- Added spanning-tree initialization plus damped Newton/backtracking for nonlinear node-continuity solution.
- Reports signed reverse flow, relative node pressures, per-node mass-balance residuals, and per-edge pressure-law residuals.
- Validates finite positive resistances, balanced injections, unique edge names, valid node references, and graph connectivity.
- Added JSON loading, Markdown/JSON reporting, the `cleanroomx-loop-flow` CLI, example data, engineering-scope documentation, and regression tests.
- Preserves v0.21 automatic Darcy-friction screening and v0.22 dossier airflow-consistency work; looped networks remain explicit fixed-resistance models.
- Keeps looped-network geometry/friction inference, leakage, dampers, controls, fan coupling, compressibility, and transient behavior outside this bounded solver.
- Bumped package/runtime metadata to v0.23.0.

## v0.22 HVAC / fan operating-airflow consistency — 2026-09-23

- Added dossier-integrated comparison of HVAC total governing airflow against standalone fan/system, reference-flow fan/duct, passive parallel-network, and fan-speed operating points.
- Uses an explicit user-supplied absolute airflow tolerance; exact agreement remains the zero-tolerance default.
- Preserves unsolved fan studies and fan-speed cases as `not_comparable` rather than converting missing operating points into failures.
- Adds pass, fail, not-comparable, and pass-with-unresolved-studies states with per-operating-point evidence in Markdown/JSON dossiers.
- Propagates solved mismatches into dossier attention items and unresolved comparisons into unchecked tracking.
- Added focused unit tests, an end-to-end dossier example, documentation, and package/runtime version 0.22.0.
- Keeps the feature bounded as cross-study consistency, not airflow adequacy, fan selection, commissioning acceptance, cleanroom certification, or a standards-derived tolerance.

## v0.21 automatic Darcy friction screening — 2026-09-23

- Added optional roughness/kinematic-viscosity-driven Darcy friction-factor resolution for path-based duct models and fixed-demand supply trees.
- Computes Reynolds number from section velocity, hydraulic diameter, and explicit kinematic viscosity.
- Uses the Darcy laminar relation `f = 64/Re` for circular ducts below `Re = 2300` and solves the Colebrook equation for `Re >= 2300`.
- Rejects automatic laminar friction for noncircular ducts instead of applying the circular-duct relation; users can still supply an explicit friction factor.
- Preserves the existing explicit `friction_factor` workflow and rejects ambiguous manual-plus-automatic inputs.
- Resolves supply-tree friction after terminal-demand airflows are propagated, so each branch uses its solved airflow.
- Resolves reference-flow fan/duct friction at the declared section reference flow, then holds that factor constant while deriving the bounded fixed-ratio quadratic system curve.
- Leaves passive parallel-flow and fan-driven parallel-network solvers on explicit fixed resistance; v0.21 does not add nonlinear variable-friction network balancing.
- Added focused regression coverage, documentation, an automatic-friction HVAC example, and 0.21.0 metadata.


## v0.20 dossier-integrated fan-speed studies — 2026-09-23

- Integrated v0.19 fan-speed affinity-law studies into engineering dossier manifests as an optional analysis list.
- Added SHA-256 source fingerprinting for every referenced fan-speed study input.
- Aggregated individual speed-case statuses so any bounded no-intersection case becomes a dossier attention item.
- Added fan-speed study/case counts to the executive summary and detailed speed-ratio, rpm, airflow, and pressure evidence to Markdown dossiers.
- Added a solved dossier fan-speed fixture plus end-to-end and adverse-state regression coverage.
- Moved the dossier non-empty-source validation after all optional fan-study lists so fan-only dossiers remain valid.
- Kept existing manifests backward compatible because the new fan-speed list is optional.
- Bumped package/runtime metadata to v0.20.0.

## v0.19 bounded fan-speed affinity-law study — 2026-09-23

- Added explicit user-supplied fan speed-ratio sweeps from a supplied reference fan curve.
- Applied classical fan affinity-law scaling to supplied points: airflow proportional to speed, pressure proportional to speed squared, and theoretical power scaling proportional to speed cubed.
- Reused the existing bounded fan/system operating-point solver for every transformed speed case, preserving no-extrapolation and no-intersection behavior.
- Added optional reference-rpm reporting while keeping allowed fan/VFD speed ranges external to CleanroomX.
- Kept fluid air power (Q×pressure) separate from the cubic affinity-law power-scaling indicator; no motor/VFD efficiency or electrical-input model is inferred.
- Added JSON loading, Markdown/JSON reporting, the `cleanroomx-fan-speed` CLI, example data, documentation, and regression coverage.
- Bumped package/runtime metadata to v0.19.0.

## v0.18 complete engineering dossier — 2026-09-23

- Integrated the v0.17 verification/HVAC duplicated-airflow consistency checker into engineering dossier manifests.
- Reuses the standalone checker's exact-name matching, absolute airflow tolerance, identical-room-set option, statuses, and scope boundary.
- Propagates consistency failures into dossier attention tracking and preserves `not_comparable` as an unresolved state.
- Adds consistency evidence to Markdown dossiers plus an end-to-end example and regression tests.
- Requires both verification and HVAC project inputs when a dossier consistency check is configured.
- Added reference-flow fan/duct-network studies to dossier manifests, executive summaries, Markdown reports, SHA-256 source traceability, and end-to-end regression coverage.
- Added fan-driven passive parallel-network studies to the same dossier workflow while preserving bounded no-extrapolation/no-intersection states.
- Promotes unresolved integrated fan-network intersections to dossier attention items rather than collapsing them into a generic success state.
- Bumped package/runtime metadata to v0.18.0 while keeping all new dossier fields optional for backward-compatible manifests.

## v0.17 cross-module input consistency — 2026-09-23

- Added a standalone verification/HVAC consistency checker for duplicated room-airflow inputs.
- Matched rooms by exact room name and compared verification supply airflow against HVAC cleanroom airflow.
- Added an explicit user-supplied absolute consistency tolerance with exact agreement as the default; no engineering tolerance is invented.
- Added optional identical-room-set enforcement while preserving unmatched-room evidence when different module scopes are intentional.
- Added pass, pass-with-scope-difference, fail, and not-comparable states plus Markdown/JSON reporting, CLI, example data, documentation, and regression coverage.
- Kept the workflow explicitly bounded as input consistency rather than airflow adequacy, cleanroom acceptance, certification, or standards conformity.

## v0.16 fan-driven passive parallel-network integration — 2026-09-23

- Coupled the bounded fan/system operating-point solver to the passive common-pressure-node parallel-path model.
- Added analytical equivalent network resistance for pressure-balanced paths following fixed R·Q² behavior.
- Added fan/system operating-point solving followed by redistribution of the solved total airflow across the original branches.
- Added fixed-pressure plus network-pressure decomposition, fan/system residual, mass-balance residual, equal-pressure residual, and per-section flow/loss reporting.
- Preserved no-extrapolation behavior when the operating point lies outside supplied fan data.
- Added JSON loading, Markdown/JSON reporting, the `cleanroomx-fan-network` CLI, example data, tests, and engineering-scope documentation.
- Kept this distinct from v0.14 reference-flow fan/duct integration: v0.16 solves the passive branch split from common pressure instead of holding reference flow fractions fixed.
- Kept the workflow explicitly bounded: no arbitrary looped-network solution, variable friction-factor iteration, dampers/controls, leakage, system effect, acoustics, fan-law scaling, stall/surge acceptance, or manufacturer selection.


## v0.15 psychrometric state uncertainty — 2026-09-23

- Added uncertain dry-bulb temperature, relative humidity, and total-pressure inputs with strict interval-domain validation.
- Added deterministic evaluation of every unique rectangular uncertainty-box corner using the existing CleanroomX psychrometric equations.
- Added bounded vapor-pressure, humidity-ratio, enthalpy, specific-volume, dew-point, and moist-air specific-heat results.
- Added provenance completeness reporting without inventing uncertainty magnitudes, probability distributions, covariance, or acceptance limits.
- Added JSON loading, Markdown/JSON reporting, the `cleanroomx-psychrometric-uncertainty` CLI, example data, documentation, and regression coverage.
- Kept the v0.10 thermal uncertainty workflow psychrometrically fixed; explicit cross-module coupling remains a later milestone.

## v0.14 fan/duct-network operating-point integration — 2026-09-23

- Added a reference-flow fan/duct-network study that derives path quadratic resistance from explicit duct geometry, Darcy friction factors, air density, local-loss coefficients, and section reference airflow fractions.
- Added critical-path selection from the derived path resistances and direct reuse of the bounded fan/system operating-point solver.
- Added per-path and per-section reference/operating airflow and pressure-drop reporting.
- Added validation that section reference airflow does not exceed the declared reference system airflow, plus rejection of zero-resistance paths.
- Added JSON loading, Markdown/JSON reporting, the cleanroomx-fan-duct CLI, example data, documentation, and regression tests.
- Kept the workflow explicitly bounded: section flow fractions, density, friction factor, geometry, and local-loss coefficients remain fixed while total airflow varies; no general network balancing, variable-friction iteration, leakage, system effect, stall/surge, or controls are inferred.

## v0.13 integrated engineering dossier — 2026-09-23

- Added a manifest-driven engineering dossier that aggregates room/cascade verification, HVAC/duct screening, v0.12 HVAC fan-curve design-duty verification, measured recovery, uncertainty/provenance, qualification uncertainty, thermal/HVAC uncertainty, and standalone fan/system operating-point studies.
- Added SHA-256 fingerprints for every referenced source file so dossier inputs are auditable and reproducible.
- Preserved component-specific fail, incomplete, indeterminate, not-checked, solved, outside-supplied-range, and no-intersection states instead of collapsing the package into a certification verdict.
- Added attention tracking for HVAC fan-duty failures/out-of-range cases, unresolved standalone fan/system intersections, and thermal uncertainty failures/indeterminate capacity checks.
- Added Markdown/JSON dossier output, the `cleanroomx-dossier` CLI, example manifest, documentation, and regression coverage.
- Kept older dossier manifests compatible by making thermal-uncertainty and standalone fan-study fields optional.
- Kept the dossier explicitly bounded as a traceability/reporting layer rather than cleanroom certification, regulatory approval, commissioning acceptance, or fan/equipment selection.

## v0.11 fan/system operating-point solver — 2026-09-23

- Added explicit fan performance curves from ordered airflow/pressure points with strict finite and monotonic validation.
- Added fixed-plus-quadratic system curves using project-supplied fixed pressure and resistance.
- Added bounded fan/system intersection solving with piecewise-linear fan interpolation and no fan-curve extrapolation.
- Added operating airflow, fan/system pressure, pressure residual, interpolation segment, and fluid air-power reporting.
- Added explicit no-intersection status when the operating point lies outside the supplied fan data.
- Added JSON loading, Markdown/JSON reporting, the `cleanroomx-fan-curve` CLI, example data, tests, and documentation.
- Kept the workflow explicitly bounded: no inferred fan laws, manufacturer acceptance, stall/surge limits, variable resistance, system effect, controls, or electrical-power inference.

## v0.10 thermal uncertainty screening — 2026-09-23

- Added deterministic interval propagation for internal sensible/latent loads, cleanroom airflow, makeup airflow, and optional supply-air temperature.
- Added conservative cooling/heating capacity requirement intervals with project-configured available-capacity pass/fail/indeterminate checks.
- Added governing supply-airflow intervals across cleanroom, makeup-air, and sensible-load airflow candidates.
- Added provenance completeness reporting for every uncertain thermal input.
- Added JSON loading, Markdown/JSON reporting, a dedicated `cleanroomx-thermal-uncertainty` CLI, example data, tests, and documentation.
- Kept room/outdoor psychrometric states fixed and explicitly bounded the workflow as screening rather than statistical uncertainty, hourly load simulation, or equipment selection.

## v0.9 passive parallel-path flow solver — 2026-09-23

- Added analytical airflow distribution across two or more passive duct paths sharing common pressure nodes.
- Added fixed-resistance R·Q² path modeling from explicit Darcy friction, geometry, air density, and local-loss coefficients.
- Added solved per-path airflow, common pressure drop, per-section losses, mass-balance residual, and equal-pressure residual reporting.
- Added circular/rectangular geometry support, finite-input validation, JSON loading, Markdown reporting, and the `cleanroomx-duct-flow` CLI.
- Added regression coverage for equal and unequal resistances, rectangular sections, zero-resistance rejection, non-finite inputs, mass continuity, and equal-pressure verification.
- Kept the solver standalone and explicitly bounded: it does not yet combine the v0.8 supply tree with arbitrary loops, fan curves, dampers, leakage, or variable-friction-factor iteration.

## v0.8 branch-flow supply-tree solver — 2026-09-23

- Added directed supply-tree topology with explicit source, branches, and fixed leaf-terminal airflow demands.
- Added automatic upstream branch-flow propagation by steady-state mass continuity.
- Reused the hardened v0.6.1 Darcy-Weisbach/local-K section model at each solved branch airflow.
- Added source-to-terminal accumulated pressure losses, critical-terminal selection, and node continuity residual reporting.
- Added topology validation for multiple feeds, unreachable nodes, missing leaf demands, and invalid terminal placement.
- Integrated branch-flow critical-path pressure loss into preliminary fan duty with an HVAC airflow-consistency guard.
- Kept the solver explicitly limited to fixed-demand trees rather than looped or pressure-balanced networks.
- Added JSON loading, Markdown reporting, tests, example data, and documentation.


## v0.7 qualification uncertainty — 2026-09-23

- Added uncertainty-aware minimum and maximum qualification checks for project-configured measured quantities.
- Added conservative room-to-room pressure-cascade interval propagation using uncertain pressure measurements.
- Added pass/fail/indeterminate overall qualification status with failure taking precedence over ambiguity.
- Preserved requirement references and input provenance while keeping traceability completeness separate from numerical acceptance.
- Added JSON loading, Markdown/JSON reports, a dedicated `cleanroomx-qualification` CLI, example data, tests, and documentation.
- Kept the workflow explicitly bounded as deterministic interval screening; no ISO class, pressure, particle, or conformity threshold is embedded.

## v0.6.1 duct-input hardening — 2026-09-23

- Rejected non-finite duct inputs (NaN and positive/negative infinity) before pressure-loss analysis.
- Added regression coverage for airflow, air density, friction factor, local-loss coefficient, length, and circular/rectangular geometry dimensions.
- Synchronized package runtime metadata with the v0.6 release line.
- Corrected duct-model documentation that still referred to v0.5.

## v0.6 duct critical-path pressure loss — 2026-09-23

- Added circular and rectangular duct-section models with strict input validation.
- Added velocity, velocity-pressure, hydraulic-diameter, Darcy-Weisbach friction-loss, and local-loss calculations.
- Added user-defined duct paths and critical-path pressure-loss selection.
- Added explicit air-density, Darcy friction-factor, and local loss-coefficient inputs; no hidden fitting or roughness assumptions.
- Integrated computed critical-path duct loss into preliminary supply-fan sizing while preserving legacy manual duct-loss input when no network is configured.
- Added duct-network JSON loading, Markdown reporting, example data, tests, and engineering-scope documentation.
- Documented ASHRAE duct-design references and kept the model explicitly preliminary rather than a branch-flow/network solver.

## v0.5 uncertainty/provenance foundation — 2026-09-23

- Added explicit provenance records for engineering inputs, including source type/name, reference, revision, date, uncertainty basis, and notes.
- Added absolute uncertainty bounds for room dimensions and supply airflow.
- Added deterministic conservative interval propagation for room volume and supply ACH.
- Added robust pass/fail/indeterminate/not-checked evaluation against a project-configured minimum ACH requirement.
- Added provenance-completeness reporting without conflating missing traceability with numerical acceptance.
- Added JSON loading, Markdown/JSON reporting, a dedicated CLI, example data, tests, and documentation.
- Kept the method explicitly bounded as interval screening rather than a statistical measurement-uncertainty budget.

## v0.4 recovery qualification — 2026-09-23

- Added measured particle-recovery test records with strict sample validation.
- Added explicit project target concentration and optional maximum recovery-time criteria.
- Added pass/fail/incomplete/not-checked qualification states.
- Added observed recovery windows based on discrete samples without inventing an exact crossing time.
- Added optional traceability metadata for instrument, sample location, occupancy state, and method/protocol reference.
- Added log-linear decay diagnostics, R², fitted target crossing, and estimated effective ACH as screening outputs only.
- Added JSON loading, Markdown/JSON reporting, a dedicated CLI, example data, tests, and documentation.
- Kept ISO/project acceptance thresholds external; no proprietary ISO limits are embedded.

## v0.3 airflow/fan extension — 2026-09-23

- Added per-room supply/return/exhaust/transfer airflow balance.
- Added explicit minimum airflow-surplus verification and margin reporting.
- Added optional filter/FFU pressure-drop input.
- Added preliminary central supply-fan static-pressure, air-power, shaft-power, and electrical-input calculations.
- Added airflow/fan report sections, example inputs, tests, and documentation.
- Kept all limits and pressure-drop values requirement-driven; no ISO class is mapped to airflow surplus or fan sizing.

## v0.2 HVAC extension — 2026-09-23

- Added psychrometric air-state calculations.
- Added explicit sensible and latent room loads.
- Added outdoor/makeup-air load calculations.
- Added preliminary cooling/heating capacity.
- Added cleanroom-vs-makeup-vs-thermal governing airflow selection.
- Added optional FFU/filter-unit sizing.
- Added a separate HVAC CLI, JSON project loader, Markdown reporting, tests, and documentation.
- Preserved the existing particle, room, and pressure-cascade verification architecture.
