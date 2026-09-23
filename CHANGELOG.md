# Changelog

## v0.20 fan-speed dossier integration — 2026-09-23

- Integrated v0.19 fan-speed affinity-law studies into engineering dossier manifests.
- Added SHA-256 source traceability and Markdown/JSON dossier reporting for every referenced fan-speed study.
- Aggregated speed-case statuses across studies and promoted any bounded no-intersection case to dossier attention tracking.
- Added a solved fan-speed dossier demo while preserving separate regression coverage for unresolved speed cases.
- Moved the empty-dossier source validation after all integrated fan-study loaders so fan-only dossiers are handled consistently.
- Bumped package/runtime metadata to v0.20.0 while keeping `fan_speed_studies` optional for backward-compatible manifests.

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
