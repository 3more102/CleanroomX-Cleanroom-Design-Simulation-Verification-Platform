# Changelog
## v0.45 correlated whole-fan-curve scenarios — 2026-09-23

- Added explicit whole-fan-curve scenario inputs for correlated alternatives that must move together rather than as independent point-wise uncertainty dimensions.
- Evaluates the nominal reference fan curve plus every supplied scenario and composes each curve case with fixed-pressure, fan-speed-ratio, and duct physical/geometry uncertainty dimensions.
- Reuses the complete nonlinear variable-friction fan/loop solver for every curve/scenario corner and preserves the no-extrapolation boundary.
- Keeps point-wise fan pressure/airflow uncertainty mutually exclusive with whole-curve scenarios to avoid inventing cross-scenario combinations the user did not supply.
- Includes the nominal reference curve in the scenario corner set so reported complete envelopes cannot omit the nominal operating state.
- Adds scenario provenance, per-corner scenario identity, Markdown evidence, a reproducible scenario+speed example, and regression coverage.
- Bumped package/runtime metadata to v0.45.0.

## v0.44 bounded fan-speed-ratio uncertainty — 2026-09-23

- Extended nonlinear fan/variable-friction corner analysis to an optional user-supplied absolute fan-speed-ratio bound.
- Reuses the existing affinity-law fan-curve transform at every speed corner: airflow scales with speed ratio and pressure with speed ratio squared.
- Composes bounded speed ratio with fixed pressure, fan-point coordinate uncertainty, and duct physical/geometry uncertainty before each complete nonlinear Darcy-friction solve.
- Rejects nonpositive speed-ratio intervals and preserves transformed supplied-curve boundaries without extrapolation.
- Added speed-ratio interval/provenance evidence, Markdown reporting, a reproducible example, and corner-limit accounting.

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
