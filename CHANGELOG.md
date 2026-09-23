# Changelog

## Unreleased — engineering dossier

- Added a manifest-driven combined engineering dossier for room/cascade verification, HVAC/duct screening, recovery qualification, uncertainty-aware qualification, and uncertainty/provenance analyses.
- Added component-aware executive states that preserve fail, incomplete, indeterminate, and not-checked conditions rather than collapsing them into a certification verdict.
- Added SHA-256 fingerprints for every referenced input file to improve report traceability.
- Added Markdown/JSON dossier output, a dedicated CLI, example manifest, tests, and documentation.
- Kept the dossier explicitly scoped as a reporting/traceability layer; it does not create acceptance limits or claim cleanroom certification.

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
